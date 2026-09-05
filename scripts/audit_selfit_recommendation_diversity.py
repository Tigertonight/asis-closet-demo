"""Read-only catalog/ranking audit. Never consumes or persists user feedback."""
from __future__ import annotations
import collections
import argparse
import hashlib
import itertools
import json
import sys
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import closet

OUT = ROOT / "docs/audits/20260903-recommendation-similarity"
MAIN = {"top", "outer", "bottom", "skirt", "dress"}


def features(garment):
    path = ROOT / "app" / garment["assets"]["image_url"].lstrip("/")
    with Image.open(path) as source:
        rgba = source.convert("RGBA")
        alpha = rgba.getchannel("A")
        bbox = alpha.getbbox()
        cropped = alpha.crop(bbox)
        aspect = cropped.width / cropped.height
        cropped.thumbnail((64, 64))
        square = Image.new("L", (64, 64))
        square.paste(cropped, ((64-cropped.width)//2, (64-cropped.height)//2))
        mask = np.array(square) >= 192
    swatches = garment.get("color_evidence", {}).get("swatches", [])
    weights = np.array([s["weight"] for s in swatches], dtype=float)
    rgbs = np.array([[int(s["hex"][i:i+2], 16) for i in (1,3,5)] for s in swatches])
    mean = np.average(rgbs, axis=0, weights=weights).astype(np.float32) / 255
    lab = cv2.cvtColor(mean.reshape(1,1,3), cv2.COLOR_RGB2LAB)[0,0]
    return mask, aspect, lab


def hero(outfit):
    return next((gid for gid, role in outfit["slot_roles"].items() if role == "hero"), outfit["garment_ids"][0])


def main_signature(outfit, garments):
    return tuple(sorted(g for g in outfit["garment_ids"] if garments[g]["category"] in MAIN))


def metrics(rows, garments, near):
    heroes = [hero(o) for o in rows]
    main_counts = collections.Counter(g for o in rows for g in o["garment_ids"] if garments[g]["category"] in MAIN)
    color_counts = collections.Counter((garments[g].get("color_evidence", {}).get("palette_names") or ["unknown"])[0] for g in heroes)
    structures = collections.Counter("+".join(sorted(garments[g]["category"] for g in o["garment_ids"] if garments[g]["category"] in MAIN)) for o in rows)
    pairs = []
    for i, j in itertools.combinations(range(len(rows)), 2):
        a,b = set(rows[i]["garment_ids"]),set(rows[j]["garment_ids"])
        jac = len(a & b)/len(a | b)
        if jac >= .6:
            pairs.append({"left":rows[i]["id"],"right":rows[j]["id"],"jaccard":round(jac,3)})
    return {
        "count":len(rows), "unique_heroes":len(set(heroes)),
        "unique_main_combinations":len({main_signature(o,garments) for o in rows}),
        "max_same_main_garment":max(main_counts.values(),default=0),
        "dominant_hero_color":color_counts.most_common(1),
        "structures":dict(structures), "shared_60pct_pairs":pairs,
        "same_hero_pairs":sum(a==b for a,b in itertools.combinations(heroes,2)),
        "different_id_similar_hero_pairs":sum(a!=b and frozenset((a,b)) in near for a,b in itertools.combinations(heroes,2)),
        "most_repeated_main":main_counts.most_common(3),
    }


def main():
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=OUT)
    args = parser.parse_args()
    OUT = args.output_dir
    if (OUT / "audit-data.json").exists():
        raise SystemExit("Audit evidence exists; choose a new --output-dir")
    OUT.mkdir(parents=True,exist_ok=True)
    paths = [ROOT/p for p in ["app/static/selfit/data/content-pool.v2.published.json", "app/static/selfit/data/content-curation.v1.json", "app/static/selfit/data/personality-report-templates.v1.json", "app/closet.py", "app/selfit_recommend.py"]]
    hashes = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    pool = closet.selfit_content_pool()
    garments = {g["id"]:g for g in pool.garments}
    outfits = {o["id"]:o for o in pool.outfits}
    catalog = closet._published_catalog_outfits()
    templates = json.loads(paths[2].read_text())["types"]
    visual = {gid:features(g) for gid,g in garments.items()}
    near = {}
    shape_count = color_count = 0
    for a,b in itertools.combinations(garments,2):
        if garments[a]["category"] != garments[b]["category"]:
            continue
        ma,ra,la=visual[a]; mb,rb,lb=visual[b]
        iou=float(np.logical_and(ma,mb).sum()/max(1,np.logical_or(ma,mb).sum()))
        de=float(np.linalg.norm(la-lb))
        shape=iou>=.85 and .8<=ra/rb<=1.25
        shape_count+=shape; color_count+=de<=12
        if shape and de<=12:
            near[frozenset((a,b))]={"left":a,"right":b,"mask_iou":round(iou,3),"color_delta_e76":round(de,2)}
    scenarios={}
    def forbidden(*args,**kwargs):
        raise AssertionError("Audit must not read private wardrobes or feedback")
    # Formal mode is a controlled cold start: no personal wardrobe or history.
    with patch.object(closet,"_published_catalog_outfits",return_value=catalog), patch.object(closet,"list_outfits",return_value={"outfits":[]}), patch.object(closet,"_ensure_recommendation_feedback",return_value={"events":[]}), patch.object(closet,"_feedback_profile",return_value={"counts":{},"reasons":{}}):
        for mode in ("preview","formal_cold"):
            for code,template in templates.items():
                for season in ("spring","summer","autumn","winter"):
                    seen=[]
                    for _ in range(5):
                        page=closet.recommend_outfits({"persona":template,"context":{"persona_preview":mode=="preview","season_tags":[season]},"limit":6,"exclude_outfit_ids":seen})
                        seen.extend(o["outfit_id"] for o in page["outfits"])
                        if not page["has_more"]: break
                    rows=[outfits[i] for i in seen]
                    windows=[metrics(rows[i:i+10],garments,near) for i in range(max(0,len(rows)-9))]
                    scenarios[f"{mode}:{code}:{season}"]={
                        "ids":seen, "first6":metrics(rows[:6],garments,near),"first10":metrics(rows[:10],garments,near),
                        "window_count":len(windows),"repeat_limit_violations":sum(w["max_same_main_garment"]>2 for w in windows),
                        "worst_window_repeat":max((w["max_same_main_garment"] for w in windows),default=0),
                        "primary_label_matches_first10":sum(o["primary_persona"].lower()==code for o in rows[:10]),
                        "top10_review_pending":sum(o.get("curation",{}).get("gates",{}).get("persona")!="passed" for o in rows[:10]),
                    }
    by_persona={}
    for code in templates:
        rows=[o for o in outfits.values() if o["primary_persona"].lower()==code]
        used={g for o in rows for g in o["garment_ids"]}
        by_persona[code]={"active":len(rows),"used_garments":len(used),"unique_heroes":len({hero(o) for o in rows}),"metrics":metrics(rows,garments,near)}
    used={g for o in outfits.values() for g in o["garment_ids"]}
    report={"source_sha256":hashes,"conditions":{"scenarios":128,"modes":["preview","formal_cold"],"seasons":"English enum sent by current app", "pages":5,"page_size":6,"private_data_used":False,"feedback_persisted":False,"visual_review":"separate manual notes; not blind"},
        "catalog":{"garments":len(garments),"active_outfits":len(outfits),"unused_garments":sorted(set(garments)-used),"persona_review_states":dict(collections.Counter(o.get("curation",{}).get("gates",{}).get("persona") for o in outfits.values())),"semantic_review_states":dict(collections.Counter(g.get("semantic_review",{}).get("status") for g in garments.values()))},
        "garment_similarity":{"method":"same category; alpha-mask IoU >= .85, aspect ratio within .8–1.25, weighted opaque-pixel mean CIELAB deltaE76 <=12; candidates only", "shape_similar_pairs":int(shape_count),"color_similar_pairs":int(color_count),"joint_pairs":sorted(near.values(),key=lambda p:(p["color_delta_e76"],-p["mask_iou"]))},
        "personas":by_persona,"scenarios":scenarios}
    (OUT/"audit-data.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
    # First six currently returned covers, not a manually chosen best-of sample.
    font=ImageFont.load_default()
    codes=list(templates)
    cover_by_id={o["outfit_id"]:o["cover_path"] for o in catalog}
    for group in range(4):
        sheet=Image.new("RGB",(1080,1080),"#ffffff"); draw=ImageDraw.Draw(sheet)
        for row,code in enumerate(codes[group*4:group*4+4]):
            for col,oid in enumerate(scenarios[f"preview:{code}:autumn"]["ids"][:6]):
                path=ROOT/"app"/cover_by_id[oid].lstrip("/")
                with Image.open(path) as im:
                    im.thumbnail((174,218)); sheet.paste(im,(col*180+(180-im.width)//2,row*270+24))
                draw.text((col*180+4,row*270+5),f"{code.upper()} #{col+1}",fill="black",font=font)
                draw.text((col*180+4,row*270+244),oid.replace(f"outfit_{code}_",""),fill="black",font=font)
        sheet.save(OUT/f"first-six-{group+1}.jpg",quality=92)
    pairs=[p for p in report["garment_similarity"]["joint_pairs"] if garments[p["left"]]["category"] in MAIN][:8]
    sheet=Image.new("RGB",(960,960),"white");draw=ImageDraw.Draw(sheet)
    for n,pair in enumerate(pairs):
        x=(n%2)*480;y=(n//2)*240
        for col,key in enumerate(("left","right")):
            gid=pair[key]
            with Image.open(ROOT/"app"/garments[gid]["assets"]["image_url"].lstrip("/")) as im:
                im=im.convert("RGBA");im=im.crop(im.getchannel("A").getbbox()); im.thumbnail((210,190));sheet.paste(im,(x+col*240+(240-im.width)//2,y+8),im)
            draw.text((x+col*240+4,y+202),gid.replace("garment_",""),fill="black",font=font)
        draw.text((x+4,y+220),f"IoU {pair['mask_iou']} / dE {pair['color_delta_e76']}",fill="black",font=font)
    sheet.save(OUT/"similar-garment-candidates.jpg",quality=93)
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==hashes[str(p.relative_to(ROOT))] for p in paths)
    print(json.dumps({"active":len(outfits),"similar_pairs":len(near),"scenarios":len(scenarios),"output":str(OUT)},ensure_ascii=False))


if __name__=="__main__": main()
