# 直播商品信息收集

独立填写页：`/selfit/product-collection`，不要求主站用户登录。独立后台入口：`/product-collection-admin`，使用专属管理密码；无主站品牌标识。原管理后台的商品页和 `/admin/api/product-collection*` 接口已移除。

字段来自「小红书特产之夜-直播商品信息收集」原表及用户提供的表头/填写说明，原表链接：
https://docs.xiaohongshu.com/sheet/f8c80ec24c4519a94dfca58164380022

## 填写与数据

- 原表 22 列全部保留；页面分为商品信息、价格库存、商品素材、上架检查四步。
- 所有项目均为必填，包括商品卖点的 10 个子项；每项显示灰色小字“如不适用，可填写‘不适用’”。金额、数量、链接支持明确填写“不适用”；上架/价格校验必须选择是、否或不适用，不再默认待确认。
- 图片必须上传，或明确勾选“不适用”。`image_not_applicable` 为布尔值，与上传图片互斥，后台和 Excel 会显示“不适用”。已有历史记录原样保留，旧空值仍按原口径显示，不强制补填。
- 商品卖点包含 10 个独立输入项，导出时按原表说明合并到“商品卖点”列。尺寸保留服饰、首饰、家居、食品四类提示。
- 商品 ID 和联系方式按字符串保存；适用金额最多两位小数，适用库存/抽奖数量为非负整数；适用链接只接受 http/https，无服务端抓取。
- 白底图限一张 JPG/PNG/WebP、20MB、4000 万像素，保留原始字节。小图用于后台预览及 Excel 嵌图；图片解码复用受限图片线程池。
- 每次提交使用随机 UUID 幂等键：网络重试不会重复入库，相同键不同内容返回冲突。
- 未引入额外埋点，不记录表单正文/联系方式到日志，不自动保存个人信息到浏览器存储。

数据库位于 `outputs/product_collection/products.sqlite3`，SQLite WAL；`products` 每条一行（单条表单 JSON），`product_images` 单独存放原图、缩略图及类型。一笔事务保存表单和图片。无需生产数据库手工迁移，首次调用自动建表。

此目录不通过静态路径开放。列表、详情、图片、Excel 导出位于 `/product-collection-admin/api/products*`，均验证独立后台身份；原后台登录态不授予此权限，新后台密码也无法进入原管理后台。普通用户没有查询他人提交的接口。

## 后台与导出

- 累计总数、北京时间今日新增、品牌/商品/品类搜索。
- 按编号倒序游标分页，每次 25 条；新增不会导致加载更多重复。
- 查看完整详情、轻量图片预览、下载原图。
- 列表和详情支持管理员单条删除，二次确认明确显示品牌、商品名称和编号。删除后刷新统计/列表，详情、原图、预览、搜索和 Excel 均排除该记录。
- `DELETE /product-collection-admin/api/products/{id}` 只接受独立后台登录态，并检查请求来源。重复删除幂等；旧提交请求重试不会恢复已删除记录。
- 删除使用同库 `product_deletions` 表记录编号和时间；原数据和图片保留以便运维误删恢复，页面无自行恢复入口。首次使用自动建表，不改动已有商品记录；导出已经开始时使用其开始时的数据快照。
- 导出当前筛选结果为真正的 `.xlsx`，保留原表 22 列，另加北京时间提交时间、记录编号；包含商品缩略图。
- 金额/数量为数字；商品 ID/联系电话等为文本，避免长数字丢失和公式注入。
- 工作表采用流式写入，导出任务单并发，结果超过 4MB 落临时文件；单次最多 5000 条，超过时提示先筛选，不静默截断。
- 新增依赖 `openpyxl==3.1.5`，部署脚本会按 requirements.txt 同步。

## 独立后台密码与登录

- 密码通过 `scripts/configure_product_collection_admin.py` 生成，24 位随机字符，无默认生产密码。
- 密码独立存储于 `outputs/product_collection/admin.sqlite3`，使用独立盐值和 scrypt 哈希；会话只存随机 token 的 SHA-256，不保存密码明文。
- Cookie 仅在 `/product-collection-admin` 路径使用，HttpOnly + SameSite=Strict，HTTPS 下启用 Secure。固定 24 小时过期；退出立即吊销；更换密码会吊销此后台的全部会话。
- 登录单独限流，每 IP 每小时 20 次；密码计算最多并发两次。未配置密码时拒绝登录，不回退主站密码。
- 主站管理员密码、用户账号和邀请码不变；已收集的商品数据库保持原路径，不迁移、不清空。
- 首次配置：`.venv/bin/python scripts/configure_product_collection_admin.py`。仅输出凭证交付文件路径；文件在 Git 忽略的 `outputs/credentials/product-collection-admin.txt`，权限 0600。应用登录只读取哈希库。
- 后续换密：增加 `--rotate --output <新的私密交付文件路径>`。现有凭证文件不会被覆盖。
- 发布时仅把已生成的盐值/哈希以受限权限写入服务器独立鉴权库（或在服务器运行配置脚本并交付新密码）；不得提交明文密码或用本地商品数据覆盖服务器。

## 本地验收

`.venv/bin/python -m pytest tests/test_product_collection.py tests/test_product_collection_admin.py -q`

`.venv/bin/python tests/support/run_product_collection.py --port 8794` 启动隔离验收服务，表单、API 和独立后台鉴权均为真实实现，数据存放在临时目录。默认仅供本机测试的密码为 `collection-local-qa-only`；可用 `--password-file` 指定本地私密凭证文件。验收服务不会加载生产账号或生产数据。
