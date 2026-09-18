# 请求耗时日志

HTTP 请求结束时，`uvicorn.error` 输出一条 `event=http_request` 的 JSON 记录，进入当前服务的标准日志（现有部署重定向到 `outputs/runtime/fastapi.log`）。WebSocket 和 lifespan 不记录。

- `timestamp`：请求进入应用的 UTC 时间，毫秒精度。
- `request_id`：服务器新生成的随机 ID，同时放入响应 `X-Request-ID`；不采用客户端提供的 ID。与旧业务响应正文中的 requestId 是不同字段。
- `method` / `route` / `status`：HTTP 方法、路由模板、响应状态。模板隐藏报告 ID、分享 token 等动态值；未匹配路径记为 `/unmatched`。
- `headers_ms`：进入应用到开始返回响应头的时间。
- `duration_ms`：进入应用到最后一个响应体分块完成发送的时间，包含上传接收、业务处理和 ASGI 发送等待；不是浏览器图片解码时间或完整公网耗时。
- `handler_ms`：包含响应之后后台工作的应用调用总耗时。
- `response_bytes`：ASGI 实际发送的响应体字节数。
- `outcome`：completed / error / disconnected / incomplete。未发送响应头就断连，状态记为统计用的 499，并非向已断开的客户端发送此状态。
- `error_type`：仅异常类型，不记录异常消息。异常原样继续传播，不改变现有错误处理。
- `slow`：默认 duration_ms >= 1000，可用 `SELFIT_SLOW_REQUEST_MS` 修改阈值。慢请求、未处理异常、5xx 使用 WARNING，其余 INFO。

不记录请求正文、查询参数、Authorization、Cookie、手机号或原始动态 URL。现有 Uvicorn access log 与本日志并存，后者通过 `event` 字段识别。统计时按 route / method 分组计算 P50/P95/P99，并分别查看 headers_ms 与 duration_ms；断连请求单独计数。日志时间是 UTC，查看北京时间需加 8 小时。

中间件包在请求拦截器外层，因此鉴权、请求体限制、限流产生的提前响应也记录。未处理异常由更外层服务器错误处理器生成的 500 响应可能不带 X-Request-ID，但耗时日志仍记录请求 ID。
