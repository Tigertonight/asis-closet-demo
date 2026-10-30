(() => {
  'use strict';
  window.ProductCollectionAdmin = ({api,onAuthError}) => {
    const $=id=>document.getElementById(id);
    let generation=0, detailGeneration=0, cursor=null, query='', schema=null, previewUrl='';
    let deleteGeneration=0, pendingDelete=null, deleting=false;
    const element=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
    const date=value=>new Date(value).toLocaleString('zh-CN',{hour12:false,timeZone:'Asia/Shanghai'});
    const fail=(error,target)=>{target.textContent=error.message||'加载失败，请重试。';if(error.status===401||error.status===403)onAuthError();};
    async function response(path){const r=await fetch(path,{credentials:'same-origin',cache:'no-store'});if(!r.ok){let data={};try{data=await r.json();}catch{}const error=Error([401,403].includes(r.status)?'登录已失效，请重新登录':typeof data.detail==='string'?data.detail:'请求失败，请重试。');error.status=r.status;throw error;}return r;}
    async function download(path,filename){const version=generation,r=await response(path),blob=await r.blob();if(version!==generation)throw Error('操作已取消，请重新尝试。');const url=URL.createObjectURL(blob),a=element('a');a.href=url;a.download=filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);}
    function closeDetail(){detailGeneration++;$('productDetail').close();$('productDetailBody').replaceChildren();if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl='';}
    function closeDelete(force=false){
      if(deleting&&!force)return;
      deleteGeneration++;pendingDelete=null;deleting=false;$('productDelete').close();
      $('productDeleteConfirm').disabled=false;$('productDeleteCancel').disabled=false;
      $('productDeleteConfirm').textContent='确认删除';$('productDeleteError').textContent='';
    }
    function askDelete(record){
      if(deleting)return;
      deleteGeneration++;pendingDelete={id:record.id,name:record.product_name,brand:record.brand};
      $('productDeleteTarget').textContent=`${record.brand} · ${record.product_name}（编号 #${record.id}）`;
      $('productDeleteError').textContent='';$('productDelete').showModal();
    }
    async function confirmDelete(){
      if(deleting||!pendingDelete)return;
      const target=pendingDelete,version=deleteGeneration;deleting=true;
      $('productDeleteConfirm').disabled=true;$('productDeleteCancel').disabled=true;
      $('productDeleteConfirm').textContent='正在删除…';$('productDeleteError').textContent='';
      try{
        await api(`/product-collection-admin/api/products/${target.id}`,{method:'DELETE'});
        if(version!==deleteGeneration)return;
        closeDelete(true);closeDetail();
        $('productActionStatus').textContent=`已删除「${target.name}」，统计及导出将不再包含这条信息。`;
        await load();
      }catch(error){if(version===deleteGeneration)fail(error,$('productDeleteError'));}
      finally{if(version===deleteGeneration){deleting=false;$('productDeleteConfirm').disabled=false;$('productDeleteCancel').disabled=false;$('productDeleteConfirm').textContent='确认删除';}}
    }
    async function detail(id){
      closeDetail();const version=++detailGeneration;$('productDetailTitle').textContent='商品信息';$('productDetailBody').textContent='正在加载…';$('productDetail').showModal();
      try{
        const [record,fields]=await Promise.all([api(`/product-collection-admin/api/products/${id}`),schema?Promise.resolve(schema):api('/api/v1/selfit/product-collection/schema')]);
        if(version!==detailGeneration)return;schema=fields;
        $('productDetailTitle').textContent=`${record.data.product_name} · #${record.id}`;const body=$('productDetailBody');body.replaceChildren();body.append(element('p',`提交时间：${date(record.created_at)}（北京时间）`));
        const list=element('dl');list.className='product-detail-list';body.append(list);
        for(const field of schema.fields){list.append(element('dt',field.label));const value=element('dd');list.append(value);
          if(field.type==='image'){
            if(!record.image){value.textContent='未上传';continue;}
            const img=element('img');img.alt='商品白底图';img.className='product-detail-image';value.append(img);
            const status=element('span','图片加载中…');value.append(status);
            const button=element('button','下载高清原图','feedback-action');button.type='button';value.append(button);button.onclick=async()=>{button.disabled=true;try{const ext={'image/jpeg':'jpg','image/png':'png','image/webp':'webp'}[record.image.mime];await download(`/product-collection-admin/api/products/${id}/image`,`product-${id}.${ext}`);}catch(e){status.textContent=e.message;}finally{button.disabled=false;}};
            response(`/product-collection-admin/api/products/${id}/image?preview=true`).then(r=>r.blob()).then(blob=>{if(version!==detailGeneration)return;previewUrl=URL.createObjectURL(blob);img.src=previewUrl;status.textContent=`原图 ${(record.image.bytes/1024/1024).toFixed(2)}MB`;}).catch(e=>{if(version===detailGeneration)fail(e,status);});
          }else if(field.type==='selling'){value.textContent=schema.selling_fields.map(f=>`${f.label}：${record.data.selling_points[f.key]||'未填写'}`).join('\n');}
          else if(field.type==='status')value.textContent={yes:'是',no:'否','':'待确认'}[record.data[field.key]];
          else if(field.type==='url'&&record.data[field.key]){const a=element('a',record.data[field.key]);a.href=record.data[field.key];a.target='_blank';a.rel='noopener noreferrer';value.append(a);}
          else value.textContent=record.data[field.key]||'未填写';
        }
        const remove=element('button','删除这条信息','danger-outline');remove.type='button';remove.onclick=()=>askDelete({id:record.id,...record.data});
        const actions=element('div',undefined,'detail-actions');actions.append(remove);body.append(actions);
      }catch(error){if(version===detailGeneration)fail(error,$('productDetailBody'));}
    }
    async function load(more=false){
      const version=++generation;$('productMore').disabled=true;$('productSummary').textContent='正在加载商品信息…';
      if(!more){cursor=null;query=$('productSearch').value.trim();$('productRows').replaceChildren();}
      const params=new URLSearchParams({q:query});if(more&&cursor)params.set('before_id',cursor);
      try{const data=await api(`/product-collection-admin/api/products?${params}`);if(version!==generation)return;
        $('productTotal').textContent=data.total;$('productToday').textContent=data.today;$('productFiltered').textContent=data.filtered;
        for(const row of data.items){const tr=element('tr');for(const text of [row.id,row.brand,row.product_name,row.category,date(row.created_at),row.has_image?'已上传':'未上传'])tr.append(element('td',text));const cell=element('td'),actions=element('div',undefined,'row-actions'),button=element('button','查看详情','mini-btn'),remove=element('button','删除','mini-btn danger-outline');button.type='button';button.onclick=()=>detail(row.id);remove.type='button';remove.setAttribute('aria-label',`删除 ${row.product_name}`);remove.onclick=()=>askDelete(row);actions.append(button,remove);cell.append(actions);tr.append(cell);$('productRows').append(tr);}
        cursor=data.next_cursor;$('productMore').hidden=!cursor;$('productSummary').textContent=data.filtered?`已展示 ${$('productRows').children.length} / ${data.filtered} 条${query?'筛选结果':''}`:'暂无符合条件的商品信息';
      }catch(error){if(version===generation)fail(error,$('productSummary'));}
      finally{if(version===generation)$('productMore').disabled=false;}
    }
    $('productSearchForm').onsubmit=e=>{e.preventDefault();void load();};$('productRefresh').onclick=()=>load();$('productMore').onclick=()=>load(true);
    $('productDetailClose').onclick=closeDetail;$('productDetail').addEventListener('cancel',e=>{e.preventDefault();closeDetail();});
    $('productDeleteCancel').onclick=()=>closeDelete();$('productDeleteConfirm').onclick=confirmDelete;
    $('productDelete').addEventListener('cancel',e=>{e.preventDefault();closeDelete();});
    $('productExport').onclick=async()=>{const button=$('productExport');button.disabled=true;button.textContent='正在导出…';$('productExportStatus').textContent='';try{await download(`/product-collection-admin/api/products/export.xlsx?${new URLSearchParams({q:query})}`,`直播商品信息-${new Date().toISOString().slice(0,10)}.xlsx`);$('productExportStatus').textContent='Excel 已生成并开始下载，包含当前筛选结果及商品缩略图。';}catch(e){fail(e,$('productExportStatus'));}finally{button.disabled=false;button.textContent='导出 Excel';}};
    return {load,reset(){generation++;closeDelete(true);closeDetail();$('productRows').replaceChildren();$('productSearch').value='';cursor=null;query='';for(const id of ['productTotal','productToday','productFiltered'])$(id).textContent='—';$('productSummary').textContent='';$('productExportStatus').textContent='';$('productActionStatus').textContent='';}};
  };
})();
