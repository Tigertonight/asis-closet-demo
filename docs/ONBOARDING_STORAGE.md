# 测评记录存储

默认 `SELFIT_ONBOARDING_STORE_BACKEND=sqlite`，文件位于 `outputs/selfit_onboarding/sessions.sqlite3`。
SQLite 使用 WAL。`documents` 中每行是一条独立测评、任务、报告、档案、照片索引、分享或幂等记录；`collection` 区分逻辑表，`(collection, doc_id)` 为主键。用户、会话、创建时间、到期时间、状态、分享 token 摘要独立建列和索引；答案和报告内容保留为行内 JSON。

业务通过 `find/select` 查询单条记录或一个用户的记录。兼容管理后台的遍历操作只加载被遍历的集合。保存时比较请求内已读记录的原值，仅对变化的行执行 INSERT/UPDATE/DELETE；UPDATE/DELETE 必须匹配内部 revision，整个业务提交在一个事务中。冲突返回 409，不覆盖其他请求。生成任务抢占同样校验 revision，只有抢占成功的 worker 执行算法。

图片不入库。现有图片文件和对象存储引用保留。测评 ID、报告 ID、用户 ID 和接口响应不变。过期判断仍在访问时生效，物理清理由维护命令执行，不再每次请求扫描全部数据。

## 上线与迁移

先停止旧版本写入，再运行（替换实际目录）：

```
.venv/bin/python scripts/onboarding_store.py migrate --directory outputs/selfit_onboarding
.venv/bin/python scripts/onboarding_store.py check --directory outputs/selfit_onboarding
```

迁移先创建带 SHA256 前缀的 `sessions.json.pre-sqlite-*.bak`，核对备份字节；事务内导入所有集合并核对逐集合数量。损坏数据、重复主键导致整次迁移回滚。原 JSON 不修改。迁移标记保证重启不会再次用旧 JSON 覆盖数据库。已有旧版 SQLite 数据原地补列、补索引，不会被 JSON 覆盖。

应用第一次打开存储也会执行同一幂等迁移；生产建议在启动接流量前运行命令，避免首个用户承担迁移耗时。若环境原来显式配置 `json`，发布时需改为 `sqlite`。不得同时运行 JSON 写入版本与 SQLite 写入版本。

发布仍必须使用项目统一 `scripts/deploy_release.sh`。本次代码改动不等于线上已切换。

## 维护与回滚

低峰执行 `prune`，先用 SQLite backup API 备份，再清理过期草稿和临时记录。登录用户的历史报告、个人档案和原图继续保留；并发更新冲突时整体回滚，重新运行即可。不自动删除数据库备份。

```
.venv/bin/python scripts/onboarding_store.py prune --directory outputs/selfit_onboarding
```

如需回退 JSON：停止写入，执行 `export --output <新的文件路径>` 导出数据库最新数据，核对后才替换 JSON、设置后端并启动。**不能直接切回旧 sessions.json**，否则迁移后的测评会丢失。SQLite 备份使用 backup API；WAL 活跃期间不能只复制 `.sqlite3` 主文件。
