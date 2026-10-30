# iOS 图片 URL 编码对照

背景：iOS 能拉起小红书但停在相册。现有唤端 Scheme/Universal Link 已使用 URL 参数编码；官方 SDK 的图片地址通过 JSON 传递，不等同于把图片 URL 拼进另一段 URL。完整 encodeURIComponent 可能被接收端当作无效 URL，因此作为明确启用的对照实验，不改所有用户的默认分享。

在有效领图链接的 `#照片凭证` 之前添加 `?xhs_url_encoding=component`；自动分享入口使用 `?intent=xhs&xhs_url_encoding=component`。保留原片段凭证，不写入日志。

- 仅当后端返回 `official-sdk`（当前 iPhone/iPad 路径）时启用。
- 交给 `xhs.share()` 的 `shareInfo.images` 执行一次 `encodeURIComponent`。
- 预览图片、原图下载、鉴权签名、遥测请求仍使用原 URL。
- 每次重试从原 URL 编码一次，不累积编码；Android prepared-link 路径保持原状。
- `xhs_share_client` 日志新增 `image_url_encoding: raw | component`，与匿名 `client_id` / `photo_ref` 对照。无完整图片 URL、签名或分享凭证。
- 本地 JS/服务端测试验证参数和日志，是否导入图片仍需真实 iPhone 验证，不将 SDK 返回视为导入或发布成功。
