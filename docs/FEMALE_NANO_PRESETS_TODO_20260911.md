# 新女模特整套预设 TODO

当前入口：[恢复进度](FEMALE_NANO_PRESETS_PROGRESS_20260912.md)。9 月 11 日的暂停历史保留在[原交接](FEMALE_NANO_PRESETS_HANDOFF_20260911.md)，以下为 2026-09-13 第 16 轮结束后的实际状态。

已完成 **258/288**（匀称 87、纤细 85、丰满 86）。本次新增 9 张；剩余接口失败 6、目检退回 14、数值失败 4、服务端审核相关暂挂 6。没有在途生成或待目检图片。

## 下一步

- [ ] 用户明确授权将本批原模特照片、服装参考及候选图发送至 Google Vertex AI / Nano Banana 后，再恢复第 17 轮 20 项有限重试。启动被自动审批拒绝，未产生新请求；当前 STOP 是技术授权暂停，不代表用户撤回七牛上传授权。
- [ ] 使用 `resume-20260912/run-17-plan.json` 和 `retry-17.py`，每项最多新增 1 次、单并发。先确认运行锁空闲、源输入 SHA 和状态一致，再归档技术 STOP。
- [ ] 4 项数值失败保留诊断，不能按通过上传或放宽质量阈值。
- [ ] 6 项审核相关暂挂等待用户处理偏好，不重发、不更改审核设置。
- [ ] 全部达到 288 张后才能 finalize；当前不得声明完整完成。

## 已通过结果的收尾

- [x] 第 16 轮新增 9 张逐张核对，绑定结果 SHA，并上传七牛 selfit 私有素材空间及登记。
- [x] 新增 9 张无损 WebP 转换、上传回读；全部 258 张真实命中与负向验证通过。
- [x] 59 项相关测试通过；原 16 条男模特预设未变。
- [ ] 限定本批脚本、测试、业务 JSON 与进度文档 commit 和 push。

## 尚未完成的 30 项

