# WOKEN DAY 周年邮票照相馆

独立入口 `/selfit/stamp`（亦支持尾斜线）；手机领取页 `/selfit/photo#<photoId>.<secret>`。
保留原有 `/selfit/mirror` 和试穿功能。2026-10-24 根据用户提供的「邮票框最终版」和
「woken-day-stamp-minitool-v56改logo」实现，原始设计与滤镜逻辑位于 `app/static/selfit/stamp/`。

## 设计与操作

本活动页按用户明确选择的 WOKEN DAY 蓝色实体照相馆素材执行，是 DESIGN.md 的品牌活动例外，
不将主站的酒红/浅粉配色覆盖到周年素材上。原有主站设计不变。

流程：掀帘进入 → 选择周年年份 → 相机六秒倒计时拍摄 / 相册导入 → 调整质感、配色、底色、
缩放和位置 → 压印出片 → 扫码分享小红书 / 打印。三种质感为纯色、网点和印刷；十款周年框对应
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
手机只展示和保存邮票，支持文件分享的浏览器提供单张邮票的系统分享按钮。
另支持配置小红书 JS SDK 后的专用分享入口，流程和配置见下节；未配置时仍可保存或系统分享。
普通浏览器的“保存高清邮票”在点击时直接请求同域 PNG 附件地址，不再等待 JS 下载为 Blob。
微信（MicroMessenger）显示“查看高清原图”，点击后在页内查看层展示同一张高清 PNG，
提示长按保存到相册，不发起附件下载；下方原图入口也走这一流程。查看层支持关闭、加载失败重试
和签名链接到期刷新。长按仍由微信原生菜单处理，页面不宣称已经写入相册。

新流程不再合成、上传或分享出片机展示图；旧领取链接也只展示邮票。历史展示图保留供后台查看。
成片页“打印照片”使用本机已生成的 900×1200 PNG，调用网页运行电脑的浏览器打印窗口；
在窗口中选择本机可用打印机、纸张和份数，确认后由系统打印。无需上传完成或新增打印服务。
独立打印文档只包含完整邮票，设备纸张固定为竖版 6 寸（4×6 英寸 / 101.6×152.4mm），零页边距，
不裁切、不带网页按钮或出片机背景。900×1200 成片是 3:4，纸张是 2:3；旧版直接居中
打印会在上下各留下约 8.47mm 白边。2026-10-28 改为本机生成专用 900×1350（2:3）PNG，
原成片逐像素保留在中间，上下各延展 75px 的最外侧背景行，沿用成片实际底色与纸纹色调。
随后针对现场残留的 1–2mm 细白边，改为 DS620 的 **105×156.1mm** 含出血打印文档和 **1240×1844** 栅格。
原邮票等比绘制为 1200×1600，位于 `(20,122)`；标称纸面为 `(20,22,1200,1800)`，四周以边缘像素延展底色。
打印图片使用 cover 只消除像素取整与毫米尺寸间不足 0.05mm 的误差，裁切限于新增底色，不影响邮票。
背景直接写入打印图片，不依赖浏览器的“打印背景图形”选项。透明底按白色相纸处理。
打印图不上传、不替换保存和小红书分享用的 900×1200 成片；打印结束释放临时画布和图片。
驱动仍需选普通 4×6、无边距及正确缩放；驱动另加边距不能由网页强制覆盖，需要现场实物确认。
打印准备及打印窗口打开期间暂停自动重置，关闭或取消后可再次打印；页面不推断实体打印是否成功。
普通浏览器需要在打印窗口确认；现场专用启动方式可开启静默打印，仍需安装打印机驱动和正确耗材。
现场 Windows 的 DS620 配置包位于 `deploy/ds620-windows/`。网页的 `window.print()` 不能指定打印机名称；
需在运行网页的电脑上设置当前用户的默认打印机和驱动纸张。脚本读取 DS620 驱动实际支持的纸张、
校验 4×6 后再写入当前用户打印首选项；不安装驱动、不生成打印作业。
2026-10-28 配置包 v3 直接解析原始 PrintCapabilities XML，覆盖厂商自定义纸型及 DNP 含出血
105×156.1mm 的 6 寸打印区域；保留纸张选项标识并回读验证，排除拼版、条带及其他纸张尺寸。
纸张清单和原始 XML 保存到现场 `%LOCALAPPDATA%\Selfit\Printing\日期时间\`，便于进一步排查驱动兼容性。
配置包同时根据选定纸张的驱动能力设置无边距、100% 缩放、每张 1 页，并在保存后回读；
驱动不开放的设置明确提示现场确认（DS620 的 Border 应为 Disable），不把未验证项当成已配置。
已知有边距、非 100% 缩放或多页拼版设置会阻止启动；写入失败会恢复之前的首选项。
`start-stamp.cmd` 固定 DS620、6 寸、1 份，配置并验证后，以独立用户目录启动 Chrome 照相馆窗口，
使用 `--kiosk-printing --use-system-default-printer` 免预览确认打印。不修改整机浏览器策略；
已有专用窗口时阻止重复启动。实际目标仍为 Windows 默认打印机，活动期间不能更换默认值；需实物验收。
直接从普通浏览器打开时，首次仍需在打印窗口选择 DS620，确认 4×6、纵向、每张 1 页和无页眉页脚。
摄像头需 HTTPS（localhost 调试例外）及设备授权。现场需使用实际智能镜/外接摄像头验收。

## 小红书 JS SDK 分享

WOKEN DAY 成片页点击「扫码分享小红书」→ 手机扫码 → 自动准备分享并尝试打开小红书编辑页，
由用户填写内容并确认发布。浏览器拦截自动唤起时保留「继续打开小红书」及备用入口。
普通领图页仍可保存高清照片，也可手动点击「分享到小红书」→「打开小红书」。
只传一张合成后的高清邮票，不传拍摄原图。
当前官方 SDK 已下线标题、正文、话题预填，代码不提交这些字段，也不调用发布接口。
官方文档：<https://agora.xiaohongshu.com/doc/js>；分享码和唤起链接沿用官方 `xhs-1.0.1.js` 的协议。

- 服务端配置 `SELFIT_XHS_APP_KEY`、`SELFIT_XHS_APP_SECRET` 才显示入口；密钥不进前端、日志和 git。
  配置写入服务器既有私有环境文件；本地 `.env.xhs.local` 仅供联调，启动时须显式加载。
- `GET /api/v1/selfit/mirror/photos/{id}/xhs-share` 校验领取凭证、照片期限及成片文件，返回短期
  `verifyConfig`、图片地址和已准备好的唤起链接。服务端调用官方 check/token，避免点击后还要等待网络。分享使用 `SELFIT_PUBLIC_BASE_URL` 指定的 HTTPS 域名，默认
  `https://selfit.com.cn`，不从 Host 头拼接。该域名应与领图页同源；仅 localhost 调试允许 HTTP。
