# 报告笔记与真实试穿套装

报告“去试穿”携带 `persona`、`report_template`、`report_notes`、`report_assets`。主站调用 `GET /selfit/try-on/report-outfits`，参数对应 `persona`、`template_id`、`note_ids`、`note_assets`。前端兼容 `imageAssetId`、`assetId` 及旧素材 URL。最多四篇笔记，保持报告顺序，默认选中第一套；后续选择写入 URL 的 `outfit`，刷新后恢复。

## 数据来源

`app/data/styling-delivery.v1.json` 是真实拆款交付清单：20 组、80 套、461 个单品。16 组标准人格与 4 组微胖版本独立绑定，不自动推断用户体型。每套通过 `note_binding.templateId + noteId` 对应报告，原图资产 ID 必须与报告模板一致。旧报告只有 `legacy` 占位符时，按原模板及笔记编号加载当前交付，返回 `resolved_legacy_assets: true`；前端将 URL 改写为真实素材 ID，不展示加载成功提示。已有具体图片 ID 但不匹配时仍返回 409，避免无提示地替换已绑定的素材。

`app/styling_catalog.py` 适配原图、单品图、名称、穿法、开合状态、遮挡关系、关联单品和由内至外的叠穿顺序。套装和单品使用独立的版本化 ID；既有示例内容库和用户衣帽间不受影响。旧的 `report-note-outfits.v1.json` mock 映射已移除，接口固定返回 `mode: live`。

图片地址由 `app/data/material-assets.v1.json` 按素材 ID 解析。交付文件中的 `image_asset.url` 可以是旧值或空值，运行时以素材注册表为准；注册完成后不需要修改前端或重启接口。只接收已注册的公开素材，无法解析时返回 503，绝不替换为示例搭配。

## 图片就绪

本次交付及报告选用素材已上传七牛 `selfit` 私有空间：共 704 张不同图片，包含全部 461 张单品图。素材接口在服务端生成签名，下载并校验后以同源地址提供图片；不会把过期签名写入报告。连接配置、清单说明和复核方式见 [Siri Styling 素材与拆款交付](SELFIT_STYLING_DELIVERY.md)。也可在尚未登记素材的新环境本地导入：

```sh
.venv/bin/python scripts/import_styling_materials.py --source /path/to/拆款交付-siri-styling
```

导入先核对所有缺失单品的 SHA-256，再复制到 `app/static/selfit/assets/styling-delivery/` 并登记素材 ID；保留已有 CDN 绑定，不更改原交付文件。线上发布仍遵循项目部署规则，先提交并推送，再运行服务器发布脚本。

## 试穿请求

点击“试穿这套搭配”直接调用 `/selfit/try-on/jobs`，提交真实 `outfit_id`、全部 `selected_item_ids` 和 `wear_all_items=true`。不展示单品确认弹窗，不把内容库单品加入个人衣帽间。

服务端通过同一套装 ID 读取真实配方。原图作为整套穿法参考，所有单品各自占据参考图的一格；穿法和叠穿数据同时进入生成提示词。整套模式上限为 16 件，覆盖当前最多 14 件的交付。经过交付确认的裙装叠穿长裤配方允许保留；普通自选套装仍保留冲突检查。

线上图片仅从素材注册表下载，核对内容哈希后缓存至 `outputs/material-cache/`。任何原图或单品图读取失败都会明确报错，避免生成缺件套装。实际生成效果仍由试穿模型决定。
