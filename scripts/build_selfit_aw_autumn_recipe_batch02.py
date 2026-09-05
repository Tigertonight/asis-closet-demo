#!/usr/bin/env python3
"""Design 27 autumn recipes for the nine remaining zero-supply conditions."""
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; AUDIT=ROOT/"docs/audits/20260904-aw-supply"
TARGETS=[("FILM","bright","n0017"),("NEON","earth","n0012"),("NOIR","earth","n0013"),
         ("NOIR","jewel","n0001"),("NOIR","bright","n0003"),("VOID","jewel","n0006"),
         ("VOID","bright","n0004"),("WABI","jewel","n0006"),("WABI","bright","n0004")]
SUPPORTS={
 "FILM":{"pants":["g0108","g0171","g0491","g0523"],"skirt":["g0337","g0439","g0491","g0523"],"dress":["g0219","g0491","g0523"]},
 "NEON":{"pants":["g0108","g0003","g0043","g0070"],"skirt":["g0337","g0188","g0254","g0513"],"dress":["g0222","g0265","g0513"]},
 "NOIR":{"pants":["g0337","g0068","g0069","g0070"],"skirt":["g0350","g0446","g0069","g0070"],"dress":["g0222","g0069","g0070"]},
 "VOID":{"pants":["g0337","g0415","g0591","g0526"],"skirt":["g0337","g0449","g0591","g0526"],"dress":["g0222","g0591","g0526"]},
 "WABI":{"pants":["g0108","g0404","g0497","g0284"],"skirt":["g0337","g0439","g0497","g0284"],"dress":["g0219","g0497","g0284"]},
}
def main():
 m=json.loads((AUDIT/"generated-garments/combined-manifest-v3.json").read_text()); v=json.loads((ROOT/"app/data/recommendation-visual.v1.json").read_text())
 recipes=[]
 for persona,palette,hero in TARGETS:
  for structure in ("pants","skirt","dress"):
   recipes.append({"persona":persona,"palette":palette,"season":"autumn","structure":structure,"hero":hero,
                   "items":[hero,*SUPPORTS[persona][structure]],"expression":"entry",
                   "intent":f"用 {hero} 的主服装颜色与结构解决 {persona}×{palette} 秋季零供给。"})
 result={"schema_version":1,"batch_id":"aw-autumn-02","source_visual_version":v["version"],"status":"designer_targets_pending_whole_image_review",
         "new_garments":m["garments"],"new_garment_manifest":"generated-garments/combined-manifest-v3.json","new_garment_version":m["version"],"recipes":recipes}
 target=AUDIT/"autumn-recipes.batch02.json"
 if target.exists() and json.loads(target.read_text())!=result: raise SystemExit("Autumn recipe batch changed; refusing overwrite")
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n"); print(json.dumps({"recipes":len(recipes),"new_garments":1},ensure_ascii=False))
if __name__=="__main__":main()
