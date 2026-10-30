# iOS 图片 URL 编码分享

背景：iOS 能拉起小红书但停在相册。唤端 Scheme/Universal Link 原本已使用 URL 参数编码；本次调整针对交给官方 SDK 的图片地址。2026-10-30 用户确认 `encodeURIComponent` 对照链接验证通过，按用户要求将此方式设为 iOS 正式默认。

普通领图页点击分享和 `?intent=xhs` 扫码自动分享均默认启用，无需更换现场二维码或添加测试参数。原 `xhs_url_encoding=component` 测试链接继续兼容；排障时可在有效领图链接的 `#照片凭证` 之前添加 `?xhs_url_encoding=raw`（自动分享使用 `?intent=xhs&xhs_url_encoding=raw`）对照原始 URL。保留原片段凭证，不写入日志。

- 仅当后端返回 `official-sdk`（当前 iPhone/iPad 路径）时启用。
- 交给 `xhs.share()` 的 `shareInfo.images` 执行一次 `encodeURIComponent`。
- 预览图片、原图下载、鉴权签名、遥测请求仍使用原 URL。
- 每次重试从原 URL 编码一次，不累积编码；Android prepared-link 路径保持原状。
- `xhs_share_client` 日志新增 `image_url_encoding: raw | component`，与匿名 `client_id` / `photo_ref` 对照。无完整图片 URL、签名或分享凭证。
- 本地 JS 测试覆盖正常扫码、手动分享、显式 raw 对照、Android 路径及重复点击不重复编码。用户已提供手机验收结果；SDK 返回仍不作为导入或发布成功的凭据。
