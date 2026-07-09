# 电子衣橱抠图生图测试集

本测试集用于生成一批可控图片，系统性验证“自动入柜 + 智能抠图”的效果。

资产位置：

- Manifest: `tests/fixtures/closet_cutout_imagegen/manifest.json`
- 分类 Prompt: `tests/fixtures/closet_cutout_imagegen/prompts/`
- 生成图片建议目录: `tests/fixtures/closet_cutout_imagegen/generated/`

## 覆盖范围

| 类别 | 名称 | 重点 | Case 数 |
|---|---|---|---:|
| A | 标准单品白底图 | 最基础的商品图抠图能力 | 5 |
| B | 电商/模特商品图 | 真人、衣架、手部、深色背景 | 5 |
| C | 多单品平铺穿搭图 | 一图多件、套装拆分、重复单品压力 | 5 |
| D | 复杂边缘和材质 | 蕾丝、毛绒、薄纱、链条、鞋带 | 5 |
| E | 颜色和背景干扰 | 同色背景、低对比、花色、过曝 | 5 |
| F | 拍摄质量问题 | 模糊、暗光、裁切、遮挡、随手拍 | 5 |
| G | 负样本/误识别 | 风景、桌面物体、鞋盒、截图、宠物衣服 | 5 |
| H | 分类边界样本 | 衬衫裙、连体裤、裤裙、长靴、配饰 | 5 |
| I | 真人姿态与遮挡 | 交叉手臂、坐姿、头发遮挡、走动姿态 | 5 |
| J | 叠穿和嵌套衣物 | 衬衫+马甲、外套+裙、围巾压衣服 | 5 |
| K | 镜子自拍和真实场景 | 镜像、手机遮挡、卧室/浴室/街拍杂乱背景 | 5 |
| L | 平台截图和图文素材 | 小红书封面、商品网格、海报字、视频封面 | 5 |
| M | 人群和身材多样性 | 男装、大码、中老年、儿童、孕妇 | 5 |
| N | 文化和特殊场合服饰 | 旗袍、纱丽、汉服、婚纱、礼服 | 5 |
| O | 小配饰和首饰 | 墨镜、项链、腰带、手表、发夹 | 5 |
| P | 内衣泳装和边界品类 | 泳衣、比基尼、运动内衣、打底裤、睡衣 | 5 |
| Q | 极端构图和画幅 | 主体很小、边缘裁切、旋转、近大远小、宽图 | 5 |
| R | 背景材质和阴影 | 木地板、草地、混凝土、反光桌、衣架阴影 | 5 |
| S | 重复和高相似单品 | 两双鞋、两条裤、正反面、反射重复、重复包 | 5 |
| T | 高难负样本和伪装物 | 毛巾、窗帘、毯子、围裙、帆布袋边界 | 5 |

总计：20 类，100 个 case。

## 推荐生成顺序

第一轮先生成每类 seed case，快速看整体能力边界。当前已经生成了 A-T 的 20 张种子图。

| Case | 用途 |
|---|---|
| A01 | 基础白底上衣 |
| B01 | 真人穿白衬衫 |
| C01 | 三件平铺套装 |
| D01 | 蕾丝复杂边缘 |
| E01 | 白衣白床低对比 |
| F01 | 用户随手拍 |
| G01 | 无衣物负样本 |
| H01 | 衬衫裙分类边界 |
| I01 | 交叉手臂遮挡西装 |
| J01 | 衬衫叠穿马甲 |
| K01 | 镜子自拍全身穿搭 |
| L01 | 小红书风格图文封面 |
| M01 | 男士西装全身图 |
| N01 | 旗袍 |
| O01 | 墨镜小配饰 |
| P01 | 连体泳衣 |
| Q01 | 主体很小的大留白图 |
| R01 | 木地板阴影 |
| S01 | 两双相似白鞋 |
| T01 | 毛巾负样本 |

第二轮生成所有 A/C/D/E/R 类，重点看 mask、cutout、背景残留和阴影泄漏。

第三轮生成 B/F/G/H/I/J/K/L/M/N/O/P/Q/S/T 类，重点看 review/rejected、类别边界、遮挡、截图噪声和重复单品。

更稳的产品验收顺序：

1. `A/C/D/E/R`：先确认基础抠图和边缘质量。
2. `B/I/J/K/M`：再确认真人、姿态、遮挡和叠穿不会产生严重误入柜。
3. `G/L/T`：压误识别和负样本。
4. `H/N/O/P/Q/S`：压品类边界、极端构图和套装去重。

## 文件命名规范

生成图片后建议保存为：

```text
tests/fixtures/closet_cutout_imagegen/generated/A01_white_background_short_sleeve_tshirt.png
tests/fixtures/closet_cutout_imagegen/generated/B01_model_wearing_white_shirt.png
```

文件名使用 `{case_id}_{short_slug}.png`，方便后续把导入结果和 manifest 对齐。

## 评估表字段

每张图导入后建议记录：

| 字段 | 可选值 | 说明 |
|---|---|---|
| found | yes / no | 是否找到衣物 |
| actual_count | number | 实际入柜单品数 |
| category_accuracy | correct / partial / wrong | 类别是否正确 |
| edge_quality | good / acceptable / bad | mask 边缘质量 |
| background_residue | none / slight / heavy | 背景残留 |
| subject_loss | none / slight / heavy | 主体缺失 |
| closet_quality | usable / review / rejected | 系统质量判断 |
| tryon_ready | yes / no | 是否适合进入试穿 |
| notes | text | 例如“鞋带断了”“白裙边缘丢失” |

## 通过标准

基础可用：

- A 类 80% 以上 `usable`
- C 类主要单品数量误差不超过 1
- G 类不产生 `usable` 单品
- T 类不产生明显服装误识别

Beta 可用：

- A 类 90% 以上 `usable`
- B/F 类能稳定进入 `review` 而不是错误 `usable`
- D/E 类边缘问题可解释，主体不大面积缺失
- H 类边界样本不产生明显错误拆分
- I/J/K 类对真人遮挡场景能保守进入 `review`
- L 类忽略 UI 文案、播放按钮、海报大字等非衣物元素
- S 类支持 closet 保存多个相似单品，但套装组合时不重复展示
