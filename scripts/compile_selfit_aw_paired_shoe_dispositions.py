"""Close the paired-shoe work queue without pretending every outfit was rescued."""
import hashlib,json
from pathlib import Path
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]; AUDIT=ROOT/"docs/audits/20260904-aw-supply"
DECISIONS={
"o0217":("adjusted_use","aw-repair-01","鞋已修复；复杂拼接裤保留创意/社交用途，不计秋冬日常"),
"o0229":("exit_default",None,"高彩巨量内外层、复杂裤包与袖量问题叠加，单换鞋没有合理救回价值"),
"o0261":("route_layer_structure",None,"长外层与短鼓袖内层的袖量须与鞋一起整体重组"),
"o0445":("retain_pending_reclassification","aw-repair-01","鞋已修复；主衣更接近 LOOP/EASE，且当前为春夏"),
"o0456":("adjusted_use",None,"高彩上衣、裙和包同时抢焦点；先按鲜明表达重组，不进默认日常"),
"o0460":("exit_default",None,"内外不对称袖量和复杂下装仍冲突，单换鞋无效"),
"o0465":("retain_pending_reclassification","aw-repair-01","鞋已修复；收腰排扣裙更接近 HEIR/MELT，且当前为春夏"),
"o0796":("exit_default",None,"高彩上衣与复杂拼接裤同时为焦点，单换鞋无效"),
"o0797":("adjusted_use","aw-repair-02","鞋已修复；成套更接近 OOPS/EDGE 鲜明表达，不沿用 NEON 日常"),
"o0814":("exit_default",None,"多层袖量、复杂下装和鞋风险叠加，退出默认池"),
"o0861":("route_layer_structure",None,"高彩巨泡袖内层与长外套的容量未证实，需整体层次重组"),
"o1136":("repair_candidate","aw-repair-02","鞋包简化后高彩短上衣成为单一焦点，作为 NEON 秋季日常鲜明候选"),
"o1137":("repair_candidate","aw-repair-02","鞋包简化后白衬衫灰裤易穿，按 LOOP/MUTE 秋季候选重审"),
"o1157":("adjusted_use",None,"不对称上衣、彩裙和彩包仍缺主次，转鲜明表达重组"),
"o1161":("exit_default",None,"袖量、密集下装和鞋风险叠加，旧版本退出默认池"),
"o1166":("adjusted_use","aw-repair-02","鞋已修复；束胸拼片花纱长裙仍属 OOPS/EDGE 社交创意场景")}

def digest(v): return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
def main():
    source=json.loads((AUDIT/"repair-ledger.initial.json").read_text())
    rows=[]
    for row in source["entries"]:
        if row["primary_group"]!="paired_shoes": continue
        decision,batch,evidence=DECISIONS[row["token"]]
        rows.append({"outfit_id":row["outfit_id"],"token":row["token"],"source_record_fingerprint":row["source_record_fingerprint"],
                     "decision":decision,"revision_batch":batch,"evidence":evidence,
                     "original_preserved":True,"counts_as_aw_daily_supply":decision=="repair_candidate"})
    assert len(rows)==16 and set(DECISIONS)=={r["token"] for r in rows}
    result={"schema_version":1,"source_ledger_version":source["version"],"entries":rows,
            "counts":dict(Counter(r["decision"] for r in rows))}
    result["version"]="aw-paired-shoes-"+digest(result)[:20]
    target=AUDIT/"paired-shoes.dispositions.json"
    if target.exists() and json.loads(target.read_text())!=result: raise SystemExit("Dispositions changed; refusing overwrite")
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(result["counts"],ensure_ascii=False,sort_keys=True))
if __name__=="__main__":main()
