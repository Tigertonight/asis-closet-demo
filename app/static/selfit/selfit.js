(() => {
  const shell = document.querySelector('#appShell');
  window.__SELFIT_BOOT_OK__ = true;
  window.clearTimeout(window.__SELFIT_BOOT_TIMER__);
  document.documentElement.dataset.selfitBoot = 'ready';
  const screens = [...document.querySelectorAll('[data-screen]')];
  const splash = document.querySelector('[data-screen="splash"]');
  const intro = document.querySelector('[data-screen="intro"]');
  const themeColor = document.querySelector('meta[name="theme-color"]');
  const onboardingNav = document.querySelector('[data-onboarding-nav]');
  const onboardingBack = document.querySelector('[data-onboarding-back]');
  const onboardingStepper = document.querySelector('[data-onboarding-stepper]');
  const onboardingSteps = onboardingStepper ? [...onboardingStepper.querySelectorAll('[data-step]')] : [];
  // Persistent nav config per onboarding screen: where "back" goes, which step
  // is current, and how far the progress fill should reach.
  const ONBOARDING_NAV = {
    suit: { back: 'like', progress: 'suit', current: 'suit', done: ['like'] },
    'suit-manual': { back: 'suit', progress: 'suit', current: 'suit', done: ['like'] },
    like: { back: 'intro', progress: 'like', current: 'like', done: [] },
    vibe: { back: 'suit', progress: 'vibe', current: 'vibe', done: ['suit', 'like'] },
  };
  const updateOnboardingNav = (name) => {
    if (!onboardingNav) return;
    // 重新测试（从「我的档案」进入）：无过场直接从 like 开始，跳过 suit 环节，
    // stepper 只显示 like / vibe 两个圆圈（.is-retest 隐藏 suit 步）；
    // like 作为 retest 的第一步，返回键直达「我的档案」；
    // 首次 onboarding 仍走完整 intro → like → suit → vibe。
    let config = ONBOARDING_NAV[name];
    if (name === 'suit' && config) {
      config = { ...config, back: choosingGender() ? 'like' : 'suit-gender' };
    }
    if (retestEntry && config && name !== 'suit' && name !== 'suit-manual') {
      if (name === 'vibe') config = { back: 'like', progress: 'vibe', current: 'vibe', done: ['like'] };
      else if (name === 'like') config = { back: 'profile', progress: 'like', current: 'like', done: [] };
      else config = null;
    }
    onboardingNav.hidden = !config;
    if (!config) return;
    if (onboardingBack) {
      onboardingBack.hidden = !config.back;
      const backLabel = config.back === 'suit-gender' ? '返回选择性别'
        : retestEntry && config.back === 'profile' ? '返回我的档案' : '返回';
      onboardingBack.setAttribute('aria-label', backLabel);
    }
    onboardingBack?.setAttribute('data-back', config.back);
    onboardingStepper?.setAttribute('data-progress', config.progress);
    onboardingSteps.forEach((step) => {
      const key = step.dataset.step;
      step.classList.toggle('is-current', key === config.current);
      step.classList.toggle('is-done', config.done.includes(key));
      if (key === config.current) step.setAttribute('aria-current', 'step');
      else step.removeAttribute('aria-current');
    });
  };
  const SESSION_STORAGE_KEY = 'selfit.onboarding.session.v1';
  const entryParams = new URLSearchParams(window.location.search);
  const retestEntry = entryParams.get('entry') === 'retest';
  const archiveReportEntry = entryParams.get('from') === 'mirror' && entryParams.get('return_screen') === 'profile';
  document.body.classList.toggle('is-archive-report', archiveReportEntry);
  document.body.classList.toggle('is-retest', retestEntry);
  if(archiveReportEntry) {document.querySelector('.report-nav h2').textContent='型格报告';}
  const handoffToken = entryParams.get('handoff') || '';
  const sharedReportEntry = entryParams.get('from') === 'shared-report';
  const sharedReportType = (entryParams.get('shared_type') || '').trim().slice(0, 24);
  const reportParentTab = ({
    'mirror': 'home',
    'app-home': 'home',
    'app-profile': 'me',
  })[entryParams.get('from')] || '';
  const reportBack = document.querySelector('[data-screen="report"] [data-back]');
  if (reportParentTab && reportBack) {
    reportBack.setAttribute('aria-label', entryParams.get('return_screen') === 'profile' ? '返回我的档案' : '返回试衣镜');
  }
  let api;
  let auth;
  let authReady = Promise.resolve(null);
  const state = {
    screen: 'splash', facePhoto: null, bodyPhoto: null, gender: null, genderBusy: false, genderEditing: false,
    photoStatus: { face: 'empty', body: 'empty' },
    photoAssets: { face: null, body: null },
    photoControllers: { face: null, body: null },
    samplePhotos: { face: null, body: null },
    manual: { skin: null, faceShape: null, bodyShape: null },
    axes: { shape: 42, energy: 64, trend: 42 },
    palette: null, answers: {}, sessionId: null, revision: 0, reportJobId: null, reportId: null, currentReportTypeId: '', authUser: null, publicShare: null,
  };
  const personalityCatalog = window.__SELFIT_PERSONALITY_TEMPLATES__ || { types: {}, renderRules: {} };
  const dismissKeyboard = () => window.SelfitViewport?.dismissKeyboard?.() || Promise.resolve();

  // 轻量埋点：fire-and-forget，失败静默（sendBeacon 页面关闭也能送达）
  const track = (event, props = {}) => {
    try {
      const payload = {
        events: [{
          event,
          screen: state.screen,
          sessionId: state.sessionId,
          userId: state.authUser?.user_id || null,
          props,
        }],
      };
      const body = JSON.stringify(payload);
      if (navigator.sendBeacon) {
        navigator.sendBeacon('/api/v1/selfit/events', new Blob([body], { type: 'application/json' }));
      } else {
        void fetch('/api/v1/selfit/events', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, keepalive: true }).catch(() => {});
      }
    } catch { /* 埋点失败不影响业务 */ }
  };

  const IMAGE_RETRY_DELAYS_MS = [350, 1200];
  const imagePathForTelemetry = (source) => {
    try { return new URL(source, location.href).pathname.slice(0, 240); }
    catch { return String(source || '').split('?')[0].slice(0, 240); }
  };
  const imageRetryUrl = (source, attempt) => {
    const url = new URL(source, location.href);
    url.searchParams.set('selfit_retry', `${attempt}-${Date.now()}`);
    return url.href;
  };
  const applyImageFallback = (image, originalSource) => {
    if (image.dataset.fallbackApplied === 'true') return;
    image.dataset.fallbackApplied = 'true';
    if (image.id === 'loadingArt') {
      image.classList.remove('is-changing');
      return;
    }
    if (/\/assets\/personality\//.test(originalSource) || image.alt) {
      image.src = '/static/selfit/assets/personality/placeholder-card.svg';
      return;
    }
    // Decorative images have empty alt text. Hiding them is preferable to exposing
    // WebKit's blue broken-image icon in the middle of an otherwise usable screen.
    image.hidden = true;
  };
  shell.addEventListener('error', (event) => {
    const image = event.target;
    if (!(image instanceof HTMLImageElement) || image.dataset.fallbackApplied === 'true') return;
    const assignedSource = image.getAttribute('src');
    if (!assignedSource) return;
    const originalSource = image.dataset.retrySource || image.currentSrc || assignedSource;
    if (!originalSource || originalSource.startsWith('blob:') || originalSource.startsWith('data:')) return;
    image.dataset.retrySource = originalSource;
    const attempt = Number(image.dataset.retryAttempt || 0) + 1;
    image.dataset.retryAttempt = String(attempt);
    track('image_load_failed', { path: imagePathForTelemetry(originalSource), attempt });
    const delayMs = IMAGE_RETRY_DELAYS_MS[attempt - 1];
    if (delayMs == null) {
      applyImageFallback(image, originalSource);
      return;
    }
    window.setTimeout(() => {
      if (!image.isConnected || image.dataset.fallbackApplied === 'true') return;
      image.src = imageRetryUrl(originalSource, attempt);
    }, delayMs);
  }, true);
  shell.addEventListener('load', (event) => {
    const image = event.target;
    if (!(image instanceof HTMLImageElement)) return;
    const attempts = Number(image.dataset.retryAttempt || 0);
    if (!attempts) return;
    track('image_load_recovered', { path: imagePathForTelemetry(image.dataset.retrySource || image.src), attempts });
    delete image.dataset.retryAttempt;
    delete image.dataset.retrySource;
  }, true);

  const showScreen = (name) => {
    const next = screens.find((screen) => screen.dataset.screen === name);
    if (!next) return;
    const previous = state.screen;
    if (previous === 'loading' && name !== 'loading') loadingStory.stop();
    if (name === 'loading' && previous !== 'loading') {
      loadingStory.start();
      void loadingStory.update(25);
    }
    screens.forEach((screen) => {
      screen.classList.toggle('is-active', screen === next);
      screen.setAttribute('aria-hidden', screen === next ? 'false' : 'true');
    });
    state.screen = name;
    if (name === 'report' && state.currentReportTypeId && !publicShareToken) {
      try { localStorage.setItem('selfit.app.persona.v1', state.currentReportTypeId); } catch { /* 无痕模式下仍可继续查看报告。 */ }
    }
    if (previous !== name) track('screen_view', { from: previous, to: name });
    updateOnboardingNav(name);
    themeColor?.setAttribute('content', ['splash', 'loading'].includes(name) ? '#8a011b' : '#fafafa');
    // 从 suit-manual 返回 suit 时保持点击「修改」前的位置；其余进入仍从顶部开始。
    if (name === 'suit' && previous === 'suit-manual' && suitReturnScroll != null) next.scrollTop = suitReturnScroll;
    else next.scrollTop = 0;
    if(name === 'report') requestAnimationFrame(()=>syncReportActions());
    // 进入 suit 屏时同步渲染：旧 session/跨账号照片回填要让上传槽和特征卡一起恢复，
    // 否则会出现「只传了全身照，肤色脸型却自动出来了」的隐形旧数据。
    if (name === 'suit') {
      syncGenderControls();
      const returnScroll = previous === 'suit-manual' ? suitReturnScroll : null;
      suitReturnScroll = null;
      // 卡片重渲染后高度可能微移，渲染完成后再校准一次位置。
      renderSuit().then(() => {
        if (returnScroll == null || state.screen !== 'suit') return;
        const suitScreen = document.querySelector('[data-screen="suit"]');
        if (suitScreen) suitScreen.scrollTop = returnScroll;
      }).catch(() => {});
    }
  };

  const returnToReportParent = () => {
    if (!reportParentTab) return false;
    const appUrl = new URL('/selfit/try-on', window.location.origin);
    const typeId = String(entryParams.get('type') || state.currentReportTypeId || '').trim().toLowerCase();
    if (typeId) appUrl.searchParams.set('persona', typeId);
    appUrl.searchParams.set('screen', entryParams.get('return_screen') === 'profile' ? 'profile' : 'mirror');
    window.location.assign(`${appUrl.pathname}${appUrl.search}`);
    return true;
  };

  // 重新测试时 like 是第一步，返回键离开 onboarding、直达「我的档案」。
  const returnToProfile = () => {
    const appUrl = new URL('/selfit/try-on', window.location.origin);
    appUrl.searchParams.set('screen', 'profile');
    window.location.assign(`${appUrl.pathname}${appUrl.search}`);
  };

  let splashTimer = 0;
  let splashTransitioning = false;
  let introTimers = [];
  const clearIntroMotion = () => { introTimers.forEach(window.clearTimeout); introTimers = []; };
  const playIntro = () => {
    clearIntroMotion();
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) { intro.classList.add('is-composed'); return; }
    intro.classList.remove('is-composed');
    const cycle = () => {
      introTimers.push(setTimeout(() => intro.classList.add('is-composed'), 1600));
      introTimers.push(setTimeout(() => intro.classList.remove('is-composed'), 3000));
      introTimers.push(setTimeout(cycle, 3600));
    };
    cycle();
  };
  const claimPendingHandoff = async () => {
    if (!handoffToken) return false;
    const result = await api.claimMirrorHandoff(handoffToken);
    state.sessionId = result.session?.sessionId || null;
    state.revision = result.session?.revision || 1;
    if (!state.sessionId) throw new Error('没有找到本次镜子测试，请重新扫码。');
    localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify({
      sessionId: state.sessionId,
      expiresAt: result.session?.expiresAt || null,
      userId: state.authUser?.user_id || null,
    }));
    const cleanUrl = new URL(window.location.href);
    cleanUrl.searchParams.delete('handoff');
    history.replaceState({}, '', `${cleanUrl.pathname}${cleanUrl.search}${cleanUrl.hash}`);
    showScreen('like');
    return true;
  };
  const enterOnboarding = () => {
    if (splashTransitioning || state.screen !== 'splash') return;
    splashTransitioning = true; clearTimeout(splashTimer); splash.classList.add('is-leaving');
    setTimeout(async () => {
      await authReady;
      const unlockEntry = entryParams.get('entry') === 'unlock';
      let destination = state.authUser ? (retestEntry ? 'like' : 'intro') : 'login';
      if (handoffToken) destination = state.authUser ? 'like' : 'phone-login';
      // 从主站被门槛弹回的用户（entry=unlock）意图明确：直接给解锁屏。
      if (unlockEntry && state.authUser && !state.authUser.beta_qualified) destination = 'beta-unlock';
      if (handoffToken && state.authUser) {
        try { await claimPendingHandoff(); }
        catch (error) {
          destination = 'phone-login';
          showScreen(destination);
          setAuthMessage(authNodes.phoneMessage, error.message || '这个二维码已失效。', 'error');
        }
      } else if (state.authUser) {
        try {
          if (await openAppForExistingReport()) return;
          if (destination === 'beta-unlock') enterBetaUnlock('report', 'generic');
          else showScreen(destination);
        } catch (error) {
          destination = 'phone-login';
          showScreen(destination);
          setAuthMessage(authNodes.phoneMessage, error.message || '暂时无法读取你的风格档案，请重试。', 'error');
        }
      } else showScreen(destination);
      splash.classList.remove('is-leaving');
      splashTransitioning = false;
      if (destination === 'intro') playIntro();
    }, matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 420);
  };

  if (sharedReportEntry) {
    track('shared_report_try_landed', { sharedType: sharedReportType });
    const introTitle = document.querySelector('#introTitle');
    if (introTitle) introTitle.textContent = sharedReportType
      ? `Ta是「${sharedReportType}」，你会是哪一种？`
      : '看过Ta的风格，也来认识你自己';
    const introAction = document.querySelector('.intro-action');
    if (introAction) introAction.textContent = '开始测我的风格';
  }
  document.querySelector('#splashEnter').addEventListener('click', enterOnboarding);

  document.addEventListener('click', async (event) => {
    const next = event.target.closest('[data-next]');
    const back = event.target.closest('[data-back]');
    if (next) {
      if (document.activeElement?.matches?.('input, textarea, [contenteditable="true"]')) await dismissKeyboard();
      if (next.classList.contains('intro-action') && !handoffToken) startNewAssessment();
      if (next.dataset.next !== 'intro') clearIntroMotion();
      showScreen(next.dataset.next);
    }
    if (back) {
      if (state.screen === 'suit' && state.genderBusy) return;
      if (back.dataset.back === 'suit-gender') { openGenderSelection(); return; }
      if (document.activeElement?.matches?.('input, textarea, [contenteditable="true"]')) await dismissKeyboard();
      if (retestEntry && back.dataset.back === 'profile') { returnToProfile(); return; }
      if (state.screen === 'report' && returnToReportParent()) return;
      if (state.screen === 'suit-manual' && manualBeforeEdit) state.manual = { ...manualBeforeEdit };
      showScreen(back.dataset.back);
      if (back.dataset.back === 'intro') playIntro();
    }
  });

  const authNodes = {
    phoneForm: document.querySelector('#phoneLoginForm'),
    phone: document.querySelector('#loginPhone'),
    clearPhone: document.querySelector('#clearLoginPhone'),
    phoneSubmit: document.querySelector('#phoneLoginSubmit'),
    phoneMessage: document.querySelector('#phoneLoginMessage'),
    inviteForm: document.querySelector('#inviteLoginForm'),
    invite: document.querySelector('#inviteCode'),
    inviteSubmit: document.querySelector('#inviteLoginSubmit'),
    inviteMessage: document.querySelector('#inviteLoginMessage'),
  };
  const setAuthMessage = (node, copy = '', stateName = '') => {
    node.textContent = copy;
    if (stateName) node.dataset.state = stateName;
    else delete node.dataset.state;
  };
  const normalizedPhone = () => authNodes.phone.value.replace(/\D/g, '').slice(0, 11);
  const syncPhoneLogin = () => {
    const phone = normalizedPhone();
    if (authNodes.phone.value !== phone) authNodes.phone.value = phone;
    // 中国大陆号段：1 + 第二位 3-9 + 共 11 位
    const phoneValid = /^1[3-9]\d{9}$/.test(phone);
    authNodes.clearPhone.hidden = !phone;
    authNodes.phoneSubmit.disabled = !phoneValid || authNodes.phoneSubmit.getAttribute('aria-busy') === 'true';
  };
  const syncInviteLogin = () => {
    authNodes.inviteSubmit.disabled = authNodes.invite.value.trim().length < 4 || authNodes.inviteSubmit.getAttribute('aria-busy') === 'true';
  };
  const completeAuth = async (session, provider = 'phone') => {
    state.authUser = session?.user || auth.user || null;
    state.sessionId = null;
    state.revision = 0;
    localStorage.removeItem(SESSION_STORAGE_KEY);
    track('login_success', { provider });
    await dismissKeyboard();
    if (handoffToken) {
      await claimPendingHandoff();
      return;
    }
    if (await openAppForExistingReport()) return;
    // 重新测试跳过 intro 过场，直接进入 like。
    if (retestEntry) { showScreen('like'); return; }
    showScreen('intro');
    playIntro();
  };
  const openAppForExistingReport = async () => {
    if (!state.authUser || retestEntry) return false;
    const result = await api.getLatestReport();
    const typeId = String(result?.report?.typeId || '').trim().toLowerCase();
    if (!typeId) return false;
    // 内测门槛：有报告但未解锁（普通手机号账号）停在解锁页，输邀请码后进主站。
    if (!state.authUser?.beta_qualified) {
      enterBetaUnlock('report');
      return true;
    }
    track('existing_report_app_entered', { typeId, reportId: result.report.reportId || '' });
    window.location.replace(`/selfit/try-on?from=login&persona=${encodeURIComponent(typeId)}`);
    return true;
  };
  const enterBetaUnlock = (backTo = 'report', context = 'report') => {
    // context 决定文案：report=报告已生成后解锁；generic=like 跳过测试/主站弹回等无报告场景。
    const unlockScreen = document.querySelector?.('[data-screen="beta-unlock"]');
    const backButton = unlockScreen?.querySelector('[data-back]');
    if (backButton) backButton.dataset.back = backTo;
    const hintNode = document.querySelector?.('#betaUnlockHint');
    const secondaryButton = unlockScreen?.querySelector('.auth-submit.secondary-action');
    if (hintNode) {
      hintNode.textContent = context === 'report'
        ? '你的风格报告已生成。试穿、AI 搭配等完整功能正在内测中，输入邀请码即可解锁。'
        : '试穿、AI 搭配等完整功能正在内测中，输入邀请码即可解锁。';
    }
    if (secondaryButton) {
      secondaryButton.textContent = context === 'report' ? '先看看我的报告' : '返回继续测试';
      secondaryButton.hidden = false;
    }
    if (typeof showScreen === 'function') showScreen('beta-unlock');
  };
  const setAuthBusy = (button, busy) => {
    button.toggleAttribute('aria-busy', busy);
    button.disabled = busy;
  };
  authNodes.phone.addEventListener('input', () => { setAuthMessage(authNodes.phoneMessage); syncPhoneLogin(); });
  authNodes.clearPhone.addEventListener('click', () => {
    authNodes.phone.value = '';
    authNodes.phone.focus();
    setAuthMessage(authNodes.phoneMessage);
    syncPhoneLogin();
  });
  authNodes.phoneForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (authNodes.phoneSubmit.disabled) return;
    setAuthBusy(authNodes.phoneSubmit, true);
    setAuthMessage(authNodes.phoneMessage, '正在登录…');
    try {
      await completeAuth(await auth.directPhone(normalizedPhone()), 'phone');
    } catch (error) {
      track('login_failed', { provider: 'phone', message: error.message || '' });
      setAuthMessage(authNodes.phoneMessage, error.message || '登录失败，请重试。', 'error');
    } finally {
      setAuthBusy(authNodes.phoneSubmit, false);
      syncPhoneLogin();
    }
  });
  authNodes.invite.addEventListener('input', () => { setAuthMessage(authNodes.inviteMessage); syncInviteLogin(); });
  authNodes.inviteForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (authNodes.inviteSubmit.disabled) return;
    setAuthBusy(authNodes.inviteSubmit, true);
    setAuthMessage(authNodes.inviteMessage, '正在登录…');
    try {
      await completeAuth(await auth.verifyInvite(authNodes.invite.value.trim()), 'invite');
    } catch (error) {
      track('login_failed', { provider: 'invite', message: error.message || '' });
      setAuthMessage(authNodes.inviteMessage, error.message || '邀请码登录失败，请重试。', 'error');
    } finally {
      setAuthBusy(authNodes.inviteSubmit, false);
      syncInviteLogin();
    }
  });
  const betaUnlockNodes = {
    form: document.querySelector('#betaUnlockForm'),
    code: document.querySelector('#betaUnlockCode'),
    submit: document.querySelector('#betaUnlockSubmit'),
    message: document.querySelector('#betaUnlockMessage'),
  };
  const syncBetaUnlock = () => {
    if (!betaUnlockNodes.form) return;
    betaUnlockNodes.submit.disabled = betaUnlockNodes.code.value.trim().length < 4 || betaUnlockNodes.submit.getAttribute('aria-busy') === 'true';
  };
  if (betaUnlockNodes.form) {
    betaUnlockNodes.code.addEventListener('input', () => { setAuthMessage(betaUnlockNodes.message); syncBetaUnlock(); });
    betaUnlockNodes.form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (betaUnlockNodes.submit.disabled) return;
      setAuthBusy(betaUnlockNodes.submit, true);
      setAuthMessage(betaUnlockNodes.message, '正在解锁…');
      try {
        const payload = await auth.upgradeInvite(betaUnlockNodes.code.value.trim());
        state.authUser = payload?.user || auth.user || state.authUser;
        track('beta_unlocked', {});
        setAuthMessage(betaUnlockNodes.message, '已解锁，正在进入…');
        const result = await api.getLatestReport();
        const typeId = String(result?.report?.typeId || '').trim().toLowerCase();
        window.location.replace(typeId ? `/selfit/try-on?from=login&persona=${encodeURIComponent(typeId)}` : '/selfit/try-on?from=login');
      } catch (error) {
        track('login_failed', { provider: 'invite_upgrade', message: error.message || '' });
        setAuthMessage(betaUnlockNodes.message, error.message || '解锁失败，请检查邀请码后重试。', 'error');
      } finally {
        setAuthBusy(betaUnlockNodes.submit, false);
        syncBetaUnlock();
      }
    });
  }

  // suit 特征卡由共享组件渲染（与「我的档案」共用），参数说明弹窗也由组件自带。

  const validatePhoto = (file) => {
    if (!file) return '请选择照片';
    if (!file.type.startsWith('image/') && !/\.(heic|heif|jpe?g|png|webp|avif)$/i.test(file.name)) return '请选择一张照片，再试一次';
    if (file.size > 20 * 1024 * 1024) return '照片请小于 20MB';
    return '';
  };
  const renderPhotoPreview = (card, file, kind) => {
    const preview = card.querySelector('.upload-preview');
    const remotePreview = typeof file === 'string';
    const objectUrl = remotePreview ? file : URL.createObjectURL(file);
    const image = Object.assign(document.createElement('img'), {
      alt: kind === 'face' ? '面部照预览' : '全身照预览',
    });
    const releaseObjectUrl = () => { if (!remotePreview) URL.revokeObjectURL(objectUrl); };
    image.addEventListener('load', releaseObjectUrl, { once: true });
    image.addEventListener('error', () => {
      releaseObjectUrl();
      if (!preview.contains(image)) return;
      const fallback = document.createElement('span');
      fallback.className = 'upload-preview-fallback';
      fallback.textContent = remotePreview ? '示例照片已选择，预览暂时无法加载' : '照片已选择';
      preview.replaceChildren(fallback);
    }, { once: true });
    preview.replaceChildren(image);
    image.src = objectUrl;
  };
  const choosingGender = () => !['female', 'male'].includes(state.gender) || state.genderEditing;
  const genderReady = () => !choosingGender() && !state.genderBusy;
  const syncSuitButton = () => { document.querySelector('#suitNext').disabled = !(genderReady() && state.photoStatus.face === 'valid' && state.photoStatus.body === 'valid'); };
  const syncGenderControls = () => {
    const ready = genderReady();
    const choosing = choosingGender();
    document.querySelector('[data-screen="suit"]').classList.toggle('is-choosing-gender', choosing);
    document.querySelector('[data-screen="suit"]').setAttribute('aria-labelledby', choosing ? 'genderTitle' : 'suitTitle');
    document.querySelector('.gender-card').hidden = !choosing;
    document.querySelector('[data-suit-photos]').hidden = choosing;
    document.querySelector('#suitTitle').textContent = '看看什么真的适合你';
    document.querySelector('.gender-card').setAttribute('aria-busy', String(state.genderBusy));
    document.querySelector('[data-suit-photos]').inert = choosing || state.genderBusy;
    document.querySelectorAll('[data-gender]').forEach(button => {
      const selected = state.gender === button.dataset.gender;
      button.classList.toggle('is-selected', selected);
      button.setAttribute('aria-pressed', String(selected));
      button.disabled = state.genderBusy || Object.values(state.photoStatus).includes('checking');
    });
    document.querySelectorAll('[data-upload-card] input').forEach(control => { control.disabled = !ready; });
    document.querySelectorAll('[data-sample-photo]').forEach(control => {
      const kind = control.dataset.samplePhoto;
      const busy = state.photoStatus[kind] === 'checking';
      control.disabled = !ready || busy;
      control.setAttribute('aria-busy', String(busy));
      control.textContent = busy && state.samplePhotos[kind] ? '正在分析示例照片…'
        : state.photoStatus[kind] === 'invalid' && state.samplePhotos[kind] ? '重新使用示例照片' : '使用示例照片';
    });
    if (state.screen === 'suit') {
      updateOnboardingNav('suit');
      if (onboardingBack) onboardingBack.disabled = state.genderBusy;
    }
    syncSuitButton();
  };
  const animateSuitPhase = async (panel, entering) => {
    if (state.screen !== 'suit' || matchMedia('(prefers-reduced-motion: reduce)').matches || !panel?.animate) return;
    // Animation is progressive enhancement: cancellation or an older browser must
    // never prevent a saved choice from opening the upload controls.
    let animation;
    try {
      animation = panel.animate(entering
        ? [{ opacity: 0, transform: 'translateY(10px)' }, { opacity: 1, transform: 'translateY(0)' }]
        : [{ opacity: 1, transform: 'translateY(0)' }, { opacity: 0, transform: 'translateY(-6px)' }],
      { duration: entering ? 180 : 120, easing: 'cubic-bezier(.22,.61,.36,1)', fill: 'both' });
      await animation.finished;
    } catch { /* Keep the two-step flow usable even if motion is unavailable. */ }
    finally { animation?.cancel(); }
  };
  const transitionSuitPhase = async (choosing) => {
    const outgoing = document.querySelector(choosing ? '[data-suit-photos]' : '.gender-card');
    const incoming = document.querySelector(choosing ? '.gender-card' : '[data-suit-photos]');
    await animateSuitPhase(outgoing, false);
    state.genderEditing = choosing;
    syncGenderControls();
    await animateSuitPhase(incoming, true);
  };
  const openGenderSelection = async () => {
    if (state.genderBusy) return;
    return runButtonAction(onboardingBack, async () => {
      state.genderBusy = true;
      // Stop a pending result reveal from scrolling the gender selection offscreen.
      ++suitRenderSeq;
      resetOnboardingPhotos(Object.keys(state.photoStatus).filter(kind => state.photoStatus[kind] === 'checking'));
      try {
        syncGenderControls();
        document.querySelector('[data-screen="suit"]').scrollTo({ top: 0, behavior: 'instant' });
        await transitionSuitPhase(true);
      } finally {
        state.genderBusy = false;
        syncGenderControls();
      }
      if (state.screen === 'suit') document.querySelector('[data-gender].is-selected')?.focus({ preventScroll: true });
    });
  };
  document.querySelectorAll('[data-gender]').forEach(button => {
    button.addEventListener('click', () => runButtonAction(button, async () => {
      if (state.genderBusy) return;
      const gender = button.dataset.gender;
      state.genderBusy = true;
      try {
        syncGenderControls();
        const sessionId = await ensureSession();
        const result = await api.saveGender(sessionId, gender);
        resetOnboardingPhotos(Object.keys(state.samplePhotos).filter(kind => state.samplePhotos[kind] && !state.samplePhotos[kind].startsWith(`${gender}-`)));
        state.gender = gender;
        state.genderEditing = true;
        state.revision = result.session?.revision || state.revision;
        syncGenderControls();
        // Give the successful selection a brief, visible acknowledgement before
        // replacing it in place. Reduced-motion users skip the pause and motion.
        if (!matchMedia('(prefers-reduced-motion: reduce)').matches) await new Promise(resolve => setTimeout(resolve, 200));
        await transitionSuitPhase(false);
      } finally {
        state.genderBusy = false;
        syncGenderControls();
      }
      if (state.screen === 'suit') document.querySelector('[data-suit-photos]')?.focus({ preventScroll: true });
      await renderSuit();
    }));
  });
  const uploadPlaceholders = new Map([...document.querySelectorAll('[data-upload-card]')].map(card =>
    [card.dataset.uploadCard, [...card.querySelector('.upload-preview').childNodes].map(node => node.cloneNode(true))]));
  const resetOnboardingPhotos = (kinds = ['face', 'body']) => {
    ++suitRenderSeq;
    for (const kind of kinds) {
      state.photoControllers[kind]?.abort();
      state.photoControllers[kind] = null;
      state.photoAssets[kind] = null;
      state.samplePhotos[kind] = null;
      state[kind === 'face' ? 'facePhoto' : 'bodyPhoto'] = null;
      const card = document.querySelector(`[data-upload-card="${kind}"]`);
      card.querySelector('input').value = '';
      card.querySelector('.upload-preview').replaceChildren(...uploadPlaceholders.get(kind).map(node => node.cloneNode(true)));
      if (analysisOverlayUrls[kind]) URL.revokeObjectURL(analysisOverlayUrls[kind]);
      delete analysisOverlayUrls[kind];
      setPhotoState(kind, 'empty', '');
    }
    syncGenderControls();
  };
  const resetSuitReveal = () => {
    const screen = document.querySelector('[data-screen="suit"]');
    const container = document.querySelector('#suitFeatures');
    container?.classList.remove('is-revealed');
    container?.replaceChildren();
    const analyzing = document.querySelector('#suitAnalyzing');
    if (analyzing) analyzing.hidden = true;
    screen?.classList.remove('is-condensed', 'is-analyzing');
  };
  const setPhotoState = (kind, status, copy) => {
    const card = document.querySelector(`[data-upload-card="${kind}"]`);
    const statusLine = document.querySelector(`[data-photo-status="${kind}"]`);
    card.classList.toggle('is-checking', status === 'checking');
    card.classList.toggle('is-valid', status === 'valid');
    card.classList.toggle('is-invalid', status === 'invalid');
    statusLine.dataset.state = status;
    statusLine.textContent = copy;
    state.photoStatus[kind] = status;
    syncGenderControls();
    // 任一照片离开可用态（重传 / 校验失败）时清空结果区，等待两张照片重新集齐。
    if (status !== 'valid') resetSuitReveal();
    syncSuitButton();
  };
  let editingFeature = null;
  let manualBeforeEdit = null;
  const manualSelections = new Set();
  // 进入 suit-manual 时记录 suit 屏的滚动位置，保存/取消返回后恢复原位而不是回到顶部。
  let suitReturnScroll = null;
  const analysisOverlayUrls = {};
  const openManual = (key = null) => {
    manualBeforeEdit = { ...state.manual };
    manualSelections.clear();
    editingFeature = key;
    window.SelfitManualOptions.renderOnboarding(document.querySelector('.manual-form'), state.gender);
    const suitScreen = document.querySelector('[data-screen="suit"]');
    suitReturnScroll = suitScreen ? suitScreen.scrollTop : null;
    document.querySelector('.manual-form').dataset.mode = key ? 'edit' : 'setup';
    document.querySelector('#manualTitle').textContent = key ? `修改${({skin:'肤色',faceShape:'脸型',bodyShape:'身材比例'})[key]}` : '选择更接近自己的特点';
    document.querySelectorAll('.manual-group').forEach(group => { group.hidden = Boolean(key && group.querySelector('[data-manual]').dataset.manual !== key); });
    document.querySelectorAll('[data-manual]').forEach(button => {
      const option = window.SelfitManualOptions.findOption(state.gender, button.dataset.manual, button.dataset.value);
      const selected = option && window.SelfitManualOptions.matches(option, state.manual[button.dataset.manual]);
      button.classList.toggle('is-selected', selected);
      button.setAttribute('aria-pressed', String(selected));
    });
    document.querySelector('#manualNext').textContent = key ? '保存修改' : '看看我的特点 →';
    document.querySelector('#manualNext').disabled = true;
    showScreen('suit-manual');
  };
  let suitRenderSeq = 0;
  const SUIT_ANALYSIS_HOLD_MS = 2600;
  const suitResultsReady = () => state.photoStatus.face === 'valid' && state.photoStatus.body === 'valid';
  const renderSuit = async () => {
    const seq = ++suitRenderSeq;
    const sessionId = await ensureSession();
    if (seq !== suitRenderSeq) return;
    syncGenderControls();
    if (!genderReady()) return;
    const summary = await api.getSuit(sessionId);
    if (seq !== suitRenderSeq) return;
    const analyses = summary.analyses || {};
    const bodyPhotoReady = Boolean(summary.photos?.body || (api.mode !== 'live' && state.bodyPhoto));
    // 服务端还有本 session 之前（或同账号回填）的照片时，把上传槽恢复成可用状态，
    // 让用户看见「已经用了哪张照片」，而不是照片在隐形生效。
    for (const kind of ['face', 'body']) {
      if (summary.photos?.[kind] && state.photoStatus[kind] === 'empty') {
        state.samplePhotos[kind] = summary.samplePhotos?.[kind] || null;
        setPhotoState(kind, 'valid', kind === 'face' ? '已使用之前上传的面部照，可重新上传替换' : '已使用之前上传的全身照，可重新上传替换');
        void applyAnalysisOverlay(kind, sessionId);
      }
    }
    const container = document.querySelector('#suitFeatures');
    const screen = document.querySelector('[data-screen="suit"]');
    // 两张照片都通过检测之前，结果区保持空白；集齐后先播放分析动效，再一次性揭示卡片。
    if (!suitResultsReady()) { resetSuitReveal(); return; }
    const firstReveal = !container.classList.contains('is-revealed');
    if (firstReveal) {
      const analyzing = document.querySelector('#suitAnalyzing');
      if (analyzing) analyzing.hidden = false;
      screen?.classList.add('is-analyzing');
      const holdMs = state.samplePhotos.face && state.samplePhotos.body ? 450 : SUIT_ANALYSIS_HOLD_MS;
      await new Promise((resolve) => setTimeout(resolve, holdMs));
      if (seq !== suitRenderSeq) return;
      if (analyzing) analyzing.hidden = true;
      screen?.classList.remove('is-analyzing');
    }
    const visibleFeatures = summary.features.filter(feature => feature.key !== 'bodyShape' || bodyPhotoReady || feature.value);
    visibleFeatures.forEach(feature => { state.manual[feature.key] = feature.value || null; });
    window.SelfitSuitCards.render(container, {
      features: visibleFeatures,
      analyses,
      photos: summary.photos || {},
      heading: true,
      entrance: firstReveal,
      onEdit: (key) => openManual(key),
    });
    document.querySelector('#suitNext').disabled = !visibleFeatures.every(feature => feature.value);
    if (firstReveal) {
      container.classList.add('is-revealed');
      screen?.classList.add('is-condensed');
      // 揭示后照片收缩为素材缩略图，把结果卡滚动到视口顶部成为视觉主体。
      requestAnimationFrame(() => {
        if (seq !== suitRenderSeq || state.screen !== 'suit' || !screen) return;
        const screenRect = screen.getBoundingClientRect();
        const targetTop = screen.scrollTop + container.getBoundingClientRect().top - screenRect.top - 8;
        screen.scrollTo({ top: Math.max(0, targetTop), behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
      });
    }
  };
  // Draw the analysis lines directly on the uploaded photo inside its upload card.
  const applyAnalysisOverlay = async (kind, sessionId) => {
    if (api.mode !== 'live') return;
    const card = document.querySelector(`[data-upload-card="${kind}"]`);
    const preview = card?.querySelector('.upload-preview');
    if (!preview) return;
    const controller = state.photoControllers[kind];
    const assetId = state.photoAssets[kind];
    const isCurrent = () => !controller?.signal.aborted && state.photoControllers[kind] === controller
      && state.photoAssets[kind] === assetId && state.photoStatus[kind] === 'valid';
    try {
      const blob = await api.getSuitPhoto(sessionId, kind, { signal: controller?.signal });
      if (!isCurrent()) return;
      const url = URL.createObjectURL(blob);
      const image = Object.assign(document.createElement('img'), {
        className: 'analysis-overlay',
        alt: kind === 'face' ? '面部照（含分析标记）' : '全身照（含分析标记）',
      });
      image.addEventListener('error', () => URL.revokeObjectURL(url), { once: true });
      image.src = url;
      try { await image.decode(); } catch { URL.revokeObjectURL(url); return; }
      if (!isCurrent()) { URL.revokeObjectURL(url); return; }
      if (analysisOverlayUrls[kind]) URL.revokeObjectURL(analysisOverlayUrls[kind]);
      analysisOverlayUrls[kind] = url;
      preview.replaceChildren(image);
    } catch { /* Analysis lines are an enhancement; keep the plain upload preview. */ }
  };
  const uploadPhoto = async (kind, file, { sampleId = null } = {}) => {
    if (!genderReady()) { toast('请先选择你的性别'); return; }
    state.photoControllers[kind]?.abort();
    const controller = new AbortController();
    state.photoControllers[kind] = controller;
    state.photoAssets[kind] = null;
    state.samplePhotos[kind] = sampleId;
    const error = sampleId ? '' : validatePhoto(file);
    if (error) { setPhotoState(kind, 'invalid', error); return; }
    state[kind === 'face' ? 'facePhoto' : 'bodyPhoto'] = file || { sampleId };
    const preview = sampleId ? `/api/v1/selfit/sample-photos/${encodeURIComponent(sampleId)}/preview` : file;
    renderPhotoPreview(document.querySelector(`[data-upload-card="${kind}"]`), preview, kind);
    setPhotoState(kind, 'checking', sampleId ? '正在分析示例照片…' : '正在处理照片…');

    try {
      const sessionId = await ensureSession();
      if (controller.signal.aborted) return;
      const result = sampleId
        ? await api.useSamplePhoto(sessionId, kind, sampleId, { signal: controller.signal })
        : await api.checkPhoto(sessionId, kind, file, { signal: controller.signal });
      if (controller.signal.aborted) return;
      const accepted = result.photo?.status === 'accepted';
      state.photoAssets[kind] = accepted ? result.photo.assetId : null;
      state.revision = result.revision || state.revision;
      track('photo_upload_result', { kind, accepted, code: result.photo?.code || '' });
      setPhotoState(kind, accepted ? 'valid' : 'invalid', result.photo?.message || (accepted ? '照片可用' : '请重新上传'));
      if (accepted && state.screen === 'suit') {
        renderSuit().catch(() => toast('照片已处理完成，结果暂时无法加载，请重新上传试试。'));
        void applyAnalysisOverlay(kind, sessionId);
      }
    } catch (requestError) {
      if (controller.signal.aborted) return;
      track('photo_upload_result', { kind, accepted: false, code: 'network' });
      setPhotoState(kind, 'invalid', requestError.message || (sampleId ? '示例照片分析未完成，请重试。' : '照片检测失败，请重试'));
    }
  };
  const bindUpload = (id, kind) => {
    const input = document.querySelector(`#${id}`);
    input.addEventListener('change', () => {
      const file = input.files?.[0]; if (!file) return;
      input.value = '';
      void uploadPhoto(kind, file);
    });
  };
  bindUpload('facePhoto', 'face'); bindUpload('bodyPhoto', 'body');
  // Submit a fixed sample ID; analysis originals stay on the server.
  const SAMPLE_PHOTOS = {
    female: {
      face: 'female-face',
      body: 'female-body',
    },
    male: {
      face: 'male-face',
      body: 'male-body',
    },
  };
  document.querySelectorAll('[data-sample-photo]').forEach((button) => {
    button.addEventListener('click', async () => {
      const kind = button.dataset.samplePhoto;
      if (!genderReady() || state.photoStatus[kind] === 'checking') return;
      const sampleId = SAMPLE_PHOTOS[state.gender]?.[kind];
      if (!sampleId) return;
      track('sample_photos_used', { kind });
      await uploadPhoto(kind, null, { sampleId });
    });
  });

  document.querySelector('.manual-form').addEventListener('click', (event) => {
    const button = event.target.closest('[data-manual]'); if (!button) return;
    const key = button.dataset.manual; state.manual[key] = button.dataset.value;
    manualSelections.add(key);
    document.querySelectorAll(`[data-manual="${key}"]`).forEach((item) => {
      const selected = item === button;
      item.classList.toggle('is-selected', selected);
      item.setAttribute('aria-pressed', String(selected));
    });
    document.querySelector('#manualNext').disabled = editingFeature ? !manualSelections.has(editingFeature) : !manualSelections.size || !Object.values(state.manual).every(Boolean);
  });
  document.querySelector('#manualNext').addEventListener('click', (event) => runButtonAction(event.currentTarget, async () => {
    const selectedFields = editingFeature ? [editingFeature].filter(key => manualSelections.has(key)) : [...manualSelections];
    if (!selectedFields.length) return;
    const sessionId = await ensureSession();
    const result = await api.saveManualProfile(sessionId, Object.fromEntries(selectedFields.map(key => [key, state.manual[key]])));
    state.revision = result.session?.revision || state.revision;
    track('manual_saved');
    manualSelections.clear();
    showScreen('suit');
  }));

  document.querySelector('#paletteGrid').addEventListener('click', (event) => {
    const button = event.target.closest('[data-palette]'); if (!button) return;
    state.palette = state.palette === button.dataset.palette ? null : button.dataset.palette;
    document.querySelectorAll('[data-palette]').forEach((item) => { const selected = item.dataset.palette === state.palette; item.classList.toggle('is-selected', selected); item.setAttribute('aria-pressed', String(selected)); });
    document.querySelector('#likeNext').disabled = false;
  });
  document.querySelector('#likeNext').addEventListener('click', (event) => runButtonAction(event.currentTarget, async () => {
    const sessionId = await ensureSession();
    state.axes = {
      shape: Number(document.querySelector('#shapeRange').value),
      energy: Number(document.querySelector('#energyRange').value),
      trend: Number(document.querySelector('#trendRange').value),
    };
    const result = await api.savePreferences(sessionId, { axes: state.axes, palette: state.palette });
    state.revision = result.session?.revision || state.revision;
    track('preferences_saved', { palette: state.palette });
    // 重新测试时跳过 suit 环节（照片在档案页维护），直接进入 vibe。
    showScreen(retestEntry && state.gender ? 'vibe' : 'suit');
  }));

  // 「先不测试，去 App 逛逛」：内测用户直进主站；未解锁用户进邀请码解锁屏
  // （此前未解锁用户会被主站门槛弹回登录页，体验断裂）。
  document.querySelector('.assessment-skip')?.addEventListener('click', (event) => {
    if (state.authUser?.beta_qualified) return;
    event.preventDefault();
    enterBetaUnlock('like', 'generic');
  });

  // 报告页「去试穿」：未解锁用户直接进邀请码解锁屏，不再绕道主站被门槛弹回。
  document.querySelector('#continueToApp')?.addEventListener('click', (event) => {
    const user = state.authUser;
    if (!user || String(user.user_id || '').startsWith('guest_') || user.beta_qualified !== false) return;
    event.preventDefault();
    enterBetaUnlock('report');
  });

  document.querySelector('#vibeQuestions').addEventListener('click', (event) => {
    const button = event.target.closest('[data-answer]'); if (!button) return;
    const field = button.closest('[data-question]'); state.answers[field.dataset.question] = button.dataset.answer;
    field.querySelectorAll('[data-answer]').forEach((item) => {
      const selected = item === button;
      item.classList.toggle('is-selected', selected);
      item.setAttribute('aria-pressed', String(selected));
    });
    const complete = Object.keys(state.answers).length === 3;
    const next = document.querySelector('#vibeNext');
    next.disabled = !complete;
    next.textContent = complete ? '生成风格报告' : '下一步';
  });

  const loadingStages = [
    { percent: 33, artStage: 25, line: '先看见真实的你', src: '/static/selfit/assets/loading-stage-25@2x.webp?v=20260826' },
    { percent: 67, artStage: 50, line: '寻找你同频的灵感', src: '/static/selfit/assets/loading-stage-50@2x.webp?v=20260826' },
    { percent: 100, line: '我们认识你了...', src: '/static/selfit/assets/loading-stage-100@2x.webp?v=20260826' },
  ];
  const loadingStagePromises = new Map();
  const loadLoadingStage = (src) => {
    if (loadingStagePromises.has(src)) return loadingStagePromises.get(src);
    const promise = new Promise((resolve) => {
      const tryLoad = (attempt = 0) => {
        const image = new Image();
        image.decoding = 'async';
        image.addEventListener('load', () => {
          if (attempt) track('image_load_recovered', { path: imagePathForTelemetry(src), attempts: attempt });
          resolve(image.currentSrc || image.src || src);
        }, { once: true });
        image.addEventListener('error', () => {
          const nextAttempt = attempt + 1;
          track('image_load_failed', { path: imagePathForTelemetry(src), attempt: nextAttempt });
          const delayMs = IMAGE_RETRY_DELAYS_MS[attempt];
          if (delayMs == null) { resolve(''); return; }
          window.setTimeout(() => tryLoad(nextAttempt), delayMs);
        }, { once: true });
        image.src = attempt ? imageRetryUrl(src, attempt) : src;
      };
      tryLoad();
    });
    loadingStagePromises.set(src, promise);
    return promise;
  };
  loadingStages.forEach(({ src }) => { void loadLoadingStage(src); });
  const loadingStory = window.SelfitLoadingStory.create({
    stages: loadingStages,
    art: document.querySelector('#loadingArt'),
    lines: document.querySelector('#loadingLines'),
    percent: document.querySelector('#loadingPercent'),
    loadImage: loadLoadingStage,
  });
  const setLoadingProgress = (progress) => loadingStory.update(progress);
  document.querySelector('#vibeNext').addEventListener('click', () => generateReport());

  const DEFAULT_REPORT_DATA = Object.freeze({
    eyebrow: '', title: '', heroImage: {}, traits: [], summary: '', illustration: {}, colors: [],
    makeup: [], hair: [], source: {}, outfitSummary: '', outfits: [], adviceIntro: '', advice: [],
  });

  const buildMockReport = (session) => {
    // mock 演示同样跑完整 16 型分型（与后端 selfit_persona.py 同口径），
    // 避免「只看色板、其余题目不影响结果」的失真演示。
    const persona = window.SelfitPersona || null;
    if (!persona) return { typeId: 'mute' };
    const vector = persona.buildUserVector(session);
    const classification = persona.classifyPersona(vector, session.gender);
    return { typeId: classification.primary_persona.toLowerCase(), gender: session.gender || null };
  };
  const runtimeConfig = window.__SELFIT_CONFIG__ || {};
  const publicShareToken = String(runtimeConfig.publicShareToken || '');
  // 邀请码登录仅内部测试用：默认隐藏，服务端配置 SELFIT_SHOW_INVITE_LOGIN=1 时显示。
  document.querySelector('[data-invite-login]')?.toggleAttribute('hidden', !runtimeConfig.showInviteLogin);
  const queryMode = new URLSearchParams(location.search).get('apiMode');
  const runtimeMode = queryMode || runtimeConfig.apiMode || shell.dataset.apiMode || 'mock';
  auth = window.SelfitAuth.createClient({
    mode: runtimeConfig.authMode || runtimeMode,
    baseUrl: runtimeConfig.authBase || '/auth',
    timeoutMs: runtimeConfig.timeoutMs || 15000,
  });
  // A visitor session supports try-on but does not replace the initial login step.
  const storedVisitor = auth.readStoredSession()?.user?.user_id?.startsWith('guest_');
  authReady = (storedVisitor ? Promise.resolve(null) : auth.restore()).then((session) => {
    state.authUser = session?.user || null;
    return session;
  }).catch(() => null);
  api = window.SelfitApi.createClient({
    mode: runtimeMode,
    baseUrl: runtimeConfig.apiBase || shell.dataset.apiBase || '/api/v1/selfit',
    timeoutMs: runtimeConfig.timeoutMs || 15000,
    buildMockReport,
    getAccessToken: () => auth.accessToken,
  });
  if (handoffToken) {
    document.querySelectorAll('[data-handoff-context]').forEach((node) => { node.hidden = false; });
    api.getMirrorHandoff(handoffToken).catch((error) => {
      document.querySelectorAll('[data-handoff-context]').forEach((node) => {
        node.textContent = error.message || '这个二维码已失效，请回到镜子重新生成。';
        node.dataset.state = 'error';
      });
    });
  }
  let sessionPromise = null;
  let startFreshSession = false;
  const startNewAssessment = () => {
    // Starting again is a new test, not a restoration of the previous answers.
    // Keep old reports/photos intact; only stop reusing the old session pointer.
    state.sessionId = null;
    state.revision = 1;
    state.manual = { skin: null, faceShape: null, bodyShape: null };
    state.gender = null;
    state.genderEditing = false;
    manualSelections.clear();
    startFreshSession = true;
    resetOnboardingPhotos();
  };
  const persistSession = (session) => {
    localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify({ sessionId: session.sessionId, expiresAt: session.expiresAt, userId: state.authUser?.user_id || null }));
  };
  const readPersistedSession = () => {
    try {
      const stored = JSON.parse(localStorage.getItem(SESSION_STORAGE_KEY) || 'null');
      const sameUser = stored?.userId && state.authUser?.user_id && stored.userId === state.authUser.user_id;
      return stored?.sessionId && sameUser && (!stored.expiresAt || Date.parse(stored.expiresAt) > Date.now()) ? stored : null;
    } catch { return null; }
  };
  const ensureSession = async () => {
    if (state.sessionId) return state.sessionId;
    if (sessionPromise) return sessionPromise;
    sessionPromise = (async () => {
      await authReady;
      const stored = retestEntry || startFreshSession ? null : readPersistedSession();
      if (stored) {
        try {
          const restored = await api.getSession(stored.sessionId);
          state.sessionId = restored.session.sessionId;
          state.revision = restored.session.revision || 0;
          state.gender = restored.session.gender || null;
          return state.sessionId;
        } catch { localStorage.removeItem(SESSION_STORAGE_KEY); }
      }
      const created = await api.createSession({ schemaVersion: 'selfit-onboarding-v1', locale: document.documentElement.lang || 'zh-CN', onboardingMode: retestEntry ? 'retest' : 'new' });
      state.sessionId = created.session.sessionId;
      state.revision = created.session.revision || 1;
      state.gender = created.session.gender || null;
      startFreshSession = false;
      persistSession(created.session);
      return state.sessionId;
    })().finally(() => { sessionPromise = null; });
    return sessionPromise;
  };

  const reportNodes = {
    hero: document.querySelector('[data-report-hero]'),
    heroImage: document.querySelector('[data-report-hero-image]'),
    eyebrow: document.querySelector('[data-report-eyebrow]'),
    title: document.querySelector('[data-report-title]'),
    traits: document.querySelector('#reportTraits'),
    illustration: document.querySelector('[data-report-illustration]'),
    summary: document.querySelector('[data-report-summary]'),
    colors: document.querySelector('#reportColors'),
    makeup: document.querySelector('#reportMakeup'),
    hair: document.querySelector('#reportHair'),
    sourceLogo: document.querySelector('[data-report-source-logo]'),
    sourceCopy: document.querySelector('[data-report-source-copy]'),
    sourceAvatars: document.querySelector('[data-report-source-avatars]'),
    outfitSummary: document.querySelector('[data-report-outfit-summary]'),
    outfits: document.querySelector('#reportOutfits'),
    advice: document.querySelector('[data-report-advice-list]'),
    adviceIntro: document.querySelector('[data-report-advice-intro]'),
  };
  const hasOwn = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
  const escapeReportMarkdown = (value) => String(value ?? '').replace(/[&<>'"]/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
  })[character]);
  const renderReportInlineMarkdown = (value) => escapeReportMarkdown(value)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/~~([^~]+)~~/g, '<s>$1</s>')
    .replace(/(^|[^*])\*([^*]+)\*/g, '$1<em>$2</em>');
  const renderReportMarkdown = (value) => {
    const lines = String(value ?? '').replace(/\r\n?/g, '\n').split('\n');
    let html = '';
    let listType = '';
    const closeList = () => { if (listType) { html += `</${listType}>`; listType = ''; } };
    lines.forEach((line) => {
      const bullet = line.match(/^\s*[-*]\s+(.+)$/);
      const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
      const heading = line.match(/^\s*#{1,3}\s+(.+)$/);
      if (bullet || ordered) {
        const type = bullet ? 'ul' : 'ol';
        if (listType !== type) { closeList(); html += `<${type}>`; listType = type; }
        html += `<li>${renderReportInlineMarkdown((bullet || ordered)[1])}</li>`;
        return;
      }
      closeList();
      if (!line.trim()) { html += '<span class="report-markdown-space"></span>'; return; }
      if (heading) { html += `<strong class="report-markdown-heading">${renderReportInlineMarkdown(heading[1])}</strong>`; return; }
      html += `<p>${renderReportInlineMarkdown(line)}</p>`;
    });
    closeList();
    return html;
  };
  const templateCardToReportCard = (item = {}) => ({
    id: item.id || '',
    imageAssetId: item.image?.assetId || '',
    name: item.name || '',
    byline: item.byline || '',
    sourceUrl: item.sourceUrl || '',
    imageUrl: item.image?.src || '',
    alt: item.image?.alt || item.name || '',
  });
  const templateToReportData = (template) => {
    if (!template) return null;
    const outfits = template.recommendations?.outfits || {};
    return {
      typeId: template.typeId,
      templateId: template.templateId || template.typeId,
      title: template.metadata?.name || '',
      eyebrow: template.metadata?.code || '',
      traits: (template.keywords || []).map((keyword) => typeof keyword === 'string' ? keyword : keyword.label).filter(Boolean),
      summary: template.summary || '',
      heroImage: template.hero?.image || {},
      illustration: {},
      colors: (template.colors?.items || []).slice(0, template.colors?.renderLimit || personalityCatalog.renderRules?.colors?.limit || 5),
      makeup: (template.recommendations?.makeup || []).map(templateCardToReportCard),
      hair: (template.recommendations?.hair || []).map(templateCardToReportCard),
      source: outfits.source || {},
      outfitSummary: outfits.summary || '',
      outfits: (outfits.items || []).map(templateCardToReportCard),
      adviceIntro: template.conclusion?.intro || '',
      advice: (template.conclusion?.points || []).map((point) => typeof point === 'string' ? point : [point.title, point.description].filter(Boolean).join('：')),
    };
  };
  const resolvePersonalityPayload = (payload = {}) => {
    if (!payload?.typeId) return payload;
    const genderId = `${String(payload.typeId).toLowerCase()}-${payload.gender}`;
    const candidate = personalityCatalog.variants?.[genderId];
    const genderTemplate = candidate?.gender === payload.gender ? candidate : null;
    const template = personalityCatalog.variants?.[payload.templateId] || genderTemplate || personalityCatalog.types?.[String(payload.typeId).toLowerCase()];
    if (!template) return payload;
    const base = templateToReportData(template);
    if (!payload.templateVersion && payload.gender === 'male' && !genderTemplate) {
      Object.assign(payload = { ...payload }, {
        templateId: genderId, recommendationStatus: 'pending_gender_content',
        recommendationNotice: '已记下你的性别。男性专属穿搭参考正在准备中，先看看你的型格与配色。',
        heroImage: {}, makeup: [], hair: [], outfits: [], source: { name: '', copy: '', avatars: {} },
        outfitSummary: '', adviceIntro: '', advice: [],
        summary: '这份型格来自你的风格偏好与表达选择，性别不会改变你的型格评分。',
      });
    }
    const personalization = payload.personalization && typeof payload.personalization === 'object' ? payload.personalization : {};
    return {
      ...base,
      ...payload,
      ...personalization,
      heroImage: personalization.heroImage || payload.heroImage || base.heroImage,
      source: payload.recommendationStatus === 'pending_gender_content' ? {} : { ...base.source, ...(payload.source || {}), ...(personalization.source || {}) },
    };
  };
  const cleanAdviceCopy = (value) => String(value || '').replace(/^\s*建议\s*[：:]\s*/, '').trim();
  const normalizeReport = (payload = {}) => {
    payload = resolvePersonalityPayload(payload);
    const hasPayload = Boolean(payload && Object.keys(payload).length);
    const list = (key) => {
      if (!hasPayload) return DEFAULT_REPORT_DATA[key];
      return hasOwn(payload, key) && Array.isArray(payload[key]) ? payload[key] : [];
    };
    const illustration = hasPayload
      ? (payload.illustration && typeof payload.illustration === 'object' ? payload.illustration : {})
      : DEFAULT_REPORT_DATA.illustration;
    const source = hasPayload
      ? (payload.source && typeof payload.source === 'object' ? payload.source : {})
      : DEFAULT_REPORT_DATA.source;
    return {
      ...DEFAULT_REPORT_DATA,
      ...payload,
      heroImage: hasPayload
        ? (payload.heroImage && typeof payload.heroImage === 'object' ? payload.heroImage : {})
        : DEFAULT_REPORT_DATA.heroImage,
      summary: hasPayload ? (payload.summary || '') : DEFAULT_REPORT_DATA.summary,
      outfitSummary: hasPayload ? (payload.outfitSummary || '') : DEFAULT_REPORT_DATA.outfitSummary,
      adviceIntro: hasPayload ? (payload.adviceIntro || '') : DEFAULT_REPORT_DATA.adviceIntro,
      traits: list('traits'),
      colors: list('colors'),
      makeup: list('makeup'),
      hair: list('hair'),
      outfits: list('outfits').map((item) => ({
        ...item,
        name: item.name || item.title || '',
        byline: item.byline || (item.author ? `@${String(item.author).replace(/^@/, '')}` : ''),
      })),
      advice: list('advice').map(cleanAdviceCopy).filter(Boolean),
      illustration,
      source: {
        ...source,
        avatars: source.avatars && typeof source.avatars === 'object' ? source.avatars : {},
      },
    };
  };
  const displayImageURL = source => window.SelfitImageURL ? window.SelfitImageURL(source) : (source || '');
  const appendImageCards = (container, items) => {
    const cards = items.filter((item) => item && item.imageUrl).map((item) => {
      const figure = document.createElement('figure');
      const image = Object.assign(document.createElement('img'), {
        src: displayImageURL(item.imageUrl), alt: item.alt || item.name || '', loading: 'lazy', decoding: 'async',
      });
      const caption = document.createElement('figcaption');
      caption.append(document.createTextNode(item.name || ''));
      if (item.byline) caption.append(Object.assign(document.createElement('small'), { textContent: item.byline }));
      figure.append(image, caption);
      return figure;
    });
    container.replaceChildren(...cards);
    return cards.length;
  };
  const toggleReportSection = (name, visible) => {
    document.querySelector(`[data-report-section="${name}"]`)?.toggleAttribute('hidden', !visible);
  };
  const mobileHeroSource = (value) => {
    const source = String(value || '');
    const isBundledPersonalityHero = source.includes('/static/selfit/assets/personality/') && source.includes('/hero.webp');
    return displayImageURL(isBundledPersonalityHero ? source.replace('/hero.webp', '/hero-mobile.webp') : source);
  };
  const REPORT_RESOURCE_MIN_HOLD_MS = 1200;
  const REPORT_RESOURCE_MAX_WAIT_MS = 8000;
  const delay = (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));
  const reportResourceUrls = (data) => {
    const typeId = String(data.typeId || '').toLowerCase();
    const urls = [
      mobileHeroSource(data.heroImage?.src),
      data.illustration?.imageUrl,
      data.source?.avatars?.imageUrl || '/static/selfit/assets/report-user-avatar-stack@4x.webp',
      ...data.makeup.map((item) => item.imageUrl),
      ...data.hair.map((item) => item.imageUrl),
      ...data.outfits.map((item) => item.imageUrl),
      typeId ? `/static/selfit/assets/personality/${typeId}/share-ornament.webp?v=20260829-webp-v1` : '',
    ];
    return [...new Set(urls.filter(Boolean).map(displayImageURL))];
  };
  const preloadReportResource = (src, heroSrc) => new Promise((resolve) => {
    const image = new Image();
    image.decoding = 'async';
    image.fetchPriority = src === heroSrc ? 'high' : 'auto';
    const settle = (loaded) => resolve({ src, loaded });
    image.addEventListener('load', async () => {
      if (typeof image.decode === 'function') await image.decode().catch(() => {});
      settle(true);
    }, { once: true });
    image.addEventListener('error', () => settle(false), { once: true });
    image.src = src;
  });
  const waitForReportResources = async (data, minimumHoldMs = REPORT_RESOURCE_MIN_HOLD_MS) => {
    const urls = reportResourceUrls(data);
    const heroSrc = mobileHeroSource(data.heroImage?.src);
    const startedAt = Date.now();
    const resourcePromise = Promise.all(urls.map((src) => preloadReportResource(src, heroSrc)))
      .then((results) => ({ timedOut: false, results }));
    const timeoutPromise = delay(REPORT_RESOURCE_MAX_WAIT_MS)
      .then(() => ({ timedOut: true, results: [] }));
    const [outcome] = await Promise.all([
      Promise.race([resourcePromise, timeoutPromise]),
      delay(minimumHoldMs),
    ]);
    return { ...outcome, durationMs: Date.now() - startedAt, resourceCount: urls.length };
  };
  const reportTryOnUrl = (typeId, outfits, templateId = typeId) => {
    const query = new URLSearchParams({from: 'report', persona: typeId, screen: 'mirror'});
    const ids = [...new Set(outfits.map((item) => item.id).filter(Boolean))].slice(0, 4);
    if (ids.length) {
      query.set('report_notes', ids.join(','));
      query.set('report_template', templateId);
      query.set('report_assets', ids.map((id) => {
        const item = outfits.find((item) => item.id === id);
        return item.imageAssetId || item.assetId || item.image?.assetId || item.imageUrl?.match(/asset_[a-f0-9]{64}/)?.[0] || 'legacy';
      }).join(','));
    }
    return `/selfit/try-on?${query}`;
  };
  const renderReport = (payload = {}) => {
    const data = normalizeReport(payload);
    const reportTypeId = String(data.typeId || 'mute').toLowerCase();
    state.currentReportTypeId = reportTypeId;
    const continueToApp = document.querySelector('#continueToApp');
    const pendingGenderContent = data.recommendationStatus === 'pending_gender_content';
    if (continueToApp) continueToApp.hidden = false;
    document.querySelector('.report-actions').classList.remove('is-pending-gender');
    const fullHero = Boolean(data.heroImage?.src);
    const heroSource = fullHero ? mobileHeroSource(data.heroImage.src) : '';
    reportNodes.hero.classList.toggle('report-hero--full', fullHero);
    reportNodes.hero.classList.toggle('report-hero--text-only', !fullHero && !data.illustration.imageUrl);
    reportNodes.hero.classList.remove('report-hero--reference');
    reportNodes.heroImage.src = heroSource;
    reportNodes.heroImage.alt = fullHero ? (data.heroImage.alt || `${data.title} ${data.eyebrow} 人格封面`) : '';
    reportNodes.heroImage.hidden = !fullHero;
    reportNodes.eyebrow.textContent = data.eyebrow;
    reportNodes.title.textContent = data.title;
    // The current onboarding report keeps retake/share available from its first
    // viewport. Shared reports and incomplete data never expose owner actions.
    document.querySelector('.report-actions').hidden = !data.title || Boolean(publicShareToken);
    reportNodes.traits.replaceChildren(...data.traits.map((trait) => {
      const card = Object.assign(document.createElement('span'), { className: 'report-trait' });
      const lace = Object.assign(document.createElement('img'), {
        src: '/static/selfit/assets/lace-card@4x.webp?v=20260821', alt: '', width: 408, height: 604,
      });
      card.append(lace, Object.assign(document.createElement('b'), { textContent: trait }));
      return card;
    }));
    reportNodes.traits.hidden = data.traits.length === 0;
    reportNodes.illustration.src = displayImageURL(data.illustration.imageUrl);
    reportNodes.illustration.alt = data.illustration.alt || '';
    reportNodes.illustration.closest('figure').hidden = fullHero || !data.illustration.imageUrl;
    reportNodes.summary.innerHTML = renderReportMarkdown(data.summary);
    reportNodes.summary.hidden = !data.summary;
    const genderNotice = document.querySelector('[data-report-gender-notice]');
    genderNotice.textContent = data.recommendationNotice || '';
    genderNotice.hidden = !data.recommendationNotice;
    const visibleColors = data.colors.slice(0, personalityCatalog.renderRules?.colors?.limit || 5);
    reportNodes.colors.replaceChildren(...visibleColors.map((color) => {
      const swatch = Object.assign(document.createElement('span'), { textContent: color.name || '' });
      swatch.style.setProperty('--c', color.value || 'transparent');
      return swatch;
    }));
    toggleReportSection('colors', visibleColors.length > 0);
    toggleReportSection('makeup', appendImageCards(reportNodes.makeup, data.makeup) > 0);
    toggleReportSection('hair', appendImageCards(reportNodes.hair, data.hair) > 0);
    const proof = reportNodes.sourceLogo.closest('.report-proof');
    const hasSource = Boolean(data.source.name || data.source.copy || data.source.avatars.imageUrl);
    reportNodes.sourceLogo.alt = data.source.name || '小红书';
    reportNodes.sourceLogo.hidden = !hasSource;
    reportNodes.sourceCopy.textContent = data.source.copy || '';
    reportNodes.sourceAvatars.src = displayImageURL(data.source.avatars.imageUrl || '/static/selfit/assets/report-user-avatar-stack@4x.webp');
    reportNodes.sourceAvatars.alt = data.source.avatars.alt || '3 位真实用户头像';
    reportNodes.sourceAvatars.hidden = !hasSource;
    proof.hidden = !hasSource;
    reportNodes.outfitSummary.innerHTML = renderReportMarkdown(data.outfitSummary);
    reportNodes.outfitSummary.hidden = !data.outfitSummary;
    const visibleOutfits = data.outfits
      .filter((item) => item && item.imageUrl)
      .slice(0, personalityCatalog.renderRules?.outfits?.limit || 4);
    if (continueToApp) continueToApp.href = pendingGenderContent
      ? '/selfit/try-on?screen=mirror'
      : reportTryOnUrl(reportTypeId, visibleOutfits, data.templateId || reportTypeId);
    const outfitCards = visibleOutfits.map((item) => {
      const figure = document.createElement('figure');
      const image = Object.assign(document.createElement('img'), {
        src: displayImageURL(item.imageUrl), alt: item.alt || item.name || '', loading: 'lazy', decoding: 'async',
      });
      const caption = document.createElement('figcaption');
      caption.append(document.createTextNode(item.name || ''));
      if (item.byline) caption.append(Object.assign(document.createElement('small'), { textContent: item.byline }));
      figure.append(image, caption);
      return figure;
    });
    reportNodes.outfits.replaceChildren(...outfitCards);
    toggleReportSection('outfits', Boolean(outfitCards.length || data.outfitSummary));
    reportNodes.adviceIntro.innerHTML = renderReportMarkdown(data.adviceIntro);
    reportNodes.adviceIntro.hidden = !data.adviceIntro;
    reportNodes.advice.replaceChildren(...data.advice.map((copy) => {
      const point = Object.assign(document.createElement('div'), { className: 'report-advice-point' });
      const text = String(copy ?? '');
      const colonIndex = text.indexOf('：');
      if (colonIndex >= 0) {
        const lead = text.slice(0, colonIndex);
        const rest = text.slice(colonIndex + 1);
        point.innerHTML = `<p><span class="advice-lead">${renderReportInlineMarkdown(lead)}：</span>${renderReportInlineMarkdown(rest)}</p>`;
      } else {
        point.innerHTML = renderReportMarkdown(copy);
      }
      return point;
    }));
    document.querySelector('#reportAdvice').hidden = !(data.adviceIntro || data.advice.length);
    document.querySelector('[data-share-title]').textContent = data.title;
    document.querySelector('[data-share-eyebrow]').textContent = data.eyebrow || '';
    document.querySelector('[data-share-summary]').textContent = data.summary || data.traits.join(' · ') || data.title;
    const shareIllustration = document.querySelector('[data-share-illustration]');
    const shareOrnament = document.querySelector('[data-share-ornament]');
    const shareIdentityCard = document.querySelector('.share-card--identity');
    shareIdentityCard.dataset.personality = String(data.typeId || 'mute').toLowerCase();
    const shareTypeId = String(data.typeId || 'mute').toLowerCase();
    const shareIllustrationSource = `/static/selfit/assets/personality/${shareTypeId}/share-ornament.webp?v=20260829-webp-v1`;
    shareIllustration.src = shareIllustrationSource;
    shareIllustration.alt = `${data.title} 风格摆件`;
    shareIllustration.hidden = false;
    shareOrnament.hidden = shareIllustration.hidden;
    shareOrnament.classList.add('is-standalone');
    document.querySelector('[data-share-color-title]').textContent = data.title;
    document.querySelector('[data-share-inspiration-title]').textContent = data.title;
    document.querySelector('#shareCardColors').replaceChildren(...visibleColors.map((color) => {
      const swatch = document.createElement('i');
      swatch.style.setProperty('--c', color.value || 'transparent');
      swatch.setAttribute('aria-label', color.name || '推荐色');
      swatch.setAttribute('role', 'img');
      return swatch;
    }));
    const shareImages = [...data.makeup.slice(0, 2), ...data.hair.slice(0, 1), ...data.outfits.slice(0, 1)];
    document.querySelector('#shareCardImages').replaceChildren(...shareImages.map((item) => Object.assign(document.createElement('img'), {
      src: displayImageURL(item.imageUrl), alt: item.alt || item.name || item.title || '', loading: 'lazy', decoding: 'async',
    })));
    window.dispatchEvent(new CustomEvent('selfit:report-rendered', { detail: { data } }));
    return data;
  };
  const loadReport = async (url, init = {}) => {
    const response = await fetch(url, { ...init, headers: { Accept: 'application/json', ...(init.headers || {}) } });
    if (!response.ok) throw new Error(`报告数据加载失败（${response.status}）`);
    return renderReport(await response.json());
  };
  const generateReport = async () => {
    const button = document.querySelector('#vibeNext');
    button.disabled = true; button.setAttribute('aria-busy', 'true');
    showScreen('loading'); setLoadingProgress(25);
    track('report_started');
    try {
      const sessionId = await ensureSession();
      const saved = await api.saveVibe(sessionId, state.answers);
      state.revision = saved.session?.revision || state.revision;
      const created = await api.createReportJob(sessionId);
      state.reportJobId = created.job.jobId;
      const deadline = Date.now() + 120000;
      let completedJob = null;
      let loading75StartedAt = 0;
      while (Date.now() < deadline) {
        const result = await api.getReportJob(state.reportJobId);
        const cappedProgress = Math.min(result.job.progress || 25, 75);
        setLoadingProgress(cappedProgress);
        if (cappedProgress >= 75 && !loading75StartedAt) loading75StartedAt = Date.now();
        if (result.job.status === 'failed') throw new window.SelfitApi.SelfitApiError(result.job.error?.message || '报告生成失败，请重试。', result.job.error || {});
        if (result.job.status === 'completed') { completedJob = result.job; break; }
        await new Promise((resolve) => setTimeout(resolve, Math.max(250, Math.min(result.job.pollAfterMs || 800, 3000))));
      }
      if (!completedJob) throw new window.SelfitApi.SelfitApiError('报告生成时间较长，请稍后重试。', { code: 'report.timeout', retryable: true });
      state.reportId = completedJob.reportId;
      state.publicShare = null;
      const report = completedJob.report || (await api.getReport(state.reportId)).report;
      const preparedReport = normalizeReport(report);
      setLoadingProgress(75);
      if (!loading75StartedAt) loading75StartedAt = Date.now();
      const remaining75HoldMs = Math.max(0, REPORT_RESOURCE_MIN_HOLD_MS - (Date.now() - loading75StartedAt));
      const resourceOutcome = await waitForReportResources(preparedReport, remaining75HoldMs);
      track('report_resources_ready', {
        resourceCount: resourceOutcome.resourceCount,
        durationMs: resourceOutcome.durationMs,
        timedOut: resourceOutcome.timedOut,
        failedCount: resourceOutcome.results.filter((item) => !item.loaded).length,
      });
      track('report_completed', { reportId: state.reportId, typeId: report?.typeId || '' });
      await setLoadingProgress(100);
      renderReport(preparedReport);
      await delay(1200);
      showScreen('report');
    } catch (error) {
      track('report_failed', { message: error.message || '' });
      showScreen('vibe');
      toast(error.message || '报告生成失败，请重试。');
    } finally {
      button.removeAttribute('aria-busy');
      button.disabled = Object.keys(state.answers).length !== 3;
    }
  };
  window.selfitPersonalityReports = Object.freeze({
    catalogVersion: personalityCatalog.templateVersion || '',
    list: () => Object.values(personalityCatalog.types || {}).map((template) => ({
      typeId: template.typeId,
      name: template.metadata?.name || '',
      code: template.metadata?.code || '',
    })),
    get: (typeId) => personalityCatalog.types?.[String(typeId || '').toLowerCase()] || null,
    resolve: (typeId, personalization = {}) => normalizeReport({ typeId, personalization }),
    render: (typeId, personalization = {}) => renderReport({ typeId, personalization }),
  });
  window.selfitReport = Object.freeze({
    render: renderReport,
    load: loadReport,
    defaults: DEFAULT_REPORT_DATA,
    personalities: window.selfitPersonalityReports,
  });
  window.addEventListener('selfit:report-data', (event) => renderReport(event.detail || {}));
  renderReport(window.__SELFIT_REPORT__ || { typeId: 'mute' });

  const toastNode = document.querySelector('#toast');
  const toastHome = toastNode.parentElement;
  const toast = (copy) => {
    const openDialog = document.querySelector('dialog[open]');
    (openDialog || toastHome).appendChild(toastNode);
    toastNode.textContent = copy;
    toastNode.classList.add('is-visible');
    setTimeout(() => toastNode.classList.remove('is-visible'), 1800);
  };
  const runButtonAction = async (button, action) => {
    if (button.getAttribute('aria-busy') === 'true') return;
    button.disabled = true; button.setAttribute('aria-busy', 'true');
    try { await action(); }
    catch (error) { toast(error.message || '这次操作没有完成，请重试。'); }
    finally { button.removeAttribute('aria-busy'); button.disabled = false; }
  };
  if (shell.dataset.reportEndpoint) loadReport(shell.dataset.reportEndpoint).catch((error) => toast(error.message));
  const reportScreen = document.querySelector('[data-screen="report"]');
  const reportActions = document.querySelector('.report-actions');
  let reportScrollFrame = 0;
  const syncReportActions = () => {
    reportScrollFrame = 0;
    const shouldDock = reportScreen.classList.contains('is-active');
    reportActions.classList.toggle('is-docked', shouldDock);
    reportActions.toggleAttribute('inert', !shouldDock);
    reportActions.setAttribute('aria-hidden', shouldDock ? 'false' : 'true');
  };
  reportActions.toggleAttribute('inert', true);
  reportActions.setAttribute('aria-hidden', 'true');
  reportScreen.addEventListener('scroll', () => {
    if (!reportScrollFrame) reportScrollFrame = requestAnimationFrame(syncReportActions);
  }, { passive: true });
  const shareDialog = document.querySelector('#shareDialog');
  const shareCloseButton = shareDialog.querySelector('button[value="cancel"]');
  const supportsNativeDialog = typeof shareDialog.showModal === 'function';
  const openShareDialog = () => {
    if (supportsNativeDialog) shareDialog.showModal();
    else {
      shareDialog.setAttribute('open', '');
      document.documentElement.classList.add('has-open-dialog');
    }
  };
  const closeShareDialog = () => {
    if (supportsNativeDialog) shareDialog.close();
    else {
      shareDialog.removeAttribute('open');
      document.documentElement.classList.remove('has-open-dialog');
    }
  };
  shareCloseButton.addEventListener('click', (event) => {
    if (supportsNativeDialog) return;
    event.preventDefault();
    closeShareDialog();
  });
  shareDialog.addEventListener('close', () => {
    document.documentElement.classList.remove('has-open-dialog');
    toastHome.appendChild(toastNode);
  });
  const shareTrack = document.querySelector('#shareTrack');
  const shareSlides = [...document.querySelectorAll('[data-share-slide]')];
  const shareSlots = shareSlides.map((slide) => slide.closest('.share-card-slot'));
  const shareDots = [...document.querySelectorAll('[data-share-dot]')];
  const shareSlideStatus = document.querySelector('#shareSlideStatus');
  const shareSaveButton = document.querySelector('#saveShareCard');
  const shareSaveLabel = document.querySelector('[data-share-save-label]');
  const saveImageGuide = document.querySelector('#saveImageGuide');
  const saveImagePreview = document.querySelector('#saveImagePreview');
  let shareSlideIndex = 0;
  let shareScrollFrame = 0;
  let sharePreviewFrame = 0;
  let saveImagePreviewUrl = '';
  const SHARE_CARD_WIDTH = 324;
  const SHARE_CARD_HEIGHT = 522;
  const SHARE_EXPORT_SCALE = 2;
  const roundedRectPath = (context, x, y, width, height, radius) => {
    const safeRadius = Math.max(0, Math.min(radius, width / 2, height / 2));
    context.beginPath();
    context.moveTo(x + safeRadius, y);
    context.arcTo(x + width, y, x + width, y + height, safeRadius);
    context.arcTo(x + width, y + height, x, y + height, safeRadius);
    context.arcTo(x, y + height, x, y, safeRadius);
    context.arcTo(x, y, x + width, y, safeRadius);
    context.closePath();
  };
  const loadCanvasImage = (source) => new Promise((resolve, reject) => {
    const image = new Image();
    image.decoding = 'async';
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error('分享卡片图片加载失败，请稍后重试。'));
    image.src = displayImageURL(source);
  });
  const drawCoverImage = (context, image, x, y, width, height, focusX = 0.5, focusY = 0.5) => {
    const imageRatio = image.naturalWidth / image.naturalHeight;
    const frameRatio = width / height;
    let sourceX = 0;
    let sourceY = 0;
    let sourceWidth = image.naturalWidth;
    let sourceHeight = image.naturalHeight;
    if (imageRatio > frameRatio) {
      sourceWidth = image.naturalHeight * frameRatio;
      sourceX = (image.naturalWidth - sourceWidth) * focusX;
    } else {
      sourceHeight = image.naturalWidth / frameRatio;
      sourceY = (image.naturalHeight - sourceHeight) * focusY;
    }
    context.drawImage(image, sourceX, sourceY, sourceWidth, sourceHeight, x, y, width, height);
  };
  const drawContainImage = (context, image, x, y, width, height) => {
    const scale = Math.min(width / image.naturalWidth, height / image.naturalHeight);
    const drawWidth = image.naturalWidth * scale;
    const drawHeight = image.naturalHeight * scale;
    context.drawImage(image, x + (width - drawWidth) / 2, y + (height - drawHeight) / 2, drawWidth, drawHeight);
  };
  const drawShareMaterial = (context, personality, width, height) => {
    if (personality === 'loop') {
      context.strokeStyle = 'rgba(255,255,255,.14)';
      context.lineWidth = .7;
      for (let offset = -height; offset < width + height; offset += 7) {
        context.beginPath(); context.moveTo(offset, 0); context.lineTo(offset - height, height); context.stroke();
      }
    } else if (personality === 'noir') {
      context.lineWidth = .7;
      for (let offset = -height; offset < width + height; offset += 34) {
        context.strokeStyle = 'rgba(118,123,127,.13)';
        context.beginPath(); context.moveTo(offset, 0); context.lineTo(offset + height, height); context.stroke();
        context.strokeStyle = 'rgba(255,255,255,.72)';
        context.beginPath(); context.moveTo(offset, height); context.lineTo(offset + height, 0); context.stroke();
      }
    } else if (personality === 'void') {
      context.fillStyle = 'rgba(255,255,255,.22)';
      for (let y = 11; y < height; y += 22) for (let x = 11; x < width; x += 22) {
        context.beginPath(); context.arc(x, y, .8, 0, Math.PI * 2); context.fill();
      }
    } else if (personality === 'oops') {
      context.lineWidth = .5;
      context.strokeStyle = 'rgba(100,83,66,.07)';
      for (let y = 1; y < height; y += 4) { context.beginPath(); context.moveTo(0, y); context.lineTo(width, y); context.stroke(); }
      context.strokeStyle = 'rgba(255,255,255,.24)';
      for (let x = 1; x < width; x += 5) { context.beginPath(); context.moveTo(x, 0); context.lineTo(x, height); context.stroke(); }
    }
  };
  const nextSharePaint = () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const waitForShareCardAssets = async (card) => {
    if (document.fonts?.ready) await document.fonts.ready;
    await Promise.all([...card.querySelectorAll('img')].map(async (image) => {
      image.loading = 'eager';
      if (!image.complete || !image.naturalWidth) {
        await new Promise((resolve, reject) => {
          image.addEventListener('load', resolve, { once: true });
          image.addEventListener('error', () => reject(new Error('分享卡片图片加载失败，请稍后重试。')), { once: true });
        });
      }
      if (typeof image.decode === 'function') await image.decode().catch(() => {});
    }));
    await nextSharePaint();
  };
  const createShareExportSurface = (sourceCard) => {
    const stage = document.createElement('div');
    stage.className = 'share-export-stage';
    stage.setAttribute('aria-hidden', 'true');
    const card = sourceCard.cloneNode(true);
    card.classList.add('is-current', 'share-export-card');
    card.querySelectorAll('[id]').forEach((element) => element.removeAttribute('id'));
    stage.append(card);
    document.body.append(stage);
    return { card, stage };
  };
  const textNodeLines = (node) => {
    const lines = [];
    for (let index = 0; index < node.length; index += 1) {
      const range = document.createRange();
      range.setStart(node, index);
      range.setEnd(node, index + 1);
      const rect = range.getBoundingClientRect();
      range.detach?.();
      const character = node.textContent[index];
      if (!rect.width && !rect.height) continue;
      let line = lines[lines.length - 1];
      if (!line || Math.abs(line.top - rect.top) > Math.max(1, rect.height * .45)) {
        line = { text: '', left: rect.left, top: rect.top, height: rect.height };
        lines.push(line);
      }
      line.text += character;
      line.left = Math.min(line.left, rect.left);
      line.top = Math.min(line.top, rect.top);
      line.height = Math.max(line.height, rect.height);
    }
    return lines.map((line) => ({ ...line, text: line.text.replace(/\s+/g, ' ').trim() })).filter((line) => line.text);
  };
  const renderShareCard = async (sourceCard) => {
    const { card, stage } = createShareExportSurface(sourceCard);
    try {
      await waitForShareCardAssets(card);
    const cardRect = card.getBoundingClientRect();
    const width = SHARE_CARD_WIDTH;
    const height = SHARE_CARD_HEIGHT;
    if (!width || !height) throw new Error('当前分享卡片还没有准备好。');

    const canvas = document.createElement('canvas');
    canvas.width = width * SHARE_EXPORT_SCALE;
    canvas.height = height * SHARE_EXPORT_SCALE;
    const context = canvas.getContext('2d');
    if (!context) throw new Error('当前浏览器不支持图片导出。');
    context.scale(SHARE_EXPORT_SCALE, SHARE_EXPORT_SCALE);
    context.imageSmoothingEnabled = true;
    context.imageSmoothingQuality = 'high';

    const cardStyle = getComputedStyle(card);
    const cardRadius = parseFloat(cardStyle.borderTopLeftRadius) || 0;
    context.save();
    roundedRectPath(context, 0, 0, width, height, cardRadius);
    context.clip();
    context.fillStyle = cardStyle.backgroundColor;
    context.fillRect(0, 0, width, height);
    const backgroundUrl = cardStyle.backgroundImage.match(/url\(["']?(.*?)["']?\)/)?.[1];
    if (backgroundUrl) drawCoverImage(context, await loadCanvasImage(backgroundUrl), 0, 0, width, height);
    drawShareMaterial(context, card.dataset.personality || '', width, height);
    context.restore();

    card.querySelectorAll('.share-card-colors i').forEach((swatch) => {
      const rect = swatch.getBoundingClientRect();
      const style = getComputedStyle(swatch);
      const x = rect.left - cardRect.left;
      const y = rect.top - cardRect.top;
      context.save();
      context.shadowColor = 'rgba(60,21,25,.12)';
      context.shadowBlur = 12;
      context.shadowOffsetY = 2;
      context.fillStyle = style.backgroundColor;
      context.beginPath();
      context.arc(x + rect.width / 2, y + rect.height / 2, Math.max(0, rect.width / 2 - 1.5), 0, Math.PI * 2);
      context.fill();
      context.shadowColor = 'transparent';
      context.strokeStyle = 'rgba(255,255,255,.8)';
      context.lineWidth = 3;
      context.stroke();
      context.restore();
    });

    const imageElements = [...card.querySelectorAll('img')];
    await Promise.all(imageElements.map(async (element) => {
      const image = element.complete && element.naturalWidth ? element : await loadCanvasImage(element.currentSrc || element.src);
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      const x = rect.left - cardRect.left;
      const y = rect.top - cardRect.top;
      const radius = parseFloat(style.borderTopLeftRadius) || 0;
      context.save();
      roundedRectPath(context, x, y, rect.width, rect.height, radius);
      context.clip();
      const isShareOrnament = element.matches('[data-share-illustration]');
      if (isShareOrnament || style.objectFit === 'contain') {
        drawContainImage(context, image, x, y, rect.width, rect.height);
      } else {
        drawCoverImage(context, image, x, y, rect.width, rect.height, 0.5, 0.5);
      }
      context.restore();
    }));

    const walker = document.createTreeWalker(card, NodeFilter.SHOW_TEXT, {
      acceptNode: (node) => node.textContent.trim() && getComputedStyle(node.parentElement).display !== 'none'
        ? NodeFilter.FILTER_ACCEPT
        : NodeFilter.FILTER_REJECT,
    });
    while (walker.nextNode()) {
      const node = walker.currentNode;
      const parent = node.parentElement;
      const style = getComputedStyle(parent);
      const fontSize = parseFloat(style.fontSize) || 16;
      const lines = textNodeLines(node);
      const lineHeight = parseFloat(style.lineHeight) || fontSize * 1.2;
      const firstLineTop = lines[0]?.top || 0;
      const glyphOffset = Math.max(0, ((lines[0]?.height || fontSize) - fontSize) / 2);
      lines.forEach((line, lineIndex) => {
        context.save();
        context.globalAlpha = Number.parseFloat(style.opacity) || 1;
        context.fillStyle = style.color;
        context.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
        context.textAlign = 'left';
        context.textBaseline = 'top';
        context.fillText(line.text, line.left - cardRect.left, firstLineTop - cardRect.top + (lineIndex * lineHeight) + glyphOffset);
        context.restore();
      });
    }

    return await new Promise((resolve, reject) => canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error('分享卡片生成失败，请重试。'));
    }, 'image/png'));
    } finally {
      stage.remove();
    }
  };
  const isAppleMobileDevice = /iPad|iPhone|iPod/i.test(navigator.userAgent)
    || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const isAndroidDevice = /Android/i.test(navigator.userAgent);
  const isWechatBrowser = /MicroMessenger/i.test(navigator.userAgent);
  const shareExportBlobs = new Map();
  const shareExportPromises = new Map();
  const shareExportErrors = new Map();
  let shareExportRevision = 0;
  const invalidateShareExports = () => {
    shareExportRevision += 1;
    shareExportBlobs.clear();
    shareExportPromises.clear();
    shareExportErrors.clear();
  };
  window.addEventListener('selfit:report-rendered', invalidateShareExports);
  const shareCardFilename = (index) => `selfit-style-card-${index + 1}@2x.png`;
  const resetSaveImageGuide = () => {
    saveImageGuide.hidden = true;
    saveImagePreview.removeAttribute('src');
    if (saveImagePreviewUrl) URL.revokeObjectURL(saveImagePreviewUrl);
    saveImagePreviewUrl = '';
  };
  const closeSaveImageGuide = () => {
    if (saveImageGuide.hidden) return;
    resetSaveImageGuide();
    openShareDialog();
    syncShareSaveButton();
    requestAnimationFrame(() => {
      syncSharePreviewScale();
      goToShareSlide(shareSlideIndex, false);
    });
  };
  const openSaveImageGuide = (blob) => {
    resetSaveImageGuide();
    closeShareDialog();
    saveImagePreviewUrl = URL.createObjectURL(blob);
    saveImagePreview.src = saveImagePreviewUrl;
    saveImageGuide.hidden = false;
    saveImageGuide.querySelector('[data-close-save-guide]')?.focus({ preventScroll: true });
  };
  saveImageGuide.querySelectorAll('[data-close-save-guide]').forEach((button) => button.addEventListener('click', () => closeSaveImageGuide()));
  saveImageGuide.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    event.preventDefault();
    closeSaveImageGuide();
  });
  const triggerBrowserDownload = (blob, index) => {
    const objectUrl = URL.createObjectURL(blob);
    const link = Object.assign(document.createElement('a'), {
      href: objectUrl,
      download: shareCardFilename(index),
    });
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
  };
  const fallbackSaveShareCard = (blob, index) => {
    if (isWechatBrowser || isAppleMobileDevice) {
      openSaveImageGuide(blob);
      return { method: 'long-press' };
    }
    triggerBrowserDownload(blob, index);
    return { method: isAndroidDevice ? 'android-download' : 'browser-download' };
  };
  const saveShareCardToDevice = (blob, index) => {
    const file = typeof File === 'function'
      ? new File([blob], shareCardFilename(index), { type: 'image/png', lastModified: Date.now() })
      : null;
    const canShareFile = Boolean(!isWechatBrowser && file && navigator.share && navigator.canShare?.({ files: [file] }));
    if (!canShareFile) return Promise.resolve(fallbackSaveShareCard(blob, index));
    toast(isAppleMobileDevice ? '请在系统菜单选择“存储图像”' : '请选择相册或图片应用保存');
    try {
      return navigator.share({ files: [file], title: 'selfit 风格报告' })
        .then(() => ({ method: 'system-share' }))
        .catch((error) => {
          if (error?.name === 'AbortError') return { method: 'cancelled' };
          return fallbackSaveShareCard(blob, index);
        });
    } catch {
      return Promise.resolve(fallbackSaveShareCard(blob, index));
    }
  };
  const syncShareSaveButton = () => {
    const isReady = shareExportBlobs.has(shareSlideIndex);
    const isPreparing = shareExportPromises.has(shareSlideIndex);
    shareSaveButton.disabled = isPreparing;
    shareSaveLabel.textContent = isReady ? '保存到相册' : (isPreparing ? '正在生成图片…' : '生成并保存');
  };
  const prepareShareCard = (index) => {
    if (shareExportBlobs.has(index)) return Promise.resolve(shareExportBlobs.get(index));
    if (shareExportPromises.has(index)) return shareExportPromises.get(index);
    shareExportErrors.delete(index);
    const exportRevision = shareExportRevision;
    const promise = renderShareCard(shareSlides[index])
      .then((blob) => {
        if (exportRevision === shareExportRevision) shareExportBlobs.set(index, blob);
        return blob;
      })
      .catch((error) => {
        if (exportRevision === shareExportRevision) shareExportErrors.set(index, error);
        return null;
      })
      .finally(() => {
        if (shareExportPromises.get(index) === promise) shareExportPromises.delete(index);
        if (index === shareSlideIndex) syncShareSaveButton();
      });
    shareExportPromises.set(index, promise);
    if (index === shareSlideIndex) syncShareSaveButton();
    return promise;
  };
  const shareSlideOffset = (slide) => slide.offsetLeft - ((shareTrack.clientWidth - slide.offsetWidth) / 2);
  const syncSharePreviewScale = () => {
    sharePreviewFrame = 0;
    if (!shareDialog.hasAttribute('open')) return;
    shareDialog.classList.toggle('is-compact', shareDialog.getBoundingClientRect().height <= 700);
    const availableHeight = Math.max(1, shareTrack.clientHeight);
    const availableWidth = Math.max(1, shareTrack.clientWidth - 68);
    const scale = Math.min(1, availableHeight / SHARE_CARD_HEIGHT, availableWidth / SHARE_CARD_WIDTH);
    const safeScale = Math.max(.01, scale);
    shareTrack.style.setProperty('--share-card-scale', String(safeScale.toFixed(4)));
    shareTrack.style.setProperty('--share-card-preview-width', `${(SHARE_CARD_WIDTH * safeScale).toFixed(2)}px`);
    shareTrack.style.setProperty('--share-card-preview-height', `${(SHARE_CARD_HEIGHT * safeScale).toFixed(2)}px`);
    requestAnimationFrame(() => {
      const slot = shareSlots[shareSlideIndex];
      if (slot) shareTrack.scrollLeft = shareSlideOffset(slot);
    });
  };
  const scheduleSharePreviewScale = () => {
    if (sharePreviewFrame) cancelAnimationFrame(sharePreviewFrame);
    sharePreviewFrame = requestAnimationFrame(syncSharePreviewScale);
  };
  if (typeof ResizeObserver === 'function') new ResizeObserver(scheduleSharePreviewScale).observe(shareTrack);
  window.visualViewport?.addEventListener('resize', scheduleSharePreviewScale, { passive: true });
  window.addEventListener('resize', scheduleSharePreviewScale, { passive: true });
  const syncShareSlide = (index) => {
    shareSlideIndex = Math.max(0, Math.min(index, shareSlides.length - 1));
    shareSlides.forEach((slide, slideIndex) => {
      const isCurrent = slideIndex === shareSlideIndex;
      slide.classList.toggle('is-current', isCurrent);
      slide.setAttribute('aria-current', String(isCurrent));
    });
    shareDots.forEach((dot, dotIndex) => dot.setAttribute('aria-current', String(dotIndex === shareSlideIndex)));
    shareSlideStatus.textContent = `第 ${shareSlideIndex + 1} 张，共 ${shareSlides.length} 张`;
    syncShareSaveButton();
    void prepareShareCard(shareSlideIndex);
  };
  const goToShareSlide = (index, smooth = true) => {
    const nextIndex = Math.max(0, Math.min(index, shareSlides.length - 1));
    shareTrack.scrollTo({
      left: shareSlideOffset(shareSlots[nextIndex]),
      behavior: smooth && !matchMedia('(prefers-reduced-motion: reduce)').matches ? 'smooth' : 'auto',
    });
    syncShareSlide(nextIndex);
  };
  shareDots.forEach((dot) => dot.addEventListener('click', () => goToShareSlide(Number(dot.dataset.shareDot))));
  shareTrack.addEventListener('scroll', () => {
    if (shareScrollFrame) return;
    shareScrollFrame = requestAnimationFrame(() => {
      shareScrollFrame = 0;
      const closestIndex = shareSlots.reduce((closest, slot, index) => (
        Math.abs(shareSlideOffset(slot) - shareTrack.scrollLeft) < Math.abs(shareSlideOffset(shareSlots[closest]) - shareTrack.scrollLeft) ? index : closest
      ), 0);
      syncShareSlide(closestIndex);
    });
  }, { passive: true });
  shareTrack.addEventListener('keydown', (event) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    if (event.key === 'Home') goToShareSlide(0);
    else if (event.key === 'End') goToShareSlide(shareSlides.length - 1);
    else goToShareSlide(shareSlideIndex + (event.key === 'ArrowRight' ? 1 : -1));
  });
  const currentReportId = () => state.reportId || window.__SELFIT_REPORT_ID__ || null;
  const applyPublicShareQr = (share) => {
    if (!share?.qrUrl) return;
    document.querySelectorAll('.share-qr').forEach((image) => {
      image.src = share.qrUrl;
      image.alt = '扫码查看这份风格报告';
    });
    invalidateShareExports();
  };
  const ensurePublicShare = async (slideIndex = shareSlideIndex) => {
    if (state.publicShare?.share) return state.publicShare;
    const reportId = currentReportId();
    if (!reportId) throw new window.SelfitApi.SelfitApiError(entryParams.get('preview') ? '这是设计预览，生成真实报告后可保存分享。' : '报告仍在准备中，请稍后再试。', { code: 'report.not_ready' });
    state.publicShare = await api.createPublicShare(reportId, { slideIndex });
    applyPublicShareQr(state.publicShare.share);
    track('share_link_created', {
      reportId,
      slideIndex,
      expiresAt: state.publicShare.share.expiresAt || '',
    });
    return state.publicShare;
  };
  const openShareButton = document.querySelector('#openShare');
  openShareButton.addEventListener('click', () => runButtonAction(openShareButton, async () => {
    await ensurePublicShare(0);
    openShareDialog();
    syncShareSaveButton();
    requestAnimationFrame(() => {
      syncSharePreviewScale();
      goToShareSlide(0, false);
    });
  }));
  const copyTextToClipboard = async (value) => {
    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(value);
        return;
      } catch { /* 部分微信 WebView 会拒绝 Clipboard API，继续使用兼容方案。 */ }
    }
    const input = Object.assign(document.createElement('textarea'), {
      value,
      readOnly: true,
      ariaHidden: 'true',
    });
    Object.assign(input.style, { position: 'fixed', top: '-1000px', opacity: '0' });
    document.body.appendChild(input);
    input.select();
    input.setSelectionRange(0, value.length);
    const copied = document.execCommand('copy');
    input.remove();
    if (!copied) throw new Error('当前浏览器无法自动复制，请稍后重试。');
  };
  const logoutConfirmDialog = document.querySelector('#logoutConfirmDialog');
  const logoutSelfitUser = () => {
    const proceedLogout = () => {
      const token = auth.accessToken;
      auth.clear();
      sessionStorage.removeItem('selfit.studio.job');
      sessionStorage.removeItem('selfit.studio.import');
      localStorage.removeItem(SESSION_STORAGE_KEY);
      if (token) {
        void fetch('/auth/logout', { method: 'POST', headers: { Authorization: `Bearer ${token}` }, keepalive: true }).catch(() => {});
      }
      window.location.replace('/selfit?entry=login');
    };
    // 二次确认防误触：取消可返回，确认才真正退出。
    if (!logoutConfirmDialog) { proceedLogout(); return; }
    const supportsNativeDialog = typeof logoutConfirmDialog.showModal === 'function';
    const cleanupLogoutConfirm = () => {
      logoutConfirmDialog.removeEventListener('close', onLogoutConfirmClose);
      logoutConfirmDialog.removeEventListener('click', onLogoutConfirmClick, true);
    };
    const onLogoutConfirmClose = () => {
      cleanupLogoutConfirm();
      if (logoutConfirmDialog.returnValue === 'confirm') proceedLogout();
    };
    const onLogoutConfirmClick = (event) => {
      const submit = event.target.closest('button[value]');
      if (!submit || supportsNativeDialog) return;
      event.preventDefault();
      logoutConfirmDialog.returnValue = submit.value;
      logoutConfirmDialog.removeAttribute('open');
      document.documentElement.classList.remove('has-open-dialog');
      onLogoutConfirmClose();
    };
    logoutConfirmDialog.addEventListener('close', onLogoutConfirmClose);
    logoutConfirmDialog.addEventListener('click', onLogoutConfirmClick, true);
    logoutConfirmDialog.returnValue = '';
    if (supportsNativeDialog) logoutConfirmDialog.showModal();
    else {
      logoutConfirmDialog.setAttribute('open', '');
      document.documentElement.classList.add('has-open-dialog');
    }
  };
  document.querySelector('#reportLogout').addEventListener('click', logoutSelfitUser);
  document.querySelector('.intro-logout').addEventListener('click', logoutSelfitUser);
  document.querySelectorAll('[data-share]').forEach((button) => button.addEventListener('click', () => runButtonAction(button, async () => {
    if (button.dataset.share === 'report-link') {
      const created = await ensurePublicShare(shareSlideIndex);
      const share = created.share;
      const reportTitle = document.querySelector('[data-share-title]')?.textContent?.trim();
      const shareCopy = reportTitle
        ? `Ta 分享了一份「${reportTitle}」风格报告\n${share.url}`
        : `Ta 分享了一份 selfit 风格报告\n${share.url}`;
      await copyTextToClipboard(shareCopy);
      track('share_action_clicked', { method: 'copy-link' });
      toast('已复制分享链接');
      return;
    }
    if (button.dataset.share === 'save-card') {
      const blob = shareExportBlobs.get(shareSlideIndex) || await prepareShareCard(shareSlideIndex);
      if (!blob) throw shareExportErrors.get(shareSlideIndex) || new Error('分享卡片生成失败，请重试。');
      const result = await saveShareCardToDevice(blob, shareSlideIndex);
      if (result.method === 'cancelled') {
        track('share_save_cancelled', { slideIndex: shareSlideIndex });
        return;
      }
      track('share_saved', { slideIndex: shareSlideIndex, channel: 'save', method: result.method });
      if (result.method.includes('download')) toast('高清图片已下载，请在相册或“下载”中查看');
      return;
    }
    const reportId = currentReportId();
    if (!reportId) throw new window.SelfitApi.SelfitApiError(entryParams.get('preview') ? '这是设计预览，生成真实报告后可保存分享。' : '报告仍在准备中，请稍后再试。', { code: 'report.not_ready' });
    const result = await api.createShareAsset(reportId, { slideIndex: shareSlideIndex, channel: button.dataset.share, format: 'png' });
    track('share_saved', { slideIndex: shareSlideIndex, channel: button.dataset.share });
    toast(`${button.dataset.share}已准备好`);
  })));

  window.selfitIntegration = Object.freeze({
    mode: api.mode,
    authMode: auth.mode,
    ensureSession,
    getState: () => ({
      screen: state.screen,
      authUser: state.authUser ? { ...state.authUser } : null,
      sessionId: state.sessionId,
      revision: state.revision,
      photoStatus: { ...state.photoStatus },
      photoAssetIds: { ...state.photoAssets },
      manual: { ...state.manual },
      axes: { ...state.axes },
      palette: state.palette,
      answeredQuestions: Object.keys(state.answers),
      reportJobId: state.reportJobId,
      reportId: state.reportId,
      publicShare: state.publicShare ? { ...state.publicShare.share } : null,
    }),
  });

  const previewParams = new URLSearchParams(window.location.search);
  if (entryParams.get('from') === 'mirror' && entryParams.get('report') === 'latest') {
    shell.classList.add('is-ready');
    showScreen('loading');
    void authReady.then(async (session) => {
      if (!session?.user) { showScreen('login'); return; }
      const result = await api.getLatestReport();
      if (!result?.report) { showScreen('intro'); playIntro(); return; }
      state.reportId = result.report.reportId || null;
      const fullReport = await api.getReport(state.reportId);
      renderReport(fullReport.report);
      showScreen('report');
    }).catch(() => { window.location.replace('/selfit/try-on'); });
    return;
  }
  const previewScreen = previewParams.get('preview');
  if (['splash', 'login', 'phone-login', 'invite-login', 'intro', 'suit', 'suit-manual', 'like', 'vibe'].includes(previewScreen)) {
    showScreen(previewScreen);
    if (previewScreen === 'intro') playIntro();
    shell.classList.add('is-ready');
    return;
  }
  if (previewScreen === 'report') {
    const requestedType = previewParams.get('type') || 'mute';
    renderReport({ typeId: requestedType });
    showScreen('report');
    shell.classList.add('is-ready');
    return;
  }
  if (previewScreen === 'share') {
    const requestedType = previewParams.get('type') || 'mute';
    renderReport({ typeId: requestedType });
    showScreen('report');
    shell.classList.add('is-ready');
    requestAnimationFrame(() => {
      openShareDialog();
      goToShareSlide(0, false);
    });
    return;
  }
  if (previewScreen === 'share-gallery') {
    const gallery = Object.assign(document.createElement('main'), { className: 'share-gallery-preview' });
    Object.keys(personalityCatalog.types || {}).forEach((typeId, index) => {
      const data = renderReport({ typeId });
      const card = document.querySelector('.share-card--identity').cloneNode(true);
      card.classList.add('is-current');
      card.setAttribute('aria-current', 'true');
      const item = Object.assign(document.createElement('section'), { className: 'share-gallery-item' });
      const label = Object.assign(document.createElement('p'), {
        className: 'share-gallery-label',
        textContent: `${String(index + 1).padStart(2, '0')} · ${data.eyebrow} · ${data.title}`,
      });
      item.append(label, card);
      gallery.append(item);
    });
    document.body.classList.add('is-share-gallery');
    document.body.append(gallery);
    shell.classList.add('is-ready');
    return;
  }
  if (previewScreen === 'loading') {
    const previewProgress = Number(previewParams.get('stage')) || 25;
    showScreen('loading');
    setLoadingProgress(previewProgress);
    shell.classList.add('is-ready');
    return;
  }

  if (publicShareToken) {
    document.body.classList.add('is-public-report');
    document.querySelector('.report-nav h2').textContent = 'Ta分享的风格报告';
    const expiry = document.querySelector('#publicReportExpiry');
    const errorState = document.querySelector('#publicReportError');
    const visitorCta = document.querySelector('#publicReportCta');
    visitorCta.hidden = false;
    showScreen('report');
    shell.classList.add('is-ready');
    api.getPublicShare(publicShareToken).then((result) => {
      renderReport(result.report || {});
      const sharedType = String(result.report?.title || result.report?.typeName || '').trim().slice(0, 24);
      const tryUrl = new URL('/selfit', window.location.origin);
      tryUrl.searchParams.set('from', 'shared-report');
      if (sharedType) tryUrl.searchParams.set('shared_type', sharedType);
      document.querySelectorAll('[data-public-report-try]').forEach((link) => {
        link.href = `${tryUrl.pathname}${tryUrl.search}`;
        link.dataset.sharedTypeId = String(result.report?.typeId || '');
      });
      const ctaCopy = document.querySelector('#publicReportCtaCopy');
      if (ctaCopy) ctaCopy.textContent = sharedType
        ? `Ta是「${sharedType}」，你会是哪一种？`
        : 'Ta已经找到自己的风格，你会是哪一种？';
      const expiresAt = Date.parse(result.share?.expiresAt || '');
      const expiryDate = Number.isFinite(expiresAt) ? new Date(expiresAt) : null;
      expiry.textContent = expiryDate
        ? `本分享将于 ${expiryDate.getMonth() + 1}月${expiryDate.getDate()}日到期`
        : '本分享将在 7 天后到期';
      expiry.hidden = false;
      track('shared_report_opened', { typeId: result.report?.typeId || '' });
    }).catch((error) => {
      document.body.classList.add('has-public-report-error');
      const isExpired = error.code === 'share.public_expired';
      errorState.querySelector('h1').textContent = isExpired ? '好可惜，本分享已过期' : '没有找到这份分享报告';
      errorState.querySelector('p').textContent = isExpired ? '请直接扫码访问selfit' : '请扫码访问selfit';
      errorState.hidden = false;
    });
    document.querySelectorAll('[data-public-report-try]').forEach((link) => link.addEventListener('click', () => {
      track('shared_report_try_clicked', { placement: link.dataset.publicReportTry || '', typeId: link.dataset.sharedTypeId || '' });
    }));
    return;
  }

  if (retestEntry) {
    // 重新测试：跳过「适我」过场，直达 like；未登录时才退回登录页。
    shell.classList.add('is-ready');
    showScreen('like');
    void authReady.then((session) => {
      if (!session?.user) showScreen('login');
    }).catch(() => showScreen('login'));
    return;
  }

  if (entryParams.get('entry') === 'login') {
    showScreen('login');
    void authReady.then(async (session) => {
      if (session?.user) {
        if (await openAppForExistingReport()) return;
        showScreen('intro');
        playIntro();
      }
    }).catch((error) => {
      showScreen('phone-login');
      setAuthMessage(authNodes.phoneMessage, error.message || '暂时无法读取你的风格档案，请重试。', 'error');
    });
    shell.classList.add('is-ready');
    return;
  }

  if (entryParams.get('entry') === 'unlock') {
    // 从主站被门槛弹回（entry=unlock）：跳过「适我」过场，直达解锁屏。
    shell.classList.add('is-ready');
    showScreen('beta-unlock');
    void authReady.then(async (session) => {
      const user = session?.user;
      if (!user) { showScreen('login'); return; }
      if (user.beta_qualified !== false) { window.location.replace('/selfit/try-on?from=login'); return; }
      try {
        if (await openAppForExistingReport()) return;
      } catch { /* 拉取报告失败也停在解锁屏，输码即可进主站 */ }
      enterBetaUnlock('like', 'generic');
    }).catch(() => showScreen('login'));
    return;
  }

  splashTimer = setTimeout(enterOnboarding, matchMedia('(prefers-reduced-motion: reduce)').matches ? 900 : 1800);
  shell.classList.add('is-ready');
})();
