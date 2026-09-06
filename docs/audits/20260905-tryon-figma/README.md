# 试穿环节设计还原与像素自测

已通过 Chrome 浏览器访问用户提供的 Figma 文件，在「视觉+交互」区域定位与截图对应的五张 393 × 852 设计稿，并导出 PNG / SVG。完成了可交互的本地前端和现有服务路由接入，未部署。

## 查看

- [原稿素材模式](http://localhost:8000/static/selfit-tryon/index.html?reference=1&v=8&screen=mirror)：便于与设计稿逐像素比较，使用 Figma 模特及服装素材，试穿弹窗明确标注示例。
- 正式入口 `/selfit/try-on`：读取登录会话、衣橱及灵感数据；现有 `/wearwow/demo` 首页新增试衣镜入口，套装详情携带 outfit ID 跳转。
- 当前共享的 8000 服务未重启，因此先用上方静态预览地址。新增正式路由已通过 FastAPI TestClient 检查，服务重启后生效。
- [五页效果总览](overview.png)。对比图由左到右为：Figma 原稿、浏览器截图、差异热图。

## 像素对比

Chrome 393 × 852、页面顶部、相同素材和选中态。只排除原稿的系统状态栏 y<54 与透明设备圆角；没有排除难还原的服装或装饰。系统状态栏按 DESIGN.md 要求不仿造。

平均绝对误差为 RGB 通道误差均值，范围 0–255，越低越好。阈值内像素指该像素三个通道的最大误差均不超过 16，不是「还原相似度」。

| 页面 | 平均绝对误差 | 阈值内像素 | 证据 |
|---|---:|---:|---|
| 模特试穿 | 2.198 | 96.68% | [对比图](mirror-model-comparison.png) |
| 自由搭配 | 5.636 | 91.84% | [对比图](mirror-styling-comparison.png) |
| 衣帽间 | 3.812 | 89.77% | [对比图](closet-comparison.png) |
| 灵感库 | 4.340 | 93.43% | [对比图](inspiration-comparison.png) |
| 套装详情 | 4.601 | 91.23% | [对比图](detail-comparison.png) |

可运行 `.venv/bin/python scripts/compare_tryon_figma.py` 重新计算。原始数据见 [pixel-metrics.json](pixel-metrics.json)。衣橱误差由 7.055 降到 3.812；灵感库由 11.59 降到 4.34，主要通过原始 SVG 裁切和网格尺寸修正。

## 已验证

- 五页导航、灵感卡片进入详情、收藏取消、自由搭配、上装分类及更换上衣、模特选择弹窗、原稿示例结果入口、横向第四页分页。
- 空分类给出添加衣服入口，未登录状态给出登录入口。
- 393 × 852 五页无横向溢出、图片加载错误；390 / 430px 和桌面 1440px 居中布局已检查。
- 390 × 640 小屏搭配页修复底部遮挡，最终分页底部 537px，导航顶部 546px。原始发现保留在 mirror-responsive-checks.json，修复证据见 small-screen-final.json/png。
- 浏览器控制台最终检查无 error/warn；JS 语法、Python 语法及三条页面路由检查通过。

## 接入范围与未验证项

上传、服装导入、生成前确认、异步任务轮询、结果查看与下载均有前端实现，并按仓库现有接口接线。上传浏览器实测被 Chrome 扩展文件访问权限阻止；未调用付费或真实生图，不能据此宣称真实上传到生成端到端通过。登录用户数据路径亦未进行真实账号写入测试。

五张稿的图像、尺寸和颜色为 SOURCE；跨页跳转、错误恢复与新增弹窗属于基于现有产品接口及按钮含义的 PARTIAL / GUESS，没有把静态导出当作 Figma 原型连线证据。

残余差异包括系统中文字体与 Figma 轮廓文本、拱形区域噪声滤镜、局部 1–2px 边缘与按钮布局。当前是有明确差异记录的还原版本，**不是零像素误差或完整生产验收通过**。

## 文件

- 前端：`app/static/selfit-tryon/`，入口、CSS、JS 和来自 Figma 的分拆素材；控件均为可访问 HTML，不是整页截图点击区。
- 路由：`app/main.py`；旧页面入口：`app/closet.py`。
- 原稿：`source/`；截图：`*-actual.png`；比对脚本：`scripts/compare_tryon_figma.py`。
- [QA 检查](qa-report.md)、[已知差异](known-gaps.md)、[来源事实](claims.json)。

本次未提交、推送、部署，未修改人格分型算法，也未清理工作区其他任务的改动。