| 任务 | 状态 | 已尝试 | 目前原因 |
| --- | --- | ---: | --- |
| `female_medium_1--flou--outfits-02` | `failed_visual` | 10 | 已完整核对原搭配与本次全身结果。十件款式、短胸门襟、连续腹部针织、圆环项链、黑腰饰及原双肩前发束都保留；持机手仍出现两枚独立绿色宝石戒指，不能通过。 |
| `female_plus_1--inspiration_commute--outfits-02` | `failed_api` | 4 | 最新请求返回 HTTP 429；遵守共享冷却后有限重试。 |
| `female_slim_1--inspiration_commute--outfits-02` | `failed_visual` | 4 | 完整核对原搭配及全身图。错配袜、外放蓝衬衫、披肩灰开衫、花饰灰裙、棕鞋白包、金链和珠耳环均正确，没有工牌，但持机手两枚金戒且垂手另有一枚，共三枚。 |
| `female_medium_1--inspiration_commute--outfits-03` | `failed_api` | 5 | 最新请求返回 HTTP 429；遵守共享冷却后有限重试。 |
| `female_slim_1--inspiration_commute--outfits-03` | `failed_visual` | 4 | 已完整查看原搭配及全身结果。七件齐全、原发型和姿势保留，但夹克成为披肩，两只夹克袖子均空垂，两条手臂只穿了衬衫；围巾前端也变为持机侧且延长至大腿，需恢复实际正常穿袖和非持机侧至胯单前端。 |
| `female_medium_1--inspiration_commute--outfits-04` | `failed_visual` | 4 | 完整查看原搭配及全身结果。八件服装配饰的款式、格纹泡袖衬衫塞腰、双端斜纹领带、阔腿裤、大棕包、黑尖鞋、金耳环、垂手红绳及发束姿势正确；唯持机手两根手指各有一枚银色多轨戒，非一枚。 |
| `female_plus_1--inspiration_commute--outfits-04` | `failed_visual` | 4 | 完整查看原搭配及全身结果。八件服装配饰的款式、格纹泡袖衬衫塞腰、双端斜纹领带、阔腿裤、大棕包、黑尖鞋、金耳环、垂手红绳及发束姿势正确；唯持机手两根手指各有一枚银色多轨戒，非一枚。 |
| `female_slim_1--inspiration_commute--outfits-04` | `failed_visual` | 5 | 完整查看原搭配及全身结果。八件服装配饰的款式、格纹泡袖衬衫塞腰、双端斜纹领带、阔腿裤、大棕包、黑尖鞋、金耳环、垂手红绳及发束姿势正确；唯持机手两根手指各有一枚银色多轨戒，非一枚。 |
| `female_medium_1--inspiration_date--outfits-04` | `blocked_moderation` | 1 | 实际 IMAGE_SAFETY 或同款审核暂挂；保留直接拒绝与同款暂挂的区别。 |
| `female_plus_1--inspiration_date--outfits-04` | `blocked_moderation` | 1 | 实际 IMAGE_SAFETY 或同款审核暂挂；保留直接拒绝与同款暂挂的区别。 |
| `female_slim_1--inspiration_date--outfits-04` | `blocked_moderation` | 1 | 实际 IMAGE_SAFETY 或同款审核暂挂；保留直接拒绝与同款暂挂的区别。 |
| `female_slim_1--inspiration_trend--outfits-01` | `failed_quality` | 4 | 面部差异 35.33，阈值 28；头巾不适用戴帽复核规则。 |
| `female_plus_1--inspiration_vacation--outfits-01` | `failed_visual` | 4 | 完整核对六件及全身结果，柠黄波点上下装衣摆外放、草编包、网面平底鞋及金色短坠齐全，人物原脸与两侧胸前发束保持。但粉色波点头巾没有下巴下方系结，改成头顶后绑带，穿法错误。 |
| `female_slim_1--inspiration_vacation--outfits-01` | `failed_api` | 4 | 最新请求返回 HTTP 429；遵守共享冷却后有限重试。 |
| `female_medium_1--inspiration_vacation--outfits-04` | `blocked_moderation` | 1 | 实际 IMAGE_SAFETY 或同款审核暂挂；保留直接拒绝与同款暂挂的区别。 |
| `female_plus_1--inspiration_vacation--outfits-04` | `blocked_moderation` | 1 | 实际 IMAGE_SAFETY 或同款审核暂挂；保留直接拒绝与同款暂挂的区别。 |
| `female_slim_1--inspiration_vacation--outfits-04` | `blocked_moderation` | 1 | 实际 IMAGE_SAFETY 或同款审核暂挂；保留直接拒绝与同款暂挂的区别。 |
| `female_medium_1--loop--outfits-04` | `failed_api` | 7 | 最新请求返回 HTTP 429；遵守共享冷却后有限重试。 |
| `female_plus_1--oops--outfits-03` | `failed_visual` | 6 | 完整查看结果、原模特和原搭配及六件单品。服装、背包两道扣、蕾丝短裤、粉袜、腿套和银鞋符合要求；但原模特两侧肩前及胸前弯曲长发再次移到肩后，退回。 |
| `female_slim_1--oops--outfits-04` | `failed_visual` | 5 | 已完整查看全身、原搭配及项链和雨靴拆图。单枚金戒指已修正，九件齐全、原发型及姿势正确，青铜面具圆牌也符合单品；但粉色蓝标雨靴被改为平底厚鞋底，缺少原单品明确的弧形小猫跟。 |
| `female_medium_1--void-curvy--outfits-03` | `failed_visual` | 5 | 完整核对原搭配、单袖上衣切图与新结果。内置金属肩饰及心形链、独立白玫瑰胸针、交叠阔腿裤、棕靴包、墨镜与金色配饰齐全，但非持手机侧整束肩前长发被移到背后。 |
| `female_plus_1--void-curvy--outfits-03` | `failed_api` | 6 | 最新请求返回 HTTP 429；遵守共享冷却后有限重试。 |
| `female_slim_1--void-curvy--outfits-03` | `failed_visual` | 5 | 完整核对原搭配、单袖上衣切图与新结果。内置金属肩饰及心形链、独立白玫瑰胸针、交叠阔腿裤、棕靴包、墨镜与金色配饰齐全，但非持手机侧整束肩前长发移到背后，且给原单袖上衣的露肩持手机侧新增了整条针织袖子。 |
| `female_medium_1--void-curvy--outfits-04` | `failed_quality` | 5 | 面部差异 45.58，阈值 28；头巾不适用戴帽复核规则。 |
| `female_plus_1--void-curvy--outfits-04` | `failed_quality` | 5 | 面部差异 41.48，阈值 28；头巾不适用戴帽复核规则。 |
| `female_slim_1--void-curvy--outfits-04` | `failed_quality` | 5 | 面部差异 44.57，阈值 28；头巾不适用戴帽复核规则。 |
| `female_medium_1--wabi-curvy--outfits-02` | `failed_visual` | 5 | 已完整核对原搭配和本次全身结果。六件齐全，原双肩前发束、手脚和单前端围巾正确；但短外套前襟依旧从颈下全开，上部单扣没有扣合。 |
| `female_plus_1--wabi-curvy--outfits-02` | `failed_visual` | 6 | 完整查看六件及原搭配。发型双束恢复、裙及内搭鞋正确，但条纹外套全开未扣最上扣，窄围巾变为两条前垂端，米白包移到非持机肩。 |
| `female_slim_1--wabi-curvy--outfits-02` | `failed_api` | 5 | 最新请求返回 HTTP 429；遵守共享冷却后有限重试。 |
| `female_plus_1--wabi-curvy--outfits-03` | `failed_visual` | 5 | 完整查看原搭配、八件单品及全身结果。发束两侧都恢复，衣裙鞋袜、单前垂流苏围巾、黑绳白坠、深棕包和银表正确；但持机手出现两枚银戒，垂手又出现一枚，共三枚，非单枚戒指。 |

## 约束及证据

- 继续使用本地 ADC → Vertex → `gemini-3.1-flash-image`，单次完整套装，全部原单品保留。
- 候选底图必须属于同模特同套装、数值通过且已目检失败并绑定 SHA；原模特仍是唯一人物、发型和姿势依据。
- 原始模特照片、过程与失败图片留本地；不纳入 Git 或上传为七牛素材。
- 不上传未经检查的图，不拼脸或局部修补生成结果，不改变 28/18 阈值。
- 第 16 轮回执：`resume-20260912/reviews-203.json` 至 `reviews-222.json`；快照 `checkpoint-after-run16.json`。
- 服务器发布需要另行指令，且只允许服务器运行 `sudo bash scripts/deploy_release.sh [commit]`。
