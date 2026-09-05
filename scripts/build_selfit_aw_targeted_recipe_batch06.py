#!/usr/bin/env python3
"""Pair six new winter dress families with distinct existing outer/support families."""
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; AUDIT=ROOT/"docs/audits/20260904-aw-supply"
ROWS=[
 ("ICED","pastel","n0042",["n0042","g0143","g0069","g0010"]),("ICED","pastel","n0042",["n0042","g0131","g0247","g0274"]),
 ("WABI","jewel","n0043",["n0043","g0137","g0030","g0029"]),("WABI","jewel","n0043",["n0043","g0155","g0245","g0278"]),
 ("HEIR","jewel","n0044",["n0044","g0131","g0004","g0270"]),("HEIR","jewel","n0044",["n0044","g0143","g0247","g0275"]),
 ("HEIR","pastel","n0045",["n0045","g0131","g0244","g0275"]),("HEIR","pastel","n0045",["n0045","g0143","g0253","g0270"]),
 ("HEIR","ocean","n0046",["n0046","g0143","g0004","g0275"]),("HEIR","ocean","n0046",["n0046","g0131","g0247","g0270"]),
 ("EASE","earth","n0047",["n0047","g0155","g0245","g0276"]),("EASE","earth","n0047",["n0047","g0137","g0253","g0271"]),
]
def main():
 visual=json.loads((ROOT/"app/data/recommendation-visual.v1.json").read_text()); manifest=json.loads((AUDIT/"generated-garments/batch08/manifest.json").read_text()); recipes=[]
 for persona,palette,hero,items in ROWS: recipes.append({"persona":persona,"palette":palette,"season":"winter","structure":"dress","hero":hero,"items":items,"expression":"entry","intent":f"{persona}×{palette} 新连衣装家族，与不同现有外层建立可出门冬季关系。"})
 result={"schema_version":1,"batch_id":"aw-targeted-06","source_visual_version":visual["version"],"status":"designer_targets_pending_whole_image_review","new_garments":manifest["garments"],"new_garment_manifest":"generated-garments/batch08/manifest.json","new_garment_version":manifest["version"],"recipes":recipes}
 target=AUDIT/"targeted-recipes.batch06.json"
 if target.exists() and json.loads(target.read_text())!=result: raise SystemExit("Targeted batch06 changed; refusing overwrite")
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n");print(json.dumps({"recipes":len(recipes),"new_garments":len(manifest["garments"])},ensure_ascii=False))
if __name__=="__main__":main()
