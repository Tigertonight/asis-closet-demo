(() => {
  const ASSET = '../../static/selfit/assets/';
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
  const form = document.querySelector('#builderForm');
  const preview = document.querySelector('#reportPreview');
  const saveState = document.querySelector('#saveState');
  const toast = document.querySelector('#toast');
  let saveTimer;
  let config = load();

  function clone(value){return JSON.parse(JSON.stringify(value))}
  function highResolutionAsset(source){
    if(typeof source!=='string'||source.startsWith('data:image/'))return source;
    const match=source.match(/\/figma-report\/(makeup|hair|outfit)-0([1-4])@(?:2x|4x)\.png$/);
    if(!match)return source;
    const folder=match[1]==='outfit'?'outfits':match[1];
    return `${ASSET}personality/flou/${folder}-0${match[2]}.webp`;
  }
  function normalizedHero(source){return typeof source==='string'&&source.endsWith('/figma-report/report-hero-reference.png')?`${ASSET}personality/lace-hero.png`:source}
  function normalize(value){
    const next=clone(defaults); if(!value||typeof value!=='object')return next;
    ['name','code','hero','summary','outfitSummary','conclusion'].forEach(k=>{if(typeof value[k]==='string')next[k]=value[k]});
    next.hero=normalizedHero(next.hero);
    ['keywords','advice'].forEach(k=>{if(Array.isArray(value[k]))next[k]=next[k].map((v,i)=>typeof value[k][i]==='string'?value[k][i]:v)});
    if(Array.isArray(value.colors))next.colors=next.colors.map((v,i)=>({...v,...(value.colors[i]||{})}));
    if(value.source&&typeof value.source==='object')next.source={...next.source,...value.source,avatars:{...next.source.avatars,...(value.source.avatars||{})}};
    ['makeup','hair','outfits'].forEach(k=>{if(Array.isArray(value[k]))next[k]=next[k].map((v,i)=>{const merged={...v,...(value[k][i]||{})};merged.image=highResolutionAsset(merged.image);return merged})});
    next.updatedAt=typeof value.updatedAt==='string'?value.updatedAt:''; return next;
  }
  function load(){try{return normalize(JSON.parse(localStorage.getItem('selfit.report-builder.v1')))}catch{return clone(defaults)}}
  function esc(value){return String(value??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}
  function normalizeHex(value){const raw=String(value).trim().toUpperCase();if(/^#[0-9A-F]{6}$/.test(raw))return raw;if(/^#[0-9A-F]{3}$/.test(raw))return `#${raw.slice(1).split('').map(char=>char+char).join('')}`;return null}
  function validHex(value){return Boolean(normalizeHex(value))}
  function textInput(name,value,placeholder=''){return `<input name="${name}" value="${esc(value)}" placeholder="${esc(placeholder)}" />`}
  function mediaFields(key,target){document.querySelector(`#${target}`).innerHTML=config[key].map((item,i)=>`<article class="media-item"><label class="media-image" data-media-image="${key}.${i}"><input type="file" accept="image/png,image/jpeg,image/webp" /><img src="${esc(item.image)}" alt="${esc(item.name)}" /></label><div class="media-copy"><label>标题${textInput(`${key}.${i}.name`,item.name,'内容标题')}</label><label>来源署名${textInput(`${key}.${i}.byline`,item.byline,'选填，如 @作者')}</label></div></article>`).join('')}
  function renderForm(){
    ['name','code','summary','outfitSummary','conclusion'].forEach(k=>{form.elements[k].value=config[k]});
    document.querySelector('#keywordFields').innerHTML=config.keywords.map((v,i)=>`<label class="field"><span>关键词 ${i+1}</span>${textInput(`keywords.${i}`,v,'输入关键词')}</label>`).join('');
    document.querySelector('#colorFields').innerHTML=config.colors.map((v,i)=>`<div class="color-item"><label class="color-swatch"><input type="color" name="colors.${i}.value" value="${validHex(v.value)?esc(v.value):'#999999'}" aria-label="颜色 ${i+1} 取色器" /></label><label class="color-hex-label">色值<input class="color-hex" data-color-hex="${i}" value="${esc(v.value)}" maxlength="7" inputmode="text" spellcheck="false" aria-label="颜色 ${i+1} HEX 色值" /></label><label class="color-name-label">名称${textInput(`colors.${i}.name`,v.name,'颜色名')}</label></div>`).join('');
    mediaFields('makeup','makeupFields'); mediaFields('hair','hairFields'); mediaFields('outfits','outfitFields');
    document.querySelector('#adviceFields').innerHTML=config.advice.map((v,i)=>`<label class="advice-row"><span>${String(i+1).padStart(2,'0')}</span><textarea name="advice.${i}" rows="2" maxlength="300" placeholder="输入建议，支持 Markdown">${esc(v)}</textarea></label>`).join('');
    document.querySelectorAll('[data-image-field]').forEach(el=>{el.querySelector('img').src=config[el.dataset.imageField]}); updateCounters();
  }
  function updateCounters(){['summary','outfitSummary','conclusion'].forEach(k=>{const el=form.elements[k];document.querySelector(`[data-counter="${k}"]`).textContent=`${el.value.length} / ${el.maxLength}`})}
  function setByPath(path,value){let cursor=config;path.slice(0,-1).forEach(part=>{cursor=cursor[Number.isNaN(Number(part))?part:Number(part)]});cursor[path.at(-1)]=value}
  function scheduleSave(){clearTimeout(saveTimer);saveState.textContent='正在保存…';saveTimer=setTimeout(()=>{config.updatedAt=new Date().toISOString();try{localStorage.setItem('selfit.report-builder.v1',JSON.stringify(config));saveState.textContent='所有更改已保存'}catch{saveState.textContent='图片过大，请导出备份';showToast('浏览器存储空间不足，请先导出配置备份')}},260)}
  function previewCard(item){return {name:item.name,byline:item.byline,imageUrl:item.image,alt:`${config.name} · ${item.name}`}}
  function previewPayload(){return {title:config.name,eyebrow:config.code,traits:config.keywords,summary:config.summary,heroImage:{src:config.hero,alt:`${config.name} ${config.code} 人格封面`},illustration:{},colors:config.colors,makeup:config.makeup.map(previewCard),hair:config.hair.map(previewCard),source:config.source,outfitSummary:config.outfitSummary,outfits:config.outfits.map(previewCard),adviceIntro:config.conclusion,advice:config.advice}}
  function renderPreview(){
    const target=preview.contentWindow;if(!target||!target.selfitReport)return;target.dispatchEvent(new target.CustomEvent('selfit:report-data',{detail:previewPayload()}));
  }
  function readImage(file,callback){if(!file||!file.type.startsWith('image/'))return;if(file.size>8*1024*1024){showToast('单张图片不能超过 8MB');return}const reader=new FileReader();reader.onload=()=>callback(String(reader.result));reader.readAsDataURL(file)}
  function showToast(message){toast.textContent=message;toast.classList.add('is-visible');setTimeout(()=>toast.classList.remove('is-visible'),2200)}
  function download(){config.updatedAt=new Date().toISOString();const blob=new Blob([JSON.stringify(config,null,2)],{type:'application/json;charset=utf-8'});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download=`selfit-${config.code.toLowerCase()||'report'}-template.json`;link.click();URL.revokeObjectURL(link.href);showToast('模板配置已导出')}

  form.addEventListener('input',event=>{
    const hexIndex=event.target.dataset.colorHex;
    if(hexIndex!==undefined){const normalized=normalizeHex(event.target.value);event.target.setAttribute('aria-invalid',String(!normalized));if(!normalized)return;config.colors[Number(hexIndex)].value=normalized;event.target.closest('.color-item').querySelector('input[type="color"]').value=normalized;scheduleSave();renderPreview();return}
    if(!event.target.name)return;setByPath(event.target.name.split('.'),event.target.value);if(event.target.type==='color'){const text=event.target.closest('.color-item').querySelector('[data-color-hex]');text.value=event.target.value.toUpperCase();text.setAttribute('aria-invalid','false')}scheduleSave();renderPreview();updateCounters()
  });
  form.addEventListener('focusout',event=>{const index=event.target.dataset.colorHex;if(index!==undefined&&!validHex(event.target.value)){event.target.value=config.colors[Number(index)].value;event.target.setAttribute('aria-invalid','false')}});
  form.addEventListener('change',event=>{if(event.target.type!=='file')return;const hero=event.target.closest('[data-image-field]');const media=event.target.closest('[data-media-image]');readImage(event.target.files[0],result=>{if(hero)config[hero.dataset.imageField]=result;if(media){const[key,index]=media.dataset.mediaImage.split('.');config[key][Number(index)].image=result}renderForm();renderPreview();scheduleSave();showToast('图片已更新')})});
  document.querySelectorAll('.image-field').forEach(el=>el.addEventListener('click',event=>{if(!event.target.closest('button'))el.querySelector('input').click()}));
  document.querySelectorAll('[data-clear-image]').forEach(button=>button.addEventListener('click',event=>{event.stopPropagation();config.hero=`${ASSET}personality/placeholder-hero.svg`;renderForm();renderPreview();scheduleSave()}));
  document.querySelectorAll('[data-jump]').forEach(button=>button.addEventListener('click',()=>{const target=document.querySelector(`#${button.dataset.jump}`);window.scrollTo({top:target.getBoundingClientRect().top+window.scrollY-124,behavior:'smooth'})}));
  const observer=new IntersectionObserver(entries=>{const visible=entries.filter(e=>e.isIntersecting).sort((a,b)=>b.intersectionRatio-a.intersectionRatio)[0];if(!visible)return;document.querySelectorAll('[data-jump]').forEach(button=>button.classList.toggle('is-active',button.dataset.jump===visible.target.id))},{rootMargin:'-140px 0px -55% 0px',threshold:[0,.2,.5]});
  document.querySelectorAll('[data-form-section]').forEach(el=>observer.observe(el));
  document.querySelector('#exportButton').addEventListener('click',download);document.querySelector('#importButton').addEventListener('click',()=>document.querySelector('#importInput').click());
  document.querySelector('#importInput').addEventListener('change',event=>{const file=event.target.files[0];if(!file)return;const reader=new FileReader();reader.onload=()=>{try{config=normalize(JSON.parse(String(reader.result)));renderForm();renderPreview();scheduleSave();showToast('配置导入成功')}catch{showToast('配置文件格式不正确')}event.target.value=''};reader.readAsText(file)});
  document.querySelector('#resetButton').addEventListener('click',()=>{if(!window.confirm('确定恢复示例内容吗？当前未导出的修改会被覆盖。'))return;config=clone(defaults);renderForm();renderPreview();scheduleSave();showToast('已恢复示例内容')});
  document.querySelector('#previewTop').addEventListener('click',()=>{const reportScreen=preview.contentDocument?.querySelector('[data-screen="report"]');if(reportScreen)reportScreen.scrollTo({top:0,behavior:'smooth'});else preview.contentWindow?.scrollTo({top:0,behavior:'smooth'})});
  preview.addEventListener('load',renderPreview);
  renderForm();renderPreview();
})();
