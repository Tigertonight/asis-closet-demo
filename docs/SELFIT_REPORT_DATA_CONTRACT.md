# selfit 报告页数据契约

> 完整的会话、照片检测、异步报告、穿搭请求与分享接口见 [`SELFIT_BACKEND_INTEGRATION.md`](./SELFIT_BACKEND_INTEGRATION.md)。本文只定义最终报告的可渲染数据。

报告页默认使用 Figma `onboarding → 报告` 的本地素材。后端接入时只需要提供数据，不需要改动页面结构。

## 数据结构

```json
{
  "eyebrow": "SOFT COOL",
  "title": "中性利落派",
  "traits": ["冷调柔和", "高质感", "清晰感"],
  "colors": [
    { "name": "橄榄绿", "value": "#c8c487" }
  ],
  "makeup": [
    {
      "name": "纯净小鹿",
      "byline": "@板牙",
      "imageUrl": "https://cdn.example.com/makeup-01.webp",
      "alt": "纯净自然妆容参考"
    }
  ],
  "hair": [
    {
      "name": "纯净小鹿",
      "byline": "@板牙",
      "imageUrl": "https://cdn.example.com/hair-01.webp",
      "alt": "暖棕层次长发参考"
    }
  ],
  "source": {
    "name": "小红书",
    "copy": "已为你筛选真实用户笔记"
  },
  "outfits": [
    {
      "badge": "活动",
      "title": "中式辣感",
      "description": "主打国风线条与柔和材质的融合，利落又有层次。",
      "imageUrl": "https://cdn.example.com/outfit-01.webp",
      "alt": "中式辣感穿搭参考",
      "author": "索贝"
    }
  ],
  "advice": [
    "建议：直线为主，局部加入柔和弧线",
    "建议：重质感与清晰配色，装饰保持克制"
  ]
}
```

数组字段会整体替换默认值；未传的顶层字段继续使用 Figma 默认数据。图片地址支持本站静态路径或后端/CDN 的完整 URL。

## 接入方式

服务端渲染时，可在 `selfit.js` 执行前注入：

```html
<script>window.__SELFIT_REPORT__ = REPORT_JSON;</script>
```

页面加载后更新：

```js
window.selfitReport.render(reportPayload);
```

从接口加载：

```js
await window.selfitReport.load('/api/selfit/report/REPORT_ID');
```

也可以给 `#appShell` 设置非空的 `data-report-endpoint`，页面会在启动时自动请求该地址。若后端通过事件推送数据：

```js
window.dispatchEvent(new CustomEvent('selfit:report-data', {
  detail: reportPayload
}));
```

每次完成渲染后，页面会派发 `selfit:report-rendered` 事件，`event.detail.data` 是已经补齐默认值的最终报告数据。

分享层的三张轮播卡会同步使用同一份数据：第一张读取 `title / traits`，第二张读取 `title / colors`，第三张读取 `title` 以及 `makeup / hair / outfits` 的代表图片，因此后端不需要维护第二套分享数据。
