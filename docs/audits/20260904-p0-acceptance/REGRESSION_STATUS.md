# 扩大回归范围：未达到完整放行

## 2026-09-05 视觉缓存与范围优化后的复验

- `non-color-regression.v4.xml`：735 passed，253.14 秒，退出码 0。
  此轮运行期间增加了 P0 视觉工作集优化，不能作为最新源码整体冻结验收。
- 优化后独立启动的 `anchor-workset-regression.v1.xml`：73 passed，10.44 秒。
  覆盖工作集仅缩小范围而不授权、异常/重复 ID、保留时间戳换清单、完整准入、P0 API 隔离及视觉审核失效。
- `non-color-regression.v5.xml` 已完成：746 passed，203.56 秒，退出码 0；JUnit 746 tests / 0 failures / 0 errors / 0 skipped。
  前后核对 234 个 Python 文件发现 `app/closet.py` 在运行中被其他工作修改，本轮没有修改该文件。
  对比证据 `non-color-regression.v5.verification.json`，启动快照 `non-color-regression.v5.sources.json`。
  因源码未稳定，不能把本次绿灯当作最新工作区冻结验收；须待相关改动稳定后重跑受影响范围。
  Python 快照也不是完整内容 release manifest。
- 针对最新衣橱/试穿改动的 `closet-integration-recheck.v1.xml` 已完成：147 passed，72.97 秒，退出码 0，
  覆盖衣橱、试穿、个人首页、分页与试衣镜模块；该检查仍不能替代浏览器真实往返或完整冻结版本回归。
- 性能组件诊断另见 `anchor-workset-component-diagnostic.v1.json`；不满足 PERF-001 的固定环境与 50 次 HTTP 采样条件，仍为 Not Run。

## 2026-09-05 最新增量

- `anchor-version-regression.v1.xml`：版本绑定、P0 验收与个人首页相关 63 项通过。
- 家族表读取取消仅按 mtime 的缓存；撤销审核关系但保留文件修改时间时，下一次读取不再沿用旧关系。
  新测试还覆盖随后损坏编码及删除文件的保守回退；家族、去重、锚点相关 34 项通过。
- 更大范围的 `non-color-regression.v3.xml` 已完成：当前工作区 698 passed，182.15 秒，退出码 0。
  命令为 `.venv/bin/python -m pytest tests --ignore=tests/test_color_analysis.py --junitxml=docs/audits/20260904-p0-acceptance/non-color-regression.v3.xml -q`。
  该轮包含最新家族读取和锚点版本绑定修复；工作区还有其他并行改动，测试总数增加不全部归因于本轮。
  进程结束时依赖库报告 clearcut 遥测上传失败，未导致 pytest 失败；不将此日志解释为浏览器资源检查通过。
  这仍是开发工作区的自动化回归证据，不是冻结发布版本，也不能单独将 G7 或 P0 标记为通过。

## 已执行

命令：`.venv/bin/python -m pytest tests --ignore=tests/test_color_analysis.py --junitxml=docs/audits/20260904-p0-acceptance/non-color-regression.v1.xml -q`

结果：623 passed / 1 failed，耗时 200.33 秒。排除了专门的色彩分析测试模块；保留建档、镜面交接等集成测试，不代表所有测试都与色彩字段无关。
该轮在素材预处理入口修复前启动，不能证明新修复经过全量回归；素材入口另跑 8 项测试通过。

失败：`tests/test_selfit_mirror_handoff.py::test_dynamic_qr_claims_suit_result_once_and_continues_at_like`

- 二维码 HTTP 请求成功，PNG 尺寸 135×135 符合断言，但 OpenCV 解码得到空字符串。
- 失败测试每次创建随机 handoff token；二维码当前按 version=5、M 纠错、3px 模块、4 模块留白生成。
- 两次隔离复跑均通过，报告 `qr-handoff-recheck.v1.xml` 和 `qr-handoff-recheck.v2.xml`。这表明未稳定复现，不代表原失败可以删除。
- 当前没有二维码生成模块或该测试的工作区差异；尚未完成固定失败 token/图样的对照复现，因此不能断言是既有缺陷、环境波动或本轮引入。

## 门禁结论

PERF-007 不能标为 Pass。保留原失败报告，继续核查二维码稳定性与改动前基线；不得以复跑绿灯替换首次失败。
完整 94-case ledger、正式 160 套、独立盲审及设备/性能采样仍未齐，当前不允许放行。

## 固定样本复现与修复

`scripts/audit_selfit_qr_decode.py` 使用公开的 SHA-256 衍生测试 token（不是有效认证 token），
按当前 135×135 生成参数审计 64 个 URL。`qr-deterministic-audit.v1.json` 记录 3 个可稳定失败的图样：
index 20、41 的原图解码失败；index 53 的模糊图失败。放大到 6px 模块不能消除前两例，
同 URL 切换其他标准 mask 后可读。此前随机 token 的测试可能抽到不同图样，单纯重跑不足以验收。

生产生成函数新增有界检查：先尝试标准自动 mask，再尝试 8 个合法 mask；原图与 3×3 轻微模糊图
均须解出原 URL。保留 URL、模块尺寸、纠错等级与留白；工作在线程池进行。若全部失败返回可重试 503，
不无限重试，不返回已知无法通过当前检查的图。此检查不能替代真实设备扫码验证。

`qr-readability-regression.v1.xml`：镜面交接 74 项通过，包括全部 64 个固定图样及有界失败测试。
较大回归已完成，报告 `non-color-regression.v2.xml`：693 passed，耗时 194.09 秒。
本轮包含素材透明度入口新增测试及 65 项二维码固定样本/失败边界测试，仍排除专门的色彩分析模块。
此结果证明本次执行的代码回归通过，不替代真实内容审核、独立盲审、浏览器矩阵或性能采样。
上方首次失败报告保留作为修复前证据；不再以“偶发可忽略”解释该问题。
