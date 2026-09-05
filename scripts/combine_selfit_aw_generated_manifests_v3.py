#!/usr/bin/env python3
"""Combine all four immutable generated-garment batches for internal recipes."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; AUDIT=ROOT/"docs/audits/20260904-aw-supply"
SOURCES=[f"generated-garments/batch{i:02d}/manifest.json" for i in (1,2,3,4)]
def main():
    manifests=[json.loads((AUDIT/p).read_text()) for p in SOURCES]
    garments=[g for m in manifests for g in m["garments"]]
    assert len({g["id"] for g in garments})==len(garments)
    result={"schema_version":1,"batch_id":"aw-generated-garments-combined-03","source_versions":[m["version"] for m in manifests],
            "status":"internal_candidate","production_approved":False,"garments":garments,
            "visual":{gid:row for m in manifests for gid,row in m["visual"].items()},
            "limitations":["Aggregate manifest only; source assets remain immutable.","No garment is in the published pool."]}
    result["version"]="aw-generated-garments-combined-"+hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]
    target=AUDIT/"generated-garments/combined-manifest-v3.json"
    if target.exists() and json.loads(target.read_text())!=result: raise SystemExit("Combined manifest changed; refusing overwrite")
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"version":result["version"],"garments":len(garments)},ensure_ascii=False))
if __name__=="__main__": main()
