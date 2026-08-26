(() => {
  const ASSET = '/static/selfit/assets/';
  const STORAGE_KEY = 'selfit.report-library.v2';
  const LEGACY_KEY = 'selfit.report-builder.v1';
  const SEED_VERSION = 7;
  const KEYWORD_ALIASES = {'同明度秩序':'同调秩序','不费力精致':'松弛精致','低饱和治愈':'柔色治愈','华丽存在感':'华丽焦点'};
  const defaults = {
    schemaVersion: 'selfit-report-template/1.0', assetQualityVersion: 2, updatedAt: '', name: '造梦浪漫型', code: 'LACE',
    hero: `${ASSET}personality/lace-hero.png`,
    keywords: ['柔和线条', '浪漫氛围', '细节表达'],
    summary: '把浪漫写得轻一点，你的温柔自带分寸。你喜欢有分寸的浪漫、线条柔和、色彩安静，细节精致但不过度用力。',
    colors: [{name:'橄榄绿',value:'#C9C786'},{name:'冷淡灰',value:'#D8CEC8'},{name:'海军蓝',value:'#82A8C7'},{name:'奶咖',value:'#B98262'},{name:'豆沙红',value:'#E47B82'}],
    makeup: [{name:'纯净小鹿妆',byline:'@极牙',image:`${ASSET}personality/flou/makeup-01.webp`},{name:'轻透氛围妆',byline:'@极牙',image:`${ASSET}personality/flou/makeup-02.webp`}],
    hair: [{name:'少女感层次',byline:'@极牙',image:`${ASSET}personality/flou/hair-01.webp`},{name:'柔软法式卷',byline:'@极牙',image:`${ASSET}personality/flou/hair-02.webp`}],
    outfitSummary: '你更容易被柔和轮廓和经典氛围打动。比起醒目的潮流元素，你更在意颜色、材质与细节之间是否舒服。',
    source: {name:'小红书',copy:'已为你筛选真实用户笔记',avatars:{imageUrl:`${ASSET}report-user-avatar-stack@4x.png`,alt:'3 位真实用户头像'}},
    outfits: [{name:'日系穿搭',byline:'@极牙',image:`${ASSET}personality/flou/outfits-01.webp`},{name:'日系穿搭',byline:'@极牙',image:`${ASSET}personality/flou/outfits-02.webp`},{name:'柔软层次穿搭',byline:'@极牙',image:`${ASSET}personality/flou/outfits-03.webp`},{name:'奶油色系穿搭',byline:'@极牙',image:`${ASSET}personality/flou/outfits-04.webp`}],
    conclusion: '你并不是不喜欢表达，只是不喜欢喧哗的表达。比起用夸张单品吸引注意，你更擅长把质感藏在面料、领口、色彩关系和一个小小的细节里。',
    advice: ['柔和轮廓：选择自然垂坠、轻微收腰和带弧度的线条。','简约表达：不需要堆叠很多元素，一个细节点就足够。','经典倾向：适合耐看、有质感的单品。']
  };
  const $ = selector => document.querySelector(selector);
  const form = $('#builderForm');
  const preview = $('#reportPreview');
  const saveState = $('#saveState');
  const saveButton = $('#saveButton');
  const toast = $('#toast');
  const selected = new Set();
  let library;
  let config;
  let pendingDeleteId = '';
  let editingId = '';
  let baseRevision = '';
  let isDirty = false;
  let hasConflict = false;

  function clone(value){return JSON.parse(JSON.stringify(value))}
  function uid(){return globalThis.crypto?.randomUUID?.() || `template-${Date.now()}-${Math.random().toString(16).slice(2)}`}
  function now(){return new Date().toISOString()}
  function highResolutionAsset(source){
    if(typeof source!=='string'||source.startsWith('data:image/'))return source;
    const match=source.match(/\/figma-report\/(makeup|hair|outfit)-0([1-4])@(?:2x|4x)\.png$/);
    if(!match)return source;
    const folder=match[1]==='outfit'?'outfits':match[1];
    return `${ASSET}personality/flou/${folder}-0${match[2]}.webp`;
  }
  function normalize(value){
    const source=value?.data&&typeof value.data==='object'?value.data:value;
    const next=clone(defaults);if(!source||typeof source!=='object')return next;
    ['name','code','hero','summary','outfitSummary','conclusion'].forEach(key=>{if(typeof source[key]==='string')next[key]=source[key]});
    next.hero=typeof next.hero==='string'&&next.hero.endsWith('/figma-report/report-hero-reference.png')?`${ASSET}personality/lace-hero.png`:next.hero;
    ['keywords','advice'].forEach(key=>{if(Array.isArray(source[key]))next[key]=next[key].map((item,index)=>typeof source[key][index]==='string'?source[key][index]:item)});
    next.keywords=next.keywords.map(value=>Array.from(KEYWORD_ALIASES[String(value).trim()]||String(value).trim()).slice(0,4).join(''));
    if(Array.isArray(source.colors))next.colors=next.colors.map((item,index)=>({...item,...(source.colors[index]||{})}));
    if(source.source&&typeof source.source==='object')next.source={...next.source,...source.source,avatars:{...next.source.avatars,...(source.source.avatars||{})}};
    ['makeup','hair','outfits'].forEach(key=>{if(Array.isArray(source[key]))next[key]=next[key].map((item,index)=>{const merged={...item,...(source[key][index]||{})};merged.image=highResolutionAsset(merged.image);return merged})});
    if(source.masterData&&typeof source.masterData==='object')next.masterData=clone(source.masterData);
    if(Array.isArray(source.outfitLibrary))next.outfitLibrary=source.outfitLibrary.map(item=>({...item}));
    next.updatedAt=typeof source.updatedAt==='string'?source.updatedAt:'';return next;
  }
  function recordFrom(value){const stamp=now();return {id:uid(),createdAt:stamp,updatedAt:value?.updatedAt||stamp,data:normalize(value)}}
  function masterSeeds(){return Array.isArray(window.SELFIT_REPORT_MASTER_DATA?.templates)?window.SELFIT_REPORT_MASTER_DATA.templates:[]}
  function migrateLibrary(current){
    const next={schemaVersion:'selfit-report-library/1.0',seedVersion:Number(current.seedVersion)||0,activeId:current.activeId||'',templates:current.templates||[]};
    if(next.seedVersion>=SEED_VERSION)return next;
    next.templates=next.templates.filter(item=>String(item.data?.code||'').toUpperCase()!=='LACE');
    if(next.seedVersion<6){const seeds=new Map(masterSeeds().map(seed=>[String(seed.code||'').toUpperCase(),seed]));next.templates.forEach(record=>{if(!record.data?.masterData?.typeId)return;const seed=seeds.get(String(record.data.code||'').toUpperCase());if(!seed)return;['hero','keywords','summary','outfitSummary','conclusion','advice'].forEach(key=>{record.data[key]=clone(seed[key])})})}
    if(next.seedVersion<7){const seeds=new Map(masterSeeds().map(seed=>[String(seed.masterData?.typeId||''),seed]));next.templates.forEach(record=>{const seed=seeds.get(String(record.data?.masterData?.typeId||''));if(seed)record.data.hero=seed.hero})}
    const existingCodes=new Set(next.templates.map(item=>String(item.data?.code||'').toUpperCase()).filter(Boolean));
    masterSeeds().forEach(seed=>{const code=String(seed.code||'').toUpperCase();if(!existingCodes.has(code)){next.templates.push(recordFrom(seed));existingCodes.add(code)}});
    next.seedVersion=SEED_VERSION;if(!next.templates.some(item=>item.id===next.activeId))next.activeId=next.templates[0]?.id||'';return next;
  }
  function parseStoredLibrary(){
    const raw=localStorage.getItem(STORAGE_KEY);if(!raw)return null;const parsed=JSON.parse(raw);if(!parsed||!Array.isArray(parsed.templates))return null;
    return migrateLibrary({seedVersion:parsed.seedVersion,activeId:parsed.activeId||'',templates:parsed.templates.map(item=>({id:item.id||uid(),createdAt:item.createdAt||now(),updatedAt:item.updatedAt||item.data?.updatedAt||now(),data:normalize(item)}))});
  }
  function loadLibrary(){
    try{const stored=parseStoredLibrary();if(stored)return stored}catch{}
    const templates=masterSeeds().map(recordFrom);if(!templates.length)templates.push(recordFrom(defaults));
    return {schemaVersion:'selfit-report-library/1.0',seedVersion:SEED_VERSION,activeId:templates[0].id,templates};
  }
  function blankTemplate(){
    const blank=clone(defaults);blank.name='未命名模板';blank.code='';blank.hero=`${ASSET}personality/placeholder-hero.svg`;blank.keywords=['','',''];blank.summary='';blank.colors=blank.colors.map(color=>({...color,name:''}));blank.makeup=blank.makeup.map(()=>({name:'',byline:'',image:''}));blank.hair=blank.hair.map(()=>({name:'',byline:'',image:''}));blank.outfitSummary='';blank.outfits=blank.outfits.map(()=>({name:'',byline:'',image:''}));blank.conclusion='';blank.advice=['','',''];return blank;
  }
  function persist(){try{localStorage.setItem(STORAGE_KEY,JSON.stringify(library));return true}catch{showToast('浏览器存储空间不足，请先批量导出备份');return false}}
  function activeRecord(){return library.templates.find(item=>item.id===(editingId||library.activeId))}
  function esc(value){return String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]))}
  function normalizeHex(value){const raw=String(value).trim().toUpperCase();if(/^#[0-9A-F]{6}$/.test(raw))return raw;if(/^#[0-9A-F]{3}$/.test(raw))return `#${raw.slice(1).split('').map(char=>char+char).join('')}`;return null}
  function validHex(value){return Boolean(normalizeHex(value))}
  function completion(data){
    const text=[data.name,data.code,data.summary,data.outfitSummary,data.conclusion,...data.keywords,...data.advice];
    const images=[data.hero,...data.makeup.map(item=>item.image),...data.hair.map(item=>item.image),...data.outfits.map(item=>item.image)];
    const done=text.filter(Boolean).length+images.filter(Boolean).length+data.colors.filter(color=>color.name&&validHex(color.value)).length;
    const total=text.length+images.length+data.colors.length;return {percent:Math.round(done/total*100),images:images.filter(Boolean).length};
  }
  function formatDate(value){if(!value)return '尚未保存';const date=new Date(value);if(Number.isNaN(date.getTime()))return '尚未保存';return new Intl.DateTimeFormat('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(date)}
  function renderLibrary(){
    const query=$('#templateSearch').value.trim().toLowerCase();
    const matches=library.templates.filter(item=>`${item.data.name} ${item.data.code}`.toLowerCase().includes(query));
    $('#templateCount').textContent=library.templates.length;$('#completeCount').textContent=library.templates.filter(item=>completion(item.data).percent===100).length;
    $('#templateList').innerHTML=matches.map(item=>{const status=completion(item.data);return `<article class="template-row" data-template-id="${item.id}"><input class="template-select" type="checkbox" aria-label="选择 ${esc(item.data.name)}" ${selected.has(item.id)?'checked':''}/><div class="template-cover"><img src="${esc(item.data.hero||`${ASSET}personality/placeholder-hero.svg`)}" alt="" /></div><div class="template-primary"><strong>${esc(item.data.name||'未命名模板')}</strong><span class="template-code">${esc(item.data.code||'NO CODE')}</span></div><div class="template-meta"><span><i class="completion-dot ${status.percent===100?'is-complete':''}"></i>配置完整度 ${status.percent}%</span><span>图片素材 ${status.images} / 9</span></div><time class="template-updated">最近更新<br>${formatDate(item.updatedAt)}</time><div class="template-actions"><button type="button" data-action="edit">编辑</button><button type="button" data-action="duplicate">复制</button><button type="button" data-action="export">导出</button><button class="delete-action" type="button" data-action="delete">删除</button></div></article>`}).join('');
    $('#libraryEmpty').hidden=matches.length>0;$('#templateList').hidden=matches.length===0;
    $('#selectAll').checked=matches.length>0&&matches.every(item=>selected.has(item.id));$('#selectAll').indeterminate=matches.some(item=>selected.has(item.id))&&!matches.every(item=>selected.has(item.id));updateSelection();
  }
  function updateSelection(){const count=selected.size;$('#selectionState').textContent=count?`已选择 ${count} 个模板`:'未选择模板';$('#batchExportButton').disabled=!count}
  function setEditorState(state,text){saveState.dataset.state=state;saveState.textContent=text;saveButton.disabled=state!=='dirty'}
  function markDirty(){isDirty=true;if(hasConflict){setEditorState('conflict','保存冲突 · 请重新进入');return}setEditorState('dirty','编辑中 · 尚未保存')}
  function showLibrary(){if(isDirty&&!window.confirm('当前修改尚未保存，确定放弃并返回模板库吗？'))return;try{library=parseStoredLibrary()||library}catch{}config=null;editingId='';baseRevision='';isDirty=false;hasConflict=false;$('#editorView').hidden=true;$('#libraryView').hidden=false;$('[data-editor-actions]').hidden=true;$('[data-library-actions]').hidden=false;renderLibrary();window.scrollTo({top:0,behavior:'smooth'})}
  function openEditor(id){const record=library.templates.find(item=>item.id===id);if(!record)return;editingId=id;library.activeId=id;config=clone(record.data);baseRevision=record.updatedAt||'';isDirty=false;hasConflict=false;setEditorState('editing','编辑中 · 尚未修改');$('#libraryView').hidden=true;$('#editorView').hidden=false;$('[data-library-actions]').hidden=true;$('[data-editor-actions]').hidden=false;renderForm();renderPreview();window.scrollTo({top:0,behavior:'smooth'})}
  function textInput(name,value,placeholder=''){return `<input name="${name}" value="${esc(value)}" placeholder="${esc(placeholder)}" />`}
  function mediaFields(key,target){$(`#${target}`).innerHTML=config[key].map((item,index)=>`<article class="media-item ${key==='outfits'?'media-item--outfit':''}"><label class="media-image" data-media-image="${key}.${index}"><input type="file" accept="image/png,image/jpeg,image/webp" /><img ${item.image?`src="${esc(item.image)}"`:'hidden'} alt="${esc(item.name)}" /></label><div class="media-copy"><label>标题${textInput(`${key}.${index}.name`,item.name,'内容标题')}</label><label>来源署名${textInput(`${key}.${index}.byline`,item.byline,'选填，如 @作者')}</label></div>${key==='outfits'?`<div class="outfit-extra"><label>笔记标题${textInput(`${key}.${index}.sourceTitle`,item.sourceTitle||'','来源笔记标题')}</label><label>笔记链接${textInput(`${key}.${index}.sourceUrl`,item.sourceUrl||'','https://...')}</label><label>素材相对路径${textInput(`${key}.${index}.assetPath`,item.assetPath||'','导入前端时使用')}</label><label>穿法说明<textarea name="${key}.${index}.styling" rows="2" placeholder="输入穿法说明">${esc(item.styling||'')}</textarea></label><label>氛围文案<textarea name="${key}.${index}.mood" rows="2" placeholder="输入氛围文案">${esc(item.mood||'')}</textarea></label></div>`:''}</article>`).join('')}
  function renderForm(){
    ['name','code','summary','outfitSummary','conclusion'].forEach(key=>{form.elements[key].value=config[key]});
    $('#keywordFields').innerHTML=config.keywords.map((value,index)=>`<label class="field"><span>关键词 ${index+1} <b>最多 4 字</b></span><input name="keywords.${index}" value="${esc(value)}" maxlength="4" placeholder="输入关键词" /></label>`).join('');
    $('#colorFields').innerHTML=config.colors.map((value,index)=>`<div class="color-item"><label class="color-swatch"><input type="color" name="colors.${index}.value" value="${validHex(value.value)?esc(value.value):'#999999'}" aria-label="颜色 ${index+1} 取色器" /></label><label class="color-hex-label">色值<input class="color-hex" data-color-hex="${index}" value="${esc(value.value)}" maxlength="7" inputmode="text" spellcheck="false" aria-label="颜色 ${index+1} HEX 色值" /></label><label class="color-name-label">名称${textInput(`colors.${index}.name`,value.name,'颜色名')}</label></div>`).join('');
    mediaFields('makeup','makeupFields');mediaFields('hair','hairFields');mediaFields('outfits','outfitFields');
    $('#outfitLibraryCount').textContent=`完整素材库 ${config.outfitLibrary?.length||config.outfits.length} 条 · 报告预览展示前 4 条；导出配置会保留全部 Excel 素材信息。`;
    $('#adviceFields').innerHTML=config.advice.map((value,index)=>`<label class="advice-row"><span>${String(index+1).padStart(2,'0')}</span><textarea name="advice.${index}" rows="2" maxlength="300" placeholder="输入建议，支持 Markdown">${esc(value)}</textarea></label>`).join('');
    document.querySelectorAll('[data-image-field]').forEach(element=>{element.querySelector('img').src=config[element.dataset.imageField]});updateCounters();
  }
  function updateCounters(){['summary','outfitSummary','conclusion'].forEach(key=>{const element=form.elements[key];$(`[data-counter="${key}"]`).textContent=`${element.value.length} / ${element.maxLength}`})}
  function setByPath(path,value){let cursor=config;path.slice(0,-1).forEach(part=>{cursor=cursor[Number.isNaN(Number(part))?part:Number(part)]});cursor[path.at(-1)]=value}
  function saveCurrent(){
    if(!config||!editingId)return false;if(!isDirty){setEditorState('saved','已保存 · 无新修改');return true}
    let fresh;try{fresh=parseStoredLibrary()||library}catch{setEditorState('error','保存失败 · 存储不可用');showToast('无法读取已保存数据，请刷新后重试');return false}
    const remote=fresh.templates.find(item=>item.id===editingId);if(remote&&String(remote.updatedAt||'')!==String(baseRevision||'')){hasConflict=true;setEditorState('conflict','保存冲突 · 请重新进入');showToast('另一页面已先保存此模板，请返回模板库重新进入');return false}
    const stamp=now();const committed={id:editingId,createdAt:remote?.createdAt||activeRecord()?.createdAt||stamp,updatedAt:stamp,data:clone(config)};committed.data.updatedAt=stamp;
    const index=fresh.templates.findIndex(item=>item.id===editingId);if(index>=0)fresh.templates[index]=committed;else fresh.templates.unshift(committed);fresh.activeId=editingId;library=fresh;
    if(!persist()){setEditorState('error','保存失败 · 请先导出备份');return false}
    config=clone(committed.data);baseRevision=stamp;isDirty=false;hasConflict=false;setEditorState('saved','保存成功 · 已生效');showToast('修改已保存');return true
  }
  function previewCard(item){return {name:item.name,byline:item.byline,imageUrl:item.image,alt:`${config.name} · ${item.name}`}}
  function previewPayload(){return {title:config.name,eyebrow:config.code,traits:config.keywords,summary:config.summary,heroImage:{src:config.hero,alt:`${config.name} ${config.code} 人格封面`},illustration:{},colors:config.colors,makeup:config.makeup.map(previewCard),hair:config.hair.map(previewCard),source:config.source,outfitSummary:config.outfitSummary,outfits:config.outfits.map(previewCard),adviceIntro:config.conclusion,advice:config.advice}}
  function renderPreview(){if(!config)return;const target=preview.contentWindow;if(!target||!target.reportTemplatePreview)return;target.dispatchEvent(new target.CustomEvent('report-template:render',{detail:previewPayload()}))}
  function readImage(file,callback){if(!file||!file.type.startsWith('image/'))return;if(file.size>8*1024*1024){showToast('单张图片不能超过 8MB');return}const reader=new FileReader();reader.onload=()=>callback(String(reader.result));reader.readAsDataURL(file)}
  function showToast(message){toast.textContent=message;toast.classList.add('is-visible');setTimeout(()=>toast.classList.remove('is-visible'),2200)}
  function downloadJson(payload,filename){const blob=new Blob([JSON.stringify(payload,null,2)],{type:'application/json;charset=utf-8'});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download=filename;link.click();setTimeout(()=>URL.revokeObjectURL(link.href),0)}
  function exportRecord(record){record.data.updatedAt=record.updatedAt;downloadJson(record.data,`selfit-${record.data.code.toLowerCase()||'report'}-template.json`);showToast('模板配置已导出')}
  function batchExport(ids){const templates=library.templates.filter(item=>ids.has(item.id)).map(item=>({...item.data,templateId:item.id,createdAt:item.createdAt,updatedAt:item.updatedAt}));downloadJson({schemaVersion:'selfit-report-library/1.0',exportedAt:now(),templates},`selfit-report-templates-${new Date().toISOString().slice(0,10)}.json`);showToast(`已导出 ${templates.length} 个模板`)}
  function importRecords(parsed){const values=Array.isArray(parsed)?parsed:Array.isArray(parsed?.templates)?parsed.templates:[parsed];const records=values.filter(value=>value&&typeof value==='object').map(recordFrom);library.templates.push(...records);persist();renderLibrary();return records.length}

  $('#templateSearch').addEventListener('input',renderLibrary);
  $('#selectAll').addEventListener('change',event=>{const query=$('#templateSearch').value.trim().toLowerCase();library.templates.filter(item=>`${item.data.name} ${item.data.code}`.toLowerCase().includes(query)).forEach(item=>event.target.checked?selected.add(item.id):selected.delete(item.id));renderLibrary()});
  $('#templateList').addEventListener('change',event=>{if(!event.target.classList.contains('template-select'))return;const id=event.target.closest('[data-template-id]').dataset.templateId;event.target.checked?selected.add(id):selected.delete(id);renderLibrary()});
  $('#templateList').addEventListener('click',event=>{const button=event.target.closest('[data-action]');if(!button)return;const id=button.closest('[data-template-id]').dataset.templateId;const record=library.templates.find(item=>item.id===id);if(button.dataset.action==='edit')openEditor(id);if(button.dataset.action==='duplicate'){const copy=recordFrom(record.data);copy.data.name=`${record.data.name||'未命名模板'} 副本`;library.templates.unshift(copy);persist();renderLibrary();showToast('模板已复制')}if(button.dataset.action==='export')exportRecord(record);if(button.dataset.action==='delete'){pendingDeleteId=id;$('#deleteDialogCopy').textContent=`“${record.data.name||'未命名模板'}”删除后无法恢复，请先确认已导出需要保留的配置。`;$('#deleteDialog').showModal()}});
  $('#deleteDialog').addEventListener('close',event=>{if(event.target.returnValue!=='confirm'||!pendingDeleteId)return;library.templates=library.templates.filter(item=>item.id!==pendingDeleteId);selected.delete(pendingDeleteId);if(library.activeId===pendingDeleteId)library.activeId=library.templates[0]?.id||'';pendingDeleteId='';persist();renderLibrary();showToast('模板已删除')});
  function createTemplate(){const record=recordFrom(blankTemplate());library.templates.unshift(record);persist();openEditor(record.id);showToast('已新建空白模板')}
  $('#createButton').addEventListener('click',createTemplate);$('#emptyCreateButton').addEventListener('click',createTemplate);$('#backButton').addEventListener('click',showLibrary);saveButton.addEventListener('click',saveCurrent);
  $('#batchExportButton').addEventListener('click',()=>batchExport(selected));
  $('#libraryImportButton').addEventListener('click',()=>$('#libraryImportInput').click());
  $('#libraryImportInput').addEventListener('change',async event=>{let total=0;for(const file of event.target.files){try{total+=importRecords(JSON.parse(await file.text()))}catch{showToast(`${file.name} 格式不正确`)}}event.target.value='';if(total)showToast(`已导入 ${total} 个模板`)});
  form.addEventListener('input',event=>{const hexIndex=event.target.dataset.colorHex;if(hexIndex!==undefined){const normalized=normalizeHex(event.target.value);event.target.setAttribute('aria-invalid',String(!normalized));if(!normalized)return;config.colors[Number(hexIndex)].value=normalized;event.target.closest('.color-item').querySelector('input[type="color"]').value=normalized;markDirty();renderPreview();return}if(!event.target.name)return;setByPath(event.target.name.split('.'),event.target.value);if(event.target.type==='color'){const text=event.target.closest('.color-item').querySelector('[data-color-hex]');text.value=event.target.value.toUpperCase();text.setAttribute('aria-invalid','false')}markDirty();renderPreview();updateCounters()});
  form.addEventListener('focusout',event=>{const index=event.target.dataset.colorHex;if(index!==undefined&&!validHex(event.target.value)){event.target.value=config.colors[Number(index)].value;event.target.setAttribute('aria-invalid','false')}});
  form.addEventListener('change',event=>{if(event.target.type!=='file')return;const hero=event.target.closest('[data-image-field]');const media=event.target.closest('[data-media-image]');readImage(event.target.files[0],result=>{if(hero)config[hero.dataset.imageField]=result;if(media){const[key,index]=media.dataset.mediaImage.split('.');config[key][Number(index)].image=result}renderForm();renderPreview();markDirty();showToast('图片已加入草稿，保存后生效')})});
  document.querySelectorAll('.image-field').forEach(element=>element.addEventListener('click',event=>{if(!event.target.closest('button'))element.querySelector('input').click()}));
  document.querySelectorAll('[data-clear-image]').forEach(button=>button.addEventListener('click',event=>{event.stopPropagation();config.hero=`${ASSET}personality/placeholder-hero.svg`;renderForm();renderPreview();markDirty()}));
  document.querySelectorAll('[data-jump]').forEach(button=>button.addEventListener('click',()=>{const target=$(`#${button.dataset.jump}`);window.scrollTo({top:target.getBoundingClientRect().top+window.scrollY-124,behavior:'smooth'})}));
  const observer=new IntersectionObserver(entries=>{const visible=entries.filter(entry=>entry.isIntersecting).sort((a,b)=>b.intersectionRatio-a.intersectionRatio)[0];if(!visible)return;document.querySelectorAll('[data-jump]').forEach(button=>button.classList.toggle('is-active',button.dataset.jump===visible.target.id))},{rootMargin:'-140px 0px -55% 0px',threshold:[0,.2,.5]});
  document.querySelectorAll('[data-form-section]').forEach(element=>observer.observe(element));
  $('#exportButton').addEventListener('click',()=>{const record=activeRecord();if(!record)return;exportRecord({...record,data:clone(config)});if(isDirty)showToast('已导出当前草稿；点击保存修改后才会生效')});$('#importButton').addEventListener('click',()=>$('#importInput').click());
  $('#importInput').addEventListener('change',async event=>{const file=event.target.files[0];if(!file)return;try{config=normalize(JSON.parse(await file.text()));renderForm();renderPreview();markDirty();showToast('配置已导入草稿，保存后生效')}catch{showToast('配置文件格式不正确')}event.target.value=''});
  $('#resetButton').addEventListener('click',()=>{const seed=masterSeeds().find(item=>String(item.code).toUpperCase()===String(config.code).toUpperCase());if(!seed){showToast('当前模板没有可恢复的主数据版本');return}if(!window.confirm('确定将当前草稿恢复为人格主数据吗？保存前不会生效。'))return;config=normalize(seed);renderForm();renderPreview();markDirty();showToast('已恢复到草稿，保存后生效')});
  $('#previewTop').addEventListener('click',()=>{const reportScreen=preview.contentDocument?.querySelector('[data-report-screen]');if(reportScreen)reportScreen.scrollTo({top:0,behavior:'smooth'});else preview.contentWindow?.scrollTo({top:0,behavior:'smooth'})});preview.addEventListener('load',renderPreview);
  window.addEventListener('storage',event=>{if(event.key!==STORAGE_KEY)return;let fresh;try{fresh=parseStoredLibrary()}catch{return}if(!fresh)return;if($('#editorView').hidden){library=fresh;renderLibrary();return}const remote=fresh.templates.find(item=>item.id===editingId);if(!remote||String(remote.updatedAt||'')===String(baseRevision||''))return;if(isDirty){hasConflict=true;setEditorState('conflict','保存冲突 · 请重新进入');showToast('另一页面已保存此模板，当前草稿不会自动覆盖');return}library=fresh;config=clone(remote.data);baseRevision=remote.updatedAt||'';renderForm();renderPreview();setEditorState('saved','已同步另一页面的更新')});
  window.addEventListener('beforeunload',event=>{if(!isDirty)return;event.preventDefault();event.returnValue='' });
  library=loadLibrary();persist();renderLibrary();
})();
