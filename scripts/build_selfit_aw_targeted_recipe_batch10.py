#!/usr/bin/env python3
"""Build 48 AW recipes for the eight lowest cross-season conditions."""
from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];AUDIT=ROOT/"docs/audits/20260904-aw-supply"
sys.path.insert(0,str(ROOT))
from scripts.build_selfit_aw_targeted_recipe_batch09 import SETS,structure
TARGETS=[("n0064","earth","FLOU"),("n0065","bright","MUTE"),("n0066","earth","NOIR"),("n0067","pastel","VOID"),("n0068","earth","NEON"),("n0069","bright","WABI"),("n0070","earth","OOPS"),("n0071","pastel","EDGE")]
def main():
 visual=json.loads((ROOT/"app/data/recommendation-visual.v1.json").read_text());manifest=json.loads((AUDIT/"generated-garments/batch11/manifest.json").read_text());recipes=[]
 for hero,palette,persona in TARGETS:
  for season in ("autumn","winter"):
   for key in ("pants_clean","skirt_dark","dress_classic"):
    recipes.append({"persona":persona,"palette":palette,"season":season,"structure":structure(key),"hero":hero,"items":[hero,*SETS[key]],"expression":"entry","intent":f"{persona}×{palette}×{season} 的低供给 {structure(key)} 结构；新长外层承担偏好色与人格证据。"})
 assert len(recipes)==48
 result={"schema_version":1,"batch_id":"aw-targeted-10","source_visual_version":visual["version"],"status":"designer_targets_pending_whole_image_review","new_garments":manifest["garments"],"new_garment_manifest":"generated-garments/batch11/manifest.json","new_garment_version":manifest["version"],"recipes":recipes};target=AUDIT/"targeted-recipes.batch10.json"
 if target.exists() and json.loads(target.read_text())!=result:raise SystemExit("Targeted batch10 changed; refusing overwrite")
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n");print(json.dumps({"recipes":48,"new_garments":8},ensure_ascii=False))
if __name__=="__main__":main()
