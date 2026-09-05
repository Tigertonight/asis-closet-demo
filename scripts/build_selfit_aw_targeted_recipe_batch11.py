#!/usr/bin/env python3
"""Build 48 AW recipes for second-family gap assets."""
from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));AUDIT=ROOT/"docs/audits/20260904-aw-supply"
from scripts.build_selfit_aw_targeted_recipe_batch09 import SETS,structure
TARGETS=[("n0072","earth","FLOU"),("n0073","bright","MUTE"),("n0074","earth","NOIR"),("n0075","pastel","VOID"),("n0076","earth","NEON"),("n0077","bright","WABI"),("n0078","earth","OOPS"),("n0079","pastel","EDGE")]
def main():
 visual=json.loads((ROOT/"app/data/recommendation-visual.v1.json").read_text());manifest=json.loads((AUDIT/"generated-garments/batch12/manifest.json").read_text());recipes=[]
 for hero,palette,persona in TARGETS:
  for season in ("autumn","winter"):
   for key in ("pants_clean","skirt_dark","dress_classic"):
    recipes.append({"persona":persona,"palette":palette,"season":season,"structure":structure(key),"hero":hero,"items":[hero,*SETS[key]],"expression":"entry","intent":f"{persona}×{palette}×{season} 的第二非近似家族 {structure(key)} 配方；不得与第一家族合并计数。"})
 result={"schema_version":1,"batch_id":"aw-targeted-11","source_visual_version":visual["version"],"status":"designer_targets_pending_whole_image_review","new_garments":manifest["garments"],"new_garment_manifest":"generated-garments/batch12/manifest.json","new_garment_version":manifest["version"],"recipes":recipes};assert len(recipes)==48;target=AUDIT/"targeted-recipes.batch11.json"
 if target.exists() and json.loads(target.read_text())!=result:raise SystemExit("Targeted batch11 changed; refusing overwrite")
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n");print(json.dumps({"recipes":48,"new_garments":8},ensure_ascii=False))
if __name__=="__main__":main()
