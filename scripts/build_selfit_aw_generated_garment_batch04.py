#!/usr/bin/env python3
"""Register the bright vintage autumn gap-fill jacket without publishing it."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_selfit_aw_generated_garment_batch import build, stable_write
from scripts.prepare_selfit_garment_asset import prepare

AUDIT=ROOT/"docs/audits/20260904-aw-supply/generated-garments/batch04"
STATIC=ROOT/"app/static/selfit/assets/content_v2_drafts/aw-autumn-02/garments"
SOURCE=Path("/Users/yuanzexiang/.codex/generated_images/01a056c3-ad43-77d1-aed3-35866995a6d6/exec-9067e92c-81ee-412f-847d-ef290530e41d.png")
SPECS=[{"slug":"autumn-jacket-bright-film-red","token":"n0017","id":"garment_aw_autumn02_outer_film_red_01",
        "name":"樱桃红七十年代灯芯绒短外套",
        "prompt":"Create a vivid cherry-red cropped corduroy jacket with late-1970s wide pointed collar, shaped waist, clean patch pockets and long sleeves.",
        "personas":["FILM","BOLT","LOOP","HEIR"],"palette":"bright","fit":"合体",
        "silhouette":["cropped_1970s","defined_waist","wide_point_collar"],
        "observation":{"subcategory":"1970s_corduroy_cropped_jacket","neckline":"wide_point_collar","sleeve":"long","length":"hip","volume":"fitted","construction":"button_front_patch_pockets_princess_seams","pattern":"solid","decoration":"low","material_appearance":"corduroy_like","main_colors":["vivid_cherry_red"]},
        "evidence":"樱桃红灯芯绒短外套以七十年代宽尖领、收腰和贴袋比例形成可辨识复古剪裁，未依赖做旧或配件。",
        "targets":["FILM×bright×autumn"],"source_output":str(SOURCE)}]

def main():
    row=SPECS[0]; raw=AUDIT/"raw"/f"{row['slug']}-raw-v1.png"; prepared=AUDIT/"prepared"/f"{row['slug']}-v1.png"; qa_path=AUDIT/"qa"/f"{row['slug']}-v1.json"
    stable_write(raw,SOURCE.read_bytes())
    if not prepared.exists():
        qa=prepare(raw,prepared); qa_path.parent.mkdir(parents=True,exist_ok=True); qa_path.write_text(json.dumps(qa,ensure_ascii=False,indent=2)+"\n")
    result=build(specs=SPECS,audit=AUDIT,static=STATIC,batch_id="aw-generated-garments-04",prompt_version="selfit-aw-autumn-exact-gap-v1")
    target=AUDIT/"manifest.json"
    if target.exists() and json.loads(target.read_text())!=result: raise SystemExit("Generated garment manifest changed; refusing overwrite")
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"version":result["version"],"garments":1,"published":False},ensure_ascii=False))

if __name__=="__main__": main()
