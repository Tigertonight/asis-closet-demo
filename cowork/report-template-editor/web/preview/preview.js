(() => {
  const $ = (selector) => document.querySelector(selector);
  const screen = $('[data-report-screen]');
  const nodes = {
    hero: $('[data-report-hero]'), heroImage: $('[data-report-hero-image]'), illustration: $('[data-report-illustration]'), title: $('[data-report-title]'), eyebrow: $('[data-report-eyebrow]'),
    traits: $('[data-report-traits]'), summary: $('[data-report-summary]'), colors: $('[data-report-colors]'), makeup: $('[data-report-makeup]'), hair: $('[data-report-hair]'),
    outfitSummary: $('[data-report-outfit-summary]'), outfits: $('[data-report-outfits]'), source: $('[data-report-source]'), sourceCopy: $('[data-report-source-copy]'),
    sourceAvatars: $('[data-report-source-avatars]'), advicePanel: $('[data-report-advice-panel]'), adviceIntro: $('[data-report-advice-intro]'), advice: $('[data-report-advice-list]'),
  };
  const assetUrl = (value) => {
    const source=String(value||'');
    if(source.startsWith('/api/'))return `.${source}`;
    return source;
  };
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (character) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' })[character]);
  const inlineMarkdown = (value) => escapeHtml(value).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,'<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/~~([^~]+)~~/g,'<s>$1</s>').replace(/(^|[^*])\*([^*]+)\*/g,'$1<em>$2</em>');
  const markdown = (value) => {
    const lines=String(value??'').replace(/\r\n?/g,'\n').split('\n');let html='';let list='';
    const close=()=>{if(list){html+=`</${list}>`;list=''}};
    lines.forEach((line)=>{const bullet=line.match(/^\s*[-*]\s+(.+)$/);const ordered=line.match(/^\s*\d+[.)]\s+(.+)$/);const heading=line.match(/^\s*#{1,3}\s+(.+)$/);if(bullet||ordered){const type=bullet?'ul':'ol';if(list!==type){close();html+=`<${type}>`;list=type}html+=`<li>${inlineMarkdown((bullet||ordered)[1])}</li>`;return}close();if(!line.trim()){html+='<span class="report-markdown-space"></span>';return}if(heading){html+=`<strong class="report-markdown-heading">${inlineMarkdown(heading[1])}</strong>`;return}html+=`<p>${inlineMarkdown(line)}</p>`});close();return html;
  };
  const cleanAdviceCopy = (value) => String(value || '').replace(/^\s*建议\s*[：:]\s*/, '').trim();
  const reportCard = (item = {}) => {
    const image = item.image && typeof item.image === 'object' ? item.image : {};
    return {
      ...item,
      name: item.name || item.title || '',
      byline: item.byline || (item.author ? `@${String(item.author).replace(/^@/, '')}` : ''),
      imageUrl: item.imageUrl || image.src || (typeof item.image === 'string' ? item.image : ''),
      alt: item.alt || image.alt || item.name || item.title || '',
    };
  };
  const normalize = (payload = {}) => {
    const isTemplate = Boolean(payload.metadata || payload.recommendations || payload.hero?.image);
    const outfits = isTemplate ? (payload.recommendations?.outfits || {}) : {};
    const conclusion = isTemplate ? (payload.conclusion || {}) : {};
    const colors = isTemplate ? (payload.colors?.items || []) : (Array.isArray(payload.colors) ? payload.colors : payload.colors?.items || []);
    const advice = isTemplate
      ? (conclusion.points || []).map((point) => typeof point === 'string' ? point : [point.title, point.description].filter(Boolean).join('：'))
      : (Array.isArray(payload.advice) ? payload.advice : []);
    return {
      ...payload,
      title: isTemplate ? (payload.metadata?.name || '') : (payload.title || payload.name || ''),
      eyebrow: isTemplate ? (payload.metadata?.code || '') : (payload.eyebrow || payload.code || ''),
      traits: (isTemplate ? payload.keywords : (payload.traits || payload.keywords) || []).map((item) => typeof item === 'string' ? item : item?.label).filter(Boolean),
      summary: payload.summary || '',
      heroImage: isTemplate ? (payload.hero?.image || {}) : (payload.heroImage || (payload.hero ? {src:payload.hero} : {})),
      illustration: payload.illustration && typeof payload.illustration === 'object' ? payload.illustration : {},
      colors,
      makeup: (isTemplate ? payload.recommendations?.makeup : payload.makeup || []).map(reportCard),
      hair: (isTemplate ? payload.recommendations?.hair : payload.hair || []).map(reportCard),
      source: isTemplate ? (outfits.source || {}) : (payload.source || {}),
      outfitSummary: isTemplate ? (outfits.summary || '') : (payload.outfitSummary || ''),
      outfits: (isTemplate ? outfits.items : payload.outfits || []).map(reportCard),
      adviceIntro: isTemplate ? (conclusion.intro || '') : (payload.adviceIntro || payload.conclusion || ''),
      advice: advice.map(cleanAdviceCopy).filter(Boolean),
    };
  };
  const section = (name, visible) => $(`[data-report-section="${name}"]`)?.toggleAttribute('hidden', !visible);
  const cards = (container, items = []) => {
    const entries=items.filter((item)=>item?.imageUrl).map((item)=>{const figure=document.createElement('figure');const image=Object.assign(document.createElement('img'),{src:assetUrl(item.imageUrl),alt:item.alt||item.name||'',loading:'lazy',decoding:'async'});const caption=document.createElement('figcaption');caption.append(document.createTextNode(item.name||''));if(item.byline)caption.append(Object.assign(document.createElement('small'),{textContent:item.byline}));figure.append(image,caption);return figure});container.replaceChildren(...entries);return entries.length;
  };
  const render = (payload = {}) => {
    const data=normalize(payload);
    const heroSource=assetUrl(data.heroImage?.src);const usesReferenceCover=!heroSource&&data.title==='造梦浪漫型人'&&data.eyebrow==='LACE';nodes.hero.classList.toggle('report-hero--full',Boolean(heroSource));nodes.hero.classList.toggle('report-hero--reference',usesReferenceCover);nodes.heroImage.src=heroSource;nodes.heroImage.alt=data.heroImage?.alt||'';nodes.heroImage.hidden=!heroSource;nodes.title.textContent=data.title||'';nodes.eyebrow.textContent=data.eyebrow||'';nodes.illustration.src=assetUrl(data.illustration?.imageUrl);nodes.illustration.alt=data.illustration?.alt||'';nodes.illustration.closest('figure').hidden=usesReferenceCover||!data.illustration?.imageUrl;
    nodes.traits.replaceChildren(...(data.traits||[]).map((trait)=>{const card=Object.assign(document.createElement('span'),{className:'report-trait'});card.append(Object.assign(document.createElement('img'),{src:'./assets/lace-card@4x.png',alt:''}),Object.assign(document.createElement('b'),{textContent:trait}));return card}));
    nodes.summary.innerHTML=markdown(data.summary);nodes.summary.hidden=!data.summary;
    const colors=(data.colors||[]).slice(0,5);nodes.colors.replaceChildren(...colors.map((color)=>{const swatch=Object.assign(document.createElement('span'),{textContent:color.name||''});swatch.style.setProperty('--c',color.value||'transparent');return swatch}));section('colors',colors.length>0);
    section('makeup',cards(nodes.makeup,data.makeup)>0);section('hair',cards(nodes.hair,data.hair)>0);nodes.outfitSummary.innerHTML=markdown(data.outfitSummary);nodes.outfitSummary.hidden=!data.outfitSummary;section('outfits',Boolean(cards(nodes.outfits,data.outfits)||data.outfitSummary));
    const source=data.source||{};nodes.source.textContent=source.name||'';nodes.sourceCopy.textContent=source.copy||'';nodes.sourceAvatars.src=assetUrl(source.avatars?.imageUrl);nodes.sourceAvatars.alt=source.avatars?.alt||'';nodes.sourceAvatars.hidden=!source.avatars?.imageUrl;nodes.source.closest('.report-proof').hidden=!(source.name||source.copy||source.avatars?.imageUrl);
    nodes.adviceIntro.innerHTML=markdown(data.adviceIntro);nodes.adviceIntro.hidden=!data.adviceIntro;nodes.advice.replaceChildren(...(data.advice||[]).map((copy)=>{const point=Object.assign(document.createElement('div'),{className:'report-advice-point'});point.innerHTML=markdown(copy);return point}));nodes.advicePanel.hidden=!(data.adviceIntro||(data.advice||[]).length);
    window.dispatchEvent(new CustomEvent('report-template:rendered',{detail:{data}}));return data;
  };
  screen.addEventListener('scroll',()=>{$('.report-actions').classList.toggle('is-docked',screen.scrollTop>500)});
  window.reportTemplatePreview=Object.freeze({render});
  window.addEventListener('report-template:render',(event)=>render(event.detail||{}));
})();
