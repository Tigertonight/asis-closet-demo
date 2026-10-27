(() => {
  const $ = id => document.getElementById(id);
  const button = $('xhsOpen'), status = $('xhsStatus');
  let payload = null, busy = false, attempt = 0;
  const fresh = () => payload?.expiresAt > Date.now() + 1000;
  const mobile = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent || '');
  $('xhsBack').onclick = () => {
    if (history.length > 1) history.back(); else location.replace('/selfit/stamp');
  };
  // Consume the handoff before loading any third-party JS. The receipt secret
  // stays in the previous page's fragment, never this URL or this handoff.
  try {
    payload = JSON.parse(sessionStorage.getItem('selfit.xhsShare'));
    sessionStorage.removeItem('selfit.xhsShare');
    const image = new URL(payload.shareInfo.images[0]);
    const localHttp = image.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(image.hostname);
    if (payload.shareInfo.type !== 'normal' || payload.shareInfo.images.length !== 1 || (image.protocol !== 'https:' && !localHttp) ||
        image.origin !== location.origin || !/^\/api\/v1\/selfit\/mirror\/photos\/mp_[a-f0-9]{32}\/files\/print\.png$/.test(image.pathname) ||
        !payload.verifyConfig?.appKey || !fresh()) throw new Error('Invalid handoff');
  } catch (_) {
    status.textContent = '分享准备已过期，请返回领图页重新点击分享。'; return;
  }
  $('xhsPhoto').src = payload.shareInfo.images[0];
  $('xhsPhotoFrame').hidden = false;
  if (!mobile) { status.textContent = '请在手机上打开领图链接，再分享到小红书。'; return; }

  const script = document.createElement('script');
  script.src = 'https://fe-static.xhscdn.com/biz-static/goten/xhs-1.0.1.js';
  script.referrerPolicy = 'no-referrer'; script.async = true;
  const timeout = setTimeout(() => {
    status.textContent = '分享组件加载较慢，请返回重试或先保存照片。';
  }, 15000);
  script.onload = () => {
    clearTimeout(timeout);
    if (!window.xhs?.share) { status.textContent = '分享组件暂不可用，请返回重试或先保存照片。'; return; }
    status.textContent = '点击下方按钮，在小红书中继续编辑。'; button.disabled = false;
  };
  script.onerror = () => { clearTimeout(timeout); status.textContent = '分享组件未加载成功，请返回重试或先保存照片。'; };
  document.head.append(script);

  button.onclick = () => {
    if (busy) return;
    if (!fresh()) { button.disabled = true; status.textContent = '分享准备已过期，请返回领图页重新点击分享。'; return; }
    busy = true; button.disabled = true;
    const current = ++attempt;
    status.textContent = '正在打开小红书，请在编辑页确认内容。';
    let failed = false;
    const fail = () => {
      if (current !== attempt) return;
      failed = true; busy = false; button.disabled = false;
      status.textContent = '暂时无法打开小红书，请确认已安装 App；也可以返回保存照片后分享。';
    };
    // Call the SDK directly within the tap. A resolved SDK promise only means
    // an app-opening attempt, never a successful post or a confirmed app launch.
    try {
      const result = window.xhs.share({shareInfo: payload.shareInfo, verifyConfig: payload.verifyConfig, fail});
      Promise.resolve(result).then(() => {
        if (!failed && current === attempt) { busy = false; button.disabled = false; }
      }, fail);
    } catch (_) { fail(); }
    setTimeout(() => {
      if (current === attempt && busy) { attempt++; busy = false; button.disabled = false; status.textContent = '打开小红书有些久，请重试或返回保存照片。'; }
    }, 15000);
  };
})();
