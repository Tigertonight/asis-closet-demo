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

from dataclasses import dataclass, field
from typing import Callable

from PIL import Image

# 契约约定的稳定问题枚举（前后端共用，新增需同步契约文档）。
ISSUE_INSUFFICIENT_LIGHT = "insufficient_light"
ISSUE_BLURRED = "blurred"
ISSUE_FACE_NOT_FOUND = "face_not_found"
ISSUE_MULTIPLE_PEOPLE = "multiple_people"
ISSUE_BODY_NOT_COMPLETE = "body_not_complete"
ISSUE_UNSUPPORTED_CONTENT = "unsupported_content"

PHOTO_ISSUES = frozenset(
    {
        ISSUE_INSUFFICIENT_LIGHT,
        ISSUE_BLURRED,
        ISSUE_FACE_NOT_FOUND,
        ISSUE_MULTIPLE_PEOPLE,
        ISSUE_BODY_NOT_COMPLETE,
        ISSUE_UNSUPPORTED_CONTENT,
    }
)

# 主问题码优先级：先照片质量（光线/清晰度），再内容合规。
ISSUE_PRIORITY = (
    ISSUE_INSUFFICIENT_LIGHT,
    ISSUE_BLURRED,
    ISSUE_MULTIPLE_PEOPLE,
    ISSUE_FACE_NOT_FOUND,
    ISSUE_BODY_NOT_COMPLETE,
    ISSUE_UNSUPPORTED_CONTENT,
)

PHOTO_KINDS = frozenset({"face", "body"})

KIND_LABELS = {"face": "面部照", "body": "全身照"}

ISSUE_MESSAGES = {
    ISSUE_INSUFFICIENT_LIGHT: "{label}光线不充足，请换到明亮环境重拍。",
    ISSUE_BLURRED: "{label}不够清晰，请拿稳手机重拍。",
    ISSUE_FACE_NOT_FOUND: "没有检测到清晰人脸，请上传单人正脸照。",
    ISSUE_MULTIPLE_PEOPLE: "照片里有多个人，请只保留本人。",
    ISSUE_BODY_NOT_COMPLETE: "没有检测到完整全身，请上传头到脚都入镜的全身照。",
    ISSUE_UNSUPPORTED_CONTENT: "{label}无法用于分析，请更换一张照片。",
}


@dataclass(frozen=True)
class PhotoInspection:
    """算法检测结果。accepted=True 时 issues 必须为空。"""

    accepted: bool
    issues: list[str] = field(default_factory=list)


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
