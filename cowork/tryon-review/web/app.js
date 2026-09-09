'use strict';
const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const media = id => esc(data.assets[id]?.url || '');
const names = {pending:'待审核',approved:'已通过',redo:'需重做'};
let data, selectedId, filtered = [], toastTimer;
let thumbObserver;
const drafts = new Map();
const review = r => data.reviews[r.reviewKey] || {decision:'pending', note:'', revision:0};
const outfitState = o => o.results.some(r => review(r).decision === 'redo') ? 'redo' : o.results.every(r => review(r).decision === 'approved') ? 'approved' : 'pending';
const formatTime = v => new Date(v).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false});

function toast(message) { $('#toast').textContent = message; $('#toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('#toast').hidden = true, 5000); }
async function api(path, opts={}) {
  const response = await fetch(path, {credentials:'same-origin', ...opts});
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(response.status === 401 ? '登录已失效，请刷新页面重新登录。' : (typeof body.detail === 'string' ? body.detail : '暂时无法保存，请稍后重试。'));
  }
  return response.json();
}

function renderStats() {
  const values = Object.values(data.reviews);
  const approved = values.filter(r => r.decision === 'approved').length;
  const redo = values.filter(r => r.decision === 'redo').length;
  $('#stats').innerHTML = [[80,'套穿搭',''],[approved,'已通过','completed'],[240-approved-redo,'待审核',''],[redo,'需重做','redo']].map(([n,label,cls]) => `<div class="stat ${cls}"><strong>${n}</strong><span>${label}</span></div>`).join('');
}

function applyFilters() {
  const q = $('#search').value.trim().toLowerCase(), persona = $('#persona').value, status = $('#status').value;
  filtered = data.outfits.filter(o => (!persona || o.persona === persona) && (!q || `${o.name} ${o.persona} ${o.personaName} ${o.byline} ${o.templateId}`.toLowerCase().includes(q)) &&
    (!status || (['pending','approved','redo'].includes(status) && outfitState(o) === status) || (status === 'adjusted' && o.results.some(r => r.adjusted)) ||
      (status === 'missing' && o.results.some(r => !r.image)) || (status === 'quality' && o.results.some(r => r.originalStatus === 'failed_quality'))));
  if (!filtered.some(o => o.id === selectedId)) selectedId = filtered[0]?.id;
  renderList(); renderWorkspace();
}

function renderList() {
  const list = $('#outfits'), scroll = list.scrollTop, scrollLeft = list.scrollLeft;
  $('#listCount').textContent = `${filtered.length} / ${data.outfits.length} 套穿搭`;
  list.innerHTML = filtered.length ? filtered.map(o => `<button class="outfit ${o.id === selectedId ? 'active' : ''}" data-outfit="${esc(o.id)}" aria-current="${o.id === selectedId ? 'true':'false'}" title="${esc(o.name)}"><img referrerpolicy="no-referrer" data-src="${media(o.source)}" alt="" loading="lazy" fetchpriority="low"><span class="list-text"><span class="list-title">${esc(o.name)}</span><span class="list-meta" style="display:block">${esc(o.personaName)} · ${o.bodyProfile === 'curvy' ? '微胖' : '标准'}</span><span class="list-status" style="display:block">${o.results.filter(r => review(r).decision !== 'pending').length}/3 已审核${o.results.some(r => !r.image) ? ' · 缺 1 张' : ''}</span></span><i class="dot ${outfitState(o)}"></i></button>`).join('') : '<p class="empty">没有符合条件的穿搭</p>';
  list.scrollTop=scroll; list.scrollLeft=scrollLeft;
  thumbObserver?.disconnect();
  thumbObserver=new IntersectionObserver(entries=>entries.forEach(({target,isIntersecting})=>{
    if(isIntersecting){target.src=target.dataset.src;thumbObserver.unobserve(target);}
  }),{root:list,rootMargin:'50px'});
  // Queue the current outfit first; restrict thumbnails to the visible list area.
  setTimeout(()=>$$('img[data-src]',list).forEach(img=>thumbObserver.observe(img)),1200);
}

function photo(id, label, modelId, cls='') {
  return `<div class="photo-wrap ${cls}"><div class="photo-label">${esc(label)}</div>${id ? `<button class="photo-btn" data-zoom="${esc(modelId)}" aria-label="放大${esc(label)}"><img referrerpolicy="no-referrer" src="${media(id)}" alt="${esc(label)}"></button>` : '<div class="missing"><strong>—</strong><span>暂未生成结果<br>此位置保留待审核</span></div>'}</div>`;
}

function renderWorkspace() {
  const o = filtered.find(o => o.id === selectedId);
  if (!o) { $('#workspace').innerHTML = '<div class="empty">换个筛选条件，再看看其他穿搭。</div>'; return; }
  const index=filtered.indexOf(o);
  $('#workspace').innerHTML = `<div class="outfit-head"><div><p class="eyebrow">${esc(o.persona.toUpperCase())} / ${esc(o.personaName)} / ${o.bodyProfile === 'curvy' ? '微胖穿搭' : '标准穿搭'}</p><h2>${String(o.position).padStart(2,'0')} · ${esc(o.name)}</h2></div><div class="pager"><span>${index+1} / ${filtered.length}</span><button data-step="-1" aria-label="上一套" ${index===0?'disabled':''}>←</button><button data-step="1" aria-label="下一套" ${index===filtered.length-1?'disabled':''}>→</button></div></div>
    <section class="source-card"><button class="source-image" data-zoom="source" aria-label="放大原穿搭照片"><img referrerpolicy="no-referrer" src="${media(o.source)}" alt="${esc(o.name)}原穿搭"></button><div class="source-copy"><div class="source-title"><h3>原穿搭参考</h3><span class="tag">${o.items.length} 件单品</span></div><p>${esc(o.byline)}${o.noteUrl ? ` · <a href="${esc(o.noteUrl)}" target="_blank" rel="noopener noreferrer">查看原笔记 ↗</a>` : ''}</p><div class="items">${o.items.map(i=>`<span class="item-tag">${esc(i)}</span>`).join('')}</div></div></section>
    <div class="section-title"><h3>三位模特 · 上身效果</h3><span class="muted">人物、服装完整性与细节均需人工确认</span></div>
    <section class="models-grid">${o.results.map((r,i)=>{
      const m=data.models.find(m=>m.id===r.modelId), saved=review(r), draft=drafts.get(r.reviewKey)||{decision:saved.decision,note:saved.note}, dirty=drafts.has(r.reviewKey);
      return `<article class="model-card" data-key="${esc(r.reviewKey)}"><div class="model-header"><div><p class="model-index">MODEL 0${i+1}</p><h3>${esc(m.name)}</h3></div><span class="badge ${saved.decision}">${names[saved.decision]}</span></div>
      <div class="photos">${photo(m.image,'模特原图',m.id)}${photo(r.image,r.adjusted?'上身效果 · 调整版':'上身效果',m.id)}</div>
      <p class="notice ${r.originalStatus==='uploaded'?'normal':''}">${r.adjusted?'调整版：部分服装或穿法已调整':!r.image?'未生成：需要补充试穿结果':r.originalStatus==='failed_quality'?'自动检查未通过，请重点复核':'已生成 · 等待人工确认'}</p>
      ${r.adjustments.length || r.warnings.length ? `<details><summary>查看${r.adjusted?'调整说明与':'已有'}检查记录</summary><ul>${[...r.adjustments,...r.warnings].map(x=>`<li>${esc(x)}</li>`).join('')}</ul></details>`:''}
      <div class="review-form"><div class="decision" role="group" aria-label="${esc(m.name)}审核结论">${Object.entries(names).map(([key,name])=>`<button data-decision="${key}" class="${draft.decision===key?'selected':''}" aria-pressed="${draft.decision===key}" ${key==='approved'&&!r.image?'disabled':''}>${name}</button>`).join('')}</div>
      <label class="note-label">审核备注<textarea maxlength="2000" placeholder="记录单品缺失、人物变化或需要调整的细节…">${esc(draft.note)}</textarea></label>
      <button class="save ${dirty?'':'saved'}" data-save ${dirty?'':'disabled'}>${dirty?'保存审核':saved.revision?'已保存':'选择结论后保存'}</button>
      <p class="saved-meta">${saved.revision?`${esc(saved.reviewer_name || '审核人')} · ${formatTime(saved.updated_at)} · 第 ${saved.revision} 次记录`:'尚无人工审核记录'}</p></div></article>`;
    }).join('')}</section><div class="bottom-actions"><button id="nextPending">下一套待审核 →</button></div>`;
  bindImageErrors();
}

function bindImageErrors() {
  $$('.photo-btn img,.source-image img').forEach(img => {img.addEventListener('error', () => {
    const btn=img.parentElement;
    if (!$('.image-error',btn)) {const message=document.createElement('span');message.className='image-error';message.textContent='图片暂不可用 · 点击重试';btn.append(message);}
    btn.dataset.retry='true';
  });});
}

function navigate(id) { selectedId=id; renderList(); renderWorkspace(); }
function changeStep(step) { const pos=filtered.findIndex(o=>o.id===selectedId), next=filtered[pos+step]; if(next) navigate(next.id); }
function updateDraft(card, decision) {
  const key=card.dataset.key, r=data.outfits.flatMap(o=>o.results).find(r=>r.reviewKey===key);
  const old=drafts.get(key)||review(r), draft={decision:decision||old.decision,note:$('textarea',card).value};
  drafts.set(key,draft); $$('.decision button',card).forEach(b=>{b.classList.toggle('selected',b.dataset.decision===draft.decision);b.setAttribute('aria-pressed',String(b.dataset.decision===draft.decision));});
  const save=$('[data-save]',card);save.disabled=false;save.classList.remove('saved');save.textContent='保存审核';
}

async function save(card) {
  const key=card.dataset.key, draft=drafts.get(key), button=$('[data-save]',card);
  if (!draft) return;
  if (draft.decision==='redo'&&!draft.note.trim()) { toast('请填写需要重做的原因。'); $('textarea',card).focus();return; }
  const body={reviewKey:key,...draft,revision:data.reviews[key]?.revision||0};
  $$('button,textarea',card).forEach(el=>el.disabled=true); button.textContent='正在保存…';
  try {
    const saved=await api('api/review',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    data.reviews[key]=saved;drafts.delete(key);renderStats();renderList();renderWorkspace();toast('审核记录已保存');
  } catch(error) {
    // Keep the draft, refresh remote revisions on conflict, and require another explicit save.
    if (error.message.includes('其他审核人')) {
      try {const fresh=await api('api/catalog'); data.reviews=fresh.reviews;renderStats();renderList();renderWorkspace();} catch (_) { /* Retain editable draft if the network is still unavailable. */ }
    }
    $$('button,textarea',card).forEach(el=>el.disabled=false);button.textContent='重试保存';toast(error.message);
  }
}

function openZoom(id) {
  const o=data.outfits.find(o=>o.id===selectedId);
  let images=[{label:'原穿搭参考',image:o.source}];
  if(id!=='source') {const m=data.models.find(m=>m.id===id), r=o.results.find(r=>r.modelId===id);images.push({label:`${m.name} · 原图`,image:m.image});if(r.image)images.push({label:r.adjusted?'上身效果 · 调整版':'上身效果',image:r.image});}
  $('#zoomTitle').textContent=o.name+' · 图片对照';
  $('#zoomImages').innerHTML=images.map(x=>`<figure><figcaption>${esc(x.label)}</figcaption><img referrerpolicy="no-referrer" src="${media(x.image)}" alt="${esc(x.label)}"></figure>`).join('');$('#zoom').showModal();
}

$('#outfits').addEventListener('click', e=>{const b=e.target.closest('[data-outfit]');if(b)navigate(b.dataset.outfit);});
$('#workspace').addEventListener('input', e=>{if(e.target.matches('textarea'))updateDraft(e.target.closest('.model-card'));});
$('#workspace').addEventListener('click', e=>{
  const retry=e.target.closest('[data-retry]'); if(retry){delete retry.dataset.retry;$('.image-error',retry)?.remove();const img=$('img',retry);const url=img.getAttribute('src');img.removeAttribute('src');img.src=url;return;}
  const step=e.target.closest('[data-step]');if(step){changeStep(Number(step.dataset.step));return;}
  const d=e.target.closest('[data-decision]');if(d){updateDraft(d.closest('.model-card'),d.dataset.decision);return;}
  const s=e.target.closest('[data-save]');if(s){save(s.closest('.model-card'));return;}
  const zoom=e.target.closest('[data-zoom]');if(zoom){openZoom(zoom.dataset.zoom);return;}
  if(e.target.closest('#nextPending')) {const i=filtered.findIndex(o=>o.id===selectedId), next=[...filtered.slice(i+1),...filtered.slice(0,i)].find(o=>outfitState(o)==='pending');if(next)navigate(next.id);else toast('当前筛选内没有其他待审核穿搭。');}
});
['search','persona','status'].forEach(id=>$('#'+id).addEventListener(id==='search'?'input':'change',applyFilters));
$('#closeZoom').addEventListener('click',()=>$('#zoom').close());
$('#export').addEventListener('click', async()=>{
  if(drafts.size)toast('导出仅包含已保存的审核记录。');
  try {const payload=await api('api/export'),url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='selfit-tryon-reviews.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){toast(e.message);}
});
window.addEventListener('beforeunload',e=>{if(drafts.size){e.preventDefault();e.returnValue='';}});

async function load() {
  try {
    data=await api('api/catalog'); $('#identity').textContent=data.user.name||'';
    const personas=[...new Map(data.outfits.map(o=>[o.persona,o.personaName])).entries()];
    $('#persona').innerHTML='<option value="">所有人格</option>'+personas.map(([id,name])=>`<option value="${esc(id)}">${esc(name)}</option>`).join('');
    $('#expiry').textContent=`239 张结果 · 3 张调整版 · 1 张待补充｜临时链接有效至 ${formatTime(data.expiresAt*1000)}`;
    if(Date.now()>data.expiresAt*1000)toast('素材链接已过期，请更新临时链接清单；审核记录仍保留。');
    $('#loading').hidden=true;$('#application').hidden=false;renderStats();applyFilters();
  } catch(e) {$('#loading').innerHTML=`<p>${esc(e.message||'加载失败')}</p><button id="retryLoad" style="margin-top:20px">重新加载</button>`;$('#retryLoad').onclick=load;}
}
load();
