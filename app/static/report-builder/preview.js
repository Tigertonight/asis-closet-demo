(() => {
  const $ = (selector) => document.querySelector(selector);
  const screen = $('[data-report-screen]');
  const nodes = {
    hero: $('[data-report-hero]'), heroImage: $('[data-report-hero-image]'), illustration: $('[data-report-illustration]'), title: $('[data-report-title]'), eyebrow: $('[data-report-eyebrow]'),
    traits: $('[data-report-traits]'), summary: $('[data-report-summary]'), colors: $('[data-report-colors]'), makeup: $('[data-report-makeup]'), hair: $('[data-report-hair]'),
    outfitSummary: $('[data-report-outfit-summary]'), outfits: $('[data-report-outfits]'), sourceLogo: $('[data-report-source-logo]'), sourceCopy: $('[data-report-source-copy]'),
    sourceAvatars: $('[data-report-source-avatars]'), advicePanel: $('[data-report-advice-panel]'), adviceIntro: $('[data-report-advice-intro]'), advice: $('[data-report-advice-list]'),
  };
  const assetUrl = (value) => {
    const source=String(value||'');
    return source.startsWith('./assets/') ? `../assets/${source.slice('./assets/'.length)}` : source;
  };
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (character) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' })[character]);
  const inlineMarkdown = (value) => escapeHtml(value).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,'<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/~~([^~]+)~~/g,'<s>$1</s>').replace(/(^|[^*])\*([^*]+)\*/g,'$1<em>$2</em>');
  const markdown = (value) => {
    const lines=String(value??'').replace(/\r\n?/g,'\n').split('\n');let html='';let list='';
    const close=()=>{if(list){html+=`</${list}>`;list=''}};
    lines.forEach((line)=>{const bullet=line.match(/^\s*[-*]\s+(.+)$/);const ordered=line.match(/^\s*\d+[.)]\s+(.+)$/);const heading=line.match(/^\s*#{1,3}\s+(.+)$/);if(bullet||ordered){const type=bullet?'ul':'ol';if(list!==type){close();html+=`<${type}>`;list=type}html+=`<li>${inlineMarkdown((bullet||ordered)[1])}</li>`;return}close();if(!line.trim()){html+='<span class="report-markdown-space"></span>';return}if(heading){html+=`<strong class="report-markdown-heading">${inlineMarkdown(heading[1])}</strong>`;return}html+=`<p>${inlineMarkdown(line)}</p>`});close();return html;
  };
  const section = (name, visible) => $(`[data-report-section="${name}"]`)?.toggleAttribute('hidden', !visible);
  const cards = (container, items = []) => {
    const entries=items.filter((item)=>item?.imageUrl).map((item)=>{const figure=document.createElement('figure');const image=Object.assign(document.createElement('img'),{src:assetUrl(item.imageUrl),alt:item.alt||item.name||'',loading:'lazy',decoding:'async'});const caption=document.createElement('figcaption');caption.append(document.createTextNode(item.name||''));if(item.byline)caption.append(Object.assign(document.createElement('small'),{textContent:item.byline}));figure.append(image,caption);return figure});container.replaceChildren(...entries);return entries.length;
  };
  const render = (data = {}) => {
    const heroSource=assetUrl(data.heroImage?.src);const usesReferenceCover=!heroSource&&data.title==='造梦浪漫型人'&&data.eyebrow==='LACE';nodes.hero.classList.toggle('report-hero--full',Boolean(heroSource));nodes.hero.classList.toggle('report-hero--reference',usesReferenceCover);nodes.heroImage.src=heroSource;nodes.heroImage.alt=data.heroImage?.alt||'';nodes.heroImage.hidden=!heroSource;nodes.title.textContent=data.title||'';nodes.eyebrow.textContent=data.eyebrow||'';nodes.illustration.src=assetUrl(data.illustration?.imageUrl);nodes.illustration.alt=data.illustration?.alt||'';nodes.illustration.closest('figure').hidden=usesReferenceCover||!data.illustration?.imageUrl;
    nodes.traits.replaceChildren(...(data.traits||[]).map((trait)=>{const card=Object.assign(document.createElement('span'),{className:'report-trait'});card.append(Object.assign(document.createElement('img'),{src:'/static/selfit/assets/lace-card@4x.png',alt:''}),Object.assign(document.createElement('b'),{textContent:trait}));return card}));
    nodes.summary.innerHTML=markdown(data.summary);nodes.summary.hidden=!data.summary;
    const colors=(data.colors||[]).slice(0,5);nodes.colors.replaceChildren(...colors.map((color)=>{const swatch=Object.assign(document.createElement('span'),{textContent:color.name||''});swatch.style.setProperty('--c',color.value||'transparent');return swatch}));section('colors',colors.length>0);
    section('makeup',cards(nodes.makeup,data.makeup)>0);section('hair',cards(nodes.hair,data.hair)>0);nodes.outfitSummary.innerHTML=markdown(data.outfitSummary);nodes.outfitSummary.hidden=!data.outfitSummary;section('outfits',Boolean(cards(nodes.outfits,data.outfits)||data.outfitSummary));
    const source=data.source||{};const hasSource=Boolean(source.name||source.copy||source.avatars?.imageUrl);nodes.sourceLogo.alt=source.name||'小红书';nodes.sourceLogo.hidden=!hasSource;nodes.sourceCopy.textContent=source.copy||'';nodes.sourceAvatars.src=assetUrl(source.avatars?.imageUrl)||'/static/selfit/assets/report-user-avatar-stack@4x.png';nodes.sourceAvatars.alt=source.avatars?.alt||'3 位真实用户头像';nodes.sourceAvatars.hidden=!hasSource;nodes.sourceLogo.closest('.report-proof').hidden=!hasSource;
    nodes.adviceIntro.innerHTML=markdown(data.adviceIntro);nodes.adviceIntro.hidden=!data.adviceIntro;nodes.advice.replaceChildren(...(data.advice||[]).map((copy)=>{const point=Object.assign(document.createElement('div'),{className:'report-advice-point'});point.innerHTML=markdown(copy);return point}));nodes.advicePanel.hidden=!(data.adviceIntro||(data.advice||[]).length);
    window.dispatchEvent(new CustomEvent('report-template:rendered',{detail:{data}}));return data;
  };
  screen.addEventListener('scroll',()=>{$('.report-actions').classList.toggle('is-docked',screen.scrollTop>500)});
  window.reportTemplatePreview=Object.freeze({render});
  window.addEventListener('report-template:render',(event)=>render(event.detail||{}));
})();
