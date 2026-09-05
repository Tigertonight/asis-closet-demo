"""Complete disposition accounting for all 47 coverage-primary outfits."""
import hashlib,json
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];AUDIT=ROOT/"docs/audits/20260904-aw-supply"
UNREVISED={
"o0128":("route_focal_recomposition","覆盖之外仍有多焦点竞争"),"o0140":("exit_default","缺内层且多焦点过载"),
"o0141":("route_layer_structure","透感内层和外套袖量同时未证实"),"o0194":("route_focal_recomposition","覆盖之外仍有多焦点竞争"),
"o0201":("exit_default","缺内层且多焦点过载"),"o0202":("route_layer_structure","透感内层和外套袖量同时未证实"),
"o0269":("route_focal_recomposition","透感和多焦点须一并重组"),"o0272":("route_focal_recomposition","覆盖照明与多焦点须一并重组"),
"o0282":("exit_default_recompose_items","原建议排除，单品拆开配置不透结构"),"o0283":("route_focal_recomposition","透感上衣与配件语汇竞争"),
"o0288":("route_layer_structure","透感内层和外套袖量同时未证实"),"o0655":("superseded_parent_variant","同父配方已用 o0123 建立覆盖修订"),
"o0658":("route_focal_recomposition","透感和多焦点须一并重组"),"o0671":("superseded_parent_variant","同父配方已用 o0670 建立覆盖修订"),
"o0682":("exit_default","透感、外层体量和多焦点过载"),"o0684":("route_layer_structure","透感与外层袖量同时未证实"),
"o1067":("superseded_parent_variant","同父配方覆盖修订仍待换素包，不重复造近似版本"),
"o1068":("superseded_parent_variant","同父配方覆盖修订仍待换素包，不重复造近似版本")}

def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
def main():
 source=json.loads((AUDIT/"repair-ledger.initial.json").read_text());review=json.loads((AUDIT/"repairs.batch03.native-review.json").read_text())
 reviewed={r["source_token"]:r for r in review["entries"]};rows=[]
 for r in source["entries"]:
  if r["primary_group"]!="opaque_coverage":continue
  if r["token"] in reviewed:
   rr=reviewed[r["token"]]
   if rr["status"]=="ai_candidate": decision,evidence="repair_candidate",rr["evidence"]
   else:
    conflict=(rr["observations"].get("conflicts") or ["review_pending"])[0]
    decision=("route_layer_structure" if "volume" in conflict else "route_focal_recomposition")
    evidence=rr["evidence"]
   batch="aw-repair-03"
  else:
   decision,evidence=UNREVISED[r["token"]];batch=None
  rows.append({"outfit_id":r["outfit_id"],"token":r["token"],"source_record_fingerprint":r["source_record_fingerprint"],
   "decision":decision,"revision_batch":batch,"evidence":evidence,"counts_as_aw_daily_supply":decision=="repair_candidate","original_preserved":True})
 assert len(rows)==47 and set(UNREVISED)|set(reviewed)=={r["token"] for r in rows}
 result={"schema_version":1,"source_ledger_version":source["version"],"review_version":review["version"],"entries":rows,"counts":dict(Counter(r["decision"] for r in rows))}
 result["version"]="aw-coverage-dispositions-"+digest(result)[:20]
 target=AUDIT/"opaque-coverage.dispositions.json"
 if target.exists() and json.loads(target.read_text())!=result:raise SystemExit("Dispositions changed; refusing overwrite")
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n");print(json.dumps(result["counts"],ensure_ascii=False,sort_keys=True))
if __name__=="__main__":main()
