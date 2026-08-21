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
  qrImageUrl: '/api/v1/selfit/mirror/demo-report-qr',
  minimumAnalysisMs: 2600,
  idleTimeoutMs: 60000
};
</script>
```

`analysisEndpoint` 接收 `multipart/form-data` 的 `photo` 字段。镜子端只承载拍照、确认和扫码交接，肤色与穿搭详情在手机报告中展开；建议返回：

```json
{
  "reportId": "rpt_xxx",
  "qrImageUrl": "/api/v1/selfit/mirror/reports/rpt_xxx/qr"
}
```

生产环境应让二维码指向一次性报告 token，并设置短有效期；不要把原始照片或用户信息放进二维码 URL。
