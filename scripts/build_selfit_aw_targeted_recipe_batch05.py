#!/usr/bin/env python3
"""Design three main structures for eight winter threshold garments."""
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; AUDIT=ROOT/"docs/audits/20260904-aw-supply"

TARGETS=[
 ("ICED","pastel","n0034"),("WABI","jewel","n0035"),("ICED","mono","n0036"),("EASE","mono","n0037"),
 ("HEIR","pastel","n0038"),("HEIR","ocean","n0039"),("HEIR","jewel","n0040"),("EASE","earth","n0041"),
]
SETS={
 "pants":["g0114","g0172","g0258","g0289"],
 "skirt":["g0337","g0429","g0069","g0070"],
 "dress":["g0222","g0265","g0513"],
}

def main():
 visual=json.loads((ROOT/"app/data/recommendation-visual.v1.json").read_text()); manifest=json.loads((AUDIT/"generated-garments/batch07/manifest.json").read_text())
 recipes=[]
 for persona,palette,hero in TARGETS:
  for structure,items in SETS.items():
   recipes.append({"persona":persona,"palette":palette,"season":"winter","structure":structure,"hero":hero,"items":[hero,*items],"expression":"entry","intent":f"{persona}×{palette} 冬季临界缺口的 {structure} 主结构；主色由外层承担。"})
 result={"schema_version":1,"batch_id":"aw-targeted-05","source_visual_version":visual["version"],"status":"designer_targets_pending_whole_image_review","new_garments":manifest["garments"],"new_garment_manifest":"generated-garments/batch07/manifest.json","new_garment_version":manifest["version"],"recipes":recipes}
 target=AUDIT/"targeted-recipes.batch05.json"
 if target.exists() and json.loads(target.read_text())!=result: raise SystemExit("Targeted batch05 changed; refusing overwrite")
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n"); print(json.dumps({"recipes":len(recipes),"new_garments":len(manifest["garments"])},ensure_ascii=False))
if __name__=="__main__":main()
