"""Prepare current images for Codex visual review. Preparation is NOT review."""
import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.closet import selfit_content_pool, _published_catalog_outfits
from app.recommendation_visual import asset_sha
from app.selfit_content_quality import record_fingerprint


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("output",type=Path)
    parser.add_argument("--per-sheet",type=int,default=24,choices=(12,24))
    args=parser.parse_args()
    if args.output.exists(): raise SystemExit("Use a new audit directory")
    args.output.mkdir(parents=True)
    pool=selfit_content_pool()
    covers={o["outfit_id"]:o["cover_path"] for o in _published_catalog_outfits()}
    manifest={"schema_version":1,"status":"pending_visual_review","human_reviewed":False,"garments":{},"outfits":{}}
    for section,rows in (("garments",pool.garments),("outfits",pool.outfits)):
        for start in range(0,len(rows),args.per_sheet):
            batch=rows[start:start+args.per_sheet]
            columns=6 if args.per_sheet==24 else 4
            sheet=Image.new("RGB",(columns*240,((len(batch)+columns-1)//columns)*320),"#ffffff")
            draw=ImageDraw.Draw(sheet)
            sheet_name=f"{section}-{start//args.per_sheet+1:03d}.jpg"
            for n,row in enumerate(batch):
                url=covers[row["id"]] if section=="outfits" else row["assets"]["image_url"]
                x,y=(n%columns)*240,(n//columns)*320
                with Image.open(ROOT/"app"/url.lstrip("/")) as source:
                    rgba=source.convert("RGBA")
                    if section=="garments": rgba=rgba.crop(rgba.getchannel("A").getbbox())
                    rgba=ImageOps.contain(rgba,(226,286))
                    sheet.paste(rgba,(x+(240-rgba.width)//2,y+24),rgba)
                token=f"{section[0]}{start+n+1:04d}"
                draw.text((x+6,y+6),token,fill="black")
                manifest[section][row["id"]]={"token":token,"status":"needs_review","record_fingerprint":record_fingerprint(row),"asset_sha256":asset_sha(url),"image_url":url,"sheet":sheet_name,"position":n+1,"source_kind":None,"evidence":None,"observations":{},"confidence":0}
            sheet.save(args.output/sheet_name,quality=94)
    (args.output/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print(json.dumps({"garments":len(manifest['garments']),"outfits":len(manifest['outfits']),"reviewed":0,"output":str(args.output)}))


if __name__=="__main__":main()
