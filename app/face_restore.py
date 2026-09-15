"""Local face-detail restoration; never performs network calls."""
from pathlib import Path
from time import perf_counter
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import cv2
import numpy as np
from PIL import Image

_PREPARATION = ThreadPoolExecutor(max_workers=2, thread_name_prefix="face-prepare")
_LANDMARK_LOCK = Lock()

_OVAL = [10,338,297,332,284,251,389,356,454,323,361,288,397,365,379,378,400,377,152,148,176,149,150,136,172,58,132,93,234,127,162,21,54,103,67,109]
_ANCHORS = [33,133,362,263,1,168,61,291,152]


class FaceRestorer:
    def __init__(self, original, detection):
        self.original = original
        box = detection.get('evidence', {}).get('primary_face', {}).get('box', {})
        self.region = None
        self.source = None
        self.points = None
        self.initialized = False
        self.preparation = None
        if box:
            x, y, w, h = (int(box[k]) for k in ('x', 'y', 'width', 'height'))
            if min(w, h) >= 64:
                self.region = (max(0, x-w//2), max(0, y-h//2), min(original.width, x+w+w//2), min(original.height, y+h+h//2))

    def prepare(self):
        if not self.initialized and self.region is not None:
            self.initialized = True
            self.source = np.asarray(self.original.crop(self.region))
            self.points = self.landmarks(self.source)

    def start(self):
        self.preparation = _PREPARATION.submit(self.prepare)

    @staticmethod
    def landmarks(rgb):
        from app.cv_pipeline import _detect_face_landmarks
        # Bound inference work regardless of uploaded resolution.
        h, w = rgb.shape[:2]
        factor = min(1., 512 / max(h, w))
        small = cv2.resize(rgb, None, fx=factor, fy=factor) if factor < 1 else rgb
        with _LANDMARK_LOCK:
            values = _detect_face_landmarks(small)
        if not values:
            return None
        return np.array([(p.x*w, p.y*h) for p in values], np.float32)

    def restore(self, result_path, output_path):
        start = perf_counter()
        evidence = {'method': 'local_face_detail_v1', 'applied': False}
        try:
            if self.region is None:
                return Path(result_path), {**evidence, 'reason': 'face_region_unavailable'}
            with Image.open(result_path) as image:
                if image.size != self.original.size:
                    return Path(result_path), {**evidence, 'reason': 'canvas_changed'}
                result = image.convert('RGB')
            if self.preparation is not None:
                if not self.preparation.done():
                    return Path(result_path), {**evidence, "reason": "preparation_not_ready"}
                self.preparation.result()
            else:
                self.prepare()
            target = np.array(result.crop(self.region))
            b = self.landmarks(target) if self.points is not None else None
            if b is None:
                return Path(result_path), {**evidence, 'reason': 'landmarks_unavailable'}
            a = self.points
            matrix, _ = cv2.estimateAffinePartial2D(a[_ANCHORS], b[_ANCHORS], method=cv2.LMEDS)
            if matrix is None or not np.isfinite(matrix).all():
                return Path(result_path), {**evidence, 'reason': 'alignment_failed'}
            width = max(1., float(np.ptp(a[_OVAL, 0])))
            scale = float(np.hypot(matrix[0,0], matrix[1,0]))
            angle = abs(float(np.degrees(np.arctan2(matrix[1,0], matrix[0,0]))))
            shift = float(np.linalg.norm(a[_OVAL].mean(0)-b[_OVAL].mean(0)) / width)
            residual = float(np.median(np.linalg.norm(cv2.transform(a[_ANCHORS,None,:], matrix)[:,0,:]-b[_ANCHORS], axis=1))/width)
            evidence.update(scale=round(scale,4), angle=round(angle,2), shift=round(shift,4), residual=round(residual,4))
            if not (.95 <= scale <= 1.05 and angle <= 5 and shift <= .1 and residual <= .025):
                return Path(result_path), {**evidence, 'reason': 'pose_changed'}
            h, w = target.shape[:2]
            warped = cv2.warpAffine(self.source, matrix, (w,h))
            polygon = cv2.transform(a[_OVAL,None,:], matrix)[:,0,:].round().astype(np.int32)
            mask = np.zeros((h,w), np.uint8)
            cv2.fillPoly(mask, [polygon], 255)
            mask = cv2.erode(mask, np.ones((5,5), np.uint8))
            bx, by, bw, bh = cv2.boundingRect(mask)
            if not bw or not bh or bx <= 1 or by <= 1 or bx+bw >= w-1 or by+bh >= h-1:
                return Path(result_path), {**evidence, 'reason': 'face_at_crop_edge'}
            # Match broad lighting, preserving source high-frequency skin detail.
            source_low = cv2.GaussianBlur(warped.astype(np.float32), (0,0), 16)
            target_low = cv2.GaussianBlur(target.astype(np.float32), (0,0), 16)
            correction = np.clip(target_low-source_low, -20, 20)
            corrected = np.clip(warped.astype(np.float32)+correction, 0, 255)
            alpha = np.clip(cv2.distanceTransform(mask, cv2.DIST_L2, 5)/28, 0, 1)[...,None]
            blended = np.round(corrected*alpha+target*(1-alpha)).astype(np.uint8)
            result.paste(Image.fromarray(blended), self.region[:2])
            result.save(output_path, format='PNG', compress_level=1)
            evidence.update(applied=True, elapsed_ms=round((perf_counter()-start)*1000,1))
            return Path(output_path), evidence
        except (cv2.error, ValueError, OSError, IndexError, RuntimeError):
            # Restoration is optional; retain the existing quality gate on failure.
            return Path(result_path), {**evidence, 'reason': 'restoration_unavailable'}


def review_face_contour(original, result, detection):
    """Compare aligned face interiors, excluding clothes and crop background.

    A conservative visual-preservation check, not an identity recognizer.
    Unavailable landmarks leave the caller's existing fallback in charge.
    """
    evidence = {'method': 'face_contour_v1', 'available': False, 'equivalent': False}
    try:
        restorer = FaceRestorer(original, detection)
        if restorer.region is None or original.size != result.size:
            return evidence
        restorer.prepare()
        a = restorer.points
        target = np.array(result.crop(restorer.region))
        b = restorer.landmarks(target) if a is not None else None
        if b is None:
            return evidence
        matrix, _ = cv2.estimateAffinePartial2D(a[_ANCHORS], b[_ANCHORS], method=cv2.LMEDS)
        if matrix is None or not np.isfinite(matrix).all():
            return evidence
        width = max(1., float(np.ptp(a[_OVAL, 0])))
        scale = float(np.hypot(matrix[0,0], matrix[1,0]))
        angle = abs(float(np.degrees(np.arctan2(matrix[1,0], matrix[0,0]))))
        shift = float(np.linalg.norm(a[_OVAL].mean(0)-b[_OVAL].mean(0))/width)
        residual = float(np.percentile(np.linalg.norm(cv2.transform(a[_ANCHORS,None,:], matrix)[:,0,:]-b[_ANCHORS], axis=1),90)/width)
        evidence.update(available=True, scale=round(scale,4), angle=round(angle,2), shift=round(shift,4), landmark_p90=round(residual,4))
        if not (.94 <= scale <= 1.06 and angle <= 5 and shift <= .1 and residual <= .035):
            return {**evidence, 'reason': 'face_geometry_changed'}
        h,w = target.shape[:2]
        source = cv2.warpAffine(restorer.source, matrix, (w,h))
        mask = np.zeros((h,w),np.uint8)
        cv2.fillPoly(mask,[cv2.transform(a[_OVAL,None,:], matrix)[:,0,:].round().astype(np.int32)],255)
        target_mask=np.zeros_like(mask);cv2.fillPoly(target_mask,[b[_OVAL].round().astype(np.int32)],255)
        mask=cv2.bitwise_and(mask,target_mask)
        radius=max(2,int(width*.035));mask=cv2.erode(mask,np.ones((radius*2+1,radius*2+1),np.uint8))>0
        if mask.sum()<256:
            return {**evidence, 'available': False, 'reason':'insufficient_region'}
        sa=source.astype(np.float32);tb=target.astype(np.float32)
        offset=np.clip(np.median(sa[mask]-tb[mask],axis=0),-25,25)
        errors=np.abs(sa[mask]-np.clip(tb[mask]+offset,0,255)).mean(axis=1)
        # Low-pass lightly to tolerate compression; retain eye/nose/mouth structure.
        ga=cv2.GaussianBlur(cv2.cvtColor(sa,cv2.COLOR_RGB2GRAY),(0,0),1)[mask]
        gb=cv2.GaussianBlur(cv2.cvtColor(tb,cv2.COLOR_RGB2GRAY),(0,0),1)[mask]
        if min(float(ga.std()),float(gb.std()))<8:
            return {**evidence,'reason':'insufficient_detail'}
        corr=float(np.corrcoef(ga,gb)[0,1]);mean=float(errors.mean());tail=float(np.percentile(errors,90))
        evidence.update(correlation=round(corr,4),mean_diff=round(mean,2),p90_diff=round(tail,2),pixels=int(mask.sum()))
        evidence['equivalent']=bool(corr>=.90 and mean<=15 and tail<=30)
        return evidence
    except (cv2.error,ValueError,IndexError,RuntimeError):
        return evidence