- access token 存在 `outputs/xhs_share/token.json`（0600）；可通过 `SELFIT_XHS_CACHE_DIR` 指定
  持久目录。锁避免多线程/多进程重复刷新，获取失败冷却 30 秒。该缓存应随 outputs 保留。
  **同一 appKey 仅由一套共享缓存管理刷新**：官方新 token 会立即使旧 token 失效，开发与线上
  不可各自频繁申请。浏览器签名最长 3 分钟，且早于 token 刷新边界失效。
- 官方 SDK 的设备判断仅认 Android/iOS，其他 UA 会静默不唤起；其异步请求也发生在点击之后。
  2026-10-27 手机反馈被误判桌面后，改为服务端按同一 check/token 协议先取得分享码，前端只处理
  官方 scheme/universal link，不再用 JS UA 禁用按钮，也不再加载第三方 SDK 脚本。
  请求头中的平台仅决定首选链接：Android 普通浏览器直接 scheme，微信/iOS/未知平台用官方
  HTTPS universal link；另外提供另一种链接作为备用。未知设备仍然可操作。
- 分享只在无领取凭证的 `/selfit/photo/share` 页面进行，官方接口中的 pageUrl 固定为此路径。
  sessionStorage 一次性交接图片短期签名地址和唤起链接；原领取 secret 仅留在上一页 fragment。
  分享图 URL 仅可读合成 PNG，最长 10 分钟且不得超过领取期限；签名接口和两页禁止缓存、referrer。
  点击时立即导航，没有 await/fetch；图片、scheme、官方 HTTPS 跳转地址均先验证白名单和有效期。
- 照相馆获取 `qr?intent=xhs`，二维码指向 `/selfit/photo?intent=xhs#凭证`，不预先申请短期分享码。
  手机扫描后立即请求分享准备接口，不等待照片预览或高清图解码；成功后一次性交接 `autoOpen: true`。
  原页面立即从历史地址移除 intent；返回、刷新、BFCache 恢复均展示普通领图页，避免循环唤起。
  准备失败可重新尝试或选择「先保存照片」；离开准备流程后忽略迟到结果。旧镜子二维码仍进入领图页。
- 接口准备失败可重试或保存照片，过期后返回领图页重新准备。点击 2.5 秒仍在页面时提示备用入口；
  微信内若被拦截，提示在浏览器打开或保存后分享。页面离开不等于笔记发布成功，不自动发布。

2026-10-27 联调：用户提供的凭据成功获取 token，官方 check/token 返回分享码；桌面浏览器
加载真实 SDK 后也完成验签和分享码请求。修复版服务端使用同一协议准备链接。真实接口只使用公开邮票框，无用户照片或发布操作。
手机原生 App 的图片载入/编辑页唤起仍需现场实机确认，尤其微信内浏览器。

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
.venv/bin/python -m pytest tests/test_selfit_xhs_share.py tests/test_selfit_mirror_photos.py -q
node --test tests/test_mirror_xhs_share.cjs tests/test_mirror_photo_download.cjs
.venv/bin/python tests/support/run_stamp_studio.py
```

隔离服务运行于 8788；`/test/stamp?photo=portrait&mode=save-failure` 使用项目示例照片模拟
视频流并让首次保存失败，不使用真实相机、不向外部存储上传。`mode=denied` 可测试权限拒绝。
测试数据独立存于临时目录；正式 `/selfit/stamp` 无测试注入。

分享页面隔离验收：`.venv/bin/python tests/support/run_xhs_share.py`，访问
`http://127.0.0.1:8789/test/xhs-receipt`。使用临时合成测试图和服务端准备桩；只检查页面和返回，
不要打开占位分享链接。导航时机、UA、过期和备用入口由前端测试覆盖，不代表原生 App 已唤起。

按 DESIGN.md 自检：独立活动首屏行动清楚；照片为视觉中心；模板完整不拉伸；手机390/430px
与桌面/镜子比例无水平溢出；按钮不重叠；加载、失败、恢复、成功、过期状态完整；控制台无缺失资源。
主站特定的登录、suit/like/vibe、推荐和试穿条款不适用于此独立活动入口。

先 commit/push，服务器唯一部署方式：`sudo bash scripts/deploy_release.sh <commit>`。
发布后核对 `/health` 的提交指纹、`/selfit/stamp`、静态资源和 `/selfit/photo`。
