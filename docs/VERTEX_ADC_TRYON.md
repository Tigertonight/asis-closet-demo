# 试穿后端：Google Cloud ADC

设置 `TRYON_GOOGLE_BACKEND=vertex_adc` 后，试穿、AI 单品抠图、套装单品枚举和试穿结果的 Google 图片核对通过同一 ADC transport 调用 Nano Banana 2。旧 Runway/API key 和本地图片桥接不会覆盖这个显式选择。配置或刷新失败会返回失败，不会自动转发到其他图片服务。现有本地图像质量检查继续运行。

## 配置

在服务器 `.env.demo` 设置：

```dotenv
TRYON_GOOGLE_BACKEND=vertex_adc
TRYON_VERTEX_PROJECT=gen-lang-client-0606324711
TRYON_VERTEX_LOCATION=global
TRYON_IMAGE_MODEL=gemini-3.1-flash-image
GOOGLE_APPLICATION_CREDENTIALS=/home/ubuntu/.config/gcloud/application_default_credentials.json
```

凭据文件须由服务运行用户读取，文件权限保持 `0600`。当前服务器 service 以 root 运行，因此显式指定 ubuntu 下已有的 ADC 文件；不复制凭据到代码仓库。凭据与 `.env.demo` 都属于服务器配置，不随 Git 发布覆盖。

基础依赖增加 `google-auth[requests]==2.50.0` 和 `requests==2.32.5`。无需在应用中调用 gcloud CLI 或手工配置短期访问令牌。请求直接发送到 `aiplatform.googleapis.com` 的项目 `global` 端点；OAuth 和生图 session 均不读取环境代理。

每个工作线程独立缓存凭据，文件变更后重新加载。`AuthorizedSession` 负责令牌刷新和认证失败重试。应用不对 429、5xx 或超时自动重复生图。凭据异常仅保留异常类型，不把原始 OAuth 错误或请求头写入响应。

试穿请求明确使用一张 `2K` 图片、最接近原图的支持比例；沿用原图画布归一化与面部、背景检查。抠图使用 `2K`，之后仍检查并转换透明背景。旧试穿缓存按后端和模型区分，避免切换后误用旧后端缓存。预先审核发布的静态试穿素材不受此设置影响。

## 发布与验证

1. 运行 `python -m pytest tests/test_vertex_image.py tests/test_tryon.py tests/test_closet.py tests/test_runtime_readiness.py -q`。
2. 仅提交本次后端、依赖、测试和配置示例；push 到远端。
3. 服务器配置 `.env.demo` 前备份；核对当前 Git 工作区无改动。
4. 按项目唯一发布流程执行 `sudo bash scripts/deploy_release.sh <已推送的commit>`。
5. 核对 `/health` 的 Git 与人格版本；登录后检查 `/try-on/capabilities` 的 `vertex_adc_configured` 和 `features.image_edit`。
6. 在应用虚拟环境和同一服务配置下发起真实图片编辑，检查图片和结果中的 `vertex_adc_generate_content`；不能用缓存命中作为生图验证。

基础 readiness 只验证 ADC 文件可解析，不代表授权、配额或生图一定可用。真实请求是最终验证。普通测试均禁用真实 ADC 后端，再通过 stub/mock 验证刷新和请求格式，不消耗生图额度。

回滚时先恢复原 `.env.demo`，再用同一发布脚本发布上一个已推送的提交；不要覆盖整个服务器目录。

参考：[Google ADC](https://docs.cloud.google.com/docs/authentication/application-default-credentials)、[Nano Banana 2 模型说明](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/3-1-flash-image)、[AuthorizedSession](https://google-auth.readthedocs.io/en/latest/reference/google.auth.transport.requests.html)。
