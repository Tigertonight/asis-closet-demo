# PERF-001 完整 HTTP 采样执行说明

工具：`scripts/measure_selfit_p0_http.py`。仅支持隔离的本机回环服务，不操作生产服务器。
这是采样工具，不是自动放行工具；本文件也不是已完成的性能测试报告。

## 执行前

1. 完成并冻结 160 套正式锚点、四门审核、独立盲审及相关版本。工具要求 160 个唯一 ID，
   每次实际推荐响应还必须返回有效 P0 准入、指定锚点 SHA 与盲审结果 SHA。
2. 启动独立端口的冻结代码测试服务，开启正式 P0 路径。不要重启其他工作正在使用的共享服务。
   记录启动命令、实际源码快照、系统、硬件、后台负载、服务缓存策略及服务启动时间。
   `/health` 的 commit 字符串不能证明脏工作区实际加载了哪些文件，须另附运行源码核对证据。
3. 准备 16 个独立测试账号，各自已有对应正式人格报告，不能使用 persona_preview 代替。
   工具只读取档案，不创建账号、生成报告或改人格。使用有授权的测试登录流程取得临时 token。
4. 复制 `http-performance.accounts.template.json` 为测试配置；配置只保存 persona 与 token_env。
   在本地安全环境设置对应 `P0_TOKEN_*` 环境变量，不把实际 token 写入 Git、日志、聊天或证据文件。

## 执行命令

在项目根目录运行；以下大写占位值必须替换为已核对的实际路径与 release 字符串：

```sh
.venv/bin/python scripts/measure_selfit_p0_http.py \
  --base-url http://127.0.0.1:8011 \
  --accounts ACCOUNTS_CONFIG.json \
  --anchor-manifest FROZEN_ANCHORS.json \
  --blind-result FROZEN_BLIND_RESULT.json \
  --expected-release 'EXPECTED_HEALTH_RELEASE' \
  --output NEW_PERFORMANCE_SAMPLES.json
```

输出路径必须不存在，不覆盖历史结果。请求可能生成 55 个账号内推荐会话快照，不写反馈、正式曝光、
账号档案或内容；应使用隔离的测试存储。工具不会自动清理会话，以保留复查证据。

## 采样规则

- 前置读取 `/health` 和 16 个 `/closet/recommendations/profile`；身份或版本不匹配则阻止采样。
- 5 次预热，再执行 50 次串行完整推荐 HTTP 请求。人格按字母序轮转，前两个人格各 4 次，其他各 3 次。
- 请求体为空对象；正式人格只由服务端账号档案决定。每次均创建新推荐会话，测首批 4 张轮播 + 6 张信息流。
- 计时从发起 HTTP 到完整响应体读取结束；不包含随后 JSON 校验，也不是浏览器图片加载时间。
  使用独立 HTTP 请求、不复用客户端连接、禁用环境代理、不跟随重定向，单次传输超时为 10 秒。
- 每条记录保留实际耗时、状态码、响应摘要及校验错误。失败样本不删除，慢样本不剔除。
- 检查首批 10 套完整且不重复、属于指定锚点、主人格正确、profile 与 P0 release 不变。
  空池/旧版/非 P0/错误人格的快速 200 响应均不能被视为有效成功样本。
- 第 48 个升序样本为 P95，要求 ≤1000ms；50 次请求错误率为 0，预热和前后版本检查也须无错误。
  采样结束后再查健康指纹，并比较输入锚点与盲审文件是否发生变化。

## 结果如何进入验收

- `blocked_preconditions`：尚未形成采样，修正前置条件后用新输出路径重跑。
- `measurement_threshold_fail`：采样阈值、内容响应或版本检查不满足，保留全部原始记录并排查。
- `measurement_threshold_pass`：仅说明本次指定环境下的采样满足工具断言，不等于正式 PERF-001 Pass。

工具始终写 `formal_acceptance=false`、`PERF-001=Not Run`。QA 必须核对运行源码、完整内容准入、
环境记录及原始样本后，另建带执行人、时间、实际结果、证据路径/SHA 的 Case ledger。
禁止仅改采样文件中的状态来制造验收通过。该采样也不能替代 PERF-002 至 008、容量压测或浏览器验收。
