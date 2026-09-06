/* Recommendation copy uses garment evidence, never carousel position or inventory titles. */
(function (root) {
  const colors = {black:'黑色',white:'白色',gray:'灰色',grey:'灰色',blue:'蓝色',navy:'藏蓝',brown:'棕色',red:'红色',pink:'粉色',green:'绿色',yellow:'黄色',purple:'紫色',cream:'奶油白',beige:'米色',黑:'黑色',白:'白色',灰:'灰色',蓝:'蓝色',棕:'棕色',红:'红色',粉:'粉色',绿:'绿色',黄:'黄色',紫:'紫色'};
  const types = ['Polo 针织','Polo衫','Polo','阔腿裤','烟管裤','直筒裤','牛仔裤','半身裙','连衣裙','衬衫','针织开衫','开衫','针织衫','针织','西装','卫衣','T恤','长靴','短靴','乐福鞋','运动鞋','芭蕾鞋','平底鞋','高跟鞋','凉鞋','腋下包','手提包','斜挎包','贝雷帽','草帽','围巾'];
  const labels = {top:'上衣',outer:'外套',bottom:'长裤',skirt:'半身裙',dress:'连衣裙',shoes:'鞋子',bag:'包袋',hat:'帽子',accessory:'配饰'};
  function garment(item) {
    const a = item.attributes || {};
    const text = [item.subcategory, item.title, item.category_label].filter(Boolean).join(' ');
    const name = types.find(t => text.toLowerCase().includes(t.toLowerCase())) || labels[item.category] || '单品';
    const values = Array.isArray(a.colors) ? a.colors : [a.colors];
    const raw = values.find(c => colors[c] || (typeof c === 'string' && /^[\u4e00-\u9fff]{1,5}$/.test(c) && !/未知|未判断|混合|多色/.test(c)));
    let color = colors[raw] || raw || '';
    const hex = (a.color_hex || [])[0];
    let light = null;
    if (/^#[0-9a-f]{6}$/i.test(hex || '')) {
      const rgb = [1,3,5].map(i => parseInt(hex.slice(i,i+2),16));
      light = (Math.max(...rgb) + Math.min(...rgb)) / 510;
      if (values.includes('蓝') && light < .25) color = '藏蓝';
      else if (['灰','白'].every(c=>values.includes(c)) && light > .6) color = '浅灰';
    }
    const pattern = String(a.pattern || '');
    const floral = /碎花|印花|floral/i.test(text + ' ' + pattern);
    const striped = /条纹|striped/i.test(text + ' ' + pattern);
    return {name, color, light, floral, striped, label: (floral ? '印花' : striped ? '条纹' : color) + name, item};
  }
  function create(card) {
    const items = (card.items || []).filter(i => !i.deleted && i.selected !== false);
    const first = items.find(i=>['dress','top','outer'].includes(i.category)) || items[0];
    if (!first) return {tag:'穿搭推荐',title:'看看这套搭配',reason:'打开详情，查看这套搭配的单品。'};
    const a = garment(first);
    const second = items.find(i=>i!==first && ['bottom','skirt'].includes(i.category)) || items.find(i=>i!==first && i.category==='outer');
    const b = second && garment(second);
    const accessory = items.find(i=>i.category==='shoes') || items.find(i=>i.category==='bag');
    const c = accessory && garment(accessory);
    let tag = '搭配细节', reason;
    const headlineName = a.name === 'Polo 针织' ? '针织' : a.name;
    const title = b ? `${a.color}${headlineName}与${b.color}${b.item.category === 'bottom' ? '裤装' : b.item.category === 'skirt' ? '裙装' : b.name}` : `${a.color}${headlineName}${c ? '与'+c.name : ''}`;
    if (b) {
      reason = `${a.label}搭配${b.label}`;
      if (a.floral || b.floral) {tag='印花点缀';reason += '，让印花成为这一套的重点。';}
      else if (a.striped || b.striped) {tag='条纹搭配';reason += '，用条纹添一点变化。';}
      else if (a.light !== null && b.light !== null && Math.abs(a.light-b.light) > .35) {tag='深浅相衬';reason += '，深浅对比清楚。';}
      else if (a.color && a.color===b.color) {tag='同色呼应';reason += '，用同色串起上下装。';}
      else if (c) reason += `，以${c.name}收尾。`;
      else reason += '，从这两件开始搭配。';
    } else reason = c ? `${a.label}搭配${c.label}，主装与配件一起选好。` : `以${a.label}为起点，试试你喜欢的鞋包。`;
    return {tag,title,reason};
  }
  root.SelfitOutfitCopy = {create};
  if (typeof module !== 'undefined') module.exports = {create};
})(typeof window !== 'undefined' ? window : globalThis);
