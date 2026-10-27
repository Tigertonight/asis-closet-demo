# WOKEN DAY 周年邮票照相馆

独立入口 `/selfit/stamp`（亦支持尾斜线）；手机领取页 `/selfit/photo#<photoId>.<secret>`。
保留原有 `/selfit/mirror` 和试穿功能。2026-10-24 根据用户提供的「邮票框最终版」和
「woken-day-stamp-minitool-v56改logo」实现，原始设计与滤镜逻辑位于 `app/static/selfit/stamp/`。

## 设计与操作

本活动页按用户明确选择的 WOKEN DAY 蓝色实体照相馆素材执行，是 DESIGN.md 的品牌活动例外，
不将主站的酒红/浅粉配色覆盖到周年素材上。原有主站设计不变。

流程：掀帘进入 → 选择周年年份 → 相机六秒倒计时拍摄 / 相册导入 → 调整质感、配色、底色、
缩放和位置 → 压印出片 → 扫码领取。三种质感为纯色、网点和印刷；十款周年框对应
2016–2017 到 2025–2026。双指或拖动调整、撤销、声音开关沿用原包。

只输出邮票成片 900×1200 PNG，和原始邮票框分辨率一致；服务器生成
720×960 WebP 供后台等缩略预览；手机领取页展示高清 PNG，确保原图链接可供浏览器原生保存。
相机以取景框裁切，导入照片最长边规范到 1400px，
后台“拍摄原图”是这份未加滤镜的规范化 JPEG，并非相机传感器原始文件。
相册导入支持最多 6400 万像素、32MiB 的原始照片，导入时显示处理提示，超限或无法解码时
提供返回/换张照片入口；解码等待最多 30 秒。缩图后释放大图资源，不将大图以 base64 再复制一份。
这仅放宽浏览器选图上限；服务器仍按下述 12MiB/1600 万像素限制接收规范化图片。

出片即后台保存。保存失败保留本机照片，支持重试；响应丢失复用同一凭证，不重复创建记录。
再做一枚会清空上一位照片；非处理状态下 120 秒无操作自动回到入口，关闭相机与领取弹窗。
手机只展示和保存邮票，支持文件分享的浏览器提供单张邮票的系统分享按钮。不依赖小红书 JS Key，
也不冒充已发布笔记；可在系统分享中选小红书，或保存后自行发布。
普通浏览器的“保存高清邮票”在点击时直接请求同域 PNG 附件地址，不再等待 JS 下载为 Blob。
微信（MicroMessenger）显示“查看高清原图”，点击后在页内查看层展示同一张高清 PNG，
提示长按保存到相册，不发起附件下载；下方原图入口也走这一流程。查看层支持关闭、加载失败重试
和签名链接到期刷新。长按仍由微信原生菜单处理，页面不宣称已经写入相册。

新流程不再合成、上传或分享出片机展示图；旧领取链接也只展示邮票。历史展示图保留供后台查看。
成片页“打印照片”使用本机已生成的 900×1200 PNG，调用网页运行电脑的浏览器打印窗口；
在窗口中选择本机可用打印机、纸张和份数，确认后由系统打印。无需上传完成或新增打印服务。
独立打印文档只包含完整邮票，固定为竖版 6 寸（4×6 英寸 / 101.6×152.4mm），零页边距，
等比居中，不裁切、不带网页按钮或出片机背景。900×1200 成片是 3:4，纸张是 2:3，
完整保留成片时上下各有约 8.47mm 留白；不能通过拉伸或裁切邮票来铺满纸张。
打印准备及打印窗口打开期间暂停自动重置，关闭或取消后可再次打印；页面不推断实体打印是否成功。
普通浏览器需要在打印窗口确认；现场专用启动方式可开启静默打印，仍需安装打印机驱动和正确耗材。
现场 Windows 的 DS620 配置包位于 `deploy/ds620-windows/`。网页的 `window.print()` 不能指定打印机名称；
需在运行网页的电脑上设置当前用户的默认打印机和驱动纸张。脚本读取 DS620 驱动实际支持的纸张、
校验 4×6 后再写入当前用户打印首选项；不安装驱动、不生成打印作业。
`start-stamp.cmd` 固定 DS620、6 寸、1 份，配置并验证后，以独立用户目录启动 Chrome 照相馆窗口，
使用 `--kiosk-printing --use-system-default-printer` 免预览确认打印。不修改整机浏览器策略；
已有专用窗口时阻止重复启动。实际目标仍为 Windows 默认打印机，活动期间不能更换默认值；需实物验收。
直接从普通浏览器打开时，首次仍需在打印窗口选择 DS620，确认 4×6、纵向、每张 1 页和无页眉页脚。
摄像头需 HTTPS（localhost 调试例外）及设备授权。现场需使用实际智能镜/外接摄像头验收。

