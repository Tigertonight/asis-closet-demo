# selfit 智能镜子前端

## 访问

- 本地路由：`/selfit/mirror`
- 设计基准：Figma `🪞 适我`，镜子区块 `450:15057`
- 逻辑画布：`393 × 698`，会按屏幕等比缩放，适配常见 `1080 × 1920` 竖屏大屏。

## 状态链路

`首页 → 摄像头/3-2-1 倒计时 → 拍照确认 → AI 处理中 → 结果与扫码 → 返回首页`

- 摄像头：优先使用 `getUserMedia`，要求 HTTPS 或 localhost。
- 权限失败：进入演示模式，用户仍可走完全流程。
- 隐私：离开页面、页面隐藏或返回首页时立即停止摄像头轨道。
- 防滞留：结果页默认 60 秒自动回首页；可通过配置覆盖。

## 后端接入

Mirro 是现场自助流程，页面访问、拍照分析和二维码生成均免密，不依赖管理员会话。`/mirror/analyze` 仍受全局上传限流、单张 12 MB 体积上限和图片格式校验保护；交接二维码保持短时有效、一次性领取。

页面加载前写入可选配置：

```html
<script>
window.__SELFIT_MIRROR_CONFIG__ = {
  analysisEndpoint: '/api/v1/selfit/mirror/analyze',
  minimumAnalysisMs: 2600,
  idleTimeoutMs: 60000
};
</script>
```

`analysisEndpoint` 接收 `multipart/form-data` 的 `photo` 字段，可选接收上游已生成的 JSON 字符串 `result`。未传 `result` 时后端会执行现有色彩分析，并把结果与照片一起绑定到交接单。返回：

新版 Mirro 会上传同一快门帧的两个版本：

- `original`：未经 Mirro 调色的原图，用于 Suit 和色彩分析。
- `retouched`：使用当前生效配置渲染的调色图，用于 Mirro 确认、相框和模板预览。
- `metadata`：记录调色配置 ID、版本和参数摘要的 JSON 字符串。

旧客户端的单 `photo` 字段继续兼容，服务端会把调色版标记为 `passthrough`。

## 影像调试模式

- 正常模式下 2 秒内连续点击 `selfit` 5 次进入调试模式。
- 调试模式下再次连续点击 5 次退出并回到首页。
- 滑杆修改会立即更新 WebGL 预览，但只有点击「保存并生效」才会写入服务端。
- 未保存退出时恢复服务端当前配置。

配置接口：

```http
GET /api/v1/selfit/mirror/color-grade
PUT /api/v1/selfit/mirror/color-grade
If-Match: <current-version>
```

`PUT` 成功后配置立即生效并递增版本；服务端保留最近 50 份历史快照用于追溯。其他空闲 Mirro 会在回到首页后重新拉取最新配置，不会在用户拍摄途中突然换色。

```json
{
  "handoffId": "mho_xxx",
  "status": "pending",
  "expiresAt": "2026-08-27T12:10:00Z",
  "qrImageUrl": "/api/v1/selfit/mirror/handoffs/<token>/qr",
  "statusUrl": "/api/v1/selfit/mirror/handoffs/<token>"
}
```

二维码指向 `/selfit?handoff=<token>`。手机号登录后调用 `POST /api/v1/selfit/mirror/handoffs/<token>/claim`，交接单将一次性绑定到该手机号对应 UID，创建已完成 `suit` 的 onboarding session，并从 `like` 继续。

生产配置 `SELFIT_PUBLIC_BASE_URL=https://<手机可访问域名>`、`SELFIT_MIRROR_HANDOFF_SECRET` 和 `SELFIT_MIRROR_HANDOFF_TTL_SECONDS`。二维码只包含高熵随机 token；服务端仅保存带 pepper 的 SHA-256 摘要，不把原始照片、手机号、UID 或测试结果放进 URL。默认 10 分钟过期，首次领取后不可被其他用户再次领取。
