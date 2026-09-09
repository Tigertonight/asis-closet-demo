(function(root){
  function slot(p) {
    const text=[p.raw?.subcategory,p.raw?.title,p.name].filter(Boolean).join(' ');
    if (/帽|hat|beret/i.test(text) || p.category==='hat') return 'hat';
    if (p.category==='outer'||p.raw?.slot==='outer'||(p.raw?.attributes?.style_tags||[]).includes('outer')) return 'outer';
    if (p.category==='bottom' && /裙|skirt/i.test(text)) return 'skirt';
    return p.category;
  }
  function wearSlot(p) {
    const category=slot(p);
    return ['skirt','bottom','pants','trousers','shorts'].includes(category) ? 'bottom' : category;
  }
  function replacePiece(pieces, next) {
    const target=wearSlot(next);
    return [...pieces.filter(p=>{
      const current=wearSlot(p);
      if(p.id===next.id || current===target) return false;
      // A dress replaces separates; choosing separates removes the dress.
      if(target==='dress' && ['top','bottom'].includes(current)) return false;
      if(['top','bottom'].includes(target) && current==='dress') return false;
      return true;
    }),next];
  }
  function layout(pieces, options) {
    const mirror = root.SelfitMirrorLayout || (typeof require === 'function' ? require('./mirror-layout.js') : null);
    return mirror.layout(pieces, options);
  }
  // Matches app/outfit_layout.py and app/outfit_layered_layout.py (1200 × 1500).
  function templateLayout(pieces) {
    const slots=pieces.map(slot), layered=slots.includes('outer') && slots.some(s=>['top','dress'].includes(s));
    const rail={outer:[70,160,420,1230],top:[450,160,800,640],bottom:[450,664,800,1330],skirt:[450,664,800,1330],dress:[450,160,800,1330],hat:[850,90,1130,260],scarf:[850,280,1130,390],bag:[850,410,1130,730],accessory_1:[860,750,1120,850],shoes:[840,880,1130,1080],socks:[860,1100,1120,1200],accessory_2:[860,1220,1120,1330]};
    const main={top:[130,160,770,620],bottom:[150,644,750,1330],skirt:[130,644,770,1330],dress:[100,160,800,1330],outer:[100,160,800,slots.some(s=>['bottom','skirt'].includes(s))?620:1330]};
    let accessories=0;
    return pieces.map(p=>{
      let key=slot(p);
      if(key==='accessory' || !(key in rail)) key='accessory_'+(++accessories);
      const [x1,y1,x2,y2]=(!layered && main[key]) || rail[key] || rail.accessory_2;
      const aspect=p.aspect || (x2-x1)/(y2-y1);
      const w=Math.min(x2-x1,(y2-y1)*aspect), h=w/aspect;
      const end=key==='top' || (key==='outer' && !layered && slots.some(s=>['bottom','skirt'].includes(s)));
      const start=['outer','dress','bottom','skirt'].includes(key);
      return {id:p.id,x:(x1+(x2-x1-w)/2)/12,y:(end?y2-h:start?y1:y1+(y2-y1-h)/2)/15,w:w/12,h:h/15,z:1,rotation:0};
    });
  }
  root.SelfitOutfitLayout={layout,templateLayout,replacePiece};
  if(typeof module!=='undefined')module.exports={layout,templateLayout,replacePiece};
})(typeof window!=='undefined'?window:globalThis);
