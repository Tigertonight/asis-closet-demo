# GPT Image 2 色彩算法盲测集

这个目录与 `tests/fixtures/expected.json` 分开，避免新样本在调参时被当成回归金标。

## 当前内容

- 身份 A：1 张中性日光基准图，2 张同人光照变体。
- A02 只改变暖室内光；A03 只改变冷屏幕光。
- 图像由 GPT Image 2 内置生成流程产生，人物均为虚构。

## 正确用法

1. 算法只读图像和 `manifest.json` 中的拍摄条件，不读任何人工季型标签。
2. 同人稳定性优先检查四季一致率、Top-2 重叠率、维度翻转率和置信度波动。
3. 独立盲测标签应由色彩顾问在不知道算法结果的情况下单独给出。
4. 不得用这个集合调阈值后，又在同一集合上报告准确率。

## 局限

合成图可用于发现光照、曝光和白平衡造成的结果翻转，但不能替代真人拍摄、真实布料对比和专家一致性标注。

## 运行

```bash
.venv/bin/python scripts/evaluate_color_stability.py
```

报告会写入 `tests/results/color_blindset_img2_results.json`。
