# Known Gaps

## gap-visual
Status: open
Severity: P3
Truth: PARTIAL
Description: 字体栅格、SVG 噪声、局部边缘尚有差异，不是零像素误差。
Evidence: pixel-metrics.json 和五张 comparison.png。
Impact: 不影响已测导航和选择，但不能称像素完全一致。
Would close with: 获取同款可用字体、进一步对齐滤镜及局部尺寸并重新截图。
Accepted by: 未获用户豁免；保留为交付限制。

## gap-upload-generation
Status: external-blocker / not verified
Severity: P2
Truth: PARTIAL
Description: Chrome 扩展拒绝文件 chooser 上传（-32000 Not allowed）；真实登录上传、导入、试穿生成、结果下载未端到端执行。
Evidence: 本次浏览器工具错误记录；JS 实现仅能证明接线，不能证明真实服务成功。
Impact: 项目完整验收不能判定通过，生产发布不在本次范围。
Would close with: Chrome ChatGPT 扩展开启 Allow access to file URLs 后使用测试账号跑上传和生成。
Accepted by: 未豁免。

## gap-prototype-wiring
Status: documented inference
Severity: P3
Truth: GUESS
Description: 已拿到五张视觉稿，未获得原型交互连线；导航、弹窗和恢复流程根据语义及现有 API 实现。
Evidence: source/*.svg 是静态帧导出。
Impact: 视觉已可对照，不能声称每个交互都来自 Figma 原型。
Would close with: 原型连接或产品交互规范。
Accepted by: 未豁免；实现选择已明确标记。
