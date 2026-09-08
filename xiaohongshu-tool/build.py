#!/usr/bin/env python3
"""构建小红书小工具产物包：selfit 风格人格测试（引流版）。

产物是一个完全离线、自包含的 Web 包：
  dist/selfit-xhs-minitool/
    index.html            唯一入口（无内联脚本 / 行内事件）
    selfit-tool.css       外置样式
    selfit-tool.js        业务逻辑（分型 / 报告 / 分享卡片 / miniTool API）
    persona.js            十六型人格算法（构建时从主项目复制，hash 校验同步）
    templates.js          16 型报告模板（从 v1.json 生成，图片路径重写为包内相对路径）
    assets/               全部图片资源（cwebp 压缩）

用法：
  python3 xiaohongshu-tool/build.py           # 构建到 dist/ 并打 zip
  python3 xiaohongshu-tool/build.py --check   # 只跑合规自检
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
SELFIT_STATIC = REPO / "app" / "static" / "selfit"
SRC = ROOT / "src"
DIST = ROOT / "dist"
PACKAGE_NAME = "selfit-xhs-minitool"
PACKAGE_DIR = DIST / PACKAGE_NAME

# ---------------------------------------------------------------------------
# 资产清单：(源文件相对 app/static/selfit/, 包内目标, 处理方式)
#   ("copy",)                    原样复制
#   ("webp", max_width, quality) cwebp 压缩（超过 max_width 时等比缩小）
# ---------------------------------------------------------------------------

UI_ASSETS = [
    # 品牌与启动
    ("assets/onboarding-splash@2x.png", "assets/ui/onboarding-splash.webp", ("webp", 900, 72)),
    ("assets/splash-textile@2x.png", "assets/ui/splash-textile.webp", ("webp", 900, 70)),
    ("assets/splash-signature@2x.png", "assets/ui/splash-signature.png", ("copy",)),
    ("assets/selfit-wordmark.svg", "assets/ui/selfit-wordmark.svg", ("copy",)),
    # intro DNA 卡片
    ("assets/suit-card-base@2x.png", "assets/ui/suit-card-base.webp", ("webp", 204, 78)),
    ("assets/like-card-base@2x.png", "assets/ui/like-card-base.webp", ("webp", 204, 78)),
    ("assets/vibe-card-base@2x.png", "assets/ui/vibe-card-base.webp", ("webp", 204, 78)),
    ("assets/suit-word@2x.png", "assets/ui/suit-word@2x.png", ("copy",)),
    ("assets/like-word@2x.png", "assets/ui/like-word@2x.png", ("copy",)),
    ("assets/vibe-word@2x.png", "assets/ui/vibe-word@2x.png", ("copy",)),
    # loading 阶段图
    ("assets/loading-stage-25@2x.png", "assets/ui/loading-stage-25.webp", ("webp", 480, 76)),
    ("assets/loading-stage-50@2x.png", "assets/ui/loading-stage-50.webp", ("webp", 480, 76)),
    ("assets/loading-stage-75@2x.png", "assets/ui/loading-stage-75.webp", ("webp", 492, 76)),
    ("assets/loading-stage-100@2x.png", "assets/ui/loading-stage-100.webp", ("webp", 480, 76)),
    # 报告页装饰与信任素材
    ("assets/lace-card@4x.png", "assets/ui/lace-card.webp", ("webp", 320, 78)),
    ("assets/xiaohongshu-badge@2x.png", "assets/ui/xiaohongshu-badge@2x.png", ("copy",)),
    ("assets/report-user-avatar-stack@4x.png", "assets/ui/report-user-avatar-stack@4x.png", ("copy",)),
    # 群聊二维码（源文件在 xiaohongshu-tool/ 根目录）
    (None, "assets/ui/group-chat-qr.jpeg", ("copy_local", ROOT / "小红书selfit群聊二维码.jpeg")),
    ("assets/personality/placeholder-card.svg", "assets/ui/placeholder-card.svg", ("copy",)),
    ("assets/personality/placeholder-hero.svg", "assets/ui/placeholder-hero.svg", ("copy",)),
    # 分享操作图标
    ("assets/iconfont-share/icon-save.svg", "assets/ui/icon-save.svg", ("copy",)),
    ("assets/iconfont-share/icon-xiaohongshu.svg", "assets/ui/icon-xiaohongshu.svg", ("copy",)),
]

# 手动选择（肤色用色块无图；脸型 / 身型用 @4x 源压到 3x 显示宽）
MANUAL_FACES = ["diamond", "square", "round", "oval", "heart"]
MANUAL_BODIES = ["pear", "inverted-triangle", "hourglass", "rectangle", "apple"]

# 报告推荐图压缩参数：两列网格 ~180px 宽（3x DPR ≈ 540px），分享卡片更小
PERSONALITY_RECIPE = {
    "hero-mobile.webp": ("copy",),
    "share-ornament.webp": ("copy",),
    "report-makeup-01.webp": ("webp", 720, 72),
    "report-makeup-02.webp": ("webp", 720, 72),
    "report-hair-01.webp": ("webp", 720, 72),
    "report-hair-02.webp": ("webp", 720, 72),
    "report-outfits-01.webp": ("webp", 720, 72),
    "report-outfits-02.webp": ("webp", 720, 72),
    "report-outfits-03.webp": ("webp", 720, 72),
    "report-outfits-04.webp": ("webp", 720, 72),
}

ALLOWED_SUFFIXES = {".html", ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".woff", ".woff2", ".json"}

# JS/HTML 中禁止出现的联网与动态执行 API（合规自检用）
FORBIDDEN_JS_PATTERNS = [
    (r"\bfetch\s*\(", "fetch 网络请求"),
    (r"\bXMLHttpRequest\b", "XMLHttpRequest"),
    (r"\bWebSocket\b", "WebSocket"),
    (r"\bEventSource\b", "SSE"),
    (r"\beval\s*\(", "eval 动态执行"),
    (r"\bnew\s+Function\s*\(", "new Function 动态执行"),
    (r"\bWebAssembly\b", "WebAssembly"),
    (r"\bWorker\b", "Web Worker"),
    (r"\bnavigator\.clipboard\b", "剪贴板 API（容器已禁用）"),
    (r"\bexecCommand\s*\(", "execCommand（容器已禁用）"),
    (r"\bsendBeacon\b", "sendBeacon 网络请求"),
    (r"\bwindow\.open\s*\(", "window.open（容器已禁用）"),
    (r"\brequestFullscreen\b", "全屏 API（容器已禁用）"),
    (r"\bgeolocation\b", "地理定位（容器已禁用）"),
    # Chrome 61 / ES2017 之后的语法与 API（官方 js-compatibility 规范：解析阶段直接失败）
    (r"\?\.", "可选链 ?.（ES2020，Chrome 80+）"),
    (r"\?\?", "空值合并 ??（ES2020，Chrome 80+）"),
    (r"\bObject\.hasOwn\s*\(", "Object.hasOwn（Chrome 93+）"),
    (r"\bObject\.fromEntries\s*\(", "Object.fromEntries（Chrome 73+）"),
    (r"\breplaceChildren\s*\(", "replaceChildren（Chrome 86+）"),
    (r"\btoggleAttribute\s*\(", "toggleAttribute（Chrome 69+）"),
    (r"\.replaceAll\s*\(", "String.replaceAll（Chrome 85+）"),
    (r"\bstructuredClone\s*\(", "structuredClone（Chrome 98+）"),
    (r"\bqueueMicrotask\s*\(", "queueMicrotask（Chrome 71+）"),
    (r"\bPromise\.any\b", "Promise.any（Chrome 85+）"),
]


def run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def convert_webp(source: Path, target: Path, max_width: int, quality: int) -> None:
    """cwebp 压缩；宽于 max_width 时等比缩小。"""
    from PIL import Image

    with Image.open(source) as image:
        width, height = image.size
    cmd = ["cwebp", "-quiet", "-q", str(quality)]
    if width > max_width:
        ratio = max_width / width
        cmd += ["-resize", str(max_width), str(max(1, round(height * ratio)))]
    cmd += [str(source), "-o", str(target)]
    run(cmd)


def copy_asset(source: Path, target: Path, recipe: tuple) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    if recipe[0] == "copy":
        shutil.copyfile(source, target)
    elif recipe[0] == "copy_local":
        _, local_source = recipe
        shutil.copyfile(local_source, target)
    elif recipe[0] == "webp":
        _, max_width, quality = recipe
        convert_webp(source, target, max_width, quality)
    else:
        raise ValueError(f"未知处理方式: {recipe}")
    return target.stat().st_size


def collect_personality_types() -> list[str]:
    data = json.loads((SELFIT_STATIC / "data" / "personality-report-templates.v1.json").read_text())
    return sorted(data["types"].keys())


def build_templates_js() -> int:
    """从 v1.json 生成 templates.js：图片路径重写为包内相对路径。

    - hero 引用改指 hero-mobile.webp（小工具全移动端，无需桌面 hero）
    - 删除 sourceUrl（站外链接数据不进包，避免审核误判）
    - 删除 colors.sourceCard（报告渲染只用 items，色卡大图不打包）
    """
    source = SELFIT_STATIC / "data" / "personality-report-templates.v1.json"
    data = json.loads(source.read_text())

    for template in data["types"].values():
        hero = template.get("hero", {}).get("image", {})
        hero["src"] = f"./assets/personality/{template['typeId']}/hero-mobile.webp"
        hero.pop("placeholder", None)
        for section in ("makeup", "hair"):
            for item in template.get("recommendations", {}).get(section, []):
                item.pop("sourceUrl", None)
                image = item.get("image", {})
                if image.get("src"):
                    image["src"] = rewrite_asset_path(image["src"], template["typeId"])
        outfits = template.get("recommendations", {}).get("outfits", {})
        for item in outfits.get("items", []):
            item.pop("sourceUrl", None)
            image = item.get("image", {})
            if image.get("src"):
                image["src"] = rewrite_asset_path(image["src"], template["typeId"])
        colors = template.get("colors", {})
        colors.pop("sourceCard", None)
        source_block = outfits.get("source", {})
        avatars = source_block.get("avatars", {})
        if avatars.get("imageUrl"):
            avatars["imageUrl"] = "./assets/ui/report-user-avatar-stack@4x.png"

    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    js = f"window.__SELFIT_PERSONALITY_TEMPLATES__=Object.freeze({payload});\n"
    target = PACKAGE_DIR / "templates.js"
    target.write_text(js, encoding="utf-8")
    return target.stat().st_size


def rewrite_asset_path(path: str, type_id: str) -> str:
    path = path.split("?")[0]
    if path.startswith(f"/static/selfit/assets/personality/{type_id}/"):
        return f"./assets/personality/{type_id}/{path.rsplit('/', 1)[-1]}"
    if path.startswith("/static/selfit/assets/"):
        return f"./assets/ui/{path.rsplit('/', 1)[-1]}"
    return path


def build_assets() -> dict[str, int]:
    sizes: dict[str, int] = {}
    for rel_source, rel_target, recipe in UI_ASSETS:
        if recipe[0] == "copy_local":
            # 源文件在本地目录，不从 SELFIT_STATIC 取
            sizes[rel_target] = copy_asset(None, PACKAGE_DIR / rel_target, recipe)
            continue
        source = SELFIT_STATIC / rel_source
        if not source.exists():
            raise FileNotFoundError(f"缺少源资产: {source}")
        sizes[rel_target] = copy_asset(source, PACKAGE_DIR / rel_target, recipe)

    manual_dir = SELFIT_STATIC / "assets" / "manual-selection"
    for name in MANUAL_FACES:
        source = manual_dir / f"face-{name}@4x.png"
        sizes[f"assets/manual/face-{name}.webp"] = copy_asset(
            source, PACKAGE_DIR / f"assets/manual/face-{name}.webp", ("webp", 120, 80))
    for name in MANUAL_BODIES:
        source = manual_dir / f"body-{name}@4x.png"
        sizes[f"assets/manual/body-{name}.webp"] = copy_asset(
            source, PACKAGE_DIR / f"assets/manual/body-{name}.webp", ("webp", 110, 80))

    personality_total = 0
    for type_id in collect_personality_types():
        type_dir = SELFIT_STATIC / "assets" / "personality" / type_id
        for filename, recipe in PERSONALITY_RECIPE.items():
            source = type_dir / filename
            if not source.exists():
                raise FileNotFoundError(f"缺少人格资产: {source}")
            target = PACKAGE_DIR / "assets" / "personality" / type_id / filename
            personality_total += copy_asset(source, target, recipe)
    sizes["assets/personality/ (16 型合计)"] = personality_total
    return sizes


def compliance_check() -> list[str]:
    """小工具容器合规自检，返回问题列表（空 = 通过）。"""
    problems: list[str] = []
    html_files = list(PACKAGE_DIR.rglob("*.html"))
    if len(html_files) != 1 or html_files[0].name != "index.html":
        problems.append(f"必须恰好一个 index.html 入口，实际: {[p.name for p in html_files]}")

    # 文件类型白名单
    for path in PACKAGE_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() not in ALLOWED_SUFFIXES:
            problems.append(f"不支持的文件类型: {path.relative_to(PACKAGE_DIR)}")

    # 内联脚本 / 行内事件 / javascript: URI
    html = (PACKAGE_DIR / "index.html").read_text(encoding="utf-8")
    if re.search(r"<script(?![^>]*\bsrc\s*=)", html):
        problems.append("index.html 含内联 <script>（容器禁止，需外置 .js）")
    if re.search(r"\son[a-z]+\s*=", html, re.IGNORECASE):
        problems.append("index.html 含行内事件属性 onclick= 等（容器禁止）")
    if "javascript:" in html:
        problems.append("index.html 含 javascript: URI（容器禁止）")

    # 外链资源（html / css / js 全量扫描）
    url_pattern = re.compile(r"""(?:src|href)\s*=\s*["']([^"']+)["']|url\(\s*["']?([^"')]+)["']?\s*\)""")
    for path in PACKAGE_DIR.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".html", ".css", ".js"}:
            continue
        text = path.read_text(encoding="utf-8")
        for match in url_pattern.finditer(text):
            url = (match.group(1) or match.group(2) or "").strip()
            if url.startswith(("http://", "https://", "//")):
                problems.append(f"外链资源（容器不联网）: {url} @ {path.relative_to(PACKAGE_DIR)}")

    # 禁用 Web API
    for path in PACKAGE_DIR.glob("*.js"):
        text = path.read_text(encoding="utf-8")
        for pattern, label in FORBIDDEN_JS_PATTERNS:
            if re.search(pattern, text):
                problems.append(f"禁用 API「{label}」出现在 {path.name}")

    # 资源引用存在性（所有相对引用都能在包内找到）
    for path in PACKAGE_DIR.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".html", ".css", ".js"}:
            continue
        base = path.parent
        text = path.read_text(encoding="utf-8")
        for match in url_pattern.finditer(text):
            url = (match.group(1) or match.group(2) or "").strip()
            if not url or url.startswith(("data:", "blob:", "#", "http", "//", "var(")):
                continue
            if not (base / url).exists():
                problems.append(f"引用资源缺失: {url} @ {path.relative_to(PACKAGE_DIR)}")

    # 人格算法与主项目源文件一致（三处同步约束的第 4 份拷贝）
    source_persona = SELFIT_STATIC / "selfit-persona.js"
    dist_persona = PACKAGE_DIR / "persona.js"
    if sha256(source_persona) != sha256(dist_persona):
        problems.append("persona.js 与 app/static/selfit/selfit-persona.js 不一致（算法口径漂移）")

    # Chrome 61 CSS 基线（官方 css-compatibility 规范）
    # 硬失败：本项目已约定彻底不用、出现即违规的模式（增强层一律走 grid-gap 物理属性等 61 可解析写法）
    css = (PACKAGE_DIR / "selfit-tool.css").read_text(encoding="utf-8")
    css_hard_fail = [
        (r":has\s*\(|:is\s*\(|:where\s*\(", ":has/:is/:where 选择器（Chrome 88+，无法回退）"),
        (r"margin-inline|margin-block|padding-inline|padding-block", "逻辑属性（Chrome 87+，须用物理属性）"),
        (r"(?<!-)\binset\s*:", "inset 简写（Chrome 87+，须用 top/right/bottom/left）"),
        (r"(?<!-)\bgap\s*:", "gap 属性（grid 用 grid-gap 基线；flex gap Chrome 84+ 须用 margin）"),
        (r":focus-visible", ":focus-visible（Chrome 86+，基线端焦点样式会整条丢失）"),
        (r"\bsvh\b|\blvh\b", "svh/lvh 视口单位（Chrome 108+）"),
        (r"backdrop-filter", "backdrop-filter（本项目约定用实色基线，不用 @supports 增强）"),
        (r"text-wrap\s*:\s*(pretty|balance)", "text-wrap: pretty/balance（Chrome 117+）"),
    ]
    for pattern, label in css_hard_fail:
        for match in re.finditer(pattern, css):
            line_no = css.count("\n", 0, match.start()) + 1
            problems.append(f"CSS「{label}」出现在 selfit-tool.css:{line_no}")

    return problems


def css_enhancement_notes() -> list[str]:
    """增强层提示（不阻断构建）：确认这些 Chrome 61 后特性都包在 @supports 内或双声明回退后。"""
    css = (SRC / "selfit-tool.css").read_text(encoding="utf-8")
    notes: list[str] = []
    for pattern, label in [
        (r"aspect-ratio\s*:", "aspect-ratio"),
        (r"\bdvh\b", "100dvh"),
        (r"scroll-snap-type", "scroll-snap"),
        (r"clamp\s*\(|(?<!-)\bmin\s*\(|(?<!-)\bmax\s*\(", "min()/max()/clamp()"),
        (r"env\s*\(", "env()"),
        (r"overscroll-behavior", "overscroll-behavior"),
    ]:
        count = len(re.findall(pattern, css))
        if count:
            notes.append(f"{label} ×{count}（应位于 @supports 增强/双声明回退中，Chrome 61 静默忽略）")
    return notes


def build() -> int:
    cwebp = shutil.which("cwebp")
    if not cwebp:
        print("错误：未找到 cwebp，请先安装（brew install webp）", file=sys.stderr)
        return 1

    if DIST.exists():
        shutil.rmtree(DIST)
    PACKAGE_DIR.mkdir(parents=True)

    # 1. 源码与算法
    for name in ("index.html", "selfit-tool.css", "selfit-tool.js"):
        shutil.copyfile(SRC / name, PACKAGE_DIR / name)
    shutil.copyfile(SELFIT_STATIC / "selfit-persona.js", PACKAGE_DIR / "persona.js")

    # 2. 模板数据（路径重写）
    templates_size = build_templates_js()

    # 3. 资产
    sizes = build_assets()

    # 4. 合规自检
    problems = compliance_check()
    if problems:
        print("\n合规自检未通过：", file=sys.stderr)
        for problem in problems:
            print(f"  ✗ {problem}", file=sys.stderr)
        return 1

    # 5. 体积报告
    total = sum(p.stat().st_size for p in PACKAGE_DIR.rglob("*") if p.is_file())
    print("构建完成 ✓  合规自检通过 ✓")
    print(f"  templates.js        {templates_size / 1024:8.1f} KB")
    for name, size in sizes.items():
        print(f"  {name:<36} {size / 1024:8.1f} KB")
    print(f"  包总体积（未压缩）    {total / 1024 / 1024:8.1f} MB")

    # 6. zip 产物（官方 zip-artifact-spec：index.html 必须在 zip 根目录，
    #    压缩的是目录内容而非目录本身，解压后顶层直接看到 index.html）
    zip_path = DIST / f"{PACKAGE_NAME}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(PACKAGE_DIR.rglob("*")):
            if path.is_file() and path.name != ".DS_Store":
                zf.write(path, path.relative_to(PACKAGE_DIR))
    # zip 结构自检：根目录必须有 index.html 且不在子目录
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        if "index.html" not in names:
            raise SystemExit("zip 根目录缺少 index.html（容器无法加载）")
        stray = [n for n in names if n.startswith("/") or ".." in n or n.endswith(".DS_Store")]
        if stray:
            raise SystemExit(f"zip 含非法条目: {stray}")
    for note in css_enhancement_notes():
        print(f"  · CSS 增强层提示: {note}")
    print(f"  {zip_path.name:<36} {zip_path.stat().st_size / 1024 / 1024:8.1f} MB")
    print(f"\n产物目录: {PACKAGE_DIR}")
    print(f"上传包:   {zip_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只对现有产物跑合规自检")
    args = parser.parse_args()
    if args.check:
        if not PACKAGE_DIR.exists():
            print("产物不存在，先运行完整构建", file=sys.stderr)
            return 1
        problems = compliance_check()
        if problems:
            print("合规自检未通过：", file=sys.stderr)
            for problem in problems:
                print(f"  ✗ {problem}", file=sys.stderr)
            return 1
        print("合规自检通过 ✓")
        return 0
    return build()


if __name__ == "__main__":
    sys.exit(main())
