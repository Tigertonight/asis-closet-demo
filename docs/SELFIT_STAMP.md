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

邮票与出片机展示图分别输出 900×1200 PNG，和原始邮票框分辨率一致；服务器生成
720×960 WebP 供手机/后台预览。相机以取景框裁切，导入照片最长边规范到 1400px，
后台“拍摄原图”是这份未加滤镜的规范化 JPEG，并非相机传感器原始文件。

出片即后台保存。保存失败保留本机照片，支持重试；响应丢失复用同一凭证，不重复创建记录。
再做一枚会清空上一位照片；非处理状态下 120 秒无操作自动回到入口，关闭相机与领取弹窗。
手机可分别保存两张高清成片，支持文件分享的浏览器提供系统分享按钮。不依赖小红书 JS Key，
也不冒充已发布笔记；可在系统分享中选小红书，或保存后自行发布。

此页提供打印用成片和出片动画，未接物理打印机，实际打印仍须设备驱动/本地桥接。
摄像头需 HTTPS（localhost 调试例外）及设备授权。现场需使用实际智能镜/外接摄像头验收。

## 存储、权限与运行

- `POST /api/v1/selfit/mirror/photos`：multipart 原图、邮票、展示图、设置；64 位随机十六进制
  `Idempotency-Key` 同时作为领取凭证。原图/各成片最多 12MB、图片最多 1600 万像素。
- `GET /api/v1/selfit/mirror/photos/{id}/{info|qr|preview|download|scene-preview|scene-download}`：
  Bearer 凭证鉴权并检查有效期。原图不向手机领取接口提供。
- 凭证只在 URL fragment 和 Authorization 头中使用，数据库存 SHA-256；响应禁止缓存，
  领取页面禁止 referrer。不要将领取链接复制进业务日志。
- SQLite WAL：`outputs/selfit_mirror_photos/photos.sqlite3`；私有图片：同目录 `assets/`。
  强制使用本地文件存储，不受项目七牛/OSS 配置影响，不挂公开静态目录。
- 图片验证和 WebP 生成使用现有受限 `photo_work` 池；POST 限流沿用上传额度，GET 单独限流。
- 管理后台「镜子拍摄」可查看/下载规范化原图、邮票成片及展示图，沿用管理员鉴权。
- `SELFIT_MIRROR_PHOTO_TTL_SECONDS` 默认 86400，可设 300–604800。
  **链接过期不删除文件**；后台仍可读取，沿用项目“素材留存、不自动删除”原则。
  运维需监控磁盘、备份此输出目录；后台删除仅隐藏条目。
- `SELFIT_PUBLIC_BASE_URL` 可指定领取域名，未配置时使用代理传入的请求域名。
  当前 Caddy 允许 48MB 请求，覆盖三张图的总上限。

## 验证与发布

```sh
.venv/bin/python -m pytest tests/test_selfit_mirror_photos.py tests/test_selfit_admin_submissions.py tests/test_selfit_persona.py tests/test_selfit_photo_wiring.py -q
node --test tests/test_stamp_delivery.cjs
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
