# selfit 小红书小工具（风格人格测试 · 引流版）

把主项目 onboarding 的十六型人格测试剥离成一个**完全离线、自包含**的小红书小工具包，
读者在笔记里点开即测，测完通过报告页二维码 / 分享卡片 / postNote 文案引流回 selfit 完整版。

## 产物结构

```
dist/selfit-xhs-minitool/
  index.html        唯一入口（无内联脚本 / 行内事件 / javascript: URI）
  selfit-tool.css   外置样式
  selfit-tool.js    业务逻辑（本地分型 / 报告渲染 / Canvas 卡片导出 / miniTool API）
  persona.js        十六型算法（构建时从 app/static/selfit/selfit-persona.js 复制并 hash 校验）
  templates.js      16 型报告模板（从 v1.json 生成，图片路径重写为包内相对路径，剔除站外链接）
  assets/           全部图片（cwebp 压缩，无任何外链）
```

## 构建与自检

```bash
brew install webp          # 依赖 cwebp
python3 xiaohongshu-tool/build.py           # 构建 dist/ 并打 zip
python3 xiaohongshu-tool/build.py --check   # 只对现有产物跑合规自检
```

合规自检覆盖（对应官方小工具容器约束）：

- 恰好一个 `index.html`；文件类型白名单（html/css/js/图片/woff/woff2/json）
- **zip 根目录必须是 `index.html`**（官方 zip-artifact-spec：压缩目录内容而非目录本身，解压后顶层直接见 index.html）
- 无内联 `<script>`、行内 `on*=` 事件、`javascript:` URI
- 无外链资源（html/css/js 全量扫描 `http(s)://` 与 `//`）
- 无禁用 API：fetch / XHR / WebSocket / eval / new Function / WebAssembly / Worker /
  剪贴板 / window.open / 全屏 / 地理定位等
- **JS 语法基线 ES2017 / Chrome 61**（官方 js-compatibility）：禁可选链、空值合并、
  `Object.hasOwn`、`Object.fromEntries`、`replaceChildren`、`toggleAttribute` 等
  Chrome 61 之后的语法与 API（解析阶段失败 = 页面渲染但 JS 全不执行）
- **CSS Chrome 61 基线**：禁 `:has/:is/:where`、逻辑属性、`inset`、`gap`（grid 用
  `grid-gap`、flex 用 margin）、`:focus-visible`、`svh/lvh`、`backdrop-filter`；
  增强层（`aspect-ratio`/`100dvh`/`scroll-snap`/`min()/max()/clamp()`/`env()`）
  必须包 `@supports` 或双声明回退（构建时输出提示清单人工确认）
- 所有相对引用的资源在包内真实存在
- `persona.js` 与主项目源文件 hash 一致（防算法口径漂移）

## 官方 skill 合规校验（minitool-zip-builder）

官方提供 skill 做产物审计（体积门禁等），构建后建议再跑一遍：

```bash
curl -sL -o /tmp/minitool-zip-builder.skill \
  "https://fe-static.xhscdn.com/mini-tool/20260831163932/minitool-zip-builder-1.6.0.skill"
unzip -o /tmp/minitool-zip-builder.skill -d /tmp/minitool-skill
python3 /tmp/minitool-skill/minitool-zip-builder/scripts/audit_artifact.py \
  xiaohongshu-tool/dist/selfit-xhs-minitool        # 审计目录
python3 /tmp/minitool-skill/minitool-zip-builder/scripts/audit_artifact.py \
  xiaohongshu-tool/dist/selfit-xhs-minitool.zip    # 审计 zip
```

当前状态：目录 PASS（0 warning）；zip PASS + 1 WARN（7.8MiB > 2MiB 建议值，
低于 10MiB 上限——16 型人格图片资产 7.2MB 是核心内容，属可接受项）。

## 上传素材

| 项 | 值 |
| --- | --- |
| 名称 | selfit 风格人格测试 |
| 简介 | 3 分钟测出你是 16 种风格人格中的哪一种，生成专属风格报告与分享卡片 |
| 图标 | `xiaohongshu-tool/app-icon.png`（1024×1024 PNG，酒红底白色字标） |
| 产物包 | `xiaohongshu-tool/dist/selfit-xhs-minitool.zip` |

## 发布步骤（首次）

1. PC 端登录小红书创作者服务中心 → Builder Hub → 小工具
2. 新建：填名称 / 简介 / 图标
3. 上传 `dist/selfit-xhs-minitool.zip`，完成配置后提交审核
4. 审核通过后，App 端发布笔记时在编辑页挂载「小工具」组件

版本更新：改 `src/` 后重新 build，上传新 zip，在同一管理面板发版。

## 本地预览与调试

```bash
cd xiaohongshu-tool/dist/selfit-xhs-minitool && python3 -m http.server 8765
```

- 浏览器打开 http://localhost:8765 走完整流程（保存/发笔记自动降级为预览模式）
- 直接预览任意阶段：`?preview=splash|intro|suit-manual|like|vibe|loading`
- 预览任意人格报告：`?preview=report&type=mute`（16 型 typeId 任选）

## 容器能力集成（window.xhs.miniTool）

容器自动注入 `window.xhs.miniTool`，无需引 SDK；调用前一律判空降级：

| 用途 | API | 降级（浏览器预览时） |
| --- | --- | --- |
| 保存分享卡片 | `writeTempFile`（完整 data:uri）→ `saveImageToPhotosAlbum` | 全屏预览 + 引导截图；writeTempFile 失败时直接传 base64 |
| 发笔记引流 | `postNote`（`pageType: 'photo_publish'`，`image_resources[].url` 传 base64 data:uri——官方 jsbridge 规范只认 data:uri/网络地址，不认本地临时路径） | toast 提示「在小红书笔记里打开即可一键发笔记」 |

## 引流设计（沙箱禁跳站外链接，全部走内容承载）

- 报告页 CTA 区：selfit 群聊二维码 + 「扫码加入 selfit 群聊」引导
- 3 张分享卡片 footer 均带 selfit wordmark + 群聊二维码
- postNote 预填文案含「16 种风格人格，来测测你是哪一种 →」

## 维护约束

- **改人格算法口径**：后端 `app/selfit_persona.py`、前端 `selfit-persona.js`、管理后台
  三处同步规则不变（见 `docs/PERSONA_ALGORITHM.md`）；小工具的 `persona.js` 是构建时
  自动复制的第 4 份拷贝，**不要手改 dist/**，改完主项目重新 build 即可（hash 校验会拦漂移）。
  注意 `selfit-persona.js` 现遵守 ES2017/Chrome 61 语法基线（小工具容器要求），
  改动时不要引入可选链、`Object.hasOwn`、`Object.fromEntries` 等新语法，
  改完必须跑 `tests/test_selfit_persona.py`（含前后端对拍）
- **改报告模板**：源头是 `app/static/selfit/data/personality-report-templates.v1.json`，
  改完重新 build；`templates.js` 会剔除 `sourceUrl` 与色卡大图，避免站外数据进包
- **新增 UI 资产**：在 `build.py` 的 `UI_ASSETS` / `MANUAL_*` / `PERSONALITY_RECIPE`
  登记源文件与压缩参数，勿直接往 dist 拖文件
- **改 `src/` 前端代码**：JS 保持 ES2017 语法基线（无构建链，不引 Babel）；
  CSS 新特性必须「61 基线声明在前 + 增强层在后」，flex 间距用 margin 不用 gap
