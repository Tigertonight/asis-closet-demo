"""Design one coverage repair per parent where coverage is the sole blocker."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; AUDIT=ROOT/"docs/audits/20260904-aw-supply"
REPLACEMENTS={"g0008":"g0087","g0354":"g0090","g0567":"g0087","g0359":"g0087",
              "g0343":"g0103","g0032":"g0099","g0327":"g0087","g0425":"g0190"}

def main():
    source=json.loads((AUDIT/"repair-ledger.initial.json").read_text()); visual=json.loads((ROOT/"app/data/recommendation-visual.v1.json").read_text())
    token_by_id={gid:r["token"] for gid,r in visual["garments"].items()}; seen=set(); edits=[]
    for row in source["entries"]:
        if row["primary_group"]!="opaque_coverage" or row["original_status"]=="suggested_exclude":continue
        if any("opaque" not in conflict for conflict in row["all_conflicts"]):continue
        if row["source_parent_recipe"] in seen:continue
        risky=next((token_by_id[gid] for gid in row["source_garment_ids"] if token_by_id[gid] in REPLACEMENTS),None)
        if not risky:continue
        seen.add(row["source_parent_recipe"])
        replacement=REPLACEMENTS[risky]
        edits.append({"token":row["token"],"replace":{risky:replacement},
                      "intent":f"用已审核不透款 {replacement} 替换覆盖未证实的 {risky}；仅解除覆盖问题，整套仍须重新看图"})
    assert len(edits)==29 and len(edits)<=48
    result={"schema_version":1,"batch_id":"aw-repair-03","source_visual_version":source["source_visual_version"],
            "status":"explicit_coverage_edits_pending_native_review","new_garments":[],"edits":edits}
    target=AUDIT/"repair-edits.batch03.json"
    if target.exists() and json.loads(target.read_text())!=result:raise SystemExit("Batch changed; refusing overwrite")
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n");print(len(edits))
if __name__=="__main__":main()
