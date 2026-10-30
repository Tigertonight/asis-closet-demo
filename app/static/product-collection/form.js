(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const names = ['商品信息','价格库存','商品素材','上架检查'];
  const descriptions = ['先介绍商品和对接人。','按本次直播的实际安排填写。','让工作人员更了解你的商品。','核对完成情况后，即可提交。'];
  let schema, step = 1, busy = false, photo = null, photoUrl = '', photoVersion = 0, requestId = '', photoPending = false;
  const makeId = () => crypto.randomUUID ? crypto.randomUUID() : [...crypto.getRandomValues(new Uint8Array(16))].map((v,i) => ((i===6 ? (v & 15) | 64 : i===8 ? (v & 63) | 128 : v).toString(16).padStart(2,'0'))).join('').replace(/(.{8})(.{4})(.{4})(.{4})(.{12})/,'$1-$2-$3-$4-$5');
  function el(tag, text, cls) { const n = document.createElement(tag); if(text) n.textContent=text; if(cls)n.className=cls; return n; }
  function inputField(field, key=field.key) {
    const wrap=el('div','','field'), label=el('label',field.label); label.htmlFor=key;
    label.append(el('span',field.required?' *':'选填',field.required?'required':'optional'));
    const input=el(field.type==='textarea'?'textarea':field.type==='status'?'select':'input'); input.id=key; input.name=key;
    input.required=!!field.required; input.maxLength=field.type==='textarea'||field.type==='url'?2000:200;
    if(field.type==='status') for(const [value,text] of [['','待确认'],['yes','是'],['no','否']]) { const option=el('option',text); option.value=value; input.append(option); }
    else { if(input.tagName==='INPUT')input.type=field.type==='url'?'url':'text'; input.placeholder=field.type==='url'?'https://…':`请填写${field.label}`; }
    if(field.type==='money'||field.type==='integer') { input.inputMode=field.type==='money'?'decimal':'numeric'; input.pattern=field.type==='money'?'[0-9]{1,9}([.][0-9]{1,2})?':'[0-9]{1,9}'; input.placeholder=field.type==='money'?'例如：99.00':'填写非负整数，例如：100'; }
    if(key==='contact')input.autocomplete='name';
    if(key==='contact_method')input.placeholder='手机号或微信号，填写一种即可';
    wrap.append(label,input);
    if(key==='dimensions') { const hint=el('p',schema.dimensions_help,'hint');hint.id='dimensionsHint';input.setAttribute('aria-describedby',hint.id);wrap.append(hint); }
    return wrap;
  }
  function build() {
    const sections=$('sections'); sections.replaceChildren(); document.querySelector('.steps').replaceChildren();
    names.forEach((name,i)=>{ const button=el('button',name);button.type='button';button.append(el('span',`0${i+1}`));button.onclick=()=>{if(!busy)showStep(i+1);};document.querySelector('.steps').append(button);
      const section=el('section');section.dataset.step=i+1;const title=el('div','','group-title');title.append(el('h2',name),el('p',descriptions[i]));section.append(title);sections.append(section); });
    for(const field of schema.fields) {
      const section=sections.querySelector(`[data-step="${field.group}"]`);
      if(field.type==='selling') {
        const group=el('fieldset','','selling-fields');group.append(el('legend','商品卖点'));
        for(const f of schema.selling_fields) { const node=inputField({...f,type:['introduction','features','differentiation','celebrity'].includes(f.key)?'textarea':'text'},`selling_${f.key}`); node.querySelector('input,textarea').maxLength=1000;
          if(['pregnancy','sensitive_skin'].includes(f.key))node.querySelector('input').placeholder='可用 / 不可用 / 不适用 / 待确认';group.append(node); }
        section.append(group);continue;
      }
      if(field.type==='image') {
        const box=el('div','','field upload'), label=el('label','产品白底图');label.htmlFor='photo'; label.append(el('span','选填','optional'));
        const input=el('input');input.type='file';input.id='photo';input.accept='image/jpeg,image/png,image/webp'; input.setAttribute('aria-describedby','photoHint');
        const hint=el('p','上传高清大图，支持 JPG、PNG、WebP，单张不超过 20MB。','hint');hint.id='photoHint';
        const img=el('img','','image-preview');img.id='preview';img.alt='所选商品白底图';img.hidden=true;
        const remove=el('button','移除图片','small-action');remove.id='removePhoto';remove.type='button';remove.hidden=true;remove.onclick=clearPhoto;
        const error=el('p','','error');error.id='photoError';error.setAttribute('role','alert');
        input.onchange=()=>selectPhoto(input.files[0]);box.append(label,input,hint,img,remove,error);section.append(box);continue;
      }
      section.append(inputField(field));
    }
  }
  function clearPhoto(){photoVersion++;photoPending=false;photo=null;if(photoUrl)URL.revokeObjectURL(photoUrl);photoUrl='';$('photo').value='';$('preview').hidden=true;$('preview').removeAttribute('src');$('removePhoto').hidden=true;$('photoError').textContent='';}
  async function selectPhoto(file){
    if(!file)return;const version=++photoVersion;photoPending=false;$('photoError').textContent='';
    if(file.size>20*1024*1024 || !['image/jpeg','image/png','image/webp'].includes(file.type)){ $('photoError').textContent='请选择 20MB 以内的 JPG、PNG 或 WebP 图片。';$('photo').value='';return; }
    photoPending=true;const url=URL.createObjectURL(file), img=new Image();img.src=url;
    try{await img.decode();if(version!==photoVersion){URL.revokeObjectURL(url);return;}if(img.naturalWidth*img.naturalHeight>40000000)throw Error('size');
      if(photoUrl)URL.revokeObjectURL(photoUrl);photoUrl=url;photo=file;$('preview').src=url;$('preview').hidden=false;$('removePhoto').hidden=false;
    }catch{URL.revokeObjectURL(url);if(version===photoVersion){$('photoError').textContent='图片无法读取或尺寸过大，请重新选择。';$('photo').value='';}}finally{if(version===photoVersion)photoPending=false;}
  }
  function showStep(value){step=value;document.querySelectorAll('[data-step]').forEach(s=>s.hidden=Number(s.dataset.step)!==step);document.querySelectorAll('.steps button').forEach((b,i)=>{if(i+1===step)b.setAttribute('aria-current','step');else b.removeAttribute('aria-current');});$('previous').hidden=step===1;$('next').hidden=step===4;$('submit').hidden=step!==4;$('formError').textContent='';}
  function validate(section){
    for(const input of section.querySelectorAll('input:not([type=file]),textarea,select')){input.value=input.value.trim();input.removeAttribute('aria-invalid');if(!input.checkValidity()) {showStep(Number(input.closest('[data-step]').dataset.step));input.setAttribute('aria-invalid','true');input.reportValidity();return false;}}
    return true;
  }
  function payload(){const data={};for(const f of schema.fields){if(f.type==='image')continue;data[f.key]=f.type==='selling'?Object.fromEntries(schema.selling_fields.map(s=>[s.key,$(`selling_${s.key}`).value.trim()])):$(f.key).value.trim();}return data;}
  function setBusy(value){busy=value;$('intake').querySelectorAll('button,input,textarea,select').forEach(n=>n.disabled=value);$('submit').textContent=value?'正在提交…':'提交商品信息';$('uploadStatus').textContent=value?'正在保存商品信息和图片，请稍候。':'';}
  $('previous').onclick=()=>showStep(step-1);
  $('next').onclick=()=>{if(validate(document.querySelector(`[data-step="${step}"]`))){showStep(step+1);$('intake').scrollIntoView({block:'start'});}};
  $('intake').onsubmit=async e=>{
    e.preventDefault();if(busy||!validate($('intake')))return;
    if(photoPending){$('formError').textContent='图片还在准备中，请稍候再提交。';return;}
    const form=new FormData();form.set('payload',JSON.stringify(payload()));form.set('request_id',requestId);if(photo)form.set('photo',photo);
    setBusy(true);$('formError').textContent='';
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),90000);
    try{const response=await fetch('/api/v1/selfit/product-collection',{method:'POST',body:form,signal:controller.signal});let data;try{data=await response.json();}catch{throw Error('暂时无法提交，请稍后重试。已填写的内容会保留。');}
      if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:data.error?.message||'请检查填写内容，或稍后重试。');
      $('intake').hidden=true;$('intro').hidden=true;$('success').hidden=false;$('receipt').textContent=`登记编号：${data.id}`;$('success').focus();window.scrollTo(0,0);
    }catch(error){$('formError').textContent=error.name==='AbortError'?'提交超时，请重试。重复点击不会重复登记。':error instanceof TypeError?'连接中断，请重试。已填写的内容会保留。':error.message||'暂时无法提交，请稍后重试。';$('formError').focus();}
    finally{clearTimeout(timer);setBusy(false);}
  };
  $('another').onclick=()=>{requestId=makeId();$('intake').reset();clearPhoto();$('success').hidden=true;$('intro').hidden=false;$('intake').hidden=false;showStep(1);window.scrollTo(0,0);};
  async function load(){ $('reload').hidden=true;$('loading').hidden=false;$('loading').textContent='正在准备表单…';try{const response=await fetch('/api/v1/selfit/product-collection/schema');if(!response.ok)throw Error();schema=await response.json();requestId=makeId();build();$('loading').hidden=true;$('intake').hidden=false;showStep(1);}catch{$('loading').textContent='表单暂时无法加载，请重试。';$('reload').hidden=false;}}
  $('reload').onclick=load;void load();
})();