## 存储、权限与运行

- `POST /api/v1/selfit/mirror/photos`：multipart 原图、邮票、设置（兼容旧客户端可选的展示图）；64 位随机十六进制
  `Idempotency-Key` 同时作为领取凭证。原图/各成片最多 12MB、图片最多 1600 万像素。
- `GET /api/v1/selfit/mirror/photos/{id}/{info|qr|preview|download|scene-preview|scene-download}`：
  Bearer 凭证鉴权并检查有效期。原图不向手机领取接口提供。
- 凭证只在 URL fragment 和 Authorization 头中使用，数据库存 SHA-256；响应禁止缓存，
  领取页面禁止 referrer。不要将领取链接复制进业务日志。
- `info` 另返回成片专用签名链接，最长 10 分钟且不超过照片领取期限。`files/{print.png|scene.png}`
  以签名鉴权，无需原生下载器携带 Bearer 头；签名绑定照片、文件、期限和 inline/attachment 用途。
  不暴露拍摄原图或主领取凭证。应用访问日志移除该接口查询参数；代理访问日志也不得记录签名参数。
  页面可见时到期前自动更新；过期点击先刷新链接，提示再次点击以保留浏览器用户手势。
- SQLite WAL：`outputs/selfit_mirror_photos/photos.sqlite3`；私有图片：同目录 `assets/`。
  强制使用本地文件存储，不受项目七牛/OSS 配置影响，不挂公开静态目录。
- 图片验证和 WebP 生成使用现有受限 `photo_work` 池；POST 限流沿用上传额度，GET 单独限流。
- 管理后台「镜子拍摄」可查看/下载规范化原图、邮票成片及展示图，沿用管理员鉴权。
- `SELFIT_MIRROR_PHOTO_TTL_SECONDS` 默认 86400，可设 300–604800。
  **链接过期不删除文件**；后台仍可读取，沿用项目“素材留存、不自动删除”原则。
  运维需监控磁盘、备份此输出目录；后台删除仅隐藏条目。
- `SELFIT_PUBLIC_BASE_URL` 可指定领取域名，未配置时使用代理传入的请求域名。
  当前 Caddy 允许 48MB 请求，兼容旧客户端三张图的总上限。

## 验证与发布

```sh
.venv/bin/python -m pytest tests/test_selfit_mirror_photos.py tests/test_selfit_admin_submissions.py tests/test_selfit_persona.py tests/test_selfit_photo_wiring.py -q
node --test tests/test_stamp_delivery.cjs tests/test_stamp_printing.cjs tests/test_stamp_photo_import.cjs tests/test_mirror_photo_download.cjs
.venv/bin/python tests/support/run_stamp_studio.py
```

隔离服务运行于 8788；`/test/stamp?photo=portrait&mode=save-failure` 使用项目示例照片模拟
视频流并让首次保存失败，不使用真实相机、不向外部存储上传。`mode=denied` 可测试权限拒绝。
测试数据独立存于临时目录；正式 `/selfit/stamp` 无测试注入。

按 DESIGN.md 自检：独立活动首屏行动清楚；照片为视觉中心；模板完整不拉伸；手机390/430px
与桌面/镜子比例无水平溢出；按钮不重叠；加载、失败、恢复、成功、过期状态完整；控制台无缺失资源。
主站特定的登录、suit/like/vibe、推荐和试穿条款不适用于此独立活动入口。

先 commit/push，服务器唯一部署方式：`sudo bash scripts/deploy_release.sh <commit>`。
发布后核对 `/health` 的提交指纹、`/selfit/stamp`、静态资源和 `/selfit/photo`。
