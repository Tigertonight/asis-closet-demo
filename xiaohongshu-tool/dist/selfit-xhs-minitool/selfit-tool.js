/* selfit 小红书小工具版逻辑 — 派生自 app/static/selfit/selfit.js。
   完全离线：分型用包内 persona.js（与后端算法对拍同步），报告数据用包内 templates.js，
   保存/分享走 window.xhs.miniTool（容器注入），浏览器预览时降级。
   语法基线 ES2017 / Chrome 61（官方 js-compatibility 规范）：禁用可选链、空值合并、
   对象展开、replaceChildren、toggleAttribute 等 Chrome 61 之后的语法与 API。 */
(() => {
  const setChildren = (parent, nodes) => {
    while (parent.firstChild) parent.removeChild(parent.firstChild);
    parent.append.apply(parent, nodes);
  };
  const toggleAttr = (element, name, on) => {
    if (on) element.setAttribute(name, '');
    else element.removeAttribute(name);
  };
  const shell = document.querySelector('#appShell');
  const screens = [...document.querySelectorAll('[data-screen]')];
  const splash = document.querySelector('[data-screen="splash"]');
  const intro = document.querySelector('[data-screen="intro"]');
  const onboardingNav = document.querySelector('[data-onboarding-nav]');
  const onboardingBack = document.querySelector('[data-onboarding-back]');
  const onboardingStepper = document.querySelector('[data-onboarding-stepper]');
  const onboardingSteps = onboardingStepper ? [...onboardingStepper.querySelectorAll('[data-step]')] : [];
  const themeColor = document.querySelector('meta[name="theme-color"]');

  const ONBOARDING_NAV = {
    'suit-manual': { back: 'intro', progress: 'suit', current: 'suit', done: [] },
    like: { back: 'suit-manual', progress: 'like', current: 'like', done: ['suit'] },
    vibe: { back: 'like', progress: 'vibe', current: 'vibe', done: ['suit', 'like'] },
  };

  const state = {
    screen: 'splash',
    manual: { skin: null, faceShape: null, bodyShape: null },
    axes: { shape: 42, energy: 64, trend: 42 },
    palette: null,
    answers: {},
    reportTypeId: '',
  };

  const personalityCatalog = window.__SELFIT_PERSONALITY_TEMPLATES__ || { types: {}, renderRules: {} };
  const renderRules = personalityCatalog.renderRules || {};

  const toastNode = document.querySelector('#toast');
  const toastHome = toastNode.parentElement;
  const toast = (copy) => {
    (document.querySelector('dialog[open]') || toastHome).appendChild(toastNode);
    toastNode.textContent = copy;
    toastNode.classList.add('is-visible');
    setTimeout(() => toastNode.classList.remove('is-visible'), 1800);
  };

  // 装饰图加载失败时隐藏，避免破图图标（离线包内资源缺失属于构建 bug）
  shell.addEventListener('error', (event) => {
    const image = event.target;
    if (!(image instanceof HTMLImageElement) || image.alt) return;
    image.hidden = true;
  }, true);

  const updateOnboardingNav = (name) => {
    if (!onboardingNav) return;
    const config = ONBOARDING_NAV[name];
    onboardingNav.hidden = !config;
    if (!config) return;
    if (onboardingBack) onboardingBack.setAttribute('data-back', config.back);
    if (onboardingStepper) onboardingStepper.setAttribute('data-progress', config.progress);
    onboardingSteps.forEach((step) => {
      const key = step.dataset.step;
      step.classList.toggle('is-current', key === config.current);
      step.classList.toggle('is-done', config.done.includes(key));
    });
  };

  const showScreen = (name) => {
    const next = screens.find((screen) => screen.dataset.screen === name);
    if (!next) return;
    screens.forEach((screen) => {
      screen.classList.toggle('is-active', screen === next);
      screen.setAttribute('aria-hidden', screen === next ? 'false' : 'true');
    });
    state.screen = name;
    updateOnboardingNav(name);
    if (themeColor) themeColor.setAttribute('content', ['splash', 'loading'].includes(name) ? '#8a011b' : '#fafafa');
    next.scrollTop = 0;
  };

  // ---------- splash → intro ----------
  let splashTimer = 0;
  let splashTransitioning = false;
  const enterOnboarding = () => {
    if (splashTransitioning || state.screen !== 'splash') return;
    splashTransitioning = true;
    clearTimeout(splashTimer);
    splash.classList.add('is-leaving');
    setTimeout(() => {
      showScreen('intro');
      playIntro();
      splash.classList.remove('is-leaving');
      splashTransitioning = false;
    }, matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 420);
  };
  document.querySelector('#splashEnter').addEventListener('click', enterOnboarding);

  // ---------- intro DNA 卡片循环动画 ----------
  let introTimers = [];
  const clearIntroMotion = () => { introTimers.forEach(clearTimeout); introTimers = []; };
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

  // ---------- 导航委托 ----------
  document.addEventListener('click', (event) => {
    const next = event.target.closest('[data-next]');
    const back = event.target.closest('[data-back]');
    if (next) {
      if (next.dataset.next !== 'intro') clearIntroMotion();
      showScreen(next.dataset.next);
    }
    if (back) {
      showScreen(back.dataset.back);
      if (back.dataset.back === 'intro') playIntro();
    }
  });

  // ---------- suit-manual 信息选择 ----------
  document.querySelector('.manual-form').addEventListener('click', (event) => {
    const button = event.target.closest('[data-manual]');
    if (!button) return;
    const key = button.dataset.manual;
    state.manual[key] = button.dataset.value;
    document.querySelectorAll(`[data-manual="${key}"]`).forEach((item) => {
      const selected = item === button;
      item.classList.toggle('is-selected', selected);
      item.setAttribute('aria-pressed', String(selected));
    });
    document.querySelector('#manualNext').disabled = !Object.values(state.manual).every(Boolean);
  });
  document.querySelector('#manualNext').addEventListener('click', () => showScreen('like'));

  // ---------- like 喜好 ----------
  document.querySelector('#paletteGrid').addEventListener('click', (event) => {
    const button = event.target.closest('[data-palette]');
    if (!button) return;
    state.palette = button.dataset.palette;
    document.querySelectorAll('[data-palette]').forEach((item) => {
      const selected = item === button;
      item.classList.toggle('is-selected', selected);
      item.setAttribute('aria-pressed', String(selected));
    });
    document.querySelector('#likeNext').disabled = false;
  });
  document.querySelector('#likeNext').addEventListener('click', () => {
    state.axes = {
      shape: Number(document.querySelector('#shapeRange').value),
      energy: Number(document.querySelector('#energyRange').value),
      trend: Number(document.querySelector('#trendRange').value),
    };
    showScreen('vibe');
  });

  // ---------- vibe 问卷 ----------
  document.querySelector('#vibeQuestions').addEventListener('click', (event) => {
    const button = event.target.closest('[data-answer]');
    if (!button) return;
    const field = button.closest('[data-question]');
    state.answers[field.dataset.question] = button.dataset.answer;
    field.querySelectorAll('[data-answer]').forEach((item) => {
      const selected = item === button;
      item.classList.toggle('is-selected', selected);
      item.setAttribute('aria-pressed', String(selected));
    });
    document.querySelector('#vibeNext').disabled = Object.keys(state.answers).length !== 3;
  });

  // ---------- loading ----------
  const loadingStages = [
    { percent: 25, line: '先看见真实的你', src: './assets/ui/loading-stage-25.webp' },
    { percent: 50, line: '寻找你同频的灵感', src: './assets/ui/loading-stage-50.webp' },
    { percent: 75, line: '拼出更像你的样子', src: './assets/ui/loading-stage-75.webp' },
    { percent: 100, line: '我们认识你了...', src: './assets/ui/loading-stage-100.webp' },
  ];
  const setLoadingProgress = (progress) => {
    const stage = [...loadingStages].reverse().find((item) => progress >= item.percent) || loadingStages[0];
    const art = document.querySelector('#loadingArt');
    const line = document.querySelector('#loadingLine');
    const percent = document.querySelector('#loadingPercent');
    const stageKey = String(stage.percent);
    if (art.dataset.stage === stageKey) return;
    [art, line, percent].forEach((element) => element.classList.add('is-changing'));
    setTimeout(() => {
      line.textContent = stage.line;
      percent.textContent = `${stage.percent}%`;
      art.src = stage.src;
      art.dataset.stage = stageKey;
      requestAnimationFrame(() => requestAnimationFrame(() => {
        [art, line, percent].forEach((element) => element.classList.remove('is-changing'));
      }));
    }, matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 150);
  };

  // ---------- 报告数据（模板目录 → 渲染数据） ----------
  const DEFAULT_REPORT_DATA = Object.freeze({
    eyebrow: '', title: '', heroImage: {}, traits: [], summary: '',
    colors: [], makeup: [], hair: [], source: {}, outfitSummary: '', outfits: [], adviceIntro: '', advice: [],
  });
  const hasOwn = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
  const escapeReportMarkdown = (value) => String(value == null ? '' : value).replace(/[&<>'"]/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
  })[character]);
  const renderReportInlineMarkdown = (value) => escapeReportMarkdown(value)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/~~([^~]+)~~/g, '<s>$1</s>')
    .replace(/(^|[^*])\*([^*]+)\*/g, '$1<em>$2</em>');
  const renderReportMarkdown = (value) => {
    const lines = String(value == null ? '' : value).replace(/\r\n?/g, '\n').split('\n');
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
    imageUrl: (item.image && item.image.src) || '',
    alt: (item.image && item.image.alt) || item.name || '',
  });
  const templateToReportData = (template) => {
    if (!template) return null;
    const recommendations = template.recommendations || {};
    const outfits = recommendations.outfits || {};
    const metadata = template.metadata || {};
    const hero = template.hero || {};
    const colors = template.colors || {};
    const conclusion = template.conclusion || {};
    const colorLimit = colors.renderLimit || (renderRules.colors && renderRules.colors.limit) || 5;
    return {
      typeId: template.typeId,
      title: metadata.name || '',
      eyebrow: metadata.code || '',
      traits: (template.keywords || []).map((keyword) => typeof keyword === 'string' ? keyword : keyword.label).filter(Boolean),
      summary: template.summary || '',
      heroImage: hero.image || {},
      colors: (colors.items || []).slice(0, colorLimit),
      makeup: (recommendations.makeup || []).map(templateCardToReportCard),
      hair: (recommendations.hair || []).map(templateCardToReportCard),
      source: outfits.source || {},
      outfitSummary: outfits.summary || '',
      outfits: (outfits.items || []).map(templateCardToReportCard),
      adviceIntro: conclusion.intro || '',
      advice: (conclusion.points || []).map((point) => typeof point === 'string' ? point : [point.title, point.description].filter(Boolean).join('：')),
    };
  };
  const cleanAdviceCopy = (value) => String(value || '').replace(/^\s*建议\s*[：:]\s*/, '').trim();
  const normalizeReport = (payload = {}) => {
    const template = personalityCatalog.types[String(payload.typeId || '').toLowerCase()];
    if (template) payload = Object.assign({}, templateToReportData(template), payload);
    const hasPayload = Boolean(payload && Object.keys(payload).length);
    const list = (key) => {
      if (!hasPayload) return DEFAULT_REPORT_DATA[key];
      return hasOwn(payload, key) && Array.isArray(payload[key]) ? payload[key] : [];
    };
    return Object.assign({}, DEFAULT_REPORT_DATA, payload, {
      summary: hasPayload ? (payload.summary || '') : '',
      outfitSummary: hasPayload ? (payload.outfitSummary || '') : '',
      adviceIntro: hasPayload ? (payload.adviceIntro || '') : '',
      traits: list('traits'),
      colors: list('colors'),
      makeup: list('makeup'),
      hair: list('hair'),
      outfits: list('outfits').map((item) => Object.assign({}, item, {
        name: item.name || item.title || '',
        byline: item.byline || (item.author ? `@${String(item.author).replace(/^@/, '')}` : ''),
      })),
      advice: list('advice').map(cleanAdviceCopy).filter(Boolean),
      source: hasPayload && payload.source && typeof payload.source === 'object' ? payload.source : {},
    });
  };

  const reportNodes = {
    heroImage: document.querySelector('[data-report-hero-image]'),
    eyebrow: document.querySelector('[data-report-eyebrow]'),
    title: document.querySelector('[data-report-title]'),
    traits: document.querySelector('#reportTraits'),
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
  const appendImageCards = (container, items) => {
    const cards = items.filter((item) => item && item.imageUrl).map((item) => {
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
    setChildren(container, cards);
    return cards.length;
  };
  const toggleReportSection = (name, visible) => {
    const section = document.querySelector(`[data-report-section="${name}"]`);
    if (section) toggleAttr(section, 'hidden', !visible);
  };

  const renderReport = (payload = {}) => {
    const data = normalizeReport(payload);
    state.reportTypeId = String(data.typeId || 'mute').toLowerCase();
    const fullHero = Boolean(data.heroImage && data.heroImage.src);
    reportNodes.heroImage.src = fullHero ? data.heroImage.src : '';
    reportNodes.heroImage.alt = fullHero ? (data.heroImage.alt || `${data.title} ${data.eyebrow} 人格封面`) : '';
    reportNodes.heroImage.hidden = !fullHero;
    reportNodes.eyebrow.textContent = data.eyebrow;
    reportNodes.title.textContent = data.title;
    setChildren(reportNodes.traits, data.traits.map((trait) => {
      const card = Object.assign(document.createElement('span'), { className: 'report-trait' });
      const lace = Object.assign(document.createElement('img'), {
        src: './assets/ui/lace-card.webp', alt: '', width: 408, height: 604,
      });
      card.append(lace, Object.assign(document.createElement('b'), { textContent: trait }));
      return card;
    }));
    reportNodes.traits.hidden = data.traits.length === 0;
    reportNodes.summary.innerHTML = renderReportMarkdown(data.summary);
    reportNodes.summary.hidden = !data.summary;
    const visibleColors = data.colors.slice(0, (renderRules.colors && renderRules.colors.limit) || 5);
    setChildren(reportNodes.colors, visibleColors.map((color) => {
      const swatch = Object.assign(document.createElement('span'), { textContent: color.name || '' });
      swatch.style.setProperty('--c', color.value || 'transparent');
      return swatch;
    }));
    toggleReportSection('colors', visibleColors.length > 0);
    toggleReportSection('makeup', appendImageCards(reportNodes.makeup, data.makeup) > 0);
    toggleReportSection('hair', appendImageCards(reportNodes.hair, data.hair) > 0);
    const proof = reportNodes.sourceLogo.closest('.report-proof');
    const hasSource = Boolean(data.source.name || data.source.copy);
    reportNodes.sourceCopy.textContent = data.source.copy || '';
    proof.hidden = !hasSource;
    reportNodes.outfitSummary.innerHTML = renderReportMarkdown(data.outfitSummary);
    reportNodes.outfitSummary.hidden = !data.outfitSummary;
    const visibleOutfits = data.outfits.filter((item) => item && item.imageUrl).slice(0, (renderRules.outfits && renderRules.outfits.limit) || 4);
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
    setChildren(reportNodes.outfits, outfitCards);
    toggleReportSection('outfits', Boolean(outfitCards.length || data.outfitSummary));
    reportNodes.adviceIntro.innerHTML = renderReportMarkdown(data.adviceIntro);
    reportNodes.adviceIntro.hidden = !data.adviceIntro;
    setChildren(reportNodes.advice, data.advice.map((copy) => {
      const point = Object.assign(document.createElement('div'), { className: 'report-advice-point' });
      const text = String(copy == null ? '' : copy);
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

    // 分享卡片数据
    document.querySelector('[data-share-title]').textContent = data.title;
    document.querySelector('[data-share-eyebrow]').textContent = data.eyebrow || '';
    document.querySelector('[data-share-summary]').textContent = data.summary || data.traits.join(' · ') || data.title;
    const shareIllustration = document.querySelector('[data-share-illustration]');
    const shareOrnament = document.querySelector('[data-share-ornament]');
    const shareIdentityCard = document.querySelector('.share-card--identity');
    shareIdentityCard.dataset.personality = state.reportTypeId;
    shareIllustration.src = `./assets/personality/${state.reportTypeId}/share-ornament.webp`;
    shareIllustration.alt = `${data.title} 风格摆件`;
    shareIllustration.hidden = false;
    shareOrnament.hidden = false;
    shareOrnament.classList.add('is-standalone');
    document.querySelector('[data-share-color-title]').textContent = data.title;
    document.querySelector('[data-share-inspiration-title]').textContent = data.title;
    setChildren(document.querySelector('#shareCardColors'), visibleColors.map((color) => {
      const swatch = document.createElement('i');
      swatch.style.setProperty('--c', color.value || 'transparent');
      swatch.setAttribute('aria-label', color.name || '推荐色');
      swatch.setAttribute('role', 'img');
      return swatch;
    }));
    const shareImages = [...data.makeup.slice(0, 2), ...data.hair.slice(0, 1), ...data.outfits.slice(0, 1)];
    setChildren(document.querySelector('#shareCardImages'), shareImages.map((item) => Object.assign(document.createElement('img'), {
      src: item.imageUrl || '', alt: item.alt || item.name || '', loading: 'lazy', decoding: 'async',
    })));
    invalidateShareExports();
    return data;
  };

  // ---------- 生成报告（本地分型，保留主项目的仪式感节奏） ----------
  const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
  const preloadReportResources = (data) => {
    const urls = [
      data.heroImage && data.heroImage.src,
      ...data.makeup.map((item) => item.imageUrl),
      ...data.hair.map((item) => item.imageUrl),
      ...data.outfits.map((item) => item.imageUrl),
      `./assets/personality/${state.reportTypeId}/share-ornament.webp`,
    ].filter(Boolean);
    return Promise.all(urls.map((src) => new Promise((resolve) => {
      const image = new Image();
      image.addEventListener('load', resolve, { once: true });
      image.addEventListener('error', resolve, { once: true });
      image.src = src;
    })));
  };
  const generateReport = async () => {
    const button = document.querySelector('#vibeNext');
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    showScreen('loading');
    setLoadingProgress(25);
    const startedAt = Date.now();
    const persona = window.SelfitPersona;
    const vector = persona.buildUserVector({
      preferences: { axes: state.axes, palette: state.palette },
      answers: state.answers,
    });
    const classification = persona.classifyPersona(vector);
    const typeId = classification.primary_persona.toLowerCase();
    setTimeout(() => setLoadingProgress(50), 700);
    setTimeout(() => setLoadingProgress(75), 1400);
    const data = renderReport({ typeId });
    await Promise.all([preloadReportResources(data), delay(2500)]);
    setLoadingProgress(100);
    await delay(650);
    showScreen('report');
    button.removeAttribute('aria-busy');
    button.disabled = Object.keys(state.answers).length !== 3;
  };
  document.querySelector('#vibeNext').addEventListener('click', () => generateReport());

  // ---------- 报告底部操作（滚动进入穿搭区后 dock） ----------
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
    toggleAttr(reportActions, 'inert', !shouldDock);
    reportActions.setAttribute('aria-hidden', shouldDock ? 'false' : 'true');
  };
  toggleAttr(reportActions, 'inert', true);
  reportActions.setAttribute('aria-hidden', 'true');
  reportScreen.addEventListener('scroll', () => {
    if (!reportScrollFrame) reportScrollFrame = requestAnimationFrame(syncReportActions);
  }, { passive: true });
  document.querySelector('#retakeBtn').addEventListener('click', () => showScreen('vibe'));

  // ---------- 分享卡片 Canvas 导出（复用主项目实现） ----------
  const shareDialog = document.querySelector('#shareDialog');
  const shareCloseButton = shareDialog.querySelector('button[value="cancel"]');
  const supportsNativeDialog = typeof shareDialog.showModal === 'function';
  const openShareDialog = () => {
    if (supportsNativeDialog) shareDialog.showModal();
    else shareDialog.setAttribute('open', '');
  };
  const closeShareDialog = () => {
    if (supportsNativeDialog) shareDialog.close();
    else shareDialog.removeAttribute('open');
  };
  shareCloseButton.addEventListener('click', (event) => {
    if (supportsNativeDialog) return;
    event.preventDefault();
    closeShareDialog();
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
    if (document.fonts && document.fonts.ready) await document.fonts.ready;
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
    return lines.map((line) => Object.assign({}, line, { text: line.text.replace(/\s+/g, ' ').trim() })).filter((line) => line.text);
  };
  const renderShareCard = async (sourceCard) => {
    const { card, stage } = createShareExportSurface(sourceCard);
    try {
      await waitForShareCardAssets(card);
      const cardRect = card.getBoundingClientRect();
      const width = SHARE_CARD_WIDTH;
      const height = SHARE_CARD_HEIGHT;
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
      const backgroundMatch = cardStyle.backgroundImage.match(/url\(["']?(.*?)["']?\)/);
      const backgroundUrl = backgroundMatch && backgroundMatch[1];
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
        const firstLineTop = (lines[0] && lines[0].top) || 0;
        const glyphOffset = Math.max(0, (((lines[0] && lines[0].height) || fontSize) - fontSize) / 2);
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

  // ---------- 分享轮播 ----------
  const shareSlideOffset = (slide) => slide.offsetLeft - ((shareTrack.clientWidth - slide.offsetWidth) / 2);
  const syncSharePreviewScale = () => {
    sharePreviewFrame = 0;
    if (!shareDialog.hasAttribute('open') && supportsNativeDialog) return;
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
  window.addEventListener('resize', scheduleSharePreviewScale, { passive: true });
  const syncShareSaveButton = () => {
    const isReady = shareExportBlobs.has(shareSlideIndex);
    const isPreparing = shareExportPromises.has(shareSlideIndex);
    shareSaveButton.disabled = isPreparing;
    shareSaveLabel.textContent = isReady ? '保存到相册' : (isPreparing ? '正在生成图片…' : '生成并保存');
  };
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
  // Chrome 61 无 scroll-snap：滚动静止后由 JS 吸附到最近卡片（有 snap 的内核此分支不执行）
  const supportsScrollSnap = typeof CSS !== 'undefined' && typeof CSS.supports === 'function' && CSS.supports('scroll-snap-type', 'x mandatory');
  let shareSnapTimer = 0;
  shareTrack.addEventListener('scroll', () => {
    if (shareScrollFrame) return;
    shareScrollFrame = requestAnimationFrame(() => {
      shareScrollFrame = 0;
      const closestIndex = shareSlots.reduce((closest, slot, index) => (
        Math.abs(shareSlideOffset(slot) - shareTrack.scrollLeft) < Math.abs(shareSlideOffset(shareSlots[closest]) - shareTrack.scrollLeft) ? index : closest
      ), 0);
      syncShareSlide(closestIndex);
      if (!supportsScrollSnap) {
        clearTimeout(shareSnapTimer);
        shareSnapTimer = setTimeout(() => {
          if (shareTrack.scrollLeft !== shareSlideOffset(shareSlots[shareSlideIndex])) goToShareSlide(shareSlideIndex);
        }, 160);
      }
    });
  }, { passive: true });
  shareTrack.addEventListener('keydown', (event) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    if (event.key === 'Home') goToShareSlide(0);
    else if (event.key === 'End') goToShareSlide(shareSlides.length - 1);
    else goToShareSlide(shareSlideIndex + (event.key === 'ArrowRight' ? 1 : -1));
  });

  const openShareButton = document.querySelector('#openShare');
  openShareButton.addEventListener('click', () => {
    openShareDialog();
    syncShareSaveButton();
    requestAnimationFrame(() => {
      syncSharePreviewScale();
      goToShareSlide(0, false);
    });
  });

  // ---------- 小红书容器端能力（window.xhs.miniTool） ----------
  const miniTool = () => (window.xhs && window.xhs.miniTool) || null;
  const blobToDataUrl = (blob) => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error('图片读取失败，请重试。'));
    reader.readAsDataURL(blob);
  });
  // 大图先落临时文件再保存/发笔记（官方建议，避免超长 base64 上行）
  const blobToTempFilePath = async (blob) => {
    const tool = miniTool();
    if (!tool) throw new Error('container-unavailable');
    const dataUrl = await blobToDataUrl(blob);
    const result = await tool.writeTempFile({ data: dataUrl });
    return (result && result.filePath) || '';
  };

  const saveCardToDevice = async (blob) => {
    const tool = miniTool();
    if (!tool) return 'browser-preview';
    try {
      const filePath = await blobToTempFilePath(blob);
      await tool.saveImageToPhotosAlbum({ filePath });
      return 'album';
    } catch (error) {
      // writeTempFile 失败时降级直接传 base64
      try {
        await tool.saveImageToPhotosAlbum({ filePath: await blobToDataUrl(blob) });
        return 'album';
      } catch (fallbackError) {
        throw fallbackError;
      }
    }
  };

  // 浏览器降级：全屏预览，引导截图保存
  const resetSaveImageGuide = () => {
    saveImageGuide.hidden = true;
    saveImagePreview.removeAttribute('src');
    if (saveImagePreviewUrl) URL.revokeObjectURL(saveImagePreviewUrl);
    saveImagePreviewUrl = '';
  };
  const openSaveImageGuide = (blob) => {
    resetSaveImageGuide();
    closeShareDialog();
    saveImagePreviewUrl = URL.createObjectURL(blob);
    saveImagePreview.src = saveImagePreviewUrl;
    saveImageGuide.hidden = false;
    const guideClose = saveImageGuide.querySelector('[data-close-save-guide]');
    if (guideClose) guideClose.focus({ preventScroll: true });
  };
  saveImageGuide.querySelectorAll('[data-close-save-guide]').forEach((button) => button.addEventListener('click', () => {
    resetSaveImageGuide();
    openShareDialog();
    syncShareSaveButton();
    requestAnimationFrame(() => {
      syncSharePreviewScale();
      goToShareSlide(shareSlideIndex, false);
    });
  }));
  saveImageGuide.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    event.preventDefault();
    resetSaveImageGuide();
    openShareDialog();
    requestAnimationFrame(() => {
      syncSharePreviewScale();
      goToShareSlide(shareSlideIndex, false);
    });
  });

  const runButtonAction = async (button, action) => {
    if (button.getAttribute('aria-busy') === 'true') return;
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    try { await action(); }
    catch (error) { toast(error.message || '这次操作没有完成，请重试。'); }
    finally { button.removeAttribute('aria-busy'); button.disabled = false; }
  };

  document.querySelector('#saveShareCard').addEventListener('click', (event) => runButtonAction(event.currentTarget, async () => {
    const blob = shareExportBlobs.get(shareSlideIndex) || await prepareShareCard(shareSlideIndex);
    if (!blob) throw shareExportErrors.get(shareSlideIndex) || new Error('分享卡片生成失败，请重试。');
    const method = await saveCardToDevice(blob);
    if (method === 'album') toast('已保存到相册');
    else if (method === 'browser-preview') openSaveImageGuide(blob);
  }));

  // 发笔记：预填引流文案 + 当前卡片，唤起小红书发布页
  const shareNoteCopy = (data) => {
    const traits = (data.traits || []).slice(0, 3).join(' · ');
    const lines = [
      `我在 selfit 测了我的风格人格，是「${data.title}」。`,
      traits ? `关键词：${traits}` : '',
      '',
      '16 种风格人格，来测测你是哪一种 →',
      '保存你的风格卡片，看看和朋友像不像。',
    ].filter((line) => line !== null);
    return lines.join('\n');
  };
  document.querySelector('#postNoteBtn').addEventListener('click', (event) => runButtonAction(event.currentTarget, async () => {
    const tool = miniTool();
    if (!tool) {
      toast('在小红书笔记里打开这个小工具，即可一键发笔记');
      return;
    }
    const blob = shareExportBlobs.get(shareSlideIndex) || await prepareShareCard(shareSlideIndex);
    if (!blob) throw shareExportErrors.get(shareSlideIndex) || new Error('分享卡片生成失败，请重试。');
    // 官方 jsbridge 规范：image_resources[].url 只接受 base64 data:uri 或网络地址（不认本地临时路径）
    const dataUrl = await blobToDataUrl(blob);
    const data = normalizeReport({ typeId: state.reportTypeId });
    const title = `我是「${data.title}」，你呢？`;
    await tool.postNote({
      title: title.slice(0, 20),
      content: shareNoteCopy(data).slice(0, 1000),
      pageType: 'photo_publish',
      mediaInfo: { image_resources: [{ url: dataUrl }] },
    });
  }));

  // ---------- 调试预览：?preview=report&type=mute 等 ----------
  const previewParams = new URLSearchParams(window.location.search);
  const previewScreen = previewParams.get('preview');
  const previewScreens = ['splash', 'intro', 'suit-manual', 'like', 'vibe', 'loading'];
  if (previewScreens.includes(previewScreen)) {
    showScreen(previewScreen);
    if (previewScreen === 'intro') playIntro();
    return;
  }
  if (previewScreen === 'report' || previewScreen === 'share') {
    renderReport({ typeId: previewParams.get('type') || 'mute' });
    showScreen('report');
    if (previewScreen === 'share') {
      requestAnimationFrame(() => {
        openShareDialog();
        goToShareSlide(0, false);
      });
    }
    return;
  }
  if (previewScreen === 'loading') {
    showScreen('loading');
    setLoadingProgress(Number(previewParams.get('stage')) || 25);
    return;
  }

  splashTimer = setTimeout(enterOnboarding, matchMedia('(prefers-reduced-motion: reduce)').matches ? 900 : 1800);
})();
