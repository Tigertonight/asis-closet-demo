(() => {
  const $ = id => document.getElementById(id);
  const match = location.hash.slice(1).match(/^(mp_[a-f0-9]{32})\.([a-f0-9]{64})$/);
  const path = match ? `/api/v1/selfit/mirror/photos/${match[1]}` : '';
  let generation = 0, info = null, files = [], preparing = [], refreshing = null, refreshTimer = 0;
  const imageLinks = () => info?.imageLinks?.print;
  const linksFresh = () => info?.imageLinks?.expiresAt > Date.now() + 1000;
  async function get(variant) {
    const response = await fetch(`${path}/${variant}`, { cache: 'no-store', headers: { Authorization: `Bearer ${match[2]}` }, signal: AbortSignal.timeout(45000) });
    if (!response.ok) { const data = await response.json().catch(() => ({})); throw new Error(typeof data.detail === 'string' ? data.detail : data.error?.message || '照片暂时无法加载，请重试。'); }
    return response;
  }
  const errorText = e => e.name === 'TimeoutError' ? '加载有些久，请检查网络后重试。' : e instanceof TypeError ? '网络暂时无法连接，请检查网络后重试。' : e.message;
  function updateShare() {
    const complete = info && files[0];
    let supported = false;
    try { supported = !!(complete && navigator.share && navigator.canShare?.({ files })); } catch (_) {}
    $('phoneShare').hidden = !supported;
    $('phoneShare').textContent = info?.edition === 'woken' ? '分享邮票' : '分享照片';
  }
  function prepareFile() {
    const index = 0;
    if (files[index]) return Promise.resolve(files[index]);
    if (preparing[index]) return preparing[index];
    const current = generation, isStamp = info.edition === 'woken';
    preparing[index] = (async () => {
      const blob = await (await get('download')).blob();
      if (current !== generation) return null;
      files[index] = new File([blob], isStamp ? 'WOKEN-DAY-STAMP.png' : 'selfit-photo.png', { type: 'image/png' });
      updateShare(); return files[index];
    })().finally(() => { if (current === generation) preparing[index] = null; });
    return preparing[index];
  }
  function applyLinks() {
    const link = $('phoneOriginal'), value = imageLinks();
    link.hidden = !value;
    if (value) link.href = value.view;
    clearTimeout(refreshTimer);
    const remaining = info.imageLinks.expiresAt - Date.now();
    // Renew before expiry while visible. Near the receipt's final expiry, let
    // the user finish saving rather than repeatedly requesting the same link.
    refreshTimer = setTimeout(() => {
      if (!document.hidden) void refreshLinks().catch(() => {});
    }, Math.max(1000, remaining > 60000 ? remaining - 60000 : remaining + 100));
  }
  function refreshLinks() {
    if (refreshing) return refreshing;
    const current = generation;
    refreshing = (async () => {
      const metadata = await (await get('info')).json();
      if (current !== generation) return;
      info = metadata; applyLinks();
      // Keep long-press saving usable after the page has been left open.
      $('phonePhoto').src = imageLinks().view;
    })().finally(() => { if (current === generation) refreshing = null; });
    return refreshing;
  }
  async function load() {
    const current = ++generation;
    clearTimeout(refreshTimer); files = []; preparing = []; refreshing = null; info = null;
    $('phoneShare').hidden = true; $('phoneRetry').hidden = true;
    $('phoneOriginal').hidden = true;
    $('phoneSaveHint').hidden = true; $('phoneDownload').disabled = true; $('phonePhoto').hidden = true;
    $('phoneStatus').textContent = '正在加载照片…'; $('phoneIntro').textContent = '';
    if (!match) { $('phoneStatus').textContent = '领取链接不完整，请重新扫描智能镜上的二维码。'; $('phonePhotoFrame').hidden = true; $('phoneDownload').hidden = true; return; }
    $('phonePhotoFrame').hidden = false; $('phoneDownload').hidden = false;
    try {
      const metadata = await (await get('info')).json();
      if (current !== generation) return;
      info = metadata; applyLinks();
      // A real, privately signed PNG URL also works for native long-press save.
      // Do not replace this with a JS-owned blob URL.
      $('phonePhoto').src = imageLinks().view; await $('phonePhoto').decode();
      if (current !== generation) return;
      $('phonePhoto').hidden = false; $('phoneIntro').textContent = info.edition === 'woken' ? '你的周年邮票，已经准备好了' : '你的照片，已经准备好了';
      $('phoneDownload').disabled = false; $('phoneDownload').textContent = info.edition === 'woken' ? '保存高清邮票' : '保存高清照片';
      $('phoneStatus').textContent = '高清成片包含你选好的模板与效果';
      $('phoneSaveHint').hidden = false;
      $('phoneExpiry').textContent = `请在 ${new Date(info.expiresAt).toLocaleString('zh-CN')} 前领取照片`;
      if (navigator.share && navigator.canShare) void prepareFile().catch(() => {});
      if (info.edition === 'woken') {
        document.body.classList.add('woken'); $('phoneBrand').hidden = true; $('phoneBrandName').hidden = false;
      }
    } catch (e) {
      if (current !== generation) return;
      $('phoneStatus').textContent = errorText(e); $('phoneRetry').hidden = false;
      if (!info || $('phonePhoto').hidden) { $('phonePhotoFrame').hidden = true; $('phoneDownload').hidden = true; }
    }
  }
  async function renewForTap() {
    const current = generation;
    $('phoneStatus').textContent = '正在更新下载链接…';
    try {
      await refreshLinks();
      if (current === generation) $('phoneStatus').textContent = '链接已更新，请再次点击保存或打开高清原图。';
    } catch (e) { if (current === generation) $('phoneStatus').textContent = errorText(e); }
  }
  function download() {
    if (!linksFresh()) { void renewForTap(); return; }
    // Run during the tap, without awaiting a fetch, to preserve user activation.
    const a = document.createElement('a'); a.href = imageLinks().download;
    a.download = info.edition === 'woken' ? 'WOKEN-DAY-STAMP.png' : 'selfit-photo.png';
    a.referrerPolicy = 'no-referrer'; document.body.append(a); a.click(); a.remove();
    $('phoneStatus').textContent = '已发起下载；如未开始，请打开高清原图后长按保存。';
  }
  $('phoneDownload').onclick = download;
  $('phoneOriginal').onclick = event => {
    if (!linksFresh()) { event.preventDefault(); void renewForTap(); }
  };
  $('phoneShare').onclick = async () => {
    // Files are prepared before the tap, preserving Safari's transient activation.
    const current = generation;
    try { await navigator.share({ files }); if (current === generation) $('phoneStatus').textContent = '照片已交给系统分享，请在目标应用中确认发布。'; }
    catch (e) { if (current === generation && e.name !== 'AbortError') $('phoneStatus').textContent = '暂时无法分享，可以保存照片后在小红书中发布。'; }
  };
  $('phoneRetry').onclick = load;
  addEventListener('visibilitychange', () => {
    if (!document.hidden && info && info.imageLinks.expiresAt < Date.now() + 60000) void refreshLinks().catch(() => {});
  });
  addEventListener('pagehide', () => { generation++; clearTimeout(refreshTimer); files = []; });
  addEventListener('pageshow', e => { if (e.persisted) void load(); });
  void load();
})();
