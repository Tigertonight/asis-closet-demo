(() => {
  const $ = id => document.getElementById(id);
  const button = $('xhsOpen'), status = $('xhsStatus'), alternate = $('xhsAlternate');
  let payload = null, timer = null, leftPage = false;
  const fresh = () => payload?.expiresAt > Date.now() + 1000;
  $('xhsBack').onclick = () => {
    if (history.length > 1) history.back(); else location.replace('/selfit/stamp');
  };
  // Only short-lived composed-image and official launch URLs cross pages.
  // Never send the receipt fragment to a third-party SDK or URL.
  try {
    payload = JSON.parse(sessionStorage.getItem('selfit.xhsShare'));
    sessionStorage.removeItem('selfit.xhsShare');
    const image = new URL(payload.shareInfo.images[0]);
    const localHttp = image.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(image.hostname);
    const scheme = new URL(payload.launch.scheme), universal = new URL(payload.launch.universal);
    if (payload.shareInfo.type !== 'normal' || payload.shareInfo.images.length !== 1 || (image.protocol !== 'https:' && !localHttp) ||
        image.origin !== location.origin || !/^\/api\/v1\/selfit\/mirror\/photos\/mp_[a-f0-9]{32}\/files\/print\.png$/.test(image.pathname) ||
        !payload.verifyConfig?.appKey || !fresh() ||
        scheme.protocol !== 'xhsdiscover:' || scheme.hostname !== 'js_share_sdk' || scheme.username || scheme.password ||
        !scheme.searchParams.get('share_code') || scheme.searchParams.get('app_key') !== payload.verifyConfig.appKey ||
        universal.origin !== 'https://oia.xiaohongshu.com' || universal.pathname !== '/oia' || universal.username || universal.password ||
        universal.searchParams.get('deeplink') !== payload.launch.scheme) throw new Error('Invalid handoff');
  } catch (_) {
    status.textContent = '分享准备已过期，请返回领图页重新点击分享。'; return;
  }
  $('xhsPhoto').src = payload.shareInfo.images[0];
  $('xhsPhotoFrame').hidden = false;
  // A missing/desktop JS user agent must not disable a real phone. Prefer the
  // request's platform only to choose the link, never to gate the feature.
  const inWeChat = payload.launch.inWeChat || /MicroMessenger/i.test(navigator.userAgent || '');
  const useScheme = payload.launch.platform === 'Android' && !inWeChat;
  const primary = useScheme ? payload.launch.scheme : payload.launch.universal;
  alternate.href = useScheme ? payload.launch.universal : payload.launch.scheme;
  button.disabled = false;
  if (payload.autoOpen === true) button.textContent = '继续打开小红书';
  status.textContent = '点击下方按钮，在小红书中继续编辑。';
  const expire = () => {
    button.disabled = true; alternate.hidden = true; alternate.removeAttribute('href');
    status.textContent = '分享准备已过期，请返回领图页重新点击分享。';
  };
  const opening = () => {
    clearTimeout(timer); leftPage = false;
    status.textContent = '正在打开小红书，请在编辑页确认内容。';
    alternate.hidden = false;
    timer = setTimeout(() => {
      if (!leftPage) status.textContent = inWeChat
        ? '若未跳转，请点击按钮继续。微信仍拦截时，请返回领图页再用浏览器打开，或保存照片后分享。'
        : '若未跳转，请点击按钮继续或尝试备用入口，并确认已安装小红书；也可返回保存照片。';
    }, 2500);
  };
  button.onclick = () => {
    if (!fresh()) { expire(); return; }
    opening();
    // No network call or promise between the user's tap and navigation.
    try { location.assign(primary); }
    catch (_) { status.textContent = '浏览器未能打开小红书，请尝试备用入口或返回保存照片。'; }
  };
  alternate.onclick = event => {
    if (!fresh()) { event.preventDefault(); expire(); return; }
    opening(); // Native link navigation retains the user's activation too.
  };
  const leave = () => { leftPage = true; clearTimeout(timer); };
  addEventListener('pagehide', leave);
  addEventListener('visibilitychange', () => {
    if (document.hidden) leave();
    else if (!fresh()) expire();
  });
  // A scan explicitly requests sharing. Try once on entry; browser activation
  // restrictions are recoverable with the same synchronous tap handler.
  if (payload.autoOpen === true) button.onclick();
})();
