(() => {
  const $ = id => document.getElementById(id);
  const match = location.hash.slice(1).match(/^(mp_[a-f0-9]{32})\.([a-f0-9]{64})$/);
  const path = match ? `/api/v1/selfit/mirror/photos/${match[1]}` : '';
  let generation = 0, info = null, files = [], urls = [], preparing = [];
  const objectUrl = blob => { const url = URL.createObjectURL(blob); urls.push(url); return url; };
  async function get(variant) {
    const response = await fetch(`${path}/${variant}`, { cache: 'no-store', headers: { Authorization: `Bearer ${match[2]}` }, signal: AbortSignal.timeout(45000) });
    if (!response.ok) { const data = await response.json().catch(() => ({})); throw new Error(typeof data.detail === 'string' ? data.detail : data.error?.message || '照片暂时无法加载，请重试。'); }
    return response;
  }
  const errorText = e => e.name === 'TimeoutError' ? '加载有些久，请检查网络后重试。' : e instanceof TypeError ? '网络暂时无法连接，请检查网络后重试。' : e.message;
  function updateShare() {
    const complete = info && files[0] && (!info.hasScene || files[1]);
    let supported = false;
    try { supported = !!(complete && navigator.share && navigator.canShare?.({ files })); } catch (_) {}
    $('phoneShare').hidden = !supported;
    $('phoneShare').textContent = files.length > 1 ? '分享两张照片' : '分享照片';
  }
  function prepareFile(index) {
    if (files[index]) return Promise.resolve(files[index]);
    if (preparing[index]) return preparing[index];
    const current = generation, hasScene = info.hasScene;
    preparing[index] = (async () => {
      const blob = await (await get(index ? 'scene-download' : 'download')).blob();
      if (current !== generation) return null;
      files[index] = new File([blob], hasScene ? (index ? 'WOKEN-DAY-MACHINE.png' : 'WOKEN-DAY-STAMP.png') : 'selfit-photo.png', { type: 'image/png' });
      updateShare(); return files[index];
    })().finally(() => { if (current === generation) preparing[index] = null; });
    return preparing[index];
  }
  async function load() {
    const current = ++generation;
    for (const url of urls) URL.revokeObjectURL(url); urls = []; files = []; preparing = []; info = null;
    $('phoneShare').hidden = true; $('phoneSceneSection').hidden = true; $('phoneRetry').hidden = true;
    $('phoneSaveHint').hidden = true; $('phoneDownload').disabled = true; $('phonePhoto').hidden = true;
    $('phoneStatus').textContent = '正在加载照片…'; $('phoneIntro').textContent = '';
    if (!match) { $('phoneStatus').textContent = '领取链接不完整，请重新扫描智能镜上的二维码。'; $('phonePhotoFrame').hidden = true; $('phoneDownload').hidden = true; return; }
    $('phonePhotoFrame').hidden = false; $('phoneDownload').hidden = false;
    try {
      const [metadata, blob] = await Promise.all([get('info').then(r => r.json()), get('preview').then(r => r.blob())]);
      if (current !== generation) return;
      info = metadata;
      $('phonePhoto').src = objectUrl(blob); await $('phonePhoto').decode();
      if (current !== generation) return;
      $('phonePhoto').hidden = false; $('phoneIntro').textContent = info.hasScene ? '你的周年邮票和出片机展示图，已经准备好了' : '你的照片，已经准备好了';
      $('phoneDownload').disabled = false; $('phoneDownload').textContent = info.hasScene ? '保存高清邮票' : '保存高清照片';
      $('phoneStatus').textContent = '高清成片包含你选好的模板与效果';
      $('phoneExpiry').textContent = `请在 ${new Date(info.expiresAt).toLocaleString('zh-CN')} 前领取照片`;
      void prepareFile(0).catch(() => {});
      if (info.hasScene) {
        void prepareFile(1).catch(() => {});
        document.body.classList.add('woken'); $('phoneBrand').hidden = true; $('phoneBrandName').hidden = false;
        $('phoneSceneSection').hidden = false;
        const sceneBlob = await (await get('scene-preview')).blob();
        if (current !== generation) return;
        $('phoneScene').src = objectUrl(sceneBlob); await $('phoneScene').decode();
      }
    } catch (e) {
      if (current !== generation) return;
      $('phoneStatus').textContent = errorText(e); $('phoneRetry').hidden = false;
      if (!info || $('phonePhoto').hidden) { $('phonePhotoFrame').hidden = true; $('phoneDownload').hidden = true; }
    }
  }
  async function download(index) {
    const current = generation, button = $(index ? 'phoneSceneDownload' : 'phoneDownload'), label = button.textContent;
    button.disabled = true; button.textContent = '正在准备高清照片…';
    try {
      const ready = await prepareFile(index); if (current !== generation || !ready) return;
      const url = objectUrl(ready); $(index ? 'phoneScene' : 'phonePhoto').src = url;
      const a = document.createElement('a'); a.href = url; a.download = ready.name; document.body.append(a); a.click(); a.remove();
      $('phoneStatus').textContent = '高清照片已准备好'; $('phoneSaveHint').hidden = false;
    } catch (e) { if (current === generation) $('phoneStatus').textContent = errorText(e); }
    finally { if (current === generation) { button.disabled = false; button.textContent = label; } }
  }
  $('phoneDownload').onclick = () => download(0); $('phoneSceneDownload').onclick = () => download(1);
  $('phoneShare').onclick = async () => {
    // Files are prepared before the tap, preserving Safari's transient activation.
    const current = generation;
    try { await navigator.share({ files }); if (current === generation) $('phoneStatus').textContent = '照片已交给系统分享，请在目标应用中确认发布。'; }
    catch (e) { if (current === generation && e.name !== 'AbortError') $('phoneStatus').textContent = '暂时无法分享，可以保存照片后在小红书中发布。'; }
  };
  $('phoneRetry').onclick = load;
  addEventListener('pagehide', () => { generation++; for (const url of urls) URL.revokeObjectURL(url); urls = []; files = []; });
  addEventListener('pageshow', e => { if (e.persisted) void load(); });
  void load();
})();
