# selfit 试衣镜

入口 `/selfit/try-on`。无构建依赖，静态 HTML/CSS/JS，由 FastAPI 返回入口页。

`?reference=1` 为显式 Figma 固定素材验收模式；默认模式读取现有 selfit 登录会话与接口。不会将原稿示例伪装为真实生成结果。可用 `screen=mirror|closet|inspiration|detail`、`mode=styling` 定位画面。

来源与 QA：`docs/audits/20260905-tryon-figma/README.md`。素材全部从用户指定 Figma 的五个节点导出；背景 SVG 只包含纹理和装饰，模型、单品、列表、导航、弹窗均分别渲染。保留 PNG/SVG 原稿用于验证。SVG 图片用 lossless WebP 编码压缩；图片资源不是外站运行时依赖。

正式流程通过已有 /closet 和 /selfit/try-on 接口加载单品、保存搭配、预检并创建生成任务。真实库单品保存、上传、照片恢复、预检、实际生成和浏览器结果回显已验收，见 `docs/audits/20260905-tryon-live/README.md`。内置浏览器下载事件未确认。
