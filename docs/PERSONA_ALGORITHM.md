# Selfit 人格分型算法：口径、变更流程与展示同步

这份文档给所有会改分型算法的人（或 AI）看。核心原则一句话：

> **分型算法有三份实现必须永远同步：后端 `app/selfit_persona.py`、前端移植版 `app/static/selfit/selfit-persona.js`、管理后台「人格匹配」展示。改任何一处都必须三处一起改、一起测、一起发布。**

## 当前算法口径（v1.1-cross-side）

### 输入 → 7 维向量

| 维度 | 取值来源 | 换算 |
|---|---|---|
| 廓形 silhouette | LIKE 滑杆「硬朗锐利 ↔ 柔和温柔」 | **反向**：`silhouette = 100 - shape`（算法坐标 0=柔和、100=硬朗） |
| 繁简 complexity | LIKE 滑杆「简约 ↔ 繁复」 | 直通 |
| 时间 time_orientation | LIKE 滑杆「经典 ↔ 先锋」 | 直通 |
| 饱和度 saturation | 偏好色板六选一 | 查表 `PALETTE_SIGNALS` |
| 冷暖 temperature | 偏好色板六选一 | 查表 `PALETTE_SIGNALS` |
| 完成度 completion | VIBE「出门场合」题 | A/B/C/D → 10/40/70/95 |
| 个性 individuality | VIBE「衣橱状态」题 | A/B/C → 20/55/90 |
| 地域 regional_style | VIBE「表达欲」题 | 日/韩/欧美/中/法 + 轻亚推导 |

SUITE（肤色/脸型/身型照片识别）**不参与**人格分型，只影响穿搭推荐。

### 距离与分型

- 对 16 型各算加权绝对距离：`Σ wᵢ·|userᵢ - centerᵢ|`
- 权重：该人格核心辨识维度 ×1.5，其余 ×1.0
- **跨侧冲突（v1.1 新增）**：某维度 `|Δ| > 50`（用户与人格中心分处量表两端）时一律按 ×1.5 计，不论是否核心维度。核心维度权重表达的是「区分相近人格」的分辨率，不能让明显跨侧冲突被轻判（修复「调硬朗反而变奶油治愈」缺陷）
- 地域罚分：答对主风格区 0 / 兼容区 +5 / 不匹配 +15；人格主风格为「无倾向」或用户未答不计
- 距离最近为主人格，次近为次人格；置信度 = (次距离-主距离)/次距离，≥0.20 高 / ≥0.10 中 / 其余低

### 算法版本

`ALGORITHM_VERSION`（当前 `v1.1-cross-side`）出现在：

- `/health` 返回的 `release` 指纹里——**线上排查「结果不对」先看这个**，确认服务器跑的算法版本
- 管理后台「人格匹配」区块顶部

## 变更流程（每次改算法必须走完）

1. **后端**：改 `app/selfit_persona.py`（中心点/权重/阈值/换算任一改动都算），`ALGORITHM_VERSION` 递增并在提交信息里写清变更内容与动机
2. **前端移植版**：同步改 `app/static/selfit/selfit-persona.js`——对拍测试 `tests/test_selfit_persona.py::test_frontend_mock_persona_matches_backend` 会拦不同步
3. **管理后台展示**：检查 `persona_breakdown()` 的输出结构与 `app/static/admin/index.html` 的「人格匹配」渲染是否仍与新口径匹配（新增维度/权重规则时展示层要同步加列/加标记，例如 v1.1 加的「跨侧」标记）
4. **测试**：`pytest tests/test_selfit_persona.py` 全过；涉及边界阈值的改动补回归用例（参考 `test_hardening_silhouette_never_lands_on_soft_persona`）
5. **发布**：走 `scripts/deploy_release.sh`（见下），发布后用 `/health` 核对版本指纹

## 部署规范（事故后定版）

**2026-08-28 事故复盘**：内测当晚两方并行部署，一方用 `rsync --delete -o -g -t` 把本地工作目录镜像覆盖服务器，把另一方 16 秒前部署的算法修复回滚成旧版（且服务器无 git，无人能发现），引发「同答案不同人格」的用户反馈。

规则：

1. **服务器发布只允许 `scripts/deploy_release.sh`**（从 git 发布：校验 → 备份 → reset --hard → 测试 → 重启 → 健康检查，失败自动回滚）
2. **禁止任何形式的镜像覆盖**：`rsync --delete`、`tar` 整目录解压、手工 scp 单文件到服务器——这些都会把服务器变成无人知晓的混合状态
3. **先 push 后部署**：本地改动必须先 commit+push，服务器只发布 git 里的提交；本地没 push 的代码永远不应该出现在服务器上
4. **代码 = git，数据 = 服务器目录**：`outputs/`（用户数据）、`.env.demo`（密钥）、`.venv` 留在服务器不进 git；其余一切（含 `app/models`、`qa_photos` 素材）都在 git 里
5. **发布后核对 `/health`**：`release` 字段的 `git:<commit> persona:<版本>` 必须与预期一致，不一致说明被别的部署覆盖了
6. 并行操作服务器前先在群里打招呼（两方同时部署 = 事故温床）

## 相关入口

- 算法实现：`app/selfit_persona.py`（后端唯一真相）、`app/static/selfit/selfit-persona.js`（前端 mock 移植版）
- 匹配过程展示：管理后台 → 用户提交 → 详情 → 「人格匹配」区块；API `GET /admin/api/submissions/{id}/persona-breakdown`
- 对拍测试：`tests/test_selfit_persona.py::test_frontend_mock_persona_matches_backend`
- 部署：`scripts/deploy_release.sh`、`deploy/setup_server.sh`（首次初始化）
