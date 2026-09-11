"""White-tee presets for the current three female selfie models.

Keep the old paused batch intact because those model photos have been replaced.
Image generation is performed only by the built-in image_gen tool.
"""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import batch_white_tee_presets as batch

batch.BATCH = ROOT / "outputs/tryon-examples/white-tee-female-selfie-20260911"
batch.MODEL_IDS = {"female_slim_1", "female_medium_1", "female_plus_1"}

# These exact full-body selfies have faces below the generic 1.2% area filter.
# Three frontal cascades agree with visual inspection; keep all quality limits.
FACE_SOURCE_SHA256 = {
    "female_slim_1": "8dedd0555421d14026ffbea8b4102ce58a042d6c6d737c44d359668e685b0501",
    "female_medium_1": "637cb742b8d5447b11e1f53509f6279b15fe0a023facaca0b15769eae940bc87",
    "female_plus_1": "365001c4e926a8bb8747a2ada7afeda8e5471cc439bfc5741b6c11fc8dc058e7",
}
_prepared = batch.prepared


@contextmanager
def prepared(row):
    expected = FACE_SOURCE_SHA256[row["modelId"]]
    if row["model"]["sha256"] != expected:
        raise ValueError("Fixed face annotation does not match model image")
    evidence = {"face_count": 1, "primary_face": {"box": {"x": 834, "y": 225, "width": 216, "height": 216}, "area_ratio": round(216*216/(1792*2400), 4)},
                "annotation": "reviewed_fixed_model_face", "source_sha256": expected,
                "detector_support": "frontalface default/alt/alt2 agree at 640/896/1280px; visually checked"}
    row["modelFaceAnnotation"] = evidence
    with _prepared(row), patch.object(batch.base.tryon, "_detect_person", return_value=batch.base.tryon._stage("pass", .84, evidence, [])):
        original_edit = batch.base.CodexEffectProvider.edit
        def preserve_selfie(provider, person_image, garment_image, mask_image, prompt, output_dir):
            prompt += ("\nSelfie pose priority: Image A is the ONLY authority for anatomy and pose. Keep the raised phone hand exactly in place. "
                       "The other arm must remain straight DOWN along the body, with the hand visible at the original height; "
                       "do NOT put it into any pocket, bend it onto the waist, cross arms, or copy hand positions mentioned in the outfit notes. "
                       "Fit jacket sleeves to that straight arm. A handbag may naturally use that lowered hand, without lifting the arm. "
                       "Preserve original face, hairline, body width, head height, leg stance, feet positions, white background and full canvas.")
            return original_edit(provider, person_image, garment_image, mask_image, prompt, output_dir)
        with patch.object(batch.base.CodexEffectProvider, "edit", preserve_selfie):
            yield


batch.prepared = prepared

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["init", "status", "advance", "ingest", "publish"])
    parser.add_argument("--model")
    parser.add_argument("--key")
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()
    if args.action == "init":
        result = batch.initialize()
    elif args.action == "status":
        result = batch.status()
    elif args.action == "publish":
        result = batch.publish()
    else:
        path, row = batch.selected(args.model, args.key)
        result = batch.advance(path, row) if args.action == "advance" else batch.ingest(path, row, args.result)
        result = {k: result[k] for k in ("id", "status", "requestPath", "qualityReview", "result") if k in result}
    print(json.dumps(result, ensure_ascii=False))
