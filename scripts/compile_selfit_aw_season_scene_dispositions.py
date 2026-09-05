"""Resolve season/scene cases by evidence; labels alone never make AW supply."""
import hashlib,json
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; AUDIT=ROOT/"docs/audits/20260904-aw-supply"

DECISIONS={
"o0070":("adjust_use_occasion","巨层袖、束腰与宝石领结主导，改为 BOLT 主题社交；运动鞋混搭不作日常依据"),
"o0144":("exit_default_recompose_items","吊带薄裙与厚绒靴季节矛盾；裙靴拆开重组"),
"o0148":("exit_default_recompose_items","与 o0144 同裙同靴，换包未解决季节矛盾"),
"o0179":("adjust_use_occasion","束腰巨袖上衣为 BOLT 场合焦点，白裤运动鞋只构成创意混搭"),
"o0189":("adjust_use_occasion","礼仪上衣配素裙运动鞋，保留主题社交用途，不作经典通勤"),
"o0198":("route_focal_recomposition","礼仪短外套与运动鞋语汇分裂，外套和背心须拆分重组"),
"o0203":("adjust_use_occasion","酒红奶油大摆礼服保留正式活动，日常邮差包退出该配方"),
"o0278":("adjust_use_occasion","束腰巨袖、层摆与宝石包同属礼仪语汇，定位 BOLT 正式社交"),
"o0350":("adjust_use_occasion","黑白红枝落地礼裙定位 JADE 正式/文化活动，普通托特不沿用"),
"o0353":("adjust_use_occasion","挂颈交领墨枝落地礼裙定位 JADE 正式/文化活动"),
"o0410":("adjust_use_occasion","尖肩方领多层落地裙定位 NOIR 正式活动；街头厚鞋不作为默认配件"),
"o0512":("adjust_use_occasion","盘扣墨枝宽袖长礼裙定位 JADE 主题活动，不因旧 MUTE 名称进日常"),
"o0557":("adjust_use_occasion","冷蓝斜裁落地裙定位 ICED 正式社交；桶包、骑士靴和花饰眼镜退出"),
"o0660":("exit_default_recompose_items","轻花纱上衣、直牛仔和厚绒靴缺少统一环境，拆开重组"),
"o0686":("exit_default_recompose_items","短袖粉直裙与厚绒雪靴无外层，拆开重组"),
"o0690":("exit_default_recompose_items","与 o0686 同裙同靴，换桶包眼镜不解决季节矛盾"),
"o0734":("adjust_use_occasion","东方宽袖落地礼裙定位文化活动；大托特不作场合完整配件"),
"o0775":("adjust_use_occasion","酒红奶油多层花礼服定位正式活动；桶包和花饰眼镜退出"),
"o0776":("exit_default_recompose_items","长袖衬衫裙与厚毛雪靴仍缺外层和环境证据，拆开重组")}

def digest(v): return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
def main():
 d=json.loads((AUDIT/"repair-ledger.initial.json").read_text()); rows=[]
 for r in d["entries"]:
  if r["primary_group"]!="season_scene":continue
  decision,evidence=DECISIONS[r["token"]]
  rows.append({"outfit_id":r["outfit_id"],"token":r["token"],"source_record_fingerprint":r["source_record_fingerprint"],
    "decision":decision,"evidence":evidence,"counts_as_aw_daily_supply":False,"original_preserved":True,
    "required_next_review":"new recipe and new image" if decision!="adjust_use_occasion" else "occasion-specific accessories and scene review"})
 assert len(rows)==19 and set(DECISIONS)=={r["token"] for r in rows}
 result={"schema_version":1,"source_ledger_version":d["version"],"entries":rows,"counts":dict(Counter(r["decision"] for r in rows))}
 result["version"]="aw-season-scene-"+digest(result)[:20]
 target=AUDIT/"season-scene.dispositions.json"
 if target.exists() and json.loads(target.read_text())!=result:raise SystemExit("Dispositions changed; refusing overwrite")
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n");print(json.dumps(result["counts"],ensure_ascii=False,sort_keys=True))
if __name__=="__main__":main()
