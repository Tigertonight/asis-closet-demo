(() => {
  // 适我 suit 特征卡共享组件：onboarding 的 suit 步骤与「我的档案」共用同一份渲染。
  // 分析参数（肤色明度 L* 等）在两个页面都默认全部展开，不提供折叠。
  const ANALYSIS_HINTS = {
    lStar: {
      title: '肤色明度 L* 是什么？',
      body: 'L* 是国际通用的颜色明度刻度，范围 0–100：数字越大肤色越明亮，越小越深邃。我们取了你脸上额头、两颊等最接近素颜的几个区域，平均后得到这个数。',
    },
    ita: {
      title: '白皙度 ITA 是什么？',
      body: 'ITA° 是色彩学里衡量肤色白皙程度的角度，由明度和黄度一起算出。角度越大越偏白皙，越小越偏小麦色或更深。它和 L* 互相印证，用来判断你的肤色档位。',
    },
    undertone: {
      title: '肤色底调是什么？',
      body: '底调指肤色的冷暖倾向：冷调偏粉、暖调偏黄、橄榄调偏青灰，中性则介于冷暖之间。挑粉底、口红和衣服颜色时，底调比深浅更重要。',
    },
    lengthWidth: {
      title: '「脸长 / 脸宽」是什么？',
      body: '脸的长度除以脸的宽度。越接近 1 越圆润饱满，超过 1.3 左右会显得修长。这是区分圆脸和鹅蛋脸最主要的指标。',
    },
    jawCheek: {
      title: '「下颌宽 / 颧骨宽」是什么？',
      body: '下颌最宽处除以颧骨最宽处。数值小说明下颌收得比较紧（偏尖、偏心形脸），接近 1 说明下颌和颧骨差不多宽（偏方脸或圆脸）。',
    },
    foreheadCheek: {
      title: '「额头宽 / 颧骨宽」是什么？',
      body: '额头最宽处除以颧骨最宽处。大于 1 说明额头比颧骨宽（偏心形脸），小于 1 说明颧骨更突出（偏菱形脸）。',
    },
    hipShoulder: {
      title: '「胯宽 / 肩宽」是什么？',
      body: '胯部宽度除以肩部宽度。大于 1 说明胯比肩宽（梨型特征），小于 1 说明肩比胯宽（倒三角特征）。',
    },
    waistHip: {
      title: '「腰宽 / 胯宽」是什么？',
      body: '腰部宽度除以胯部宽度。数值越小说明腰线越明显（沙漏型特征），接近 1 说明腰和胯差不多宽（矩型特征）。',
    },
  };
  const PHOTO_LABELS = { face: '面部照', body: '全身照' };

  const ensureHintDialog = () => {
    let dialog = document.querySelector('dialog.selfit-suit-hint-dialog');
    if (!dialog) {
      dialog = document.createElement('dialog');
      dialog.className = 'selfit-suit-hint-dialog';
      const title = document.createElement('h2');
      const body = document.createElement('p');
      const form = document.createElement('form');
      form.method = 'dialog';
      const close = document.createElement('button');
      close.type = 'submit';
      close.className = 'suit-hint-close';
      close.textContent = '知道了';
      form.append(close);
      dialog.append(title, body, form);
      dialog.addEventListener('click', (event) => { if (event.target === dialog) dialog.close(); });
      document.body.append(dialog);
    }
    return dialog;
  };
  const openAnalysisHint = (key) => {
    const hint = ANALYSIS_HINTS[key];
    if (!hint) return;
    const dialog = ensureHintDialog();
    dialog.querySelector('h2').textContent = hint.title;
    dialog.querySelector('p').textContent = hint.body;
    dialog.showModal();
  };
  const buildAnalysisHintButton = (key, label) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'analysis-hint';
    button.textContent = '?';
    button.setAttribute('aria-label', `${label}是什么意思`);
    button.onclick = () => openAnalysisHint(key);
    return button;
  };
  const buildAnalysisMetrics = (analysis) => {
    const wrap = document.createElement('div');
    wrap.className = 'suit-analysis';
    (analysis.metrics || []).forEach((metric) => {
      const row = document.createElement('div');
      row.className = 'suit-analysis-row';
      const label = document.createElement('span');
      label.className = 'suit-analysis-label';
      label.textContent = metric.label;
      label.append(buildAnalysisHintButton(metric.key, metric.label));
      const value = document.createElement('b');
      value.textContent = metric.value;
      row.append(label, value);
      wrap.append(row);
    });
    return wrap;
  };
  const buildAnalysisNotes = (notes) => {
    const wrap = document.createElement('div');
    wrap.className = 'suit-analysis-notes';
    notes.forEach((note) => {
      const item = document.createElement('p');
      item.textContent = note.suggestion ? `${note.message}——${note.suggestion}` : note.message;
      wrap.append(item);
    });
    return wrap;
  };
  const buildCard = (feature, analysis, { photos = {}, onEdit }) => {
    const card = document.createElement('article');
    card.className = 'suit-feature';
    card.dataset.featureKey = feature.key;
    const header = document.createElement('header');
    if (typeof onEdit === 'function') {
      const edit = document.createElement('button');
      edit.type = 'button';
      edit.textContent = '修改';
      edit.setAttribute('aria-label', `修改${feature.title}`);
      edit.onclick = () => onEdit(feature.key);
      header.append(edit);
    }
    card.append(header);
    const valueRow = document.createElement('div');
    valueRow.className = 'suit-feature-value';
    const value = document.createElement('h3');
    value.textContent = feature.value || '等你补充';
    if (analysis?.subLabel && feature.source === 'photo' && feature.value === analysis.label) {
      value.textContent = `${feature.value} · ${analysis.subLabel}`;
    }
    valueRow.append(value);
    header.prepend(valueRow);
    if (feature.source === 'manual') {
      const badge = document.createElement('small');
      badge.className = 'suit-feature-calibration';
      badge.textContent = '手动校准';
      valueRow.append(badge);
    } else if (feature.source !== 'photo') {
      const source = document.createElement('small');
      const photoKind = feature.key === 'bodyShape' ? 'body' : 'face';
      source.textContent = photos[photoKind] ? '暂时无法判断' : `还没有上传${PHOTO_LABELS[photoKind]}`;
      card.append(source);
    }
    if (feature.description) {
      const description = document.createElement('p');
      description.className = 'suit-feature-description';
      description.textContent = feature.description;
      card.append(description);
    }
    if (analysis?.metrics?.length) card.append(buildAnalysisMetrics(analysis));
    if (analysis?.notes?.length) card.append(buildAnalysisNotes(analysis.notes));
    if (feature.advice) {
      const advice = document.createElement('p');
      advice.className = 'suit-advice';
      const adviceCopy = String(feature.advice).replace(/^可以试试\s*/, '').replace(/[。\s]+$/, '');
      advice.textContent = `搭配建议：${adviceCopy}`;
      card.append(advice);
    }
    return card;
  };

  const render = (container, options = {}) => {
    if (!container) return;
    const {
      features = [], analyses = {}, photos = {},
      heading = false, entrance = false, onEdit = null,
    } = options;
    container.classList.add('selfit-suit-cards');
    container.replaceChildren();
    if (!features.length) return;
    if (heading) {
      const headingElement = document.createElement('h2');
      headingElement.className = 'suit-features-heading';
      headingElement.textContent = '从照片里认识到的你';
      if (entrance) headingElement.classList.add('suit-feature--enter');
      container.append(headingElement);
    }
    features.forEach((feature, index) => {
      const analysis = (analyses[feature.key === 'bodyShape' ? 'body' : 'face'] || {}).attributes?.[feature.key] || null;
      const card = buildCard(feature, analysis, { photos, onEdit });
      if (entrance) {
        card.classList.add('suit-feature--enter');
        card.style.animationDelay = `${110 + index * 120}ms`;
      }
      container.append(card);
    });
  };

  window.SelfitSuitCards = Object.freeze({ render });
})();
