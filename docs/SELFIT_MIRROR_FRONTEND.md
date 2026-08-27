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
