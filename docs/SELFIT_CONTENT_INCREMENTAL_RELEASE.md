# Selfit 已审核资产增量发布

增量发布用于让已完成设计审核和图片 QA 的 V2 资产及时进入 App，不需等待 600 件单品和 1,200 套穿搭全部完成。完整 V2 发布门槛保持不变。

## 发布命令

```bash
.venv/bin/python scripts/publish_selfit_content_pool_incremental.py
```

命令生成 `app/static/selfit/data/content-pool.v2.incremental.json`。产物由两部分组成：

- 已迁移的 V1 穿搭作为稳定推荐基线。
- 生产清单中已审核的 V2 单品，以及所有单品引用都已通过的设计师审核穿搭。

每次发布都会校验原创版权状态、生产 QA、透明 PNG、安全留白、成图存在性、引用完整性和 V2 JSON Schema。任一错误都会阻止生成新产物。

## App 读取顺序

`SELFIT_CONTENT_POOL_VERSION=auto` 是默认模式：

1. 完整 V2 已发布池（满足 600/1,200 硬门槛）。
2. 通过清单校验的 V2 增量池。
3. V1 稳定池。

可用 `v1` 强制回退，用 `v2-full` 只接受完整 V2，用 `v2-incremental` 或 `incremental` 只接受增量 V2。

增量穿搭会进入主 App 首页推荐和试穿详情，不会混入用户的私人衣橱清单。推荐层对主人格和兼容人格分别加权。
