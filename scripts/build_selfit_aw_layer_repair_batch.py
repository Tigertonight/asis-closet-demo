"""Replace bulky inner tops only where sleeve volume is the sole blocker."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];AUDIT=ROOT/"docs/audits/20260904-aw-supply"

def replacement(colors):
    colors=set(colors)
    if colors & {"charcoal","black"}:return "g0094"
    if colors & {"taupe","olive","brown"}:return "g0097"
    if colors & {"pale_pink"}:return "g0103"
    if colors & {"ice_blue","washed_blue","cobalt","denim_blue","navy","multicolor"}:return "g0104"
    return "g0085"

def main():
 source=json.loads((AUDIT/"repair-ledger.initial.json").read_text());visual=json.loads((ROOT/"app/data/recommendation-visual.v1.json").read_text())
 gs=visual["garments"];seen=set();edits=[]
 for row in source["entries"]:
  if (row["primary_group"]!="layer_structure" or row["original_status"]=="suggested_exclude"
      or row["all_conflicts"]!=["outer_inner_volume_unverified"] or row["source_parent_recipe"] in seen):continue
  top=next(gs[gid] for gid in row["source_garment_ids"] if gs[gid]["observations"]["category"]=="top")
  target=replacement(top["observations"].get("main_colors") or [])
  seen.add(row["source_parent_recipe"])
  edits.append({"token":row["token"],"replace":{top["token"]:target},
    "intent":f"用贴身、低袖量内层 {target} 替换 {top['token']}，保留外套为主视觉；仅解除袖量冲突，整套重新看图"})
 assert len(edits)==27 and len(edits)<=48
 result={"schema_version":1,"batch_id":"aw-repair-04","source_visual_version":source["source_visual_version"],
  "status":"explicit_layer_edits_pending_native_review","new_garments":[],"edits":edits}
 target=AUDIT/"repair-edits.batch04.json"
 if target.exists() and json.loads(target.read_text())!=result:raise SystemExit("Batch changed; refusing overwrite")
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n");print(len(edits))
if __name__=="__main__":main()
