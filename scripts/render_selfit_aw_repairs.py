"""Render explicit designer edits as new draft records. Never inherit approvals."""
import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.closet import selfit_content_pool
from app.outfit_layout import render_outfit_preview,outfit_preview_url
from app.recommendation_visual import load_visual,valid_observation
from app.selfit_content_quality import record_fingerprint


def replace_ids(value,mapping):
    if isinstance(value,str):return mapping.get(value,value)
    if isinstance(value,list):return [replace_ids(v,mapping) for v in value]
    if isinstance(value,dict):return {mapping.get(k,k):replace_ids(v,mapping) for k,v in value.items()}
    return value


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("edits",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise SystemExit("Rendered revision exists; do not overwrite")
    edit=json.loads(args.edits.read_text());v=load_visual();pool=selfit_content_pool()
    assert edit["source_visual_version"]==v["version"]
    assert len(edit["edits"])<=48 and len(edit["new_garments"])<=24
    gs={g["id"]:g for g in pool.garments};os={o["id"]:o for o in pool.outfits}
    gt={r["token"]:gid for gid,r in v["garments"].items()};ot={r["token"]:oid for oid,r in v["outfits"].items()}
    result=[]
    for e in edit["edits"]:
        oid=ot[e["token"]];old=os[oid]
        assert v["outfits"][oid]["record_fingerprint"]==record_fingerprint(old)
        mapping={gt[a]:gt[b] for a,b in e["replace"].items()}
        assert set(mapping)<=set(old["garment_ids"])
        assert all(gs[a]["category"]==gs[b]["category"] for a,b in mapping.items())
        new=replace_ids(copy.deepcopy(old),mapping)
        new["id"]=oid+"__"+edit["batch_id"]
        new["parent_outfit_id"]=old.get("parent_outfit_id") or oid
        new["recipe_version"]=edit["batch_id"]
        new["annotation"]={"status":"draft","source_outfit_id":oid}
        for key in ("curation","quality_review","color_evidence","recommendation_reasons"):
            new.pop(key,None)
        new["design_intent"]=e["intent"]
        items=[gs[gid] for gid in new["garment_ids"]]
        assert all(valid_observation(g,v["garments"][g["id"]],g["assets"]["image_url"],"garments") for g in items)
        url=outfit_preview_url(items)
        target=ROOT/"app"/url.lstrip("/")
        if target.exists():
            qa=json.loads(target.with_suffix(".qa.json").read_text())
            assert {p["garment_id"] for p in qa["placements"]}==set(new["garment_ids"])
        else:
            qa=render_outfit_preview(items,ROOT)
        new["assets"]={"image_url":qa["image_url"],"width":1200,"height":1500,"rights_status":"owned",
                       "layout_version":qa["layout_version"]}
        result.append({"source_outfit_id":oid,"source_token":e["token"],"source_record_fingerprint":record_fingerprint(old),
            "new_record":new,"record_fingerprint":record_fingerprint(new),
            "asset_sha256":hashlib.sha256(target.read_bytes()).hexdigest(),"layout_qa":qa,
            "replacements":mapping,"status":"pending_native_review","review":None})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({"schema_version":1,"batch_id":edit["batch_id"],"source_visual_version":v["version"],
        "entries":result,"production_approved":False},ensure_ascii=False,indent=2)+"\n")
    print(json.dumps([{ "token":r["source_token"],"image_url":r["new_record"]["assets"]["image_url"]} for r in result]))


if __name__=="__main__":main()
