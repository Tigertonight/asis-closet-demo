#!/usr/bin/env python3
"""Use each batch09 outer in its fourth, previously unused supported persona."""
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];AUDIT=ROOT/"docs/audits/20260904-aw-supply"
SETS={"pants_clean":["g0114","g0172","g0258","g0289"],"pants_soft":["g0084","g0164","g0253","g0276"],"pants_dark":["g0002","g0003","g0004","g0005"],"skirt_dark":["g0337","g0190","g0069","g0070"],"skirt_soft":["g0086","g0198","g0246","g0278"],"dress_dark":["g0222","g0265","g0513"],"dress_soft":["g0230","g0245","g0276"],"dress_classic":["g0217","g0004","g0270"]}
TARGETS=[("n0048","ocean","BOLT","pants_dark","skirt_dark"),("n0049","ocean","WABI","pants_soft","dress_soft"),("n0050","earth","HEIR","pants_clean","dress_classic"),("n0051","earth","EASE","skirt_soft","dress_soft"),("n0052","bright","NEON","pants_dark","dress_classic"),("n0053","bright","LOOP","skirt_soft","dress_soft"),("n0054","jewel","HEIR","skirt_dark","pants_dark"),("n0055","jewel","WABI","skirt_soft","dress_soft")]
def structure(k):return "dress" if k.startswith("dress") else "skirt" if k.startswith("skirt") else "pants"
def main():
 visual=json.loads((ROOT/"app/data/recommendation-visual.v1.json").read_text());manifest=json.loads((AUDIT/"generated-garments/batch09/manifest.json").read_text());recipes=[]
 for hero,palette,persona,*keys in TARGETS:
  for key in keys:recipes.append({"persona":persona,"palette":palette,"season":"winter","structure":structure(key),"hero":hero,"items":[hero,*SETS[key]],"expression":"entry","intent":f"盘活 {hero} 已有视觉亲和中的 {persona}×{palette}，补 {structure(key)} 结构。"})
 result={"schema_version":1,"batch_id":"aw-targeted-08","source_visual_version":visual["version"],"status":"designer_targets_pending_whole_image_review","new_garments":[],"new_garment_manifest":"generated-garments/batch09/manifest.json","new_garment_version":manifest["version"],"recipes":recipes}
 target=AUDIT/"targeted-recipes.batch08.json"
 if target.exists() and json.loads(target.read_text())!=result:raise SystemExit("Targeted batch08 changed; refusing overwrite")
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n");print(json.dumps({"recipes":len(recipes),"new_garments":0},ensure_ascii=False))
if __name__=="__main__":main()
