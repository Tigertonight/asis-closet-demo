(() => {
  const shell = document.querySelector('#studio, #appShell');
  if (!shell) return;
  const entry = document.createElement('button');
  entry.type = 'button'; entry.className = 'feedback-entry'; entry.textContent = '反馈';
  entry.setAttribute('aria-label', '问题反馈');
  function placeEntry() {
    const target = shell.id === 'studio'
      ? (shell.dataset.screen === 'profile' ? shell.querySelector('.profile-header') : null)
      : shell;
    if (!target) { if (entry.parentNode) entry.remove(); return; }
    if (entry.parentNode !== target) {
      if (shell.id === 'studio') target.querySelector('span[aria-hidden]')?.remove();
      target.append(entry);
    }
  }
  new MutationObserver(placeEntry).observe(shell, {childList:true, subtree:true, attributes:true, attributeFilter:['class','data-screen']});
  placeEntry();
  const page = document.createElement('dialog'); page.className = 'feedback-page';
  page.setAttribute('aria-labelledby', 'feedback-title');
  page.innerHTML = `<form class="feedback-form"><header><button type="button" class="feedback-back" aria-label="返回">‹</button><h1 id="feedback-title">问题反馈</h1><span></span></header><div class="feedback-content"><p class="feedback-intro">告诉我们遇到的问题，帮助我们把 selfit 做得更好。</p><label for="feedback-description">问题说明</label><textarea id="feedback-description" placeholder="请描述遇到的问题，或你希望改进的地方…" maxlength="2000" required></textarea><div class="feedback-count">0 / 2000</div><label for="feedback-photo">添加照片 <span>（选填）</span></label><label class="feedback-upload" for="feedback-photo"><span>＋<br>上传照片</span><img alt="反馈照片预览" hidden></label><input id="feedback-photo" type="file" accept="image/jpeg,image/png,image/webp" hidden><button type="button" class="feedback-remove" hidden>移除照片</button><p class="feedback-help">支持 JPG、PNG、WebP，最多 10MB</p><p class="feedback-error" role="alert"></p></div><footer><button class="feedback-submit" type="submit">提交反馈</button></footer></form>`;
  document.body.append(page);
  const form=page.querySelector('form'), text=page.querySelector('textarea'), input=page.querySelector('input');
  const error=page.querySelector('.feedback-error'), submit=page.querySelector('.feedback-submit'), remove=page.querySelector('.feedback-remove'), preview=page.querySelector('img');
  let objectURL='', requestId='', busy=false, generation=0, source='';
  function clearPhoto() { if(objectURL) URL.revokeObjectURL(objectURL); objectURL=''; input.value=''; preview.hidden=true; preview.removeAttribute('src'); remove.hidden=true; }
  function close() { generation++; page.close(); clearPhoto(); entry.focus(); }
  entry.onclick=()=>{form.reset(); clearPhoto(); error.textContent=''; busy=false; submit.disabled=false; submit.textContent='提交反馈'; requestId=crypto.randomUUID(); source=location.pathname+':'+(shell.dataset.screen||new URLSearchParams(location.search).get('screen')||'app'); page.querySelector('.feedback-count').textContent='0 / 2000';page.showModal();};
  page.querySelector('.feedback-back').onclick=close;
  page.addEventListener('cancel', e=>{e.preventDefault();close();});
  text.oninput=()=>page.querySelector('.feedback-count').textContent=`${text.value.length} / 2000`;
  remove.onclick=clearPhoto;
  preview.onerror=()=>{clearPhoto();error.textContent="照片无法读取，请换一张照片。";};
  input.onchange=()=>{const file=input.files[0]; if(!file)return; if(!['image/jpeg','image/png','image/webp'].includes(file.type)||file.size>10*1024*1024){error.textContent='请选择 10MB 以内的 JPG、PNG 或 WebP 照片。';clearPhoto();return;} if(objectURL)URL.revokeObjectURL(objectURL);objectURL=URL.createObjectURL(file);preview.src=objectURL;preview.hidden=false;remove.hidden=false;error.textContent='';};
  form.onsubmit=async e=>{e.preventDefault();if(busy)return;if(!text.value.trim()){error.textContent='请填写问题说明。';text.focus();return;}busy=true;submit.disabled=true;submit.textContent='提交中…';error.textContent='';const version=generation;
    const data=new FormData();data.append('description',text.value.trim());data.append('request_id',requestId);data.append('source',source);if(input.files[0])data.append('photo',input.files[0]);
    const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),30000);
    try {const auth=window.SelfitAuth?.createClient({mode:'live'});const session=auth?.readStoredSession();const token=session?.accessToken;const response=await fetch('/api/v1/selfit/feedback',{method:'POST',signal:controller.signal,headers:token?{Authorization:`Bearer ${token}`}:{},body:data});const result=await response.json();if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:'提交失败，请稍后重试。');if(version!==generation)return;close();const notice=document.createElement('div');notice.className='feedback-toast';notice.setAttribute('role','status');notice.textContent='反馈已收到，谢谢你的帮助。';document.body.append(notice);setTimeout(()=>notice.remove(),3000);
    }catch(err){if(version===generation)error.textContent=err.name==='AbortError'?'提交超时，请重试。':(err.message||'网络连接失败，请重试。');}finally{clearTimeout(timeout);if(version===generation){busy=false;submit.disabled=false;submit.textContent='提交反馈';}}};
})();
