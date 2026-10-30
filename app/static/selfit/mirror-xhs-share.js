(() => {
  const $ = id => document.getElementById(id);
  const button = $('xhsOpen'), status = $('xhsStatus'), alternate = $('xhsAlternate');
  let payload = null, timer = null, leftPage = false, flow = 'prepared-link', busy = false, sdkPromise = null;
  const enteredAt = Date.now(), eventCounts = new Map();
  const fresh = () => payload?.expiresAt > Date.now() + 1000;
  let eventUrl = null, imageUrlEncoding = 'raw';
  const report = (event, errorCode = null) => {
    if (!eventUrl || (eventCounts.get(event) || 0) >= 5) return;
    eventCounts.set(event, (eventCounts.get(event) || 0) + 1);
    // Never send SDK error messages, signatures, launch URLs or receipt secrets in logs.
    const error_code = Number.isSafeInteger(errorCode) && Math.abs(errorCode) <= 2147483647 ? errorCode : null;
    try {
      void fetch(eventUrl, { method: 'POST', credentials: 'omit', keepalive: true,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event, flow, error_code, image_url_encoding: imageUrlEncoding, elapsed_ms: Math.min(3600000, Math.max(0, Date.now() - enteredAt)) }),
      }).catch(() => {});
    } catch (_) { /* Diagnostics must never block sharing. */ }
  };
  $('xhsBack').onclick = () => {
    if (history.length > 1) history.back(); else location.replace('/selfit/stamp');
  };
  // Only short-lived composed-image capabilities cross into this clean page.
  try {
    payload = JSON.parse(sessionStorage.getItem('selfit.xhsShare'));
    sessionStorage.removeItem('selfit.xhsShare');
    const image = new URL(payload.shareInfo.images[0]);
    const localHttp = image.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(image.hostname);
    if (payload.shareInfo.type !== 'normal' || payload.shareInfo.images.length !== 1 || (image.protocol !== 'https:' && !localHttp) ||
        image.origin !== location.origin || !/^\/api\/v1\/selfit\/mirror\/photos\/mp_[a-f0-9]{32}\/files\/print\.png$/.test(image.pathname) ||
        !payload.verifyConfig?.appKey || !fresh()) throw new Error('Invalid handoff');
    flow = payload.flow || 'prepared-link';
    if (flow === 'official-sdk') {
      if (payload.imageUrlEncoding && !['raw', 'component'].includes(payload.imageUrlEncoding)) throw new Error('Invalid image encoding');
      imageUrlEncoding = payload.imageUrlEncoding || 'component';
      if (!['nonce', 'timestamp', 'signature'].every(key => typeof payload.verifyConfig[key] === 'string' && payload.verifyConfig[key])) throw new Error('Invalid SDK config');
    } else if (flow === 'prepared-link') {
      const scheme = new URL(payload.launch.scheme), universal = new URL(payload.launch.universal);
      if (scheme.protocol !== 'xhsdiscover:' || scheme.hostname !== 'js_share_sdk' || scheme.username || scheme.password ||
          !scheme.searchParams.get('share_code') || scheme.searchParams.get('app_key') !== payload.verifyConfig.appKey ||
          universal.origin !== 'https://oia.xiaohongshu.com' || universal.pathname !== '/oia' || universal.username || universal.password ||
          universal.searchParams.get('deeplink') !== payload.launch.scheme) throw new Error('Invalid launch');
    } else throw new Error('Invalid flow');
    if (/^[a-f0-9]{64}$/.test(image.searchParams.get('signature') || '') && /^\d+$/.test(image.searchParams.get('expires') || '')) {
      const endpoint = new URL(image);
      endpoint.pathname = endpoint.pathname.replace('/files/print.png', '/share-events');
      endpoint.searchParams.delete('download');
      eventUrl = endpoint.href;
    }
  } catch (_) {
    status.textContent = '分享准备已过期，请返回领图页重新点击分享。'; return;
  }
  $('xhsPhoto').onload = () => report('preview_loaded');
  $('xhsPhoto').onerror = () => report('preview_failed');
  $('xhsPhoto').src = payload.shareInfo.images[0];
  $('xhsPhotoFrame').hidden = false;
  const inWeChat = payload.launch?.inWeChat || /MicroMessenger/i.test(navigator.userAgent || '');
  const expire = () => {
    button.disabled = true; alternate.hidden = true; alternate.removeAttribute('href');
    status.textContent = '分享准备已过期，请返回领图页重新点击分享。';
  };
  const opening = () => {
    clearTimeout(timer); leftPage = false;
    status.textContent = '正在打开小红书，请在编辑页确认内容。';
    timer = setTimeout(() => {
      if (!leftPage) status.textContent = inWeChat
        ? '若未跳转，请点击按钮继续。微信仍拦截时，请返回领图页再用浏览器打开，或保存照片后分享。'
        : '若未跳转，请点击按钮继续，并确认已安装小红书；也可返回保存照片。';
    }, 2500);
  };
  const leave = () => { leftPage = true; clearTimeout(timer); };
  addEventListener('pagehide', leave);
  addEventListener('visibilitychange', () => {
    if (document.hidden) { report('page_hidden'); leave(); }
    else { report('page_returned'); if (!fresh()) expire(); }
  });

  if (flow === 'official-sdk') {
    // The SDK checks/token from the phone browser and uses its own iOS handoff.
    // Do not silently fall back to server-prepared codes when diagnosing import.
    const loadSdk = () => {
      if (typeof globalThis.xhs?.share === 'function') return Promise.resolve();
      if (sdkPromise) return sdkPromise;
      sdkPromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        let settled = false;
        const finish = ok => {
          if (settled) return;
          settled = true; clearTimeout(timeout);
          if (ok) resolve(); else { script.remove(); reject(new Error('SDK unavailable')); }
        };
        const timeout = setTimeout(() => finish(false), 8000);
        script.src = 'https://fe-static.xhscdn.com/biz-static/goten/xhs-1.0.1.js';
        script.async = true; script.referrerPolicy = 'no-referrer';
        script.onload = () => finish(typeof globalThis.xhs?.share === 'function');
        script.onerror = () => finish(false);
        document.head.append(script);
      }).finally(() => { sdkPromise = null; });
      return sdkPromise;
    };
    const runSdk = () => {
      if (!fresh()) { expire(); return; }
      if (busy) return;
      busy = true; button.disabled = true; clearTimeout(timer); leftPage = false;
      status.textContent = '正在准备分享…'; report('sdk_start');
      let failed = false;
      const fail = error => {
        if (failed) return;
        failed = true; clearTimeout(timer); report('sdk_failed', error?.errCode);
        status.textContent = '分享准备失败，请重新尝试；也可以返回保存照片。';
      };
      timer = setTimeout(() => {
        if (busy && !leftPage) status.textContent = '分享准备时间较长，可以稍等，或返回领图页重新尝试。';
      }, 10000);
      try {
        // Encode exactly once from the validated raw URL on each attempt. Keep
        // preview/telemetry and Android handoff untouched. iOS uses the
        // phone-verified encoded URL by default; raw remains a diagnostic override.
        const shareInfo = imageUrlEncoding === 'component'
          ? { ...payload.shareInfo, images: payload.shareInfo.images.map(url => encodeURIComponent(url)) }
          : payload.shareInfo;
        Promise.resolve(globalThis.xhs.share({ shareInfo, verifyConfig: payload.verifyConfig, fail }))
          .then(() => {
            if (!failed) {
              report('sdk_returned');
              // Resolution only means the SDK handed off, never import/publish success.
              if (!leftPage) opening();
            }
          }, fail).finally(() => { busy = false; button.disabled = !fresh(); if (!fresh()) expire(); });
      } catch (error) { fail(error); busy = false; button.disabled = !fresh(); }
    };
    const prepareSdk = async autoOpen => {
      button.disabled = true; status.textContent = '正在准备小红书分享…';
      try {
        await loadSdk(); report('sdk_ready');
        if (!fresh()) { expire(); return; }
        button.disabled = false; button.textContent = '打开小红书';
        status.textContent = '点击下方按钮，在小红书中继续编辑。';
        if (autoOpen && !leftPage && !document.hidden) { button.textContent = '继续打开小红书'; runSdk(); }
      } catch (_) {
        report('sdk_load_failed'); button.disabled = !fresh(); button.textContent = '重新加载分享';
        status.textContent = '分享组件暂时未加载，请重新尝试；也可以返回保存照片。';
        if (!fresh()) expire();
      }
    };
    button.onclick = () => {
      if (!fresh()) { expire(); return; }
      if (typeof globalThis.xhs?.share === 'function') runSdk(); else void prepareSdk(true);
    };
    void prepareSdk(payload.autoOpen === true);
  } else {
    // Preserve the Android/unknown-device path, including old handoffs.
    const useScheme = payload.launch.platform === 'Android' && !inWeChat;
    const primary = useScheme ? payload.launch.scheme : payload.launch.universal;
    alternate.href = useScheme ? payload.launch.universal : payload.launch.scheme;
    button.disabled = false;
    if (payload.autoOpen === true) button.textContent = '继续打开小红书';
    status.textContent = '点击下方按钮，在小红书中继续编辑。';
    button.onclick = () => {
      if (!fresh()) { expire(); return; }
      report('prepared_link_open'); opening(); alternate.hidden = false;
      try { location.assign(primary); }
      catch (_) { status.textContent = '浏览器未能打开小红书，请尝试备用入口或返回保存照片。'; }
    };
    alternate.onclick = event => {
      if (!fresh()) { event.preventDefault(); expire(); return; }
      report('prepared_link_open'); opening();
    };
    if (payload.autoOpen === true) button.onclick();
  }
})();
