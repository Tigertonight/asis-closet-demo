(function(root) {
  'use strict';
  // Coordinates are percentages of the existing 207 × 437 mirror artwork.
  const FRAME_ASPECT = 207 / 437;
  const GAP = 0.6, INSET = 1;
  const BOUNDS = {x:4, y:19, w:92, h:76};
  const COLUMN_GAP = 2;
  const ORDER = ['outer','top','pants','skirt','dress','hat','neck','waist','bag','accessory','socks','shoes'];
  const LABELS = {outer:'外套',top:'上衣',pants:'裤子',skirt:'半裙',dress:'连衣裙',hat:'帽子',neck:'颈饰',waist:'腰饰',bag:'包袋',accessory:'其他配饰',socks:'袜子',shoes:'鞋子'};
  const areaWeight = category => ['outer','dress'].includes(category) ? 1 : ['top','pants','skirt'].includes(category) ? 2/3 : 2/9;
  const text = p => {
    let filename='';
    try { filename=decodeURIComponent((p.src || '').split('?')[0].split('/').pop()); } catch {}
    return [p.filename,filename,p.raw?.asset_filename,p.raw?.styling?.asset_filename,p.raw?.subcategory,p.raw?.title,p.name].filter(Boolean).join(' ');
  };
  function category(p) {
    if (ORDER.includes(p.mirrorCategory)) return p.mirrorCategory;
    const name = text(p), known = p.raw?.slot || p.category;
    // Specific filename matches precede generic "skirt" and broad API groups.
    if (/连衣裙|连身裙|\bdress\b/i.test(name) || known === 'dress') return 'dress';
    if (/裙|skirt/i.test(name) || known === 'skirt') return 'skirt';
    if (/外套|大衣|夹克|风衣|西装|开衫|coat|jacket|blazer|cardigan/i.test(name) || known === 'outer') return 'outer';
    if (/裤|pants|trousers|shorts/i.test(name) && !/袜|tight|stocking/i.test(name)) return 'pants';
    if (/帽|\bhat\b|beret/i.test(name) || known === 'hat') return 'hat';
    if (/项链|颈链|围巾|领带|领结|necklace|choker|scarf|necktie/i.test(name)) return 'neck';
    if (/腰带|腰链|belt/i.test(name)) return 'waist';
    if (['neck','waist'].includes(known)) return known;
    if (/包|bag|clutch|tote/i.test(name) || known === 'bag') return 'bag';
    if (/袜|sock|stocking|tight/i.test(name) || known === 'socks') return 'socks';
    if (/鞋|靴|shoe|boot|sneaker|sandal|loafer/i.test(name) || known === 'shoes') return 'shoes';
    if (/上衣|衬衫|背心|抹胸|针织|毛衣|卫衣|吊带|shirt|blouse|sweater|hoodie|tank|\btop\b/i.test(name) || known === 'top') return 'top';
    if (['bottom','pants','trousers','shorts'].includes(known)) return 'pants';
    if (/饰|链|框|戒指|手表|眼镜|手镯|胸针|发夹|earring|ring|watch|glasses|bracelet|brooch/i.test(name) || known === 'accessory') return 'accessory';
    return null;
  }
  function delicate(p) {
    const kind = category(p);
    return ['neck','waist','accessory'].includes(kind) &&
      (/细链|细框|细金属|细戒|链|项链|耳环|耳饰|眼镜|镜框|手镯|chain|wire|necklace|earring|glasses|spectacles|bracelet|bangle/i.test(text(p)) || (p.inkRatio > 0 && p.inkRatio < .18));
  }
  function dimensions(p, frameAspect) {
    const kind = category(p);
    const short = /短裙|迷你裙|超短|短裤|mini|shorts/i.test(text(p));
    const fallback = {outer:.8,top:1,pants:.45,skirt:short?1:.6,dress:.45,hat:1.3,neck:.65,waist:3,bag:1,accessory:1,socks:.4,shoes:/长靴|高筒|过膝|knee|tall.*boot/i.test(text(p))?.5:1.5};
    const aspect = Number.isFinite(p.aspect) && p.aspect > 0 ? p.aspect : fallback[kind] || 1;
    const weight = areaWeight(kind);
    // Use the trimmed silhouette envelope, not the original source canvas or
    // inverse ink coverage (which would make a fine chain enormous).
    const w = Math.sqrt(weight * aspect / frameAspect), h = w * frameAspect / aspect;
    return {p,kind,w,h,weight,delicate:delicate(p)};
  }
  const layer = kind => kind === 'outer' ? 1 : ['top','pants','skirt','dress'].includes(kind) ? 2 : 3;
  function upperAccessory(item) {
    if(!item.delicate) return false;
    const name=text(item.p);
    if(/手链|手镯|腕|戒指|bracelet|bangle|\bring\b/i.test(name)) return false;
    return item.kind==='neck' || /眼镜|镜框|项链|颈链|耳饰|耳环|glasses|spectacles|necklace|earring/i.test(name);
  }
  function fineBounds(p) {
    const name=text(p);
    if (/戒指|\bring\b/i.test(name)) return {minW:9,maxW:12,maxH:7};
    if (/眼镜|镜框|glasses|spectacles/i.test(name)) return {minW:19,maxW:27,maxH:9};
    if (/耳环|耳饰|earring/i.test(name)) return {minW:8,maxW:10,maxH:6};
    if (category(p)==='waist') return {minW:18,maxW:30,maxH:10};
    return {minW:14,maxW:24,maxH:18};
  }
  function fit(item, zone, area, manualScale = 1) {
    const fine=item.delicate?fineBounds(item.p):null;
    const inset=item.delicate?2:INSET;
    const maxW = Math.min(Math.max(.01, zone.w - 2*inset),fine?.maxW || Infinity);
    const maxH = Math.min(Math.max(.01, zone.h - 2*inset),fine?.maxH || Infinity);
    // Thin accessories get a modest display enlargement, still contained by
    // the reserved zone; the original image and try-on inputs stay untouched.
    const displayScale = Math.max(Math.sqrt(area) * (item.delicate ? 1.18 : 1),fine?fine.minW/item.w:0)*manualScale;
    const scale = Math.min(displayScale, maxW/item.w, maxH/item.h);
    const w = item.w*scale, h = item.h*scale;
    return {id:item.p.id,layoutId:item.p.mirrorLayoutId || item.p.id,category:item.kind,
      x:zone.x+(zone.w-w)/2,y:zone.y+(zone.h-h)/2,w,h,z:layer(item.kind),
      zone:{...zone},area,manualScale,delicate:item.delicate};
  }
  // Small adjacent accessories share a row instead of each consuming a full
  // column width. Larger garments retain their original area relationship.
  function rowsFor(column, width, maxPerRow=2) {
    const rows=[];
    for(const item of column) {
      const last=rows[rows.length-1];
      if(item.delicate && last?.items.length<maxPerRow && last.items.every(i=>i.delicate)) last.items.push(item);
      else rows.push({items:[item]});
    }
    return rows.map(row=>{
      const weights=row.items.map(i=>i.delicate?fineBounds(i.p).minW+4:1);
      const total=weights.reduce((a,b)=>a+b,0);
      return {...row,widths:weights.map(w=>(width-GAP*(weights.length-1))*w/total)};
    });
  }
  function rowHeight(row,scale) {
    return Math.max(...row.items.map((i,n)=>{
      const fine=i.delicate?fineBounds(i.p):null,inset=i.delicate?2:INSET;
      const preferred=Math.max(scale*(i.delicate?1.18:1),fine?fine.minW/i.w:0);
      return Math.min(i.h*preferred,Math.max(.01,row.widths[n]-2*inset)*i.h/i.w,fine?.maxH || Infinity)+2*inset;
    }));
  }
  const columnHeight=(rows,scale)=>rows.reduce((sum,row)=>sum+rowHeight(row,scale),0)+GAP*Math.max(0,rows.length-1);
  function columnOffsets(columns,scale) {
    const clothing=row=>row?.items.some(i=>['outer','top','dress'].includes(i.kind));
    const leaders=columns.filter(rows=>clothing(rows[0]));
    const belowUpper=leaders.length?Math.min(...leaders.map(rows=>rowHeight(rows[0],scale)))+GAP:0;
    return columns.map(rows=>rows[0]?.items.every(i=>['bag','accessory','waist'].includes(i.kind))?belowUpper:0);
  }
  function layout(pieces, {previous=[],region=null,frameAspect=FRAME_ASPECT} = {}) {
    if (!pieces.length) return [];
    const items = pieces.map(p=>dimensions(p,frameAspect));
    const bounds=region || BOUNDS;
    if (items.some(item=>!item.kind)) return [];
    const old = new Map(previous.map(box=>[box.layoutId || box.id,box]));
    // Replacing a cutout or a same-slot garment does not rebalance its neighbours.
    if (old.size === items.length && items.every(item=>{
      const box=old.get(item.p.mirrorLayoutId || item.p.id);
      return box?.zone && box.category===item.kind;
    })) return items.map(item=>{
      const box=old.get(item.p.mirrorLayoutId || item.p.id);
      return fit(item,box.zone,box.area,box.manualScale);
    });
    // Head/neck pieces get an upper band. Wrist pieces and bags remain with
    // the clothing below, rather than drifting to the foot of a long column.
    const upper=items.filter(upperAccessory),body=items.filter(i=>!upperAccessory(i));
    if(!region && upper.length && body.length) {
      const rows=rowsFor(upper,70,3),scale=10;
      const naturalHeight=rows.reduce((sum,row)=>sum+rowHeight(row,scale),0);
      const compression=Math.min(1,(23-GAP*Math.max(0,rows.length-1))/naturalHeight);
      let y=7;
      const boxes=[];
      for(const row of rows) {
        const h=rowHeight(row,scale)*compression;
        let x=15;
        row.items.forEach((item,index)=>{
          boxes.push(fit(item,{x,y,w:row.widths[index],h},scale*scale));
          x+=row.widths[index]+GAP;
        });
        y+=h+GAP;
      }
      const bodyY=Math.max(BOUNDS.y,y);
      return [...boxes,...layout(body.map(i=>i.p),{region:{...BOUNDS,y:bodyY,h:BOUNDS.y+BOUNDS.h-bodyY},frameAspect})];
    }
    const bodyOrder=['outer','top','dress','hat','neck','waist','bag','accessory','pants','skirt','socks','shoes'];
    const ordered = [...items].sort((a,b)=>bodyOrder.indexOf(a.kind)-bodyOrder.indexOf(b.kind));
    if (items.length===1) {
      const zone=region?{x:21,y:bounds.y,w:58,h:bounds.h}:{x:21,y:27,w:58,h:54};
      return [fit(items[0],zone,650)];
    }
    const width=(bounds.w-COLUMN_GAP)/2;
    const tops=items.filter(i=>['outer','top'].includes(i.kind));
    const lowers=items.filter(i=>['pants','skirt'].includes(i.kind));
    const requireSeparates=tops.length>0 && lowers.length>0;
    let best=null;
    // Search feasible two-column partitions with a shared clothing scale.
    // Large drafts use the bounded fallback below.
    const count=ordered.length;
    function consider(left,right) {
      if (!left.length || !right.length) return;
      if (requireSeparates) {
        const upperCount=left.filter(i=>['outer','top'].includes(i.kind)).length;
        if (upperCount<1 || upperCount>2 || !left.some(i=>['pants','skirt'].includes(i.kind))) return;
      }
      const area=column=>column.reduce((sum,i)=>sum+i.weight,0);
      const rows=[rowsFor(left,width),rowsFor(right,width)];
      const widthScale=Math.min(...ordered.filter(i=>!i.delicate).map(i=>(width-2*INSET)/i.w));
      let low=0,high=Number.isFinite(widthScale)?widthScale:30;
      for(let n=0;n<14;n++) {
        const mid=(low+high)/2;
        const offsets=columnOffsets(rows,mid);
        if(rows.every((r,i)=>columnHeight(r,mid)+offsets[i]<=bounds.h)) low=mid; else high=mid;
      }
      const scale=Math.max(.001,low);
      const balance=Math.abs(area(left)-area(right));
      const heightBalance=Math.abs(columnHeight(rows[0],scale)-columnHeight(rows[1],scale));
      const singleFine=rows.flat().filter(r=>r.items.length===1 && r.items[0].delicate).length;
      const score=balance*6 + heightBalance*.04 - scale*3 + singleFine*.7;
      if (!best || score<best.score-1e-8) best={left,right,scale,score,rows};
    }
    function split(index,left,right) {
      if(index===count) return consider(left,right);
      split(index+1,[...left,ordered[index]],right);
      split(index+1,left,[...right,ordered[index]]);
    }
    if(count<=12) split(0,[],[]);
    else {
      // Bound the search for large drafts so rearranging cannot freeze the UI.
      const left=[],right=[];
      if(requireSeparates) left.push(tops.find(i=>i.kind==='top') || tops[0],lowers[0]);
      for(const item of ordered.filter(i=>!left.includes(i))) {
        const fullUpper=left.filter(i=>['outer','top'].includes(i.kind)).length>=2 && ['outer','top'].includes(item.kind);
        const weight=c=>c.reduce((sum,i)=>sum+i.weight,0);
        (fullUpper || weight(left)>weight(right)?right:left).push(item);
      }
      left.sort((a,b)=>bodyOrder.indexOf(a.kind)-bodyOrder.indexOf(b.kind));
      consider(left,right);
    }
    // Two separates alone cannot both occupy the left column and leave a right
    // column. Use the natural top-to-bottom arrangement in that case.
    if (!best) {
      const scale=Math.max(.001,Math.min(...ordered.map(i=>(width-2*INSET)/i.w),(bounds.h-(2*INSET+GAP)*count)/ordered.reduce((s,i)=>s+i.h,0)));
      best={left:ordered,right:[],scale};
    }
    const boxes=[];
    const columns=best.rows || [rowsFor(best.left,width),rowsFor(best.right,width)];
    const offsets=columnOffsets(columns,best.scale);
    for(const [side,rows] of columns.entries()) {
      let y=bounds.y+offsets[side];
      // A very crowded jewelry-only draft may exceed the legibility minima.
      // Containment wins: shrink its row zones before fitting each silhouette.
      const naturalHeight=rows.reduce((sum,row)=>sum+rowHeight(row,best.scale),0);
      const compression=Math.min(1,(bounds.h-offsets[side]-GAP*Math.max(0,rows.length-1))/Math.max(.01,naturalHeight));
      for(const row of rows) {
        const h=rowHeight(row,best.scale)*compression;
        let x=best.right.length?bounds.x+side*(width+COLUMN_GAP):50-width/2;
        row.items.forEach((item,index)=>{
          const zone={x,y,w:row.widths[index],h};
          boxes.push(fit(item,zone,best.scale*best.scale));
          x+=zone.w+GAP;
        });
        y+=h+GAP;
      }
    }
    return boxes;
  }
  root.SelfitMirrorLayout={layout,category,delicate,LABELS,GAP,INSET};
  if(typeof module!=='undefined') module.exports=root.SelfitMirrorLayout;
})(typeof window!=='undefined'?window:globalThis);
