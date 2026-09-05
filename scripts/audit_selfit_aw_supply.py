"""Compare fixed slots and bounded flexible selection on the SAME audited pool."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.closet import selfit_content_pool,_published_catalog_outfits
from app.recommendation_visual import load_visual,attach_visual
from app.recommendation_aw import load_recomposition_candidates,prepare_candidates
from app.recommendation_feed import rank_candidates,select_sequence
from app.recommendation_sequence import daily_candidates,select_flexible_sequence,VERSION
from app.recommendation_profile import PERSONAS,PALETTES
from scripts.audit_selfit_personal_home_supply import sequence_diagnostics


def audit(include_recompositions=False):
    pool=selfit_content_pool();visual=load_visual()
    candidates,held=attach_visual(_published_catalog_outfits(),pool.garments,pool.outfits,visual)
    supplemental=[]; supplemental_version=None
    if include_recompositions:
        supplemental,supplemental_version=load_recomposition_candidates(pool.garments,visual)
    candidates,bundle=prepare_candidates(candidates+supplemental,pool.garments,visual,
                                         supplemental_version=supplemental_version)
    matrix=[]
    for season in ("autumn","winter"):
        for persona in sorted(PERSONAS):
            for palette in PALETTES:
                ranked,rejected=rank_candidates(candidates,{"persona_id":persona,"palette":palette,"axes":{}},
                                               {"season_tags":[season],"scene_tags":["daily"]})
                old,old_gaps=select_sequence(ranked,30)
                daily,daily_rejected=daily_candidates(ranked,winter=season=="winter")
                before,before_gaps=select_sequence(daily,30)
                started=perf_counter()
                after,gaps,selection=select_flexible_sequence(daily,30)
                elapsed=perf_counter()-started
                diagnostics=sequence_diagnostics(after)
                assert not diagnostics["constraint_violations"]
                matrix.append({"season":season,"persona":persona,"palette":palette,
                    "ranked_candidates":len(ranked),"daily_candidates":len(daily),
                    "legacy_selected_count":len(old),"same_quality_fixed_count":len(before),"flexible_selected_count":len(after),
                    "quality_gate_change":len(before)-len(old),"selection_change":len(after)-len(before),
                    "fixed_ids":[r["outfit_id"] for r in before],"selected_ids":[r["outfit_id"] for r in after],
                    "qualified_first_ten":len(after)>=10,"qualified_browse_thirty":len(after)==30,
                    "rejected":rejected,"daily_rejected":daily_rejected,"gaps":gaps,"selection":selection,
                    "eligible_by_expression_structure":dict(Counter(r["visual"]["expression"]+":"+r["visual"]["structure"] for r in daily)),
                    "sequence_diagnostics":diagnostics,"selection_seconds":round(elapsed,6)})
        print(season,json.dumps({"first_ten":sum(r["qualified_first_ten"] for r in matrix if r["season"]==season),
                                "thirty":sum(r["qualified_browse_thirty"] for r in matrix if r["season"]==season)}),flush=True)
    return {"schema_version":1,"strategy_version":VERSION,"bundle":bundle,"matrix":matrix,
            "supplemental_candidates":len(supplemental),
            "counts":{"conditions":len(matrix),"first_ten":sum(r["qualified_first_ten"] for r in matrix),
                      "thirty":sum(r["qualified_browse_thirty"] for r in matrix),"held_outfits":len(held)},
            "interpretation":"Paired comparison separates stricter daily/winter evidence gates from selection changes. Not a maximum feasible supply proof or end-to-end P95 benchmark.",
            "production_approved":False}


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--include-recompositions",action="store_true")
    parser.add_argument("--output",type=Path,default=ROOT/"docs/audits/20260904-aw-supply/coverage.initial.json")
    args=parser.parse_args()
    data=audit(args.include_recompositions)
    output=args.output
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():raise SystemExit("Baseline exists; do not overwrite")
    output.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")
