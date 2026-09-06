# QA Report

## Fixed Conditions

- Source: Figma 7WvSROZhohAyvpEMfxZ3Dd，五个目标节点见 target-lock.json。
- Baseline / Project: 同一 HTML/CSS/JS 实现，reference=1 只选择固定数据，正式模式接现有服务。
- Environment: Chrome、393 × 852 主画幅；另测 390 × 640 / 844、430 × 932、1440 × 1000。
- Sample points: 模特、自由搭配、衣橱套装、灵感库、粉色套装详情。

## Source -> Baseline

| Check | Source Evidence | Baseline Evidence | Difference Evidence | Status | Severity | Notes |
|---|---|---|---|---|---|---|
| 五页主样本 | source/*.png/svg | *-actual.png | *-comparison.png | measured with gaps | P3 | 非零误差保留，详见 README |
| 独立控件与状态 | 静态帧按钮与卡片 | 浏览器导航、分类、收藏、分页 | interaction-checks.json | passed within inferred flow | P3 | 连线 GUESS，不是来源事实 |
| 主视觉结构 | 原始 SVG geometry | 分拆图片 + DOM | source/ 与 assets/ | passed | — | 非整页背景截图替代产品 |

## Baseline -> Project

| Check | Baseline Evidence | Project Evidence | Difference Evidence | Status | Severity | Notes |
|---|---|---|---|---|---|---|
| 路由与入口 | 静态预览 | route-checks.json | TestClient | passed | — | 共享服务未重启 |
| 适配与控制台 | 393 主稿 | responsive-checks.json / small-screen-final.json | 浏览器截图 | passed in measured states | — | 小屏导航遮挡已修复 |
| 上传到生成 | 前端接口实现 | 未完整执行 | 扩展禁止文件上传 | blocked | P2 | 不宣称生产 E2E 通过 |

## Truth Audit

| Audit | Status | Evidence | Notes |
|---|---|---|---|
| critical facts labeled | passed | claims.json | SOURCE / PARTIAL / GUESS 分开 |
| leaf vs wiring | passed | claims.json | 图像不是交互连线证据 |
| fitted values remain GUESS | passed | known-gaps.md | 字体、细小布局与响应式拟合 |
| external unknowns | documented | known-gaps.md | 上传权限限制未豁免 |
| known gaps documented | passed | known-gaps.md | 保留 P2 未验证项 |

## DESIGN.md Implementation Self-Test

| 项目 | 状态 |
|---|---|
| 393 × 852 像素审阅 | 已完成，差异保留 |
| 首屏 wine splash / onboarding stepper / 600ms 动画 | 本次不涉及，未改动这些页面 |
| selfit 品牌、无 AS IS、无伪造状态栏 | 通过 |
| CTA 酒红色、圆角、44px 高度 | 通过；详情双按钮依据本次 Figma 使用两列 |
| 上传、生成、恢复提示 | 已实现；文件权限导致上传未实测 |
| 图片优先、试穿为次要 feed 动作 | 通过 |
| 桌面居中手机壳 | 通过，393 × 852 |
| 无溢出、文字重叠、按钮裁切、导航碰撞 | 所测画幅通过，小屏修复证据已保存 |
| 控制台无资源/运行错误 | 最终 error/warn 空数组 |
| 原始装饰素材 | 直接从 Figma SVG/PNG 提取 |

## Failure Routing

| Issue | Category | Return State | Status | Notes |
|---|---|---|---|---|
| 衣橱与灵感图片裁切 | geometry | BASELINE_RUN | repaired | 更新源 SVG 裁切 |
| 小屏导航碰撞 | responsive | PROJECT_VERIFY | repaired | small-screen-final.json |
| 文件上传被拒 | external permission | PROJECT_VERIFY | blocked | 留待扩展权限具备时实测 |
| 字体与噪声 | rasterization | BASELINE_VERIFY | open P3 | 不掩盖像素差异 |

## Final Status

Status: DONE_BASELINE_WITH_GAPS

完成了视觉还原、自测和本地接口接入交付；baselineVerified / projectVerified 均不标为全量通过，因为仍有未豁免的上传生成 P2 验证缺口。此状态不是发布批准。
