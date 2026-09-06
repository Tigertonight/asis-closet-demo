"""Reproduce QR decode failures using public deterministic, non-auth tokens."""
import argparse
import base64
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import qrcode


def sample_url(index):
    token = base64.urlsafe_b64encode(hashlib.sha256(f"qr-test-{index}".encode()).digest()).decode().rstrip("=")
    return "http://testserver/selfit?handoff=" + token


def check(url, box_size=3, mask=None):
    qr = qrcode.QRCode(version=5, error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=box_size, border=4, mask_pattern=mask)
    qr.add_data(url)
    qr.make(fit=True)
    image = np.asarray(qr.make_image(fill_color="#171313", back_color="#ffffff").convert("RGB"))
    decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(image)
    blurred = cv2.GaussianBlur(image, (3, 3), 0)
    blurred_text, _, _ = cv2.QRCodeDetector().detectAndDecode(blurred)
    return {"decoded": decoded == url, "blurred_decoded": blurred_text == url}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Refusing to overwrite diagnostic evidence")
    rows = []
    for index in range(args.samples):
        url = sample_url(index)
        original = check(url)
        row = {"index": index, "synthetic_url": url, "original": original}
        if not all(original.values()):
            row["six_pixel_modules"] = check(url, box_size=6)
            row["masks"] = {str(mask): check(url, mask=mask) for mask in range(8)}
        rows.append(row)
    report = {"schema_version": 1, "opencv_version": cv2.__version__,
              "samples": args.samples, "failed": sum(not all(row["original"].values()) for row in rows),
              "note": "Diagnostic synthetic tokens only; no real handoff credential is included.", "rows": rows}
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("opencv_version", "samples", "failed")}))


if __name__ == "__main__":
    main()
