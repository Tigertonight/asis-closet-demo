# selfit 16 人格报告数据契约

> 完整的会话、照片检测、异步报告、穿搭请求与分享接口见 [`SELFIT_BACKEND_INTEGRATION.md`](./SELFIT_BACKEND_INTEGRATION.md)。本文只定义最终报告模板与可个性化内容。

## 模板与运行规则

- 本地模板清单：`app/static/selfit/data/personality-report-templates.v1.json`
- 浏览器运行时清单：`app/static/selfit/personality-report-templates.js`
- 素材目录：`app/static/selfit/assets/personality/{typeId}/`
- 16 个稳定 `typeId`：`mute / iced / heir / ease / melt / wabi / flou / neon / edge / bolt / film / jade / loop / noir / void / oops`
- 顶部 Hero 是一张完整图片，中英文名称和插画都已融合在图内；前端不得再覆盖绘制标题、英文代号或装饰。
- 色卡中的色值全部保存到 `colors.items`，包括超过五个的颜色；报告页和分享页只加载、渲染数组前 5 个。
- 三类全量候选保存在报告主数据的 `makeupLibrary / hairLibrary / outfitLibrary`，当前共 `34 / 51 / 156` 条；浏览器运行时只下发每个人格排在前面的展示项。
- 妆容、发型、穿搭默认分别渲染前 `2 / 2 / 4` 个；这个限制只作用于展示，不截断底层候选库。
- 缺失素材必须指向明确的占位图，不能借用其他人格的图片或文案；当前 16 张 Hero 均使用各人格已交付的完整头图。

## 本地内容库更新

- 表格归档：穿搭、妆容、发型三份明细表分别作为候选顺序和内容元数据的来源。
- 可版本化数据快照：`app/static/report-builder/data/personality-content-library.v2.json`。
- 报告主数据：`app/static/report-builder/data/16-personality-templates.json`。
- 算法穿搭池：`app/static/selfit/data/content-pool.v1.json`，使用 `outfitLibrary` 全量生成；算法可在完整候选中重排，前端最终仍只渲染前 4 个。
- 同步入口：`scripts/sync_selfit_personality_database.py`；运行后再执行 `scripts/import_selfit_report_data.py` 生成浏览器模板与算法内容池。

## 后端最小响应

算法只需返回稳定的人格类型，前端会直接解析对应模板：

```json
{
  "typeId": "flou",
  "templateVersion": "2026.08.assets-v1"
}
```

如需加入本次分析生成的个性化文案，可放进 `personalization`；同名字段会覆盖模板值：

```json
{
  "typeId": "flou",
  "templateVersion": "2026.08.assets-v1",
  "personalization": {
    "summary": "针对本次测试生成的整体风格解释",
    "outfitSummary": "针对本次测试生成的穿搭综述",
    "adviceIntro": "结论引导语",
    "advice": ["建议一", "建议二"]
  }
}
```

## 单个人格模板

```json
{
  "typeId": "flou",
  "index": "07",
  "metadata": { "name": "造梦浪漫", "code": "FLOU" },
  "hero": {
    "image": {
      "src": "/static/selfit/assets/personality/placeholder-hero.svg",
      "alt": "造梦浪漫 FLOU 人格封面待补充",
      "placeholder": true
    }
  },
  "keywords": [],
  "summary": "",
  "colors": {
    "tagline": "",
    "renderLimit": 5,
    "sourceCard": { "src": "/static/selfit/assets/personality/flou/color-card.png" },
    "items": [
      {
        "id": "color-01",
        "name": "颜色名称",
        "value": "#RRGGBB",
        "sample": { "x": 189, "y": 256, "colorSpace": "sRGB" }
      }
    ]
  },
  "recommendations": {
    "makeup": [
      {
        "id": "makeup-01",
        "name": "妆容名称",
        "byline": "@作者",
        "sourceUrl": "原笔记链接",
        "image": {
          "src": "/static/selfit/assets/personality/flou/makeup-01.webp",
          "alt": "妆容图片替代文字"
        }
      }
    ],
    "hair": [],
    "outfits": { "summary": "", "source": null, "items": [] }
  },
  "conclusion": { "intro": "", "points": [] }
}
```

颜色 `sample` 保存从原始色卡取色的位置和色彩空间，便于复核；`items` 不得在数据生成阶段截断。`renderLimit` 是展示规则，不是存储规则。

## 前端调用

按人格类型加载并渲染：

```js
window.selfitPersonalityReports.render('flou');
```

先合并个性化内容再取得标准报告数据：

```js
const report = window.selfitPersonalityReports.resolve('flou', {
  summary: '本次测试的个性化风格解释'
});
```

调试预览地址：

```text
/selfit?preview=report&type=flou
```

旧的扁平报告响应继续兼容，可通过 `window.selfitReport.render(reportPayload)` 或 `window.selfitReport.load(url)` 渲染。旧穿搭字段 `title / author` 会映射到 `name / byline`；缺失的可选模块会隐藏。

分享层复用同一份标准报告数据，不维护第二套协议。每次渲染后页面会派发 `selfit:report-rendered`，`event.detail.data` 为合并模板与个性化内容后的最终数据。
