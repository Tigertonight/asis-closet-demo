#!/usr/bin/env python3
"""Build 48 colour-axis winter recipes against exact structural gaps."""
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];AUDIT=ROOT/"docs/audits/20260904-aw-supply"
SETS={
 "pants_clean":["g0114","g0172","g0258","g0289"],"pants_soft":["g0084","g0164","g0253","g0276"],"pants_dark":["g0002","g0003","g0004","g0005"],
 "skirt_dark":["g0337","g0190","g0069","g0070"],"skirt_soft":["g0086","g0198","g0246","g0278"],"skirt_iced":["g0006","g0194","g0248","g0010"],
 "dress_dark":["g0222","g0265","g0513"],"dress_soft":["g0230","g0245","g0276"],"dress_classic":["g0217","g0004","g0270"],
}
TARGETS=[
 ("n0048","ocean",[("MUTE","skirt_dark","dress_dark"),("ICED","pants_clean","dress_classic"),("JADE","pants_clean","dress_classic")]),
 ("n0049","ocean",[("FLOU","pants_soft","dress_soft"),("MELT","pants_soft","dress_soft"),("EASE","dress_soft","skirt_soft")]),
 ("n0050","earth",[("ICED","pants_clean","skirt_iced"),("MUTE","skirt_dark","dress_dark"),("JADE","pants_soft","dress_classic")]),
 ("n0051","earth",[("WABI","pants_soft","skirt_soft"),("VOID","pants_dark","dress_dark"),("MELT","dress_soft","skirt_soft")]),
 ("n0052","bright",[("EDGE","skirt_dark","dress_classic"),("JADE","pants_clean","dress_classic"),("NOIR","skirt_dark","pants_dark")]),
 ("n0053","bright",[("WABI","pants_soft","skirt_soft"),("MELT","pants_soft","dress_soft"),("EASE","skirt_soft","dress_soft")]),
 ("n0054","jewel",[("BOLT","skirt_dark","dress_classic"),("EDGE","dress_classic","pants_dark"),("NOIR","skirt_dark","pants_dark")]),
 ("n0055","jewel",[("FLOU","pants_soft","dress_soft"),("MELT","pants_soft","dress_soft"),("VOID","skirt_soft","dress_dark")]),
]
def structure(key):return "dress" if key.startswith("dress") else "skirt" if key.startswith("skirt") else "pants"
def main():
 visual=json.loads((ROOT/"app/data/recommendation-visual.v1.json").read_text());manifest=json.loads((AUDIT/"generated-garments/batch09/manifest.json").read_text());recipes=[]
 for hero,palette,groups in TARGETS:
  for persona,*keys in groups:
   for key in keys:recipes.append({"persona":persona,"palette":palette,"season":"winter","structure":structure(key),"hero":hero,"items":[hero,*SETS[key]],"expression":"entry","intent":f"{persona}×{palette} 冬季真实缺口的 {structure(key)} 结构；新主外层家族承担偏好色。"})
 assert len(recipes)==48
 result={"schema_version":1,"batch_id":"aw-targeted-07","source_visual_version":visual["version"],"status":"designer_targets_pending_whole_image_review","new_garments":manifest["garments"],"new_garment_manifest":"generated-garments/batch09/manifest.json","new_garment_version":manifest["version"],"recipes":recipes}
 target=AUDIT/"targeted-recipes.batch07.json"
 if target.exists() and json.loads(target.read_text())!=result:raise SystemExit("Targeted batch07 changed; refusing overwrite")
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n");print(json.dumps({"recipes":48,"new_garments":8},ensure_ascii=False))
if __name__=="__main__":main()
