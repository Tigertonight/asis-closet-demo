# selfit 试穿素材审核

独立 Cowork FastAPI 应用，用于审核 80 套穿搭与 3 位女模特的 240 个结果位置。包含 239 张已生成图片，其中 3 张为提示词调整版；1 个位置缺图。37 张自动质量检查未通过的图片同样保留供人工审核。

页面展示原穿搭照片、三位模特原图及各自结果。支持主题/审核状态搜索、三种人工结论、备注、放大对照、下一套待审核及导出完整审核记录。结论按「示例 ID + 图片 SHA-256」存储，刷新链接不会丢失审核记录，换图不会继承旧图结论。并发保存使用版本校验，旧版本不能覆盖其他人的审核。

## Cowork 部署与验收

- 审核页：https://cowork.xiaohongshu.com/s/8555be63/
- 作品管理：https://cowork.xiaohongshu.com/app/NWEzNjQ1MGQ
- 2026-09-10 已部署至原作品 V4（应用 1.1.0），仅自己可见。
- 已验证：80 套 / 240 个位置加载，SSO 身份显示，备注写入 PostgreSQL 后刷新仍保留。验收备注已清空，所有结论保持待审核；修改历史保留两次验收操作。
- V4 直连实测：首套三张 HTTPS 模特原图均加载成功；七牛 HTTP 原穿搭与三张试穿结果加载失败。HTML 已直接引用原 URL，不再经过转发。完整图片可用性与 393px 手机布局仍待验证。

## 图片与数据

- 不上传任何原图或结果图，不打包图片，不部署七牛 AK/SK。
- `seeds/catalog.json` 为只读发布快照，包含临时签名 URL，已加入忽略规则。
- 三张模特原图使用已存在的 `https://selfit.com.cn/tryon-models/` 图片；已逐张核对 SHA-256 与批次输入一致。
- 图片由 HTML 的 `img src` 直接引用素材清单中的现有 URL，后端只返回清单并处理审核记录。原图、结果图、缩略图和放大图均不经过 Cowork 转发；已移除图片转发与诊断接口。图片重试保留原始签名参数，设置 `referrerpolicy="no-referrer"`。
- 2026-09-10 只读查询七牛空间域名，只有 `tk7xxzqgj.hd-bkt.clouddn.com`。该域名的现有链接为 HTTP；HTTPS 页面中的自动升级 / 混合内容策略可能阻止它加载。要在正常 HTTPS 浏览器中稳定直连，需要为同一空间提供可用的 HTTPS 访问域名后重新签名，不需要重新上传图片。
- 审核结果、审核人及修改历史保存于 Cowork 注入的 PostgreSQL。所有业务接口要求 SSO；没有匿名或本地绕过开关。

## 刷新临时链接与发布

在主仓库根目录运行：

```sh
.venv/bin/python scripts/export_tryon_review_catalog.py
```

默认有效期 7 天。只签名已有图片，不产生上传操作。该文件不提交 git。发布前将本目录内容同步至 Cowork 官方 scaffold 生成的主项目目录：`~/.openclaw/workspace/cowork/selfit-tryon-review/`，保留该目录的 `.cowork.json`；使用 cowork-publish 工具 pack/publish，后续只更新原作品。

`install.sh`、`start.sh`、`health.sh` 均来自官方 scaffold。数据库使用 lifespan 幂等初始化。平台负责注入 `db.properties`，不得将此文件写入代码包。
