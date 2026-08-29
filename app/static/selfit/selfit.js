(() => {
  const shell = document.querySelector('#appShell');
  window.__SELFIT_BOOT_OK__ = true;
  window.clearTimeout(window.__SELFIT_BOOT_TIMER__);
  document.documentElement.dataset.selfitBoot = 'ready';
  shell.addEventListener('error', (event) => {
    const image = event.target;
    if (!(image instanceof HTMLImageElement) || image.dataset.fallbackApplied === 'true') return;
    if (!/\/assets\/personality\//.test(image.currentSrc || image.src)) return;
    image.dataset.fallbackApplied = 'true';
    image.src = '/static/selfit/assets/personality/placeholder-card.svg';
  }, true);
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
    suit: { back: 'intro', progress: 'suit', current: 'suit', done: [] },
    'suit-manual': { back: 'suit', progress: 'suit', current: 'suit', done: [] },
    like: { back: 'suit', progress: 'like', current: 'like', done: ['suit'] },
    vibe: { back: 'like', progress: 'vibe', current: 'vibe', done: ['suit', 'like'] },
  };
  const updateOnboardingNav = (name) => {
    if (!onboardingNav) return;
    const config = ONBOARDING_NAV[name];
    onboardingNav.hidden = !config;
    if (!config) return;
    onboardingBack?.setAttribute('data-back', config.back);
    onboardingStepper?.setAttribute('data-progress', config.progress);
    onboardingSteps.forEach((step) => {
      const key = step.dataset.step;
      step.classList.toggle('is-current', key === config.current);
      step.classList.toggle('is-done', config.done.includes(key));
    });
  };
  const SESSION_STORAGE_KEY = 'selfit.onboarding.session.v1';
  const handoffToken = new URLSearchParams(window.location.search).get('handoff') || '';
  let api;
  let auth;
  let authReady = Promise.resolve(null);
  const state = {
    screen: 'splash', facePhoto: null, bodyPhoto: null,
    photoStatus: { face: 'empty', body: 'empty' },
    photoAssets: { face: null, body: null },
    manual: { skin: null, faceShape: null, bodyShape: null },
    axes: { shape: 42, energy: 64, trend: 42 },
    palette: null, answers: {}, sessionId: null, revision: 0, reportJobId: null, reportId: null, authUser: null,
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

  const showScreen = (name) => {
    const next = screens.find((screen) => screen.dataset.screen === name);
    if (!next) return;
    const previous = state.screen;
    screens.forEach((screen) => {
      screen.classList.toggle('is-active', screen === next);
      screen.setAttribute('aria-hidden', screen === next ? 'false' : 'true');
    });
    state.screen = name;
    if (previous !== name) track('screen_view', { from: previous, to: name });
    updateOnboardingNav(name);
    themeColor?.setAttribute('content', ['splash', 'loading'].includes(name) ? '#8a011b' : '#fafafa');
    next.scrollTop = 0;
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
      let destination = state.authUser ? 'intro' : 'login';
      if (handoffToken) destination = state.authUser ? 'like' : 'phone-login';
      if (handoffToken && state.authUser) {
        try { await claimPendingHandoff(); }
        catch (error) {
          destination = 'phone-login';
          showScreen(destination);
          setAuthMessage(authNodes.phoneMessage, error.message || '这个二维码已失效。', 'error');
        }
      } else showScreen(destination);
      splash.classList.remove('is-leaving');
      splashTransitioning = false;
      if (destination === 'intro') playIntro();
    }, matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 420);
  };
  document.querySelector('#splashEnter').addEventListener('click', enterOnboarding);

  document.addEventListener('click', async (event) => {
    const next = event.target.closest('[data-next]');
    const back = event.target.closest('[data-back]');
    if (next) {
      if (document.activeElement?.matches?.('input, textarea, [contenteditable="true"]')) await dismissKeyboard();
      if (next.dataset.next !== 'intro') clearIntroMotion();
      showScreen(next.dataset.next);
    }
    if (back) {
      if (document.activeElement?.matches?.('input, textarea, [contenteditable="true"]')) await dismissKeyboard();
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
  const completeAuth = async (session) => {
    state.authUser = session?.user || auth.user || null;
    state.sessionId = null;
    state.revision = 0;
    localStorage.removeItem(SESSION_STORAGE_KEY);
    track('login_success', { provider: 'phone' });
    await dismissKeyboard();
    if (handoffToken) {
      await claimPendingHandoff();
      return;
    }
    showScreen('intro');
    playIntro();
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
      await completeAuth(await auth.directPhone(normalizedPhone()));
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
      await completeAuth(await auth.verifyInvite(authNodes.invite.value.trim()));
    } catch (error) {
      const copy = error.status === 404 ? '邀请码登录接口尚未接入，请先使用手机号登录。' : (error.message || '邀请码登录失败，请重试。');
      setAuthMessage(authNodes.inviteMessage, copy, 'error');
    } finally {
      setAuthBusy(authNodes.inviteSubmit, false);
      syncInviteLogin();
    }
  });

  const validatePhoto = (file) => {
    if (!file) return '请选择照片';
    if (file.size > 20 * 1024 * 1024) return '照片请小于 20MB';
    return '';
  };
  const renderPhotoPreview = (card, file, kind) => {
    const preview = card.querySelector('.upload-preview');
    const objectUrl = URL.createObjectURL(file);
    const image = Object.assign(document.createElement('img'), {
      alt: kind === 'face' ? '面部照预览' : '全身照预览',
    });
    const releaseObjectUrl = () => URL.revokeObjectURL(objectUrl);
    image.addEventListener('load', releaseObjectUrl, { once: true });
    image.addEventListener('error', () => {
      releaseObjectUrl();
      if (!preview.contains(image)) return;
      const fallback = document.createElement('span');
      fallback.className = 'upload-preview-fallback';
      fallback.textContent = '照片已选择';
      preview.replaceChildren(fallback);
    }, { once: true });
    preview.replaceChildren(image);
    image.src = objectUrl;
  };
  const syncSuitButton = () => { document.querySelector('#suitNext').disabled = !(state.photoStatus.face === 'valid' && state.photoStatus.body === 'valid'); };
  const setPhotoState = (kind, status, copy) => {
    const card = document.querySelector(`[data-upload-card="${kind}"]`);
    const statusLine = document.querySelector(`[data-photo-status="${kind}"]`);
    card.classList.toggle('is-checking', status === 'checking');
    card.classList.toggle('is-valid', status === 'valid');
    card.classList.toggle('is-invalid', status === 'invalid');
    statusLine.dataset.state = status;
    statusLine.textContent = copy;
    state.photoStatus[kind] = status;
    syncSuitButton();
  };
  const bindUpload = (id, kind) => {
    const input = document.querySelector(`#${id}`);
    const card = document.querySelector(`[data-upload-card="${kind}"]`);
    let activeController = null;
    input.addEventListener('change', async () => {
      const file = input.files?.[0]; const error = validatePhoto(file);
      if (error) { setPhotoState(kind, 'invalid', error); return; }
      state[kind === 'face' ? 'facePhoto' : 'bodyPhoto'] = file;
      renderPhotoPreview(card, file, kind);
      setPhotoState(kind, 'checking', '照片检测中...');
      activeController?.abort(); activeController = new AbortController();
      try {
        const sessionId = await ensureSession();
        const result = await api.checkPhoto(sessionId, kind, file, { signal: activeController.signal });
        const accepted = result.photo?.status === 'accepted';
        state.photoAssets[kind] = accepted ? result.photo.assetId : null;
        state.revision = result.revision || state.revision;
        track('photo_upload_result', { kind, accepted, code: result.photo?.code || '' });
        setPhotoState(kind, accepted ? 'valid' : 'invalid', result.photo?.message || (accepted ? '照片可用' : '请重新上传'));
      } catch (requestError) {
        if (activeController.signal.aborted) return;
        track('photo_upload_result', { kind, accepted: false, code: 'network' });
        setPhotoState(kind, 'invalid', requestError.message || '照片检测失败，请重试');
      }
    });
  };
  bindUpload('facePhoto', 'face'); bindUpload('bodyPhoto', 'body');
  document.querySelector('#suitNext').addEventListener('click', () => showScreen('like'));

  document.querySelector('.manual-form').addEventListener('click', (event) => {
    const button = event.target.closest('[data-manual]'); if (!button) return;
    const key = button.dataset.manual; state.manual[key] = button.dataset.value;
    document.querySelectorAll(`[data-manual="${key}"]`).forEach((item) => {
      const selected = item === button;
      item.classList.toggle('is-selected', selected);
      item.setAttribute('aria-pressed', String(selected));
    });
    document.querySelector('#manualNext').disabled = !Object.values(state.manual).every(Boolean);
  });
  document.querySelector('#manualNext').addEventListener('click', (event) => runButtonAction(event.currentTarget, async () => {
    const sessionId = await ensureSession();
    const result = await api.saveManualProfile(sessionId, state.manual);
    state.revision = result.session?.revision || state.revision;
    track('manual_saved');
    showScreen('like');
  }));

  document.querySelector('#paletteGrid').addEventListener('click', (event) => {
    const button = event.target.closest('[data-palette]'); if (!button) return;
    state.palette = button.dataset.palette;
    document.querySelectorAll('[data-palette]').forEach((item) => { const selected = item === button; item.classList.toggle('is-selected', selected); item.setAttribute('aria-pressed', String(selected)); });
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
    showScreen('vibe');
  }));

  document.querySelector('#vibeQuestions').addEventListener('click', (event) => {
    const button = event.target.closest('[data-answer]'); if (!button) return;
    const field = button.closest('[data-question]'); state.answers[field.dataset.question] = button.dataset.answer;
    field.querySelectorAll('[data-answer]').forEach((item) => {
      const selected = item === button;
      item.classList.toggle('is-selected', selected);
      item.setAttribute('aria-pressed', String(selected));
    });
    document.querySelector('#vibeNext').disabled = Object.keys(state.answers).length !== 3;
  });

  const loadingStages = [
    { percent: 25, line: '先看见真实的你', src: '/static/selfit/assets/loading-stage-25@2x.png?v=20260826' },
    { percent: 50, line: '寻找你同频的灵感', src: '/static/selfit/assets/loading-stage-50@2x.png?v=20260826' },
    { percent: 75, line: '拼出更像你的样子', src: '/static/selfit/assets/loading-stage-75@2x.png?v=20260826' },
    { percent: 100, line: '我们认识你了...', src: '/static/selfit/assets/loading-stage-100@2x.png?v=20260826' },
  ];
  loadingStages.forEach(({ src }) => { const image = new Image(); image.src = src; });
  const setLoadingProgress = (progress) => {
    const stage = [...loadingStages].reverse().find((item) => progress >= item.percent) || loadingStages[0];
    const art = document.querySelector('#loadingArt');
    const line = document.querySelector('#loadingLine');
    const percent = document.querySelector('#loadingPercent');
    const stageChanged = art.dataset.stage !== String(stage.percent);
    if (stageChanged) {
      [art, line, percent].forEach((element) => element.classList.add('is-changing'));
      window.setTimeout(() => {
        art.src = stage.src;
        art.dataset.stage = String(stage.percent);
        line.textContent = stage.line;
        percent.textContent = `${stage.percent}%`;
        requestAnimationFrame(() => requestAnimationFrame(() => {
          [art, line, percent].forEach((element) => element.classList.remove('is-changing'));
        }));
      }, window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 150);
      return;
    }
    art.dataset.stage = String(stage.percent);
    line.textContent = stage.line;
    percent.textContent = `${stage.percent}%`;
  };
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
    const classification = persona.classifyPersona(vector);
    return { typeId: classification.primary_persona.toLowerCase() };
  };
  const runtimeConfig = window.__SELFIT_CONFIG__ || {};
  // 邀请码登录仅内部测试用：默认隐藏，服务端配置 SELFIT_SHOW_INVITE_LOGIN=1 时显示。
  document.querySelector('[data-invite-login]')?.toggleAttribute('hidden', !runtimeConfig.showInviteLogin);
  const queryMode = new URLSearchParams(location.search).get('apiMode');
  const runtimeMode = queryMode || runtimeConfig.apiMode || shell.dataset.apiMode || 'mock';
  auth = window.SelfitAuth.createClient({
    mode: runtimeConfig.authMode || runtimeMode,
    baseUrl: runtimeConfig.authBase || '/auth',
    timeoutMs: runtimeConfig.timeoutMs || 15000,
  });
  authReady = auth.restore().then((session) => {
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
      const stored = readPersistedSession();
      if (stored) {
        try {
          const restored = await api.getSession(stored.sessionId);
          state.sessionId = restored.session.sessionId;
          state.revision = restored.session.revision || 0;
          return state.sessionId;
        } catch { localStorage.removeItem(SESSION_STORAGE_KEY); }
      }
      const created = await api.createSession({ schemaVersion: 'selfit-onboarding-v1', locale: document.documentElement.lang || 'zh-CN' });
      state.sessionId = created.session.sessionId;
      state.revision = created.session.revision || 1;
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
    const template = personalityCatalog.types?.[String(payload.typeId).toLowerCase()];
    if (!template) return payload;
    const base = templateToReportData(template);
    const personalization = payload.personalization && typeof payload.personalization === 'object' ? payload.personalization : {};
    return {
      ...base,
      ...payload,
      ...personalization,
      heroImage: personalization.heroImage || payload.heroImage || base.heroImage,
      source: { ...base.source, ...(payload.source || {}), ...(personalization.source || {}) },
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
  const appendImageCards = (container, items) => {
    const cards = items.filter((item) => item && item.imageUrl).map((item) => {
      const figure = document.createElement('figure');
      const image = Object.assign(document.createElement('img'), {
        src: item.imageUrl || '', alt: item.alt || item.name || '', loading: 'lazy', decoding: 'async',
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
  const renderReport = (payload = {}) => {
    const data = normalizeReport(payload);
    const fullHero = Boolean(data.heroImage?.src);
    reportNodes.hero.classList.toggle('report-hero--full', fullHero);
    reportNodes.hero.classList.remove('report-hero--reference');
    reportNodes.heroImage.src = fullHero ? data.heroImage.src : '';
    reportNodes.heroImage.alt = fullHero ? (data.heroImage.alt || `${data.title} ${data.eyebrow} 人格封面`) : '';
    reportNodes.heroImage.hidden = !fullHero;
    reportNodes.eyebrow.textContent = data.eyebrow;
    reportNodes.title.textContent = data.title;
    reportNodes.traits.replaceChildren(...data.traits.map((trait) => {
      const card = Object.assign(document.createElement('span'), { className: 'report-trait' });
      const lace = Object.assign(document.createElement('img'), {
        src: '/static/selfit/assets/lace-card@4x.png?v=20260821', alt: '', width: 408, height: 604,
      });
      card.append(lace, Object.assign(document.createElement('b'), { textContent: trait }));
      return card;
    }));
    reportNodes.traits.hidden = data.traits.length === 0;
    reportNodes.illustration.src = data.illustration.imageUrl || '';
    reportNodes.illustration.alt = data.illustration.alt || '';
    reportNodes.illustration.closest('figure').hidden = fullHero || !data.illustration.imageUrl;
    reportNodes.summary.innerHTML = renderReportMarkdown(data.summary);
    reportNodes.summary.hidden = !data.summary;
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
    reportNodes.sourceAvatars.src = data.source.avatars.imageUrl || '/static/selfit/assets/report-user-avatar-stack@4x.png';
    reportNodes.sourceAvatars.alt = data.source.avatars.alt || '3 位真实用户头像';
    reportNodes.sourceAvatars.hidden = !hasSource;
    proof.hidden = !hasSource;
    reportNodes.outfitSummary.innerHTML = renderReportMarkdown(data.outfitSummary);
    reportNodes.outfitSummary.hidden = !data.outfitSummary;
    const visibleOutfits = data.outfits
      .filter((item) => item && item.imageUrl)
      .slice(0, personalityCatalog.renderRules?.outfits?.limit || 4);
    const outfitCards = visibleOutfits.map((item) => {
      const figure = document.createElement('figure');
      const image = Object.assign(document.createElement('img'), {
        src: item.imageUrl, alt: item.alt || item.name || '', loading: 'lazy', decoding: 'async',
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
      src: item.imageUrl || '', alt: item.alt || item.name || item.title || '', loading: 'lazy', decoding: 'async',
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
      while (Date.now() < deadline) {
        const result = await api.getReportJob(state.reportJobId);
        setLoadingProgress(result.job.progress || 25);
        if (result.job.status === 'failed') throw new window.SelfitApi.SelfitApiError(result.job.error?.message || '报告生成失败，请重试。', result.job.error || {});
        if (result.job.status === 'completed') { completedJob = result.job; break; }
        await new Promise((resolve) => setTimeout(resolve, Math.max(250, Math.min(result.job.pollAfterMs || 800, 3000))));
      }
      if (!completedJob) throw new window.SelfitApi.SelfitApiError('报告生成时间较长，请稍后重试。', { code: 'report.timeout', retryable: true });
      state.reportId = completedJob.reportId;
      const report = completedJob.report || (await api.getReport(state.reportId)).report;
      // 分型一确定就预加载 hero 大图：报告数据渲染前的等待时间里图片已在下载，
      // 报告页出现时封面通常已就绪（hero.webp ~100KB，之前 PNG 1.6MB 要 6-10s）。
      const heroTemplate = personalityCatalog.types?.[String(report?.typeId || '').toLowerCase()];
      const heroSrc = heroTemplate?.hero?.image?.src;
      if (heroSrc) { const preload = new Image(); preload.src = heroSrc; }
      track('report_completed', { reportId: state.reportId, typeId: report?.typeId || '' });
      setLoadingProgress(100);
      renderReport(report);
      await new Promise((resolve) => setTimeout(resolve, 900));
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

  const toast = (copy) => {
    const node = document.querySelector('#toast'); node.textContent = copy; node.classList.add('is-visible'); setTimeout(() => node.classList.remove('is-visible'), 1800);
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
  const outfitList = document.querySelector('.outfit-list');
  let reportScrollFrame = 0;
  const syncReportActions = () => {
    reportScrollFrame = 0;
    const reportRect = reportScreen.getBoundingClientRect();
    const outfitRect = outfitList.getBoundingClientRect();
    const shouldDock = reportScreen.classList.contains('is-active')
      && reportScreen.scrollTop > 0
      && outfitRect.top <= reportRect.bottom - 112;
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
  shareDialog.addEventListener('close', () => document.documentElement.classList.remove('has-open-dialog'));
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
    image.src = source;
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
  const closeSaveImageGuide = () => {
    saveImageGuide.hidden = true;
    saveImagePreview.removeAttribute('src');
    if (saveImagePreviewUrl) URL.revokeObjectURL(saveImagePreviewUrl);
    saveImagePreviewUrl = '';
  };
  const openSaveImageGuide = (blob) => {
    closeSaveImageGuide();
    closeShareDialog();
    saveImagePreviewUrl = URL.createObjectURL(blob);
    saveImagePreview.src = saveImagePreviewUrl;
    saveImageGuide.hidden = false;
  };
  saveImageGuide.querySelectorAll('[data-close-save-guide]').forEach((button) => button.addEventListener('click', closeSaveImageGuide));
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
  document.querySelector('#openShare').addEventListener('click', () => {
    openShareDialog();
    invalidateShareExports();
    syncShareSaveButton();
    requestAnimationFrame(() => {
      syncSharePreviewScale();
      goToShareSlide(0, false);
    });
  });
  const currentReportId = () => state.reportId || window.__SELFIT_REPORT_ID__ || null;
  document.querySelector('#retakeBtn').addEventListener('click', () => { track('retake_clicked'); showScreen('vibe'); });
  document.querySelectorAll('[data-share]').forEach((button) => button.addEventListener('click', () => runButtonAction(button, async () => {
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
    if (!reportId) throw new window.SelfitApi.SelfitApiError('报告仍在准备中，请稍后再试。', { code: 'report.not_ready' });
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
    }),
  });

  const previewParams = new URLSearchParams(window.location.search);
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

  splashTimer = setTimeout(enterOnboarding, matchMedia('(prefers-reduced-motion: reduce)').matches ? 900 : 1800);
  shell.classList.add('is-ready');
})();
