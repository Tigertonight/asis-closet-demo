"""selfit onboarding 照片质量检测的算法接口层。

前后端契约约定见 docs/SELFIT_BACKEND_INTEGRATION.md 4.2 节：
`POST /api/v1/selfit/sessions/{id}/photos/{kind}`（kind = face | body）。

算法接入说明
------------
接口层只依赖本模块暴露的稳定抽象，算法任务只需要：

1. 实现一个 `PhotoInspector`：`inspect(image, kind) -> PhotoInspection`，
   返回是否可用以及命中的问题枚举（`PHOTO_ISSUES` 中的稳定值）。
2. 调用 `register_photo_inspector()` 注册（或直接把 `accept_all_inspector`
   替换为真实实现）。

约束：
- `image` 是已经完成格式/大小/解码校验的 RGB `PIL.Image`。
- `kind` 只会是 `"face"` 或 `"body"`。
- 返回值只允许使用 `PHOTO_ISSUES` 里的枚举；未知枚举会被降级为
  `unsupported_content`，避免破坏前端契约。
- 检测到多个问题时全部返回，接口层会按 `ISSUE_PRIORITY` 决定主问题码和文案。
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from PIL import Image

# ---------------------------------------------------------------------------
# 路演容量保护：单机 2 核下的照片检测并发上限与输入预缩。
#
# 实测（2核4G 服务器）：face 检测 2.6s/张 纯 CPU，8 并发无限流时全部请求
# 排队 10s+ 且拖垮其他接口。限制同时检测数 = 核数后排队反而更快（8.3s），
# 且静态资源/报告查询不受影响。检测输入长边压到 1280：face 快 3 倍
# （landmark 是归一化坐标，判定结果一致）；body 不缩（轮廓测量对分辨率
# 敏感，缩图会让身型漂移）。
# ---------------------------------------------------------------------------
_INSPECT_MAX_SIDE = 1280
_INSPECT_SEMAPHORE = threading.Semaphore(
    max(1, int(os.getenv("SELFIT_PHOTO_INSPECT_CONCURRENCY", "0")) or (os.cpu_count() or 2))
)


def _prepare_inspect_input(image: Image.Image, kind: str) -> Image.Image:
    """face 检测输入预缩（body 不缩，见模块注释）。"""

    if kind != "face":
        return image
    if max(image.size) <= _INSPECT_MAX_SIDE:
        return image
    resized = image.copy()
    resized.thumbnail((_INSPECT_MAX_SIDE, _INSPECT_MAX_SIDE))
    return resized

# 契约约定的稳定问题枚举（前后端共用，新增需同步契约文档）。
ISSUE_INSUFFICIENT_LIGHT = "insufficient_light"
ISSUE_BLURRED = "blurred"
ISSUE_FACE_NOT_FOUND = "face_not_found"
ISSUE_MULTIPLE_PEOPLE = "multiple_people"
ISSUE_BODY_NOT_COMPLETE = "body_not_complete"
ISSUE_UNSUPPORTED_CONTENT = "unsupported_content"
# 算法接入后新增的枚举（message 必须可行动，引导用户重拍）。
ISSUE_OVEREXPOSED = "overexposed"
ISSUE_BANGS_FOREHEAD = "bangs_forehead"
ISSUE_SIDE_POSE = "side_pose"
ISSUE_BODY_UNCLEAR = "body_unclear"

PHOTO_ISSUES = frozenset(
    {
        ISSUE_INSUFFICIENT_LIGHT,
        ISSUE_BLURRED,
        ISSUE_FACE_NOT_FOUND,
        ISSUE_MULTIPLE_PEOPLE,
        ISSUE_BODY_NOT_COMPLETE,
        ISSUE_UNSUPPORTED_CONTENT,
        ISSUE_OVEREXPOSED,
        ISSUE_BANGS_FOREHEAD,
        ISSUE_SIDE_POSE,
        ISSUE_BODY_UNCLEAR,
    }
)

# 主问题码优先级：先照片质量（光线/清晰度），再内容合规。
ISSUE_PRIORITY = (
    ISSUE_INSUFFICIENT_LIGHT,
    ISSUE_OVEREXPOSED,
    ISSUE_BLURRED,
    ISSUE_MULTIPLE_PEOPLE,
    ISSUE_FACE_NOT_FOUND,
    ISSUE_BANGS_FOREHEAD,
    ISSUE_SIDE_POSE,
    ISSUE_BODY_NOT_COMPLETE,
    ISSUE_BODY_UNCLEAR,
    ISSUE_UNSUPPORTED_CONTENT,
)

PHOTO_KINDS = frozenset({"face", "body"})

KIND_LABELS = {"face": "面部照", "body": "全身照"}

ISSUE_MESSAGES = {
    ISSUE_INSUFFICIENT_LIGHT: "{label}光线不充足，请换到明亮环境重拍。",
    ISSUE_BLURRED: "{label}不够清晰，请拿稳手机重拍。",
    ISSUE_FACE_NOT_FOUND: "没有检测到清晰人脸，请上传单人正脸照。",
    ISSUE_MULTIPLE_PEOPLE: "照片里有多个人，请只保留本人。",
    ISSUE_BODY_NOT_COMPLETE: "没有拍到完整身形，请上传头到大腿都入镜的照片。",
    ISSUE_UNSUPPORTED_CONTENT: "{label}无法用于分析，请更换一张照片。",
    ISSUE_OVEREXPOSED: "{label}过曝了，请避开强光直射重拍。",
    ISSUE_BANGS_FOREHEAD: "刘海遮住了额头，把刘海拨开、露出额头后重拍。",
    ISSUE_SIDE_POSE: "照片角度偏侧，请正对镜头重新拍一张。",
    ISSUE_BODY_UNCLEAR: "身形轮廓提取不稳定，请换背景简洁、正面修身、手臂微张的全身照。",
}


@dataclass(frozen=True)
class PhotoInspection:
    """算法检测结果。accepted=True 时 issues 必须为空。

    attributes 为算法识别出的属性标签（如肤色/脸型/身型），键为属性名、
    值为 {"label", "confidence"}；仅在 accepted=True 时有意义，接口层把它
    存进会话记录供报告任务消费，不回传给前端契约。
    """

    accepted: bool
    issues: list[str] = field(default_factory=list)
    attributes: dict = field(default_factory=dict)


PhotoInspector = Callable[[Image.Image, str], PhotoInspection]


def accept_all_inspector(image: Image.Image, kind: str) -> PhotoInspection:
    """默认占位实现：协议校验通过后全部放行。

    算法接入前用于跑通联调链路；接入时替换为真实检测。
    """

    return PhotoInspection(accepted=True, issues=[])


_inspector: PhotoInspector = accept_all_inspector


def register_photo_inspector(inspector: PhotoInspector) -> None:
    global _inspector
    _inspector = inspector


def inspect_photo(image: Image.Image, kind: str) -> PhotoInspection:
    return _inspector(image, kind)


def sanitize_issues(issues: list[str]) -> list[str]:
    """过滤算法返回的未知枚举，保持前端契约稳定。"""

    known = [issue for issue in issues if issue in PHOTO_ISSUES]
    if not known and issues:
        return [ISSUE_UNSUPPORTED_CONTENT]
    return known


def primary_issue(issues: list[str]) -> str:
    for candidate in ISSUE_PRIORITY:
        if candidate in issues:
            return candidate
    return ISSUE_UNSUPPORTED_CONTENT


def issue_message(issue: str, kind: str) -> str:
    template = ISSUE_MESSAGES.get(issue, ISSUE_MESSAGES[ISSUE_UNSUPPORTED_CONTENT])
    return template.format(label=KIND_LABELS.get(kind, "照片"))


# ---------------------------------------------------------------------------
# 真实算法接入：app/attribute_pipeline → PhotoInspector
# ---------------------------------------------------------------------------

# attribute_pipeline 的 issue code → 契约枚举。
# 值为 None 表示 warn 级提示（不拦截上传，只进属性置信度）。
_ISSUE_CODE_TO_ENUM: dict[str, str | None] = {
    # 大头照门禁（app/cv_pipeline.run_face_cv 与 attribute_pipeline 共用 code）
    "photo.insufficient_light": ISSUE_INSUFFICIENT_LIGHT,
    "photo.overexposed": ISSUE_OVEREXPOSED,
    "photo.color_cast": None,
    "photo.face_crop_empty": ISSUE_UNSUPPORTED_CONTENT,
    "face.no_face": ISSUE_FACE_NOT_FOUND,
    "face.too_small": ISSUE_FACE_NOT_FOUND,
    "face.cropped": ISSUE_FACE_NOT_FOUND,
    "face.eye_occluded": ISSUE_FACE_NOT_FOUND,
    "face.lower_occluded": ISSUE_FACE_NOT_FOUND,
    "face.landmark_missing": ISSUE_FACE_NOT_FOUND,
    "face.multiple_faces": ISSUE_MULTIPLE_PEOPLE,
    "face.blurry": ISSUE_BLURRED,
    "face.soft_detail": None,
    "face.edge_close": None,
    "face.bangs_forehead": None,  # 产品口径：刘海照不拦截上传，脸型交给用户手动确认
    "face.side_pose": ISSUE_SIDE_POSE,
    "face.shape_close": None,
    "skin.sample_failed": ISSUE_UNSUPPORTED_CONTENT,
    # 全身照
    "body.no_person": ISSUE_BODY_NOT_COMPLETE,
    "body.upper_incomplete": ISSUE_BODY_NOT_COMPLETE,
    "body.not_full_body": ISSUE_BODY_NOT_COMPLETE,
    "body.side_pose": ISSUE_SIDE_POSE,
    "body.silhouette_unclear": ISSUE_BODY_UNCLEAR,
    "body.shape_ambiguous": ISSUE_BODY_UNCLEAR,
    "body.loose_clothing": None,
    "body.arms_attached": None,
}


def attribute_inspector(image: Image.Image, kind: str) -> PhotoInspection:
    """真实照片检测 + 属性识别。

    - 任一「重拍级」问题（见映射表）都会拒绝并返回对应枚举；
    - warn 级提示（偏色/轮廓接近/衣物宽松等）不拦截，只降低属性置信度；
    - accepted 时把识别出的属性标签放进 PhotoInspection.attributes；
    - 并发受信号量保护（=CPU 核数）：高峰期公平排队，超载请求不会把
      CPU 打满拖垮其他接口；face 输入预缩到长边 1280 提速 3 倍。
    """
    from app.attribute_pipeline import analyze_body_photo, analyze_face_photo

    inspect_image = _prepare_inspect_input(image, kind)
    with _INSPECT_SEMAPHORE:
        analysis = analyze_face_photo(inspect_image) if kind == "face" else analyze_body_photo(inspect_image)
    issues: list[str] = []
    for issue in analysis.get("issues", []):
        mapped = _ISSUE_CODE_TO_ENUM.get(str(issue.get("code", "")))
        if mapped and mapped not in issues:
            issues.append(mapped)
    if analysis.get("status") == "fail" and not issues:
        issues = [ISSUE_UNSUPPORTED_CONTENT]

    attributes: dict[str, dict[str, Any]] = {}
    if not issues:
        for name, attribute in analysis.get("attributes", {}).items():
            if attribute.get("status") in {"pass", "warn"} and attribute.get("label"):
                attributes[name] = {
                    "label": attribute["label"],
                    "confidence": attribute.get("confidence", 0.0),
                }
    return PhotoInspection(accepted=not issues, issues=issues, attributes=attributes)
