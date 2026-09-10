# Onboarding 性别选择

新流程在 SUIT 上传区前放置「女性 / 男性」选择，无默认值。只有服务端保存成功后才开放上传、示例照片及后续步骤。性别由用户声明，不读取照片推断结果，不改变 LIKE × VIBE 人格评分。

SUIT 分为互斥的两个界面：性别选择时不显示任何上传内容；保存成功后隐藏性别模块，仅显示照片与识别内容。照片页左上角返回重新选性别，再返回才到 LIKE。重新选择不清空照片和识别结果，保存失败留在性别页。移除原来的引导说明文案，仅保留「选择你的性别」标题和两个选项。

## 会话契约

- `POST /api/v1/selfit/sessions` 新客户端传 `onboardingMode: "new"`。创建空照片会话，持久化 `reuse_account_photos: false` 和 `requires_gender: true`，不再从账号历史照片索引补图。
- `onboardingMode: "retest"` 仅继承本人最新报告里明确记录的性别；未知时仍需选择。
- 未传模式的旧客户端保留原行为，兼容档案换照和镜子接续。
- `PATCH /sessions/{id}/gender` 传 `{ "gender": "female" | "male" }`，使用现有鉴权、会话归属、幂等及 revision 机制。
- 会话返回 `gender`、`requiresGender`。未选择的新流程在上传照片、生成报告时返回 422 / `profile.gender_required`。
- gender 单独写入报告 profile 快照及账号 profile，不混入肤色、脸型、身型的 `manualOverrides`。

## 报告匹配

先按 LIKE × VIBE 算出人格，再选发布目录 `variants[人格代码 + "-" + gender]`。`typeId` 保持人格代码，`templateId` 记录选中的性别模板，报告保留 `gender`。

当前发布目录没有男性专属模板，历史 `unisex` 实为女性主导素材。因此男性选择暂不展示这些封面、妆发、穿搭和建议；保留型格与配色，返回 `recommendationStatus: "pending_gender_content"` 和提示，隐藏无对应内容的试穿入口。没有使用未发布的编辑器草稿充当正式推荐。发布男版模板后自动匹配。

## 验证

```
node --test tests/test_selfit_gender.cjs tests/test_selfit_manual_interactions.cjs tests/test_selfit_suit_cards.cjs
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 ../.venv-selfit312/bin/python tests/test_selfit_gender.py -v
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 ../.venv-selfit312/bin/python tests/test_selfit_manual_provenance.py -v
```

测试使用临时存储和 mock 预览，不清除用户历史照片、报告、登录或邀请码。
