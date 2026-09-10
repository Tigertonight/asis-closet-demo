(() => {
  "use strict";
  const $ = (s) => document.querySelector(s),
    params = new URLSearchParams(location.search);
  const reference = params.get("reference") === "1",
    A = "/static/selfit-tryon/assets/";
  const esc = (s) =>
    String(s ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const asset = (n) => `${A}${n}.webp`;
  const image = (src, alt = "", cls = "") =>
    `<img src="${esc(mediaURL(src))}" alt="${esc(alt)}" class="${cls}" draggable="false">`;
  const fixtures = [
    { id: "skirt", category: "bottom", name: "黑色半裙" },
    { id: "tee", category: "top", name: "白色短袖" },
    { id: "yellow", category: "top", name: "黄色上衣" },
  ].map((x) => ({ ...x, src: asset(x.id) }));
  const fixtureOutfits = Array.from({ length: 9 }, (_, i) => ({
    id: `reference-${i}`,
    name: "灵感套装",
    raw: {can_delete:true},
    src: `${A}main-app/outfit-reference-${i}.svg`,
    items: fixtures,
    saved: i === 5,
  }));
  const feedFixtures = [
    "look-grey",
    "outfit-white",
    "outfit-silver",
    "look-pink",
    "look-street",
    "look-chair",
    "look-sea",
  ].map((n, i) => ({
    id: `look-${i}`,
    name: [
      "灰色露肩穿搭",
      "白色轻盈套装",
      "银色夏日套装",
      "粉色日常穿搭",
      "黑色街头穿搭",
      "清爽学院穿搭",
      "海边灵感",
    ][i],
    src: `${A}${n}-media.svg`,
    flat: n.startsWith("outfit"),
    kind: n.startsWith("outfit") ? "outfit" : "note",
    width:184, height:245,
    items: fixtures,
    saved: [2, 3].includes(i),
  }));
  let savedSession = null;
  try {
    // 与 selfit-auth.js 同口径：v2 存 localStorage（跨会话保持），v1（sessionStorage）做一次性迁移。
    const legacySession = sessionStorage.getItem("selfit.auth.session.v1");
    if (legacySession && !localStorage.getItem("selfit.auth.session.v2")) {
      localStorage.setItem("selfit.auth.session.v2", legacySession);
      sessionStorage.removeItem("selfit.auth.session.v1");
    }
    savedSession = JSON.parse(
      localStorage.getItem("selfit.auth.session.v2")
        || sessionStorage.getItem("selfit.auth.session.v1")
        || "null",
    );
  } catch {}
  if (
    savedSession?.expiresAt &&
    Date.parse(savedSession.expiresAt) <= Date.now()
  )
    savedSession = null;
  // 内测门槛：已登录的非内测账号（普通手机号用户）不进主站，回 onboarding 解锁屏。
  if (
    savedSession?.user &&
    !String(savedSession.user.user_id || "").startsWith("guest_") &&
    savedSession.user.beta_qualified === false &&
    !reference
  ) {
    window.location.replace("/selfit?entry=unlock");
    throw new Error("redirect-to-unlock");
  }
  let visitorReady = null;
  function ensureVisitorSession() {
    if (!visitorReady) visitorReady = window.SelfitAuth.createClient({mode:'live'}).ensureVisitor().then(session => {
      savedSession = session;
      return session;
    }).catch(error => { visitorReady = null; throw error; });
    return visitorReady;
  }
  function mediaURL(path) {
    if (!path) return "";
    try {
      const url = new URL(path, location.origin);
      if (!["http:", "https:", "blob:"].includes(url.protocol)) return "";
      if (url.origin === location.origin && url.pathname.startsWith("/static/selfit-tryon/assets/main-app/"))
        url.searchParams.set("v", "20260908-assets7");
      if (
        url.origin === location.origin &&
        url.pathname.startsWith("/user-assets/") &&
        savedSession?.accessToken
      )
        url.searchParams.set("access_token", savedSession.accessToken);
      return url.href;
    } catch {
      return "";
    }
  }
  const state = {
    page: ["mirror", "closet", "inspiration", "detail", "chat", "profile", "profile-edit", "import-review", "result-viewer", "tryon-history", "topic", "builder"].includes(
      params.get("screen"),
    )
      ? params.get("screen")
      : "mirror",
    styling: params.get("mode") === "styling",
    source: params.get("from") === "report" && params.has("report_notes") ? "report" : "inspiration",
    reportOutfits: [], reportOutfitsMode: "", reportOutfitsKey: "",
    homeOutfits: [], homeNotesError: "",
    category: "all",
    closetCategory: "all",
    wardrobeDeleting: "",
    builderMatching:false, builderRequest:0, builderAnchor:null, builderItems:[], builderMatch:null, builderMatchError:"",
    builderMatches:[], builderMatchIndex:0,
    profile: null, profileLoading: false, profileError: "", profileSaving: false, profileDraft: null, profilePhotoDraft: {}, profileSuit: null, profileReplacing: "",
    chatMessages: [], chatDraft: "", chatBusy: false, chatLoaded: false, chatLoading: false, chatError: "", chatReturn: "mirror",
    items: reference ? fixtures : [],
    outfits: reference ? fixtureOutfits : [],
    feed: reference ? [feedFixtures[2],feedFixtures[1],feedFixtures[4],feedFixtures[3],feedFixtures[6],feedFixtures[5]] : [],
    topics: reference ? [{id:"reference-date",title:"赴一场约会",cover:feedFixtures[0].src,
      previews:[feedFixtures[1].src,feedFixtures[2].src,asset("outfit")],
      entries:[feedFixtures[4],feedFixtures[3],feedFixtures[5],feedFixtures[5]]}] : [],
    topicId: params.get("topic") || (reference ? "reference-date" : ""),
    importItems: reference ? fixtures : [], importSelection: new Set(reference ? fixtures.map(x=>x.id) : []), importPhoto: reference ? feedFixtures[3].src : "", importSaving:false, importError:"",
    savedNotes: [],
    current: reference ? feedFixtures[3] : null,
    photo: reference ? `${A}main-app/mirror-reference-photo.svg` : "",
    viewerPhoto: params.get("preview") === "photo",
    file: null,
    modelId: "",
    modelLibrary: [],
    personalPhoto: "",
    personalFile: null,
    top: "top",
    bottom: "pants",
    result: "",
    resultOriginal: "",
    historyRecords: [], historyLoading: true, historyError: "", historyRequest: 0,
    viewerReturnPage: params.get("viewer_from") === "history" ? "tryon-history" : "mirror",
    loading: !reference,
    error: "",
    selected: new Set(),
    canvasSelection: "",
    canvasHistory: [],
    canvasFuture: [],
    uploadURLs: [],
    returnPage: params.get("screen") === "detail" && params.get("topic") ? "topic" : "inspiration",
    job: null,
    feedSession: null,
    feedCursor: null,
    feedMore: false,
    feedBusy: false,
    feedOffset: 0,
    pendingTry: false,
    profileRequired: false,
    feedError: "",
    wardrobeError: "",
    exampleAccepted: false,
  };
  let toastTimer,
    pollTimer,
    importTimer,
    importFile = null,
    importJob = null,
    importEpoch = 0,
    generationBusy = false;
  function notify(text, presentation = "") {
    $("#notice").classList.toggle("favorite-notice", presentation === "favorite");
    $("#notice").style.removeProperty("top");
    if (presentation === "favorite") {
      const photo=$(".note-detail-photo, .outfit-detail-image");
      if (photo?.getBoundingClientRect().height) $("#notice").style.top=`${photo.getBoundingClientRect().bottom - $("#studio").getBoundingClientRect().top - 88}px`;
    }
    $("#notice").textContent = text;
    $("#notice").classList.add("visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(
      () => $("#notice").classList.remove("visible"),
      3200,
    );
  }
  async function api(path, options = {}, timeoutMs = 30000) {
    const controller = new AbortController(),
      timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const r = await fetch(path, {
        ...options,
        signal: controller.signal,
        headers: {
          ...(savedSession?.accessToken
            ? { Authorization: `Bearer ${savedSession.accessToken}` }
            : {}),
          ...options.headers,
        },
      });
      let data;
      try {
        data = await r.json();
      } catch {
        throw Error("暂时无法连接，请稍后重试。");
      }
      if (!r.ok) {
        if (r.status === 401) {
          savedSession = null;
          try {
            localStorage.removeItem("selfit.auth.session.v2");
            sessionStorage.removeItem("selfit.auth.session.v1");
          } catch {}
        }
        const reportDetail = (path.startsWith('/selfit/try-on/report-outfits?') || /^\/selfit\/try-on\/items\/[^/]+\/outfits$/.test(path)) &&
          [404, 409, 422, 429, 502, 503, 504].includes(r.status) && typeof data?.detail === 'string' ? data.detail : '';
        const gateDetail = typeof data?.detail === 'string' ? data.detail : '';
        const e = Error(
          r.status === 401
            ? "请先登录，再查看你的衣橱。"
            : r.status === 403
              ? (gateDetail || "内测名额有限，输入邀请码解锁完整体验。")
              : r.status === 429
                ? (gateDetail || "操作太频繁了，请稍后再试。")
                : reportDetail || "这次操作没有完成，请稍后再试。",
        );
        e.status = r.status;
        throw e;
      }
      return data;
    } catch (error) {
      if (error.name === "AbortError")
        throw Error("连接时间有点久，请稍后重新尝试。");
      if (error instanceof TypeError)
        throw Error("暂时连接不上，请检查网络后重试。");
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }
  function nav() {
    const visible = !["detail","chat","profile","profile-edit","import-review","result-viewer","tryon-history","topic","builder"].includes(state.page);
    $("#navigation").hidden = !visible;
    $("#navigation").innerHTML = [
      ["mirror", "试衣镜"],
      ["closet", "衣帽间"],
      ["inspiration", "灵感库"],
    ]
      .map(
        ([id, label]) =>
          `<button class="nav-item" data-page="${id}" ${state.page === id ? 'aria-current="page"' : ""}><span>${label}</span>${state.page === id ? (id === "mirror" ? image(asset("mirror"), "", "nav-ornament") : id === "inspiration" ? image(asset("butterfly"), "", "nav-ornament butterfly") : image(`${A}main-app/nav-shirt.webp`, "", "nav-shirt")) : ""}</button>`,
      )
      .join("") + `<button class="nav-ai" data-action="open-chat" aria-label="AI 搭配对话">${image(`${A}main-app/nav-ai.webp`,"")}</button>`;
  }
  function card(x, kind = "item", i = 0) {
    const mirrorNote = !reference && state.page === "mirror" && kind === "outfit";
    const target = state.generating?.target || state.current;
    const targetIds = [target?.id, target?.personalId].filter(Boolean);
    const activeOutfit = state.page === "mirror" && kind === "outfit" &&
      [x.id, x.personalId].some(id => id && targetIds.includes(id));
    const pending = activeOutfit && Boolean(state.generating || (reference && params.get("mirror_state") === "generating"));
    const mark = activeOutfit ? `<span class="outfit-state ${pending ? "pending" : ""}" aria-label="${pending ? "正在试穿" : "已选中"}">${pending ? "" : "✓"}</span>` : "";
    if (mirrorNote) return `<article class="card outfit-card mirror-note-card" data-kind="${esc(x.id)}" data-active="${activeOutfit}"><button class="mirror-note-open" data-note-preview="${esc(x.id)}" aria-label="查看${esc(x.name)}大图">${image(x.src, x.name)}</button>${mark}<button class="try-chip" data-try="${esc(x.id)}" aria-label="试穿${esc(x.name)}">试穿</button></article>`;
    return `<button class="card ${kind === "outfit" ? "outfit-card" : "item-card"}" data-${kind}="${esc(x.id)}" data-kind="${esc(x.id)}" aria-label="${esc(x.name)}" aria-pressed="${activeOutfit || state.selected.has(x.id)}">${image(x.src, x.name)}${mark}</button>`;
  }
  function empty(text) {
    return `<div class="empty">${esc(text)}<br>${!reference && !savedSession?.accessToken ? '<a href="/selfit">登录 selfit</a>' : state.error ? '<button class="secondary" data-action="reload">重新加载</button>' : '<button class="secondary" data-action="add">添加衣服</button>'}</div>`;
  }
  function categories(compact = true) {
    return `<div class="${compact ? "categories" : "category-tabs"}" role="tablist" aria-label="服装分类">${(compact
      ? [
          ["set", "穿搭"],
          ["all", "全部单品"],
          ["top", "上装"],
          ["bottom", "下装"],
          ["shoes", "鞋子"],
          ["accessory", "配饰"],
        ]
      : [
          ["set", "我的搭配"],
          ["saved", "收藏"],
          ["all", "全部单品"],
          ["top", "上装"],
          ["bottom", "下装"],
          ["dress", "连衣裙"],
          ["shoes", "鞋子"],
          ["hat", "帽子"],
          ["accessory", "配饰"],
        ]
    )
      .map(
        ([id, n]) =>
          `<button role="tab" aria-selected="${(compact ? state.category : state.closetCategory) === id}" data-category="${id}" data-location="${compact ? "mirror" : "closet"}">${n}</button>`,
      )
      .join("")}</div>`;
  }
  function mirror() {
    const pending = state.generating || (reference && params.get("mirror_state") === "generating" ? {photo:state.photo,target:state.current} : null);
    const styling = pending ? false : state.styling,
      framedPhoto = !styling && (pending?.photo || state.photo) && (!reference || state.file),
      category = "set",
      homeNotes = state.source !== "closet" && state.source !== "report",
      collection = reference
        ? state.feed.slice(0, 6).map(row => ({...row, kind:"outfit", saved:false}))
        : state.source === "closet"
          ? state.outfits
          : state.source === "report"
            ? state.reportOutfits
          : state.homeOutfits;
    const availableItems =
      reference || state.source === "closet"
        ? state.items
        : uniqueItems(collection.flatMap((x) => x.items));
    const items =
      category === "set"
        ? collection
        : availableItems.filter(
            (x) =>
              category === "all" ||
              categoryGroup(x.category) === category,
          );
    return `<section class="mirror-screen ${styling ? "styling-mode" : "model-mode"}" aria-label="试衣镜"><div class="mirror-stage ${styling ? "styling" : ""} ${pending ? "is-generating" : ""} ${state.result ? "has-result" : ""} ${framedPhoto ? "has-framed-photo" : ""}" aria-busy="${Boolean(pending)}">${image(styling ? `${A}mirror-styling-background.svg?v=20260908-aligned` : `${A}main-app/mirror-background.svg`, "", "stage-background")}<button class="mirror-profile-card" data-page="profile" aria-label="我的档案，查看风格报告"><span class="profile-card-title" aria-hidden="true">my<br>style</span><span>我的档案</span></button><div class="arch"></div>${
      styling && !reference
        ? livePieces()
        : styling
          ? `${image(lookup(state.bottom)?.src || asset(state.bottom), "已选下装", `styling-piece piece-bottom ${state.bottom !== "pants" ? "changed" : ""}`)}${image(lookup(state.top)?.src || asset(state.top), "已选上衣", `styling-piece piece-top ${state.top !== "top" ? "changed" : ""}`)}${[
              [52.163, 30.335, "top"],
              [61.323, 35.983, "top"],
              [40.458, 53.556, "top"],
              [52.672, 57.741, "bottom"],
              [51.145, 80.335, "bottom"],
            ]
              .map(
                ([x, y, s]) =>
                  `<button class="piece-dot" style="left:${x}%;top:${y}%" data-slot="${s}" aria-label="更换${s === "top" ? "上装" : "下装"}"></button>`,
              )
              .join("")}`
          : pending?.photo || state.photo
            ? `${!reference || state.file ? '<div class="mirror-photo-frame">' : ''}${image(
                pending?.photo || state.result || state.photo,
                "当前试穿效果",
                `model-photo ${!reference || state.file ? "personal" : ""}`,
              )}${!reference || state.file ? '</div>' : ''}`
            : '<div class="empty-stage"><span>先放入你的全身照</span><button data-action="model">选择模特</button></div>'
    }${styling && !reference ? canvasTools() : ""}${pending ? `<div class="mirror-generation" role="status" aria-live="polite">${image(`${A}main-app/mirror-loading.svg`, '正在试穿')}</div>` : ""}${!styling && !pending ? `<button class="mirror-result-actions" data-action="result-actions" aria-label="绑定智能穿衣镜">${image(`${A}main-app/mirror-result-actions.svg`, "")}</button>` : ""}${!styling && !pending ? `<button class="mirror-history" data-action="tryon-history" aria-label="试穿历史">${image(`${A}main-app/mirror-history.svg`, "")}</button>` : ""}${!pending ? `<div class="mirror-edit-tools" role="group" aria-label="试衣镜工具"><button data-action="toggle" aria-label="${styling ? '全身镜' : '看单品'}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 8a8 8 0 0 0-14-2L3 9m0-5v5h5M4 16a8 8 0 0 0 14 2l3-3m0 5v-5h-5"/></svg><span>${styling ? '全身镜' : '看单品'}</span></button><button data-action="model" aria-label="替换模特或上传我的照片"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="7" r="4"/><path d="M4 21v-3a8 8 0 0 1 16 0v3Z"/></svg><span>替换模特</span></button></div>` : ''}${!styling && !pending && (state.result || state.photo) ? `<button class="result-expand" data-action="open-viewer" aria-label="${state.result ? '查看试穿大图' : '查看模特大图'}">${image(`${A}main-app/mirror-expand.svg`, "")}</button>${state.current ? `<button class="mirror-favorite" data-action="favorite" aria-label="${state.current.saved ? '取消收藏搭配' : '收藏搭配'}" aria-pressed="${Boolean(state.current.saved)}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 2 3.1 6.3 6.9 1-5 4.9 1.2 6.9-6.2-3.3-6.2 3.3L7 14.2l-5-4.9 6.9-1Z"/></svg></button>` : ""}` : ""}</div>${
      state.loading
        ? empty("正在整理你的搭配…")
        : state.error || (homeNotes && state.homeNotesError)
          ? empty(state.error || state.homeNotesError)
          : `${state.source === "report" ? `<div class="report-outfit-context" aria-live="polite"><span>来自你的风格报告${state.reportOutfitsMode === "mock" ? " · 示例搭配" : ""}</span><strong>${esc(state.current?.reportNote?.title || "选择一套喜欢的搭配")}</strong></div>` : ""}<div class="strip" aria-label="${homeNotes ? "选择穿搭笔记" : category === "set" ? "选择套装" : "选择单品"}">${items.map((x, i) => card(x, category === "set" ? "outfit" : "item", i)).join("") || empty(homeNotes ? "穿搭笔记暂时无法加载，请稍后重试。" : "这里还没有搭配，先添加一件喜欢的衣服。")}</div>`
    }${items.length > 3 ? `<div class="mirror-pagination" aria-label="套装分页">${Array.from({length:Math.ceil(items.length/3)},(_,i)=>`<span data-strip-page="${i}" ${i===0?'data-active="true"':''}></span>`).join('')}</div>` : ''}</section>`;
  }
  const trimmedPieces = new Map();
  function preparePiece(src, retainFineEdges=false) {
    if (trimmedPieces.has(src)) return;
    trimmedPieces.set(src, {ready:false, src});
    const img = new Image();
    img.crossOrigin = "anonymous";
    let done = false;
    const finish = (output, aspect, inkRatio) => {
      if(done) return;
      done = true; clearTimeout(timer);
      trimmedPieces.set(src, {ready:true, src:output || src, aspect:aspect || img.naturalWidth/img.naturalHeight, inkRatio});
      if((state.page === "mirror" && state.styling) || state.page === "builder") render();
    };
    const timer = setTimeout(()=>finish(src), 15000);
    img.onerror = ()=>finish(src);
    img.onload = ()=>{
      try {
        const scale = Math.min(1, (retainFineEdges?1024:512) / Math.max(img.naturalWidth,img.naturalHeight));
        const probe = document.createElement("canvas");
        probe.width = Math.max(1,Math.round(img.naturalWidth*scale));
        probe.height = Math.max(1,Math.round(img.naturalHeight*scale));
        const ctx=probe.getContext("2d",{willReadFrequently:true});
        ctx.drawImage(img,0,0,probe.width,probe.height);
        const pixels=ctx.getImageData(0,0,probe.width,probe.height).data;
        let left=probe.width,top=probe.height,right=-1,bottom=-1,ink=0;
        for(let y=0;y<probe.height;y++)for(let x=0;x<probe.width;x++){
          const offset=(y*probe.width+x)*4,alpha=pixels[offset+3];
          if(alpha>4){
            left=Math.min(left,x);right=Math.max(right,x);top=Math.min(top,y);bottom=Math.max(bottom,y);ink+=alpha/255;
          }
        }
        if(right<left) return finish(src);
        left=Math.max(0,left-2);top=Math.max(0,top-2);
        right=Math.min(probe.width-1,right+2);bottom=Math.min(probe.height-1,bottom+2);
        const crop=document.createElement("canvas");
        crop.width=Math.ceil((right-left+1)/scale);crop.height=Math.ceil((bottom-top+1)/scale);
        crop.getContext("2d").drawImage(img,left/scale,top/scale,crop.width,crop.height,0,0,crop.width,crop.height);
        const inkRatio=ink/((right-left+1)*(bottom-top+1));
        crop.toBlob(blob=>{if(!blob || done)return finish(src,crop.width/crop.height,inkRatio);const url=URL.createObjectURL(blob);state.uploadURLs.push(url);finish(url,crop.width/crop.height,inkRatio);},"image/png");
      } catch { finish(src); }
    };
    img.src=mediaURL(src);
  }
  function canvasSnapshot() {
    return {current:state.current ? {...state.current,items:[...(state.current.items || [])]} : null, selection:state.canvasSelection};
  }
  function rememberCanvas() {
    state.canvasHistory.push(canvasSnapshot());
    state.canvasFuture=[];
    if(state.canvasHistory.length>30) state.canvasHistory.shift();
    state.canvasSelection="";
  }
  function canvasTools() {
    return `<div class="canvas-tools" aria-label="画布操作"><button data-action="undo-canvas" aria-label="撤回上一步" title="撤回上一步" ${state.canvasHistory.length ? "" : "disabled"}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 4 4 9l5 5M4 9h9a7 7 0 0 1 0 14" transform="translate(0 -2)"/></svg><span>撤回</span></button><button data-action="redo-canvas" aria-label="重做上一步" title="重做上一步" ${state.canvasFuture.length ? "" : "disabled"}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 4 5 5-5 5m5-5h-9a7 7 0 0 0 0 14" transform="translate(0 -2)"/></svg><span>重做</span></button>${state.canvasSelection?'<button data-action="adjust-mirror-piece" aria-label="调整选中单品"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 17h16M9 4v6m6 4v6"/></svg><span>调整</span></button>':''}</div>`;
  }
  function livePieces() {
    const pieces = state.current?.items || [];
    if (!pieces.length) return '<div class="empty-stage"><span>选择下方单品，搭出你喜欢的样子</span></div>';
    pieces.forEach(p=>preparePiece(p.src,window.SelfitMirrorLayout.delicate(p)));
    if(pieces.some(p=>!trimmedPieces.get(p.src)?.ready)) return '<div class="empty-stage" role="status"><span>正在整理搭配…</span></div>';
    const measured=pieces.map(p=>({...p,aspect:trimmedPieces.get(p.src)?.aspect,inkRatio:trimmedPieces.get(p.src)?.inkRatio}));
    const unknown=measured.filter(p=>!window.SelfitMirrorLayout.category(p));
    if(unknown.length) return `<div class="empty-stage"><span>有 ${unknown.length} 件单品需要确认分类</span><button class="secondary" data-action="classify-pieces">确认分类</button></div>`;
    const boxes=window.SelfitMirrorLayout.layout(measured,{previous:state.current.mirrorLayout || []});
    state.current.mirrorLayout=boxes;
    const selectedBox=boxes.find(box=>box.id===state.canvasSelection);
    return `<div class="outfit-composition" aria-label="当前搭配">${boxes.map(box=>{
      const p=pieces.find(p=>p.id===box.id);
      const prepared=trimmedPieces.get(p.src);
      return `<button class="composition-piece ${box.delicate?'delicate-piece':''}" data-canvas-piece="${esc(p.id)}" aria-label="选择画布单品：${esc(p.name)}" aria-pressed="${state.canvasSelection === p.id}" style="left:${box.x}%;top:${box.y}%;width:${box.w}%;height:${box.h}%;z-index:${box.z}">${image(prepared.src,p.name)}</button>`;
    }).join("")}</div>${selectedBox ? `<div class="composition-actions"><button class="canvas-remove" data-action="remove-piece" aria-label="从画布移除选中单品" style="left:${selectedBox.x+selectedBox.w}%;top:${selectedBox.y}%"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 10v7m4-7v7"/></svg></button></div>` : ""}`;
  }
  function adjustMirrorPiece(id=state.canvasSelection) {
    const p=state.current?.items.find(item=>item.id===id) || state.current?.items.find(item=>!window.SelfitMirrorLayout.category(item));
    if(!p) return;
    const category=window.SelfitMirrorLayout.category(p),box=state.current.mirrorLayout?.find(b=>b.id===p.id);
    modal(category?'调整单品':'确认单品分类',`${image(trimmedPieces.get(p.src)?.src || p.src,p.name,'mirror-piece-preview')}<p class="mirror-piece-name">${esc(p.name)}</p><div class="mirror-category-options" aria-label="单品分类">${Object.entries(window.SelfitMirrorLayout.LABELS).map(([key,label])=>`<button data-mirror-category="${key}" data-id="${esc(p.id)}" aria-pressed="${category===key}">${label}</button>`).join('')}</div>${box?`<div class="mirror-size-controls" aria-label="单品显示大小"><button data-mirror-size="-1" data-id="${esc(p.id)}" aria-label="缩小单品" ${box.manualScale<=.5?'disabled':''}>−</button><span>显示大小 ${Math.round(box.manualScale*100)}%</span><button data-mirror-size="1" data-id="${esc(p.id)}" aria-label="放大单品" ${box.manualScale>=1.5?'disabled':''}>＋</button></div><p class="mirror-piece-hint">放大至可用空间后会自动停止，保持单品完整。</p>`:''}<button class="primary" data-action="close">完成</button>`);
    $('#sheet').classList.add('mirror-piece-sheet');
  }
  function wardrobeEmpty() {
    const saved = state.closetCategory === "saved";
    const outfits = state.closetCategory === "set";
    const title = saved || outfits ? "还没有收藏" : "给喜欢的衣服，留一个位置";
    const copy = saved || outfits ? "" : "从一件常穿的单品开始，\n慢慢收集，只属于你的风格。";
    return `<div class="wardrobe-empty">${mirrorPairArt()}<h2>${title}</h2>${copy ? `<p>${copy.split('\n').join('<br>')}</p>` : ''}<button class="primary" ${saved || outfits ? 'data-page="inspiration"' : 'data-action="upload-garment"'}>${saved || outfits ? '去灵感库逛逛' : '上传第一件单品'}</button>${!saved && !outfits ? '<button class="empty-browse" data-page="inspiration">先看看穿搭灵感 <span aria-hidden="true">→</span></button>' : ''}</div>`;
  }
  function mirrorPairArt(className = "") {
    return `<div class="wardrobe-empty-art ${className}" aria-hidden="true"><span class="empty-mirror empty-mirror--back">${image('/static/selfit/assets/lace-card@4x.png', '', 'empty-mirror-frame')}${image(asset('butterfly'), '', 'empty-mirror-butterfly')}</span><span class="empty-mirror empty-mirror--front">${image('/static/selfit/assets/lace-card@4x.png', '', 'empty-mirror-frame')}${image(`${A}closet-shirt.svg`, '', 'empty-mirror-shirt')}</span></div>`;
  }
  const chatPrompts = [
    ['日常通勤', '想穿得利落，又不太正式', '想要一套利落但不太正式的通勤搭配，可以给我一些建议吗？'],
    ['周末约会', '舒服自在，也有一点心动', '周末约会想穿得舒服又有一点特别，可以怎么搭配？'],
    ['单品搭配', '让衣橱里的衣服有新意', '想把衣橱里常穿的单品搭出新感觉，你可以先问问我有哪些衣服吗？'],
  ];
  function chatWelcome() {
    return `<div class="chat-welcome">${mirrorPairArt("chat-welcome-art")}<p class="chat-eyebrow">selfit · 你的穿搭搭子</p><h2>今天，想穿出什么感觉？</h2><p class="chat-welcome-copy">从一个场景、一件衣服，或一点灵感开始。<br>我们一起慢慢找到适合你的搭配。</p><div class="chat-prompts" aria-label="试着聊聊这些">${chatPrompts.map(([title,copy],i)=>`<button type="button" data-chat-prompt="${i}"><span><strong>${title}</strong><small>${copy}</small></span><span aria-hidden="true">↗</span></button>`).join('')}</div></div>`;
  }
  function chat() {
    return `<section class="chat-screen" aria-label="AI 搭配对话"><header class="chat-header"><button data-page="${esc(state.chatReturn)}" aria-label="返回上一页">‹</button><div class="chat-header-title"><h1>穿搭搭子</h1><span>和 selfit 聊聊怎么穿</span></div></header><div class="chat-messages" role="log" aria-label="对话记录">${state.chatLoading ? '<p class="chat-thinking" role="status">正在打开我们的对话…</p>' : !state.chatMessages.length ? chatWelcome() : state.chatMessages.map(m=>`<article class="chat-message ${m.role==='user'?'from-user':'from-assistant'}"><span class="chat-speaker">${m.role==='user'?'我':'selfit · 穿搭搭子'}</span><p>${esc(m.content)}</p></article>`).join("")}${state.chatBusy?'<p class="chat-thinking" role="status"><span aria-hidden="true">···</span> 正在为你整理搭配灵感</p>':''}${state.chatError?`<div class="chat-error" role="alert">${esc(state.chatError)}</div>`:''}</div><form class="chat-composer" id="chatComposer"><div class="chat-input-row"><label class="sr-chat-label" for="chatInput">想聊的搭配问题</label><textarea id="chatInput" placeholder="今天去哪儿，想怎么穿？" rows="2" maxlength="2000" ${state.chatBusy?'disabled':''}>${esc(state.chatDraft)}</textarea><button type="submit" class="primary" aria-label="发送消息" ${state.chatBusy||state.chatLoading||!state.chatDraft.trim()?'disabled':''}><span aria-hidden="true">↑</span></button></div><p class="chat-composer-note">搭配没有标准答案，你的感受最重要</p></form></section>`;
  }
  async function loadChat() {
    if(state.chatLoaded||state.chatLoading||reference) return;
    state.chatLoading=true;
    if(state.page==='chat')render();
    try {
      await ensureVisitorSession();
      state.chatError = '';
      const session=await api('/stylist/sessions/selfit-mirror');
      state.chatMessages=(session.messages||[]).filter(m=>['user','assistant'].includes(m.role)).map(m=>({role:m.role,content:m.role==='assistant'&&m.metadata?.status==='failed' ? '这次没有收到搭配建议，请稍后重新发送。' : String(m.content||'')}));
      state.chatLoaded=true;
    } catch(e) { if(e.status===404)state.chatLoaded=true; else state.chatError=e.message; }
    finally { state.chatLoading=false; if(state.page==='chat')render(); }
  }
  async function sendChat() {
    const message=state.chatDraft.trim();
    if(!message||state.chatBusy||state.chatLoading) return;
    if(reference) {state.chatError="这是设计预览。登录后可使用 AI 搭配对话。";render();return;}
    state.chatBusy=true;state.chatError="";state.chatDraft="";
    state.chatMessages.push({role:'user',content:message});render();
    try {
      await ensureVisitorSession();
      const result=await api('/stylist/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message,session_id:'selfit-mirror',context:{source:'mirror',outfit_id:state.current?.id||null}})},250000);
      if(result.status==='failed') throw Error(result.error?.message||'暂时无法提供建议，请稍后再试。');
      state.chatMessages.push({role:'assistant',content:String(result.assistant_message||'暂时没有收到回复，请稍后再试。')});
    } catch(e) {state.chatError=e.status===503 ? '穿搭搭子暂时无法回复，问题已保留，请稍后重新发送。' : e.message;state.chatDraft=message;}
    finally {state.chatBusy=false;if(state.page==='chat'){render();const log=$('.chat-messages');if(log)log.scrollTop=log.scrollHeight;}}
  }
  function pendingImport() {
    if (reference) return null;
    try {return JSON.parse(sessionStorage.getItem('selfit.studio.import') || 'null');} catch {return null;}
  }
  async function resumeImport() {
    const pending=pendingImport(); if(!pending?.job_id)return;
    ++importEpoch;
    importJob={job_id:pending.job_id}; state.importReviewJobId=pending.reviewed ? pending.job_id : '';
    state.importSelection=new Set(pending.selected || []);
    modal("正在拆分单品", '<p id="importCopy" role="status">正在恢复拆款进度…</p><button class="secondary" data-action="close">继续浏览</button>');
    $("#sheet").dataset.importFlow = 'true';
    await pollImport();
  }
  function importStatusCopy() {
    const job = pendingImport();
    if (job?.status === 'awaiting_confirmation' || job?.reviewed) return '单品已拆好 · 继续确认';
    if (job?.status === 'failed') return '拆款未完成 · 查看并重试';
    return '正在拆分单品 · 查看进度';
  }
  function wardrobeItemGroups(items) {
    const groups = [
      {id:"top", label:"上装", icon:"👕", categories:["top","outer"]},
      {id:"bottom", label:"下装", icon:"👖", categories:["bottom","skirt"]},
      {id:"dress", label:"连体", icon:"👗", categories:["dress","jumpsuit","one_piece"]},
      {id:"shoes", label:"鞋子", icon:"👟", categories:["shoes"]},
      {id:"bag", label:"包包", icon:"👜", categories:["bag"]},
      {id:"hat", label:"帽子", icon:"🧢", categories:["hat"]},
      {id:"accessory", label:"配饰", icon:"🧣", categories:["accessory","scarf","socks","belt","jewelry"]},
      {id:"other", label:"其他", icon:"🧺", categories:[]},
    ].map(group => ({...group, items:[]}));
    for (const item of items) {
      if (item.raw?.deleted) continue;
      const group = groups.find(group => group.categories.includes(item.category)) || groups[groups.length - 1];
      group.items.push(item);
    }
    return groups.filter(group => group.items.length);
  }
  function wardrobeItemSections(items) {
    return `<div class="wardrobe-groups">${wardrobeItemGroups(items).map(group =>
      `<section class="wardrobe-group" aria-labelledby="wardrobe-group-${group.id}"><h2 id="wardrobe-group-${group.id}"><span aria-hidden="true">${group.icon}</span>${group.label}</h2><div class="wardrobe-items-row" role="group" aria-label="${group.label}单品" tabindex="0">${group.items.map(item =>
        `<article class="card item-card" data-wardrobe-card="${esc(item.id)}" aria-busy="${state.wardrobeDeleting===item.id}">
          <button class="wardrobe-item-photo" data-wardrobe-hold="${esc(item.id)}" aria-label="${esc(item.name)}，长按显示删除按钮" aria-keyshortcuts="Shift+F10" aria-expanded="false" ${state.wardrobeDeleting===item.id?'disabled':''}>${image(item.src, "")}</button>
          <button class="wardrobe-item-delete" data-action="delete-item" data-id="${esc(item.id)}" aria-label="删除${esc(item.name)}" hidden ${state.wardrobeDeleting?'disabled':''}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 10v7m4-7v7"/></svg></button>
          <button class="wardrobe-style" data-action="item-generate" data-id="${esc(item.id)}" aria-label="帮我搭配：${esc(item.name)}" ${state.wardrobeDeleting===item.id?'disabled':''}>帮我搭配</button>
        </article>`
      ).join("")}</div></section>`
    ).join("")}</div>`;
  }
  function closet() {
    if (state.loading)
      return `<section class="closet-screen"><p class="empty" role="status">正在打开衣帽间…</p></section>`;
    const list =
      ["set", "saved"].includes(state.closetCategory)
        ? uniqueItems([...state.outfits.filter(x => state.closetCategory !== "saved" || x.saved), ...state.savedNotes])
        : state.items;
    const outfits=["set","saved"].includes(state.closetCategory);
    const tabs=`<header class="wardrobe-header"><div role="tablist" aria-label="衣帽间内容"><button role="tab" data-category="all" data-location="closet" aria-selected="${!outfits}">我的单品</button><button role="tab" data-category="set" data-location="closet" aria-selected="${outfits}">我的搭配</button></div><button class="wardrobe-add" data-action="upload-garment" aria-label="添加衣服"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg></button></header>`;
    const content=outfits ? `<div class="closet-grid">${list.map(x => card(x, "outfit")).join("")}</div>` : wardrobeItemSections(list);
    return `<section class="closet-screen wardrobe-source-layout ${outfits ? "wardrobe-outfits" : ""}" aria-label="衣帽间">${tabs}${pendingImport()?.job_id ? `<button class="resume-import" data-action="resume-import">${importStatusCopy()}</button>` : ""}${state.wardrobeError ? `<div class="empty">${esc(state.wardrobeError)}<button class="secondary" data-action="reload">重新加载</button></div>` : `${content}${!list.length ? wardrobeEmpty() : ""}`}</section>`;
  }
  function feedCard(x) {
    return `<article class="feed-card ${x.flat ? "flat" : ""} ${x.kind === "note" ? "note-card" : ""}" ${x.kind === "note" ? `style="aspect-ratio:${x.width || 184}/${x.height || 245}"` : ""}><button class="feed-open" data-detail="${esc(x.id)}" aria-label="查看${esc(x.name)}">${image(x.src, x.name)}</button>${`<button class="feed-favorite" data-action="favorite" data-favorite-id="${esc(x.id)}" aria-label="${x.saved ? '取消收藏' : '收藏'}${esc(x.name)}" aria-pressed="${Boolean(x.saved)}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 2 3.1 6.3 6.9 1-5 4.9 1.2 6.9-6.2-3.3-6.2 3.3L7 14.2l-5-4.9 6.9-1Z"/></svg></button>`}<button class="try-chip" data-try="${esc(x.id)}">试穿</button></article>`;
  }
  function topicCard(collection) {
    return `<button class="topic-card" data-topic="${esc(collection.id)}" aria-label="查看${esc(collection.title)}合集，共${collection.entries.length}套穿搭">${image(collection.cover, "", "topic-cover")}<span class="topic-badge">#${esc(collection.title)}</span><span class="topic-previews" aria-hidden="true">${(collection.previews || []).slice(0,3).map(src=>image(src, "")).join("")}</span></button>`;
  }
  function topic() {
    const selected=(state.topics || []).find(x=>x.id===state.topicId);
    if (state.loading) return '<section class="topic-screen"><p class="empty" role="status">正在打开主题穿搭…</p></section>';
    if (!selected) return '<section class="topic-screen"><p class="empty">这个主题暂时不可用。<button class="secondary" data-page="inspiration">返回灵感库</button></p></section>';
    const hasCurvy = selected.entries.some(entry=>entry.raw?.body_profile === "curvy");
    const groups = hasCurvy ? [
      {title:"风格穿搭", entries:selected.entries.filter(entry=>entry.raw?.body_profile !== "curvy")},
      {title:"微胖穿搭", entries:selected.entries.filter(entry=>entry.raw?.body_profile === "curvy")},
    ] : [{title:"", entries:selected.entries}];
    return `<section class="topic-screen" aria-label="主题穿搭"><header><button class="back" data-page="inspiration" aria-label="返回灵感库"><svg viewBox="0 0 24 24"><path d="m15 4-7 8 7 8"/></svg></button><h1>#${esc(selected.title)}</h1></header>${groups.map(group=>`${group.title ? `<h2 class="topic-group-title">${group.title}</h2>` : ""}<div class="feed">${[0,1].map(col=>`<div class="feed-column">${group.entries.filter((_,i)=>i%2===col).map(feedCard).join('')}</div>`).join('')}</div>`).join("")}</section>`;
  }
  function inspiration() {
    if (state.loading)
      return `<section class="inspiration-screen"><p class="empty" role="status">正在整理穿搭库…</p></section>`;
    const collections = state.topics || [];
    return `<section class="inspiration-screen" aria-label="灵感库"><div class="topic-grid">${collections.map(topicCard).join("")}</div>${!collections.length ? `<div class="empty">${esc(state.topicsError || "暂时没有可用的主题穿搭。")}<button class="secondary" data-action="reload">重新加载合集</button></div>` : state.topicsError ? `<button class="secondary load-more" data-action="reload">${esc(state.topicsError)}</button>` : ""}</section>`;
  }
  function detail() {
    if (state.loading)
      return `<section class="detail-screen"><p class="empty" role="status">正在打开这套穿搭…</p></section>`;
    const x = state.current;
    if (!x) return empty("先选择一套搭配。");
    if (x.kind === "note") return `<section class="note-detail" aria-label="穿搭详情"><header><button class="back" data-action="back" aria-label="返回"><svg viewBox="0 0 24 24"><path d="m15 4-7 8 7 8"/></svg></button><h1>${esc(x.name)}</h1></header>${image(x.src,x.name,'note-detail-photo')}<div class="note-attribution">${esc(x.byline)}${x.sourceUrl ? `<a href="${esc(x.sourceUrl)}" target="_blank" rel="noopener noreferrer">查看原笔记 ↗</a>` : ''}</div></section><div class="detail-dock note-dock"><button class="secondary" data-action="favorite">${x.saved ? '取消收藏' : '收藏穿搭'}</button><button class="primary" data-action="try">立即试穿</button></div>`;
    const items = x.items || [];
    return `<section class="note-detail outfit-source-detail" aria-label="套装详情"><header><button class="back" data-action="back" aria-label="返回"><svg viewBox="0 0 24 24"><path d="m15 4-7 8 7 8"/></svg></button><h1>${esc(x.name)}</h1></header>${image(x.src,x.name,'outfit-detail-image')}<div class="outfit-detail-pieces">${items.map(i=>card(i)).join('')}</div>${x.raw?.can_delete ? '<button class="detail-remove" data-action="delete-outfit" aria-label="删除穿搭"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 10v7m4-7v7"/></svg></button>' : ''}</section><div class="detail-dock note-dock"><button class="secondary" data-action="favorite">${x.saved ? '取消收藏' : '收藏套装'}</button><button class="primary" data-action="try">立即试穿</button></div>`;
  }
  const mirrorImages = new Map();
  function mirrorLoading(message = "正在准备你的试衣镜…", failed = false) {
    return `<section class="mirror-loading" aria-label="试衣镜加载" aria-busy="${!failed}">${failed ? "" : '<span class="mirror-spinner" aria-hidden="true"></span>'}<p role="status">${esc(message)}</p>${failed ? '<button class="secondary" data-action="retry-mirror">重新加载</button>' : ""}</section>`;
  }
  function readyMirror() {
    if (reference) return mirror();
    if (state.loading) return mirrorLoading();
    if (!state.photo && (state.error || state.modelLoadFailed))
      return mirrorLoading(state.error || "模特暂时未能加载，请重试。", true);
    const src = state.result || state.photo;
    if (state.styling || !src) return mirror();
    if (!mirrorImages.has(src)) {
      mirrorImages.set(src, "loading");
      const photo = new Image();
      let settled = false;
      const finish = status => {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        mirrorImages.set(src, status);
        if (state.page === "mirror" && (state.result || state.photo) === src) render();
      };
      const timeout = setTimeout(() => finish("error"), 20000);
      photo.onload = () => photo.decode().then(() => finish("ready"), () => finish("error"));
      photo.onerror = () => finish("error");
      photo.src = mediaURL(src);
    }
    if (mirrorImages.get(src) === "error") return mirrorLoading("模特图片未能加载，请重试。", true);
    if (mirrorImages.get(src) !== "ready") return mirrorLoading("正在加载模特…");
    return mirror();
  }
  let renderedBrowseKey = "";
  let mirrorBrowsePosition = { strip: 0, categories: 0, screen: 0 };
  const profileOptions = {
    faceShape: ['椭圆脸','圆脸','方脸','心形脸','菱形脸'],
    skin: ['冷白肤','暖白肤','中性自然肤','暖黄肤','橄榄肤','小麦色'],
    bodyShape: ['梨型','倒三角型','沙漏型','矩型','苹果型'],
  };
  const profileLabels = {faceShape:'脸型',skin:'肤色',bodyShape:'身型'};
  function profileArt(field, value) {
    if(field === 'skin') return `<i class="profile-skin" style="background:${{'冷白肤':'#f5ddd0','暖白肤':'#f7dbc1','中性自然肤':'#fcd1bb','暖黄肤':'#dfb48a','橄榄肤':'#bbaa83','小麦色':'#b68c66'}[value] || '#eee'}"></i>`;
    const key = {'椭圆脸':'face-oval','圆脸':'face-round','方脸':'face-square','心形脸':'face-heart','菱形脸':'face-diamond','梨型':'body-pear','倒三角型':'body-inverted-triangle','沙漏型':'body-hourglass','矩型':'body-rectangle','苹果型':'body-apple'}[value];
    if(!key) return '<span class="profile-unknown">—</span>';
    return image(['face-oval','body-rectangle'].includes(key) ? `${A}main-app/archive-${key}.svg` : `/static/selfit/assets/manual-selection/${key}@4x.png`, '', 'profile-attribute-art');
  }
  function profileHeader(edit=false) {
    return `<header class="profile-header"><button data-page="${edit ? 'profile' : 'mirror'}" aria-label="${edit ? '返回我的档案' : '返回试衣镜'}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 5-7 7 7 7"/></svg></button><h1>${edit ? '编辑档案' : '我的档案'}</h1><span aria-hidden="true"></span></header>`;
  }
  function profilePhoto(kind, editable=false) {
    const replacing = state.profileReplacing===kind;
    const src=(editable ? state.profilePhotoDraft[kind]?.url : '') || state.profile?.photos?.[kind];
    const label=kind==='face' ? '正面照' : '全身照';
    const content=src ? image(src,label) : `<span class="profile-photo-empty">${label}<small>还未上传</small></span>`;
    // 与 onboarding 的 suit 页一致：照片本身就是替换入口，点击直接换图。
    if(editable) return `<label class="profile-photo edit-photo">${content}<span class="profile-photo-plus" aria-hidden="true">＋</span><input type="file" accept="image/*" data-profile-photo="${kind}" aria-label="更换${label}" ${state.profileSaving ? 'disabled' : ''}></label>`;
    return `<label class="profile-photo profile-photo-replace ${replacing ? 'is-replacing' : ''}" title="更换${label}">${content}${src ? '<span class="profile-photo-swap" aria-hidden="true">＋</span>' : ''}<input type="file" accept="image/*" data-profile-photo="${kind}" aria-label="更换${label}" ${replacing ? 'disabled' : ''}></label>`;
  }
  function profileStatus(edit=false) {
    return `<section class="profile-screen">${profileHeader(edit)}<div class="profile-status" role="status">${state.profileError ? `<p>${esc(state.profileError)}</p>${!savedSession?.accessToken && !reference ? '<a href="/selfit?entry=login">去登录</a>' : '<button data-action="reload-profile">重新加载</button>'}` : '<p>正在整理你的档案…</p>'}</div></section>`;
  }
  // 从档案特征卡进入编辑时记录的滚动位置，返回档案页后恢复原位而不是回到顶部。
  let profileReturnScroll = null;
  function profile() {
    if(!state.profile || state.profileLoading) return profileStatus();
    const p=state.profile,r=p.report;
    return `<section class="profile-screen">${profileHeader()}${p.tested ? `<div class="profile-analysis profile-suit"><div class="profile-suit-photos">${profilePhoto('face')}${profilePhoto('body')}</div><div class="profile-suit-cards" data-selfit-suit-cards aria-label="身体特征分析"></div></div>` : ''}${r ? `<div class="profile-report-card"><a class="profile-report" href="/selfit?from=mirror&amp;report=latest&amp;return_screen=profile" aria-label="查看我的风格报告">${r.heroImage?.src ? image(r.heroImage.src,r.title || '我的风格报告') : `<strong>${esc(r.typeId?.toUpperCase())}<br>${esc(r.title || '我的风格报告')}</strong>`}</a><a class="profile-retest" href="/selfit?from=mirror&amp;entry=retest">重新测试 →</a></div>` : `<a class="profile-test-invite" href="/selfit?from=mirror">${image(`${A}main-app/profile-test-pin.svg`, "", "profile-test-pin")}<strong>selfit 16 型格测试</strong>${image(`${A}main-app/profile-test-art.svg`, 'suit · like · vibe')}<span>去测试 →</span></a>`}<section class="profile-more"><h2>更多测试</h2><div><button disabled>${image(`${A}main-app/archive-more-mirror.webp`, "")}<span>专业脸型风格<small>即将开放</small></span></button><button disabled>${image(`${A}main-app/archive-more-flower.webp`, "")}<span>十二季肤色<small>即将开放</small></span></button></div></section>${!reference && typeof savedSession !== "undefined" && savedSession?.user && !String(savedSession.user.user_id || "").startsWith?.('guest_') && !savedSession.user.phone_e164 ? '<button class="profile-bind-phone" data-action="bind-phone">绑定手机号，换设备不丢数据</button>' : ''}${!reference ? '<button class="profile-logout" data-action="logout">退出登录</button>' : ''}</section>`;
  }
  function profileFeatureEdit() {
    const field = state.profileEditingField;
    const values = field === 'faceShape' ? ['菱形脸','方脸','圆脸','椭圆脸','心形脸'] : field === 'skin' ? ['冷白肤','暖白肤','中性自然肤','橄榄肤','暖黄肤','小麦色'] : profileOptions[field];
    const assetKeys = {'菱形脸':'face-diamond','方脸':'face-square','圆脸':'face-round','椭圆脸':'face-oval','心形脸':'face-heart','梨型':'body-pear','倒三角型':'body-inverted-triangle','沙漏型':'body-hourglass','矩型':'body-rectangle','苹果型':'body-apple'};
    const colors = {'冷白肤':'#FFDED7','暖白肤':'#FCD1BB','中性自然肤':'#F2C9B8','橄榄肤':'#E6D3AF','暖黄肤':'#E6BEAA','小麦色':'#CB956C'};
    return `<section class="profile-screen profile-feature-screen"><header class="profile-header"><button data-action="cancel-profile-feature" aria-label="返回我的档案"><svg viewBox="0 0 24 24"><path d="m15 5-7 7 7 7"/></svg></button><h1>修改${profileLabels[field]}</h1></header><div class="profile-feature-content"><h2>${profileLabels[field]}</h2><div class="profile-feature-options" data-kind="${field}" role="group" aria-label="选择${profileLabels[field]}">${values.map(value=>`<button data-profile-choice="${value}" aria-pressed="${state.profileFeatureValue===value}"><span class="profile-feature-art">${field==='skin'?`<i style="background:${colors[value]}"></i>`:image('/static/selfit/assets/manual-selection/'+assetKeys[value]+'@4x.png',value+'示意')}</span><span>${esc(value)}</span></button>`).join('')}</div></div><button class="primary profile-save" data-action="confirm-profile-feature" ${state.profileFeatureValue?'':'disabled'}>保存修改</button></section>`;
  }
  function profileEdit() {
    if(!state.profile || state.profileLoading) return profileStatus(true);
    if(!state.profile.tested) return profile();
    const draft=state.profileDraft || state.profile.manual;
    if (state.profileEditingField) return profileFeatureEdit();
    return `<section class="profile-screen profile-edit-screen">${profileHeader(true)}<div class="profile-edit-photos">${profilePhoto('face',true)}${profilePhoto('body',true)}</div><div class="profile-edit-fields"><p class="profile-edit-hint">点击下方信息，修改你的档案</p>${Object.keys(profileOptions).map(field=>`<button type="button" class="profile-field-row" data-profile-edit="${field}" aria-label="修改${profileLabels[field]}" ${state.profileSaving ? 'disabled' : ''}><span class="profile-field-label">${profileLabels[field]}</span><strong class="profile-field-value">${esc(draft[field] || '请选择')}</strong>${profileArt(field,draft[field])}<svg class="profile-field-chevron" viewBox="0 0 24 24" aria-hidden="true"><path d="m9 5 7 7-7 7"/></svg></button>`).join('')}</div>${state.profileError ? `<p class="profile-save-error" role="alert">${esc(state.profileError)}</p>` : ''}<button class="primary profile-save" data-action="save-profile" ${state.profileSaving ? 'disabled' : ''}>${state.profileSaving ? '正在保存…' : '保存修改'}</button></section>`;
  }
  const REFERENCE_PROFILE_SUIT = {
    photos: {face: true, body: true},
    analyses: {
      face: {kind: 'face', attributes: {
        skin: {label: '中性自然肤', status: 'warn', confidence: 0.72, metrics: [
          {key: 'lStar', label: '肤色明度 L*', value: '63.8'},
          {key: 'ita', label: '白皙度 ITA', value: '45.3°'},
          {key: 'undertone', label: '肤色底调', value: '中性'},
        ], notes: []},
        faceShape: {label: '椭圆脸', status: 'pass', confidence: 0.86, metrics: [
          {key: 'lengthWidth', label: '脸长 / 脸宽', value: '1.074'},
          {key: 'jawCheek', label: '下颌宽 / 颧骨宽', value: '0.787'},
          {key: 'foreheadCheek', label: '额头宽 / 颧骨宽', value: '0.98'},
        ], notes: []},
      }, notes: []},
      body: {kind: 'body', attributes: {
        bodyShape: {label: '矩型', status: 'pass', confidence: 0.78, metrics: [
          {key: 'hipShoulder', label: '胯宽 / 肩宽', value: '0.94'},
          {key: 'waistHip', label: '腰宽 / 胯宽', value: '0.87'},
        ], notes: []},
      }, notes: []},
    },
    features: [
      {key: 'skin', title: '肤色', value: '中性自然肤', source: 'photo', description: '肤色明度自然，冷暖倾向较平衡。', advice: '从柔和中性色开始，比较不同配色在自然光下的效果。'},
      {key: 'faceShape', title: '脸型', value: '椭圆脸', source: 'photo', description: '额头与颧骨宽度接近，下颌收窄，轮廓连接较圆润。', advice: '领口选择比较灵活，可以从方领、V 领试起。'},
      {key: 'bodyShape', title: '身材比例', value: '矩型', source: 'photo', description: '肩、腰、胯的宽度变化较小。', advice: '用腰线、叠穿和不同材质增加轮廓层次。'},
    ],
  };
  async function loadProfile(force=false) {
    if(state.profileLoading || (state.profile && !force)) return;
    state.profileLoading=true;state.profileError='';
    if(reference) {
      state.profile={tested:true,revision:1,manual:{faceShape:'椭圆脸',skin:'中性自然肤',bodyShape:'矩型'},photos:{face:`${A}main-app/archive-face-reference.svg`,body:`${A}main-app/archive-body-reference.svg`},report:{reportId:'reference',typeId:'flou',title:'造梦浪漫',heroImage:{src:'/static/selfit/assets/personality/flou/hero.png?v=20260907-config-v2'}},suit:REFERENCE_PROFILE_SUIT};
      if(params.get('profile_state')==='untested') state.profile={tested:false,manual:{},photos:{},report:null,revision:1};
      if(params.get('profile_state')==='no-photo') state.profile.photos={face:null,body:null};
      state.profileSuit=state.profile.suit || null;
      state.profileLoading=false;render();return;
    }
    try {
      if(!savedSession?.accessToken) throw new Error('登录后，查看你的个人档案。');
      const {profile:p}=await api('/api/v1/selfit/me/profile');
      for(const kind of ['face','body']) if(p.photos[kind]) {
        const response=await fetch(p.photos[kind],{headers:{Authorization:`Bearer ${savedSession.accessToken}`}});
        if(response.ok && response.status!==204) { const url=URL.createObjectURL(await response.blob());state.uploadURLs.push(url);p.photos[kind]=url; }
        else if(response.status===204 || response.status===404) p.photos[kind]=null;
        else throw new Error('照片暂时无法加载，请重试。');
      }
      state.profile=p;
      state.profileSuit=p.suit || null;
    } catch(e) { state.profileError=e.message; }
    finally {state.profileLoading=false;if(['profile','profile-edit'].includes(state.page)) render();}
  }
  async function uploadProfilePhoto(kind, file, previewUrl) {
    if(reference) { state.profile.photos[kind]=previewUrl; return; }
    const {session}=await api('/api/v1/selfit/sessions',{method:'POST',body:JSON.stringify({schemaVersion:'selfit-onboarding-v1',locale:'zh-CN'})});
    const form=new FormData();form.append('image',file);
    const result=await api(`/api/v1/selfit/sessions/${encodeURIComponent(session.sessionId)}/photos/${kind}`,{method:'POST',body:form});
    if(result.photo?.status!=='accepted') throw new Error(result.photo?.message || '照片不合适，请换一张。');
    if(kind==='body') {
      const modelForm=new FormData();modelForm.append('image',file);
      await api('/closet/preferences/model-photo',{method:'POST',body:modelForm});
      state.personalPhoto=previewUrl;state.personalFile=file;
      if(state.modelId==='self') {state.photo=previewUrl;state.file=file;state.result='';}
    }
  }
  async function replaceProfilePhoto(kind, file) {
    if(state.profileReplacing || !state.profile?.tested) return;
    const url=URL.createObjectURL(file);
    state.uploadURLs.push(url);
    state.profileReplacing=kind;
    render();notify('正在更换照片…');
    try {
      const photo=new Image();photo.src=url;await photo.decode();
      if(kind==='body' && (photo.naturalWidth<240 || photo.naturalHeight<320)) throw new Error('全身照分辨率偏低，请选择更清晰的照片。');
      await uploadProfilePhoto(kind, file, url);
      if(!reference) await loadProfile(true); else {state.profile.photos[kind]=url;render();}
      notify('照片已更新');
    } catch(e) { notify(e.message || '照片暂时无法更换，请重试。'); }
    finally { state.profileReplacing='';if(['profile','profile-edit'].includes(state.page)) render(); }
  }
  async function saveProfile() {
    if(state.profileSaving || !state.profile?.tested) return;
    const manual=Object.fromEntries(Object.entries(state.profileDraft || state.profile.manual).filter(([,v])=>v));
    if(!Object.keys(manual).length) {state.profileError='请至少选择一项档案信息。';render();return;}
    if(reference) {state.profile.manual=manual;Object.entries(state.profilePhotoDraft).forEach(([k,v])=>state.profile.photos[k]=v.url);state.profilePhotoDraft={};go('profile');notify('已更新预览档案');return;}
    state.profileSaving=true;state.profileError='';render();
    try {
      for(const [kind,entry] of Object.entries(state.profilePhotoDraft)) {
        await uploadProfilePhoto(kind, entry.file, entry.url);
        state.profile.photos[kind]=entry.url;
        delete state.profilePhotoDraft[kind];
      }
      const saved=await api('/api/v1/selfit/me/profile',{method:'PATCH',headers:{'If-Match':String(state.profile.revision)},body:JSON.stringify({reportId:state.profile.report.reportId,manual})});
      state.profile={...saved.profile,photos:state.profile.photos};state.profileSuit=saved.profile.suit || null;state.profileDraft=null;go('profile');notify('档案已保存');
    } catch(e) {state.profileError=e.status===409 ? '档案已更新，请返回档案页重新加载，再保存修改。' : e.message;}
    finally {state.profileSaving=false;render();}
  }

  function restoreTryonRecord(record) {
    state.viewerPhoto = false;
    state.result = record.image_path;
    state.resultOriginal = record.original_image_path || "";
    state.current = lookup(record.note_id || record.outfit_id) || null;
    state.viewRecordId = record.record_id;
    state.job = null;
    state.styling = false;
  }
  async function restoreHistoryRoute(recordId) {
    const request = state.viewerRequest = (state.viewerRequest || 0) + 1;
    state.viewerLoading = true;
    state.viewerError = "";
    state.viewRecordId = recordId;
    render();
    try {
      const data = await api("/closet/tryon-records");
      if (request !== state.viewerRequest || state.page !== "result-viewer") return;
      const record = (data.records || []).find(row => row.record_id === recordId);
      if (!record) throw new Error("这条试穿记录已不存在，请返回历史记录重新选择。");
      restoreTryonRecord(record);
    } catch (error) {
      if (request !== state.viewerRequest || state.page !== "result-viewer") return;
      state.result = "";
      state.resultOriginal = "";
      state.current = null;
      state.job = null;
      state.viewerError = error.message || "试穿记录暂时无法打开，请重试。";
    } finally {
      if (request === state.viewerRequest && state.page === "result-viewer") {
        state.viewerLoading = false;
        render();
      }
    }
  }
  function tryonHistory() {
    const header = `<header class="history-header"><button data-page="mirror" aria-label="返回试衣镜"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 4-8 8 8 8"/></svg></button><h1 id="historyTitle">试穿历史</h1></header>`;
    let content;
    if (state.historyLoading) content = '<div class="history-empty" role="status">正在加载试穿历史…</div>';
    else if (state.historyError) content = `<div class="history-empty" role="status"><p>${esc(state.historyError)}</p><button class="secondary" data-action="reload-tryon-history">重新加载</button></div>`;
    else if (!state.historyRecords.length) content = '<div class="history-empty"><p>还没有试穿历史</p><span>完成一次试穿，就能在这里找回结果。</span><button class="secondary" data-page="mirror">去试穿</button></div>';
    else content = `<div class="tryon-history">${state.historyRecords.map(row => {
      const date = new Date(row.created_at || NaN);
      const dateLabel = Number.isNaN(date.getTime()) ? '' : `${date.getFullYear()}/${date.getMonth()+1}/${date.getDate()}`;
      const title = row.outfit_title || '试穿结果';
      return `<button class="history-card" data-record="${esc(row.record_id)}" aria-label="查看${esc(title)}${dateLabel ? '，'+dateLabel : ''}">${image(row.image_path,title)}${dateLabel ? `<time datetime="${esc(row.created_at)}">${dateLabel}</time>` : '<span></span>'}</button>`;
    }).join('')}</div>`;
    return `<section class="history-screen" aria-labelledby="historyTitle">${header}${content}</section>`;
  }
  async function loadTryonHistory() {
    const request = ++state.historyRequest;
    state.historyLoading = true;
    state.historyError = '';
    render();
    try {
      if (!reference) await ensureVisitorSession();
      const data = reference ? {records:[]} : await api('/closet/tryon-records');
      if (request !== state.historyRequest || state.page !== 'tryon-history') return;
      state.historyRecords = data.records || [];
    } catch {
      if (request !== state.historyRequest || state.page !== 'tryon-history') return;
      state.historyError = '试穿历史暂时无法加载，请稍后重试。';
    } finally {
      if (request === state.historyRequest && state.page === 'tryon-history') {
        state.historyLoading = false;
        render();
      }
    }
  }
  function resultViewer() {
    const returnLabel = state.viewerReturnPage === "tryon-history" ? "返回试穿历史" : "返回试衣镜";
    const back = `<button class="secondary" data-action="close-viewer">${returnLabel}</button>`;
    if (state.viewerLoading) return `<section class="result-viewer"><p class="empty" role="status">正在打开试穿记录…</p>${back}</section>`;
    if (state.viewerError) return `<section class="result-viewer"><p class="empty">${esc(state.viewerError)}</p><button class="secondary" data-action="retry-history-viewer">重新加载</button>${back}</section>`;
    const src=state.viewerPhoto ? state.photo : state.result;
    if (!src && !reference && (state.loading || (state.job?.job_id && !["completed","failed"].includes(state.job.status))))
      return `<section class="result-viewer"><p class="empty" role="status">正在准备试穿大图…</p>${back}</section>`;
    if (!src && !reference) return `<section class="result-viewer"><p class="empty">还没有可查看的试穿图。${back}</p></section>`;
    if (!reference || state.file) return `<section class="result-viewer is-photo" aria-label="试穿大图">${image(`${A}main-app/mirror-background.svg`,'','result-viewer-background')}<div class="result-viewer-photo-area">${image(src,state.viewerPhoto ? '当前模特大图' : '试穿结果大图','result-viewer-photo')}</div><button class="viewer-collapse" data-action="close-viewer" aria-label="收起大图，${returnLabel}">${image(`${A}main-app/result-viewer-collapse.svg`,'')}<span>收起大图</span></button></section>`;
    return `<section class="result-viewer" aria-label="试穿大图">${image(`${A}main-app/result-viewer-background.svg`,'','result-viewer-background')}${reference && !state.file ? image(`${A}main-app/result-viewer-model.svg`,state.viewerPhoto ? '当前模特大图' : '原稿试穿示例','result-viewer-reference') : image(src,state.viewerPhoto ? '当前模特大图' : '试穿结果大图','result-viewer-photo')}<button class="viewer-collapse" data-action="close-viewer" aria-label="收起大图，${returnLabel}">${image(`${A}main-app/result-viewer-collapse.svg`,'')}</button></section>`;
  }
  function importReview() {
    if (!reference && state.error) return `<section class="import-review">${empty(state.error)}</section>`;
    if (state.loading) return `<section class="import-review"><p class="empty" role="status">正在打开上传确认…</p></section>`;
    return `<section class="note-detail import-review" aria-label="确认上传"><header><button class="back" data-action="leave-import" aria-label="返回衣帽间"><svg viewBox="0 0 24 24"><path d="m15 4-7 8 7 8"/></svg></button><h1>确认上传</h1></header>${state.importPhoto ? image(state.importPhoto,'上传的穿搭照片','import-review-photo') : ''}<p class="import-review-copy">已识别 ${state.importItems.length} 件单品，选中 ${state.importSelection.size} 件。确认后才会加入衣帽间；未识别的衣物可以补拍单品图。</p><div class="import-review-pieces">${state.importItems.map(i=>`<button class="import-choice" data-import-piece="${esc(i.id)}" aria-label="${esc(i.name)}" aria-pressed="${state.importSelection.has(i.id)}" ${state.importSaving ? 'disabled' : ''}>${image(i.src,i.name)}${i.approximate ? '<small class="import-approximate">遮挡部分已补全，请核对</small>' : ""}<span aria-hidden="true">${state.importSelection.has(i.id) ? '✓' : ''}</span></button>`).join('')}</div>${!state.importItems.length ? '<p class="empty">暂未识别出可添加的单品，请换一张清晰的穿搭照片。</p>' : ''}${state.importError ? `<p class="import-review-error" role="alert">${esc(state.importError)}</p>` : ''}</section><div class="detail-dock note-dock"><button class="secondary" data-action="upload-garment" ${state.importSaving ? 'disabled' : ''}>重新上传</button><button class="primary" data-action="confirm-import" ${state.importSaving || !state.importSelection.size ? 'disabled' : ''}>${state.importSaving ? '正在添加…' : `确认添加（${state.importSelection.size}）`}</button></div>`;
  }
  function rememberImport() {
    if (!reference && importJob?.job_id) sessionStorage.setItem('selfit.studio.import',JSON.stringify({job_id:importJob.job_id,status:importJob.status,selected:[...state.importSelection],reviewed:state.importReviewJobId===importJob.job_id}));
  }
  async function confirmImport() {
    if (state.importSaving || !state.importSelection.size) return;
    state.importSaving=true; state.importError=''; render();
    try {
      if (reference) {
        state.items=uniqueItems([...state.items,...state.importItems.filter(i=>state.importSelection.has(i.id))]);
      } else {
        if (!importJob?.job_id) throw Error('这次上传暂时无法恢复，请重新上传。');
        const committed=await api(`/closet/import/jobs/${encodeURIComponent(importJob.job_id)}/confirm`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({selected_item_ids:[...state.importSelection]})});
        state.items=uniqueItems([...state.items,...(committed.result?.items || []).map(normalizeItem)]);
        state.outfits=uniqueItems([...state.outfits,...(committed.result?.outfits || []).map(x=>normalizeOutfit(x,state.items))]);
        sessionStorage.removeItem('selfit.studio.import'); importJob=null;
      }
      state.closetCategory='all'; go('closet'); notify(reference ? '已添加到本次设计预览。' : '所选单品已加入衣帽间。');
    } catch(e) {state.importError=e.message;}
    finally {state.importSaving=false;render();}
  }
  function render() {
    wardrobeGestures.reset();
    const detailScroll = state.page === "detail" && $("#studio").dataset.screen === "detail" ? $(".note-detail")?.scrollTop : null;
    const keepWardrobePosition = state.page === 'closet' && $('#studio').dataset.screen === 'closet';
    const wardrobePosition = keepWardrobePosition ? {screen:$('#screen').scrollTop, rows:Array.from(document.querySelectorAll('.wardrobe-group'), group => [group.getAttribute('aria-labelledby'), group.querySelector('.wardrobe-items-row').scrollLeft])} : null;
    const browseKey = JSON.stringify([state.page, state.source, state.category]);
    const keepPosition = state.page === "mirror" && browseKey === renderedBrowseKey;
    if (!keepPosition) mirrorBrowsePosition = { strip: 0, categories: 0, screen: 0 };
    else if ($(".strip")) mirrorBrowsePosition = {
      strip: $(".strip").scrollLeft,
      categories: $(".categories")?.scrollLeft || 0,
      screen: $("#screen").scrollTop,
    };
    if (reference) $("#studio").setAttribute("data-reference", "true");
    nav();
    $("#completionNotice").hidden = !state.completedTryon && !(reference && params.get("notice") === "success" && state.page === "inspiration");
    $("#screen").innerHTML = { mirror: readyMirror, closet, inspiration, topic, builder: outfitBuilder, detail, chat, profile, "profile-edit": profileEdit, "import-review": importReview, "result-viewer": resultViewer, "tryon-history": tryonHistory }[
      state.page
    ]();
    $("#studio").dataset.screen = state.page;
    $("#studio").dataset.mode = state.styling ? "styling" : "model";
    if (detailScroll != null && $(".note-detail")) $(".note-detail").scrollTop = detailScroll;
    // 我的档案顶部的 suit 特征卡：共享组件渲染，分析参数默认全部展开；
    // 照片直接点击替换（与 onboarding suit 页一致），特征值通过卡片上的「修改」进入单字段编辑。
    const suitHost = document.querySelector('[data-selfit-suit-cards]');
    if (suitHost && window.SelfitSuitCards) {
      const suit = state.profileSuit;
      const manual = state.profile?.manual || {};
      const features = suit?.features?.length ? suit.features : [
        {key:'skin',title:'肤色',value:manual.skin,source:manual.skin?'manual':'unknown'},
        {key:'faceShape',title:'脸型',value:manual.faceShape,source:manual.faceShape?'manual':'unknown'},
        {key:'bodyShape',title:'身材比例',value:manual.bodyShape,source:manual.bodyShape?'manual':'unknown'},
      ];
      window.SelfitSuitCards.render(suitHost, {features, analyses:(suit && suit.analyses) || {}, photos:(suit && suit.photos) || {}, onEdit:(key)=>{
        // 记录离开档案页时的滚动位置，保存/取消返回后恢复原位而不是回到顶部。
        profileReturnScroll=$("#screen").scrollTop;
        state.profileDraft={...(state.profileDraft || state.profile.manual)};
        state.profilePhotoDraft={};
        state.profileEditingField=key;
        state.profileFeatureValue=state.profileDraft[key] || '';
        go('profile-edit');
      }});
    }
    if (wardrobePosition) {
      const positions = new Map(wardrobePosition.rows);
      document.querySelectorAll('.wardrobe-group').forEach(group => { group.querySelector('.wardrobe-items-row').scrollLeft = positions.get(group.getAttribute('aria-labelledby')) || 0; });
      $('#screen').scrollTop = wardrobePosition.screen;
    }
    $("#addGarmentFloating").hidden = true;
    const mirrorPhoto = $(".mirror-photo-frame .model-photo");
    if (mirrorPhoto) window.SelfitMirrorPhoto.show(mirrorPhoto, mirrorPhoto.getAttribute("src"));
    const viewerPhoto = $(".result-viewer-photo-area .result-viewer-photo");
    if (viewerPhoto) window.SelfitMirrorPhoto.show(viewerPhoto, viewerPhoto.getAttribute("src"), {fit:"contain"});
    // Image preparation can render again after selection; keep the same browsing context still.
    if (keepPosition) {
      if ($(".strip")) $(".strip").scrollLeft = mirrorBrowsePosition.strip;
      if ($(".categories")) $(".categories").scrollLeft = mirrorBrowsePosition.categories;
      $("#screen").scrollTop = mirrorBrowsePosition.screen;
    }
    const strip = $(".mirror-screen .strip");
    if (strip) {
      const updatePage = () => {
        const first = strip.querySelector('.card');
        if (!first) return;
        const count = document.querySelectorAll('[data-strip-page]').length;
        const page = Math.round(strip.scrollLeft / Math.max(1,strip.scrollWidth-strip.clientWidth) * Math.max(0,count-1));
        document.querySelectorAll('[data-strip-page]').forEach(dot => dot.dataset.active=String(Number(dot.dataset.stripPage)===page));
      };
      strip.addEventListener('scroll', updatePage, {passive:true});
      strip.addEventListener('focusin', (event) => {
        const card = event.target.closest('.card');
        if (!card) return;
        const viewport = strip.getBoundingClientRect();
        const bounds = card.getBoundingClientRect();
        if (bounds.right > viewport.right) strip.scrollLeft += bounds.right - viewport.right + 17;
        else if (bounds.left < viewport.left) strip.scrollLeft -= viewport.left - bounds.left + 17;
      });
      updatePage();
    }
    if (state.result && (state.resultOriginal || reference) && $(".model-photo")) {
      const photo=$(".model-photo"); photo.dataset.action="compare"; photo.tabIndex=0;
      photo.setAttribute("role","button"); photo.setAttribute("aria-label","按住查看原图，松开查看试穿效果");
    }
    renderedBrowseKey = browseKey;
  }
  let mirrorTurning = false;
  async function turnMirror() {
    if (mirrorTurning || state.page !== 'mirror') return;
    mirrorTurning = true;
    const studio = $('#studio');
    const top = $('#screen').scrollTop;
    const motion = !matchMedia('(prefers-reduced-motion: reduce)').matches;
    try {
      if (motion) {
        studio.dataset.mirrorTurn = 'out';
        await new Promise(resolve => setTimeout(resolve, 230));
      }
      if (state.page !== 'mirror') return;
      state.styling = !state.styling;
      state.selected = new Set((state.current?.items || []).map(item => item.id));
      if (motion) studio.dataset.mirrorTurn = 'in';
      go('mirror', true, false);
      $('#screen').scrollTop = top;
      if (motion) await new Promise(resolve => setTimeout(resolve, 310));
    } finally {
      delete studio.dataset.mirrorTurn;
      mirrorTurning = false;
    }
  }

  function go(page, push = true, acceptCompleted = true) {
    if (state.page === 'builder' && page !== 'builder') {
      state.builderRequest++; state.builderMatching=false;
    }
    if (page !== "profile-edit") state.profileEditingField=null;
    if (page !== "result-viewer") {
      state.viewerJobId = "";
      state.viewerRequest = (state.viewerRequest || 0) + 1;
      state.viewerLoading = false;
      state.viewerError = "";
    }
    if(page === 'profile' && state.page === 'profile-edit' && !state.profileSaving) {state.profileDraft=null;state.profilePhotoDraft={};}
    if(page === 'profile' && state.page === 'profile-edit' && state.profileError) {state.profile=null;state.profileError='';}
    if (page === "mirror" && acceptCompleted && state.completedTryon) {
      const completed=state.completedTryon;
      state.result=completed.src;state.current=completed.outfit;state.resultOriginal=completed.original;
      state.photo=completed.original || state.photo;state.styling=false;state.job=completed.job;
      state.viewRecordId="";state.completedTryon=null;
    }
    if (state.current && state.source === "report" && !state.current.reportNote)
      state.source = "inspiration";
    state.page = page;
    if (page === "tryon-history") state.historyLoading = true;
    else state.historyRequest++;
    render();
    if(page === "tryon-history") loadTryonHistory();
    if(page === "chat") loadChat();
    if(["profile","profile-edit"].includes(page)) loadProfile();
    $("#screen").scrollTop = 0;
    // 从特征编辑返回档案页时恢复进入编辑前的滚动位置。
    if (page === "profile" && profileReturnScroll != null) { $("#screen").scrollTop = profileReturnScroll; profileReturnScroll = null; }
    if (push) {
      const u = new URL(location.href);
      u.searchParams.set("screen", page);
      if (page === "result-viewer" && state.viewerReturnPage === "tryon-history") u.searchParams.set("viewer_from", "history"); else u.searchParams.delete("viewer_from");
      if (state.source && state.source !== "report") u.searchParams.delete("report_notes");
      if ((page === "topic" || (page === "detail" && state.returnPage === "topic")) && state.topicId) u.searchParams.set("topic",state.topicId); else u.searchParams.delete("topic");
      if (page === "result-viewer" && state.viewerPhoto) u.searchParams.set("preview","photo"); else u.searchParams.delete("preview");
      if (page === "result-viewer" && !state.viewerPhoto && state.viewRecordId) u.searchParams.set("record",state.viewRecordId); else u.searchParams.delete("record");
      if (page === "result-viewer" && !state.viewerPhoto && state.job?.job_id) u.searchParams.set("job",state.job.job_id);
      else u.searchParams.delete("job");
      if (state.current?.id && !reference && !["import-review","result-viewer"].includes(page))
        u.searchParams.set("outfit", state.current.id);
      else u.searchParams.delete("outfit");
      if (state.styling) u.searchParams.set("mode", "styling");
      else u.searchParams.delete("mode");
      history.pushState({ page }, "", u);
    }
  }
  function categoryGroup(c) {
    return ["outer"].includes(c)
      ? "top"
      : ["skirt"].includes(c)
        ? "bottom"
        : ["bag", "scarf", "socks"].includes(c)
          ? "accessory"
          : c;
  }
  function uniqueItems(items) {
    return [
      ...new Map(items.filter((x) => x.id).map((x) => [x.id, x])).values(),
    ];
  }
  function lookup(id) {
    return [
      ...(state.homeOutfits || []),
      ...(state.reportOutfits || []),
      ...state.feed,
      ...(state.topics || []).flatMap(x=>x.entries),
      ...state.savedNotes,
      ...state.outfits,
      ...state.items,
      ...state.feed.flatMap((x) => x.items),
      ...(state.reportOutfits || []).flatMap((x) => x.items),
      ...(state.homeOutfits || []).flatMap((x) => x.items),
      ...(state.current?.items || []),
    ].find((x) => x.id === id);
  }
  function updateWardrobeBusy() {
    document.querySelectorAll('[data-wardrobe-card]').forEach(card => {
      const busy = card.dataset.wardrobeCard === state.wardrobeDeleting;
      card.setAttribute('aria-busy', String(busy));
      card.querySelectorAll('button').forEach(button => {
        button.disabled = button.dataset.action === 'delete-item' ? Boolean(state.wardrobeDeleting) : busy;
      });
    });
  }
  async function deleteWardrobeItem(id) {
    if (state.wardrobeDeleting || !state.items.some(item => item.id === id)) return;
    state.wardrobeDeleting = id;
    updateWardrobeBusy();
    let deleted = false, refreshed = true;
    try {
      if (!reference) await api(`/closet/items/${encodeURIComponent(id)}`, {method:'DELETE'});
      deleted = true;
      state.items = state.items.filter(item => item.id !== id);
      state.outfits = state.outfits.map(outfit => ({...outfit, items:(outfit.items || []).filter(item => item.id !== id)})).filter(outfit => outfit.items.length);
      if (state.current?.items?.some(item => item.id === id)) {
        state.current = {...state.current, id:'', items:state.current.items.filter(item => item.id !== id)};
        state.result = '';
      }
      state.selected.delete(id);
      state.builderIds?.delete(id);
      state.canvasHistory = []; state.canvasFuture = []; state.canvasSelection = '';
      if (!reference) {
        try {
          const wardrobe = await api('/selfit/try-on/wardrobe');
          state.items = (wardrobe.items || []).map(normalizeItem);
          state.outfits = (wardrobe.outfits || []).map(outfit => normalizeOutfit(outfit, state.items));
          state.wardrobeError = '';
        } catch { refreshed = false; }
      }
    } catch {
      notify('删除失败，请重试');
    } finally {
      state.wardrobeDeleting = '';
      if (deleted) {
        const restoreFocus = document.activeElement?.closest('[data-wardrobe-card]')?.dataset.wardrobeCard === id;
        render();
        if (restoreFocus) ($('[data-wardrobe-hold]') || $('.wardrobe-add'))?.focus({preventScroll:true});
        notify(refreshed ? '已删除单品' : '单品已删除，搭配更新暂未加载，请稍后刷新。');
      } else updateWardrobeBusy();
    }
  }
  async function generateForItem(id) {
    if (state.builderMatching || state.builderSaving) return;
    const anchor = state.items.find(item=>item.id===id);
    if (!anchor) return;
    const request = ++state.builderRequest;
    state.builderAnchor=anchor; state.builderMatching=true; state.builderMatchError=''; state.builderMatch=null;
    state.builderMatches=[]; state.builderMatchIndex=0;
    state.builderItems=[]; state.builderIds=new Set([id]); state.builderError='';
    $("#sheet").close(); go('builder');
    const started=Date.now();
    try {
      if (reference) throw Error('请在衣帽间上传自己的单品，再让搭配助手为你挑选。');
      const result=await api(`/selfit/try-on/items/${encodeURIComponent(id)}/outfits`,{method:'POST'},260000);
      const entries=(result.outfits || []).map((outfit,index)=>({outfit, match:(result.matches || [])[index]}))
        .filter(entry=>entry.match && (entry.outfit.items || []).length>=2 && entry.outfit.items.some(item=>item.item_id===id));
      if (request!==state.builderRequest || state.page!=='builder') return;
      if (!entries.length) throw Error('搭配结果暂时不完整，请再试一次。');
      state.builderMatches=entries;
      selectBuilderMatch(0);
    } catch (error) {
      if (request===state.builderRequest && state.page==='builder') state.builderMatchError=error.message || '这次没有完成搭配，请再试一次。';
    } finally {
      const remain=(state.builderMatchMinMs ?? 3000)-(Date.now()-started);
      if (remain>0) await new Promise(resolve=>setTimeout(resolve,remain));
      if (request===state.builderRequest && state.page==='builder') {state.builderMatching=false;render();}
    }
  }
  function selectBuilderMatch(index) {
    const entry=(state.builderMatches || [])[index];
    if (!entry) return;
    state.builderMatchIndex=index;
    const items=(entry.outfit.items || []).map(normalizeItem);
    state.builderItems=items; state.builderIds=new Set(items.map(item=>item.id));
    state.builderMatch=entry.match; state.builderError='';
  }
  function builderCatalog() {
    return uniqueItems([...(state.builderItems || []), ...state.items]);
  }
  function outfitBuilder() {
    const selected = state.builderIds || new Set();
    const catalog=builderCatalog();
    const chosen=[...selected].map(id=>catalog.find(item=>item.id===id)).filter(Boolean);
    const header='<header><button class="back" data-page="closet" aria-label="返回衣帽间">‹</button><h1>单品搭配</h1></header>';
    if(state.builderMatching || state.builderMatchError) return `<section class="outfit-builder" aria-label="单品搭配">${header}<div class="builder-match-state">${state.builderAnchor?image(state.builderAnchor.src,state.builderAnchor.name):''}${state.builderMatching?'<span class="builder-match-spinner" aria-hidden="true"></span><h2 role="status">正在从笔记库挑选搭配…</h2><p>结合单品特点与套装描述，寻找适合你的组合。</p>':`<p role="alert">${esc(state.builderMatchError)}</p><button class="primary" data-action="retry-item-match">重新搭配</button>`}</div></section>`;
    const anchor=state.builderAnchor;
    const anchorFigure=anchor?`<figure class="builder-anchor">${image(anchor.src,anchor.name)}<figcaption>${esc(anchor.name)}</figcaption></figure>`:'';
    const match=state.builderMatch;
    const note=match?`<aside class="builder-match-note" aria-label="搭配推荐理由"><div>${image(match.image_url,'参考笔记中的原始穿搭')}<div><span>参考笔记</span><strong>${esc(match.title)}</strong><span>已换入你的${esc(anchor?.name || '单品')}</span></div></div><p>${esc(match.reason)}</p></aside>`:'';
    const matches=state.builderMatches || [];
    const notes=matches.length?`<h2>为你挑选的搭配笔记</h2><div class="builder-notes" role="listbox" aria-label="匹配的搭配笔记">${matches.map((entry,index)=>{const m=entry.match;return `<button class="builder-note-card" data-builder-match="${index}" role="option" aria-selected="${index===state.builderMatchIndex}" aria-label="${esc(m.title)}" ${state.builderSaving?'disabled':''}>${image(m.image_url,m.title)}<span class="builder-note-name">${esc(m.title)}</span><i aria-hidden="true">✓</i></button>`;}).join('')}</div>`:'';
    return `<section class="outfit-builder" aria-label="单品搭配">${header}${anchorFigure}${note}${notes}${state.builderError?`<p role="alert">${esc(state.builderError)}</p>`:''}</section><div class="detail-dock note-dock"><button class="secondary" data-action="save-builder" ${chosen.length<2 || state.builderSaving?'disabled':''}>保存搭配</button><button class="primary" data-action="try-builder" ${chosen.length<2 || state.builderSaving?'disabled':''}>${state.builderSaving?'正在保存…':'保存并试穿'}</button></div>`;
  }
  async function saveBuilder(tryAfter = false) {
    if (state.builderSaving || state.builderMatching || state.builderMatchError || (state.builderIds?.size || 0)<2) return;
    const itemIds = [...state.builderIds];
    state.builderSaving=true;state.builderError='';render();
    try {
      const data=await api('/selfit/try-on/outfits',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({item_ids:itemIds,title:'我的搭配',favorite:true})},180000);
      const outfit=normalizeOutfit(data,builderCatalog());
      state.outfits=uniqueItems([outfit,...state.outfits]);
      if(state.page!=='builder'){notify('搭配已保存到衣帽间。');return;}
      state.current=outfit;state.selected=new Set(itemIds);state.result='';
      if(tryAfter){state.styling=true;go('mirror',true,false);await startTry();}
      else {state.closetCategory='set';go('closet');notify('搭配已保存。');}
    } catch(e){state.builderError=e.message || '保存失败，请重试。';}
    finally {state.builderSaving=false;render();}
  }
  function openOutfitSheet(id) {
    const outfit = lookup(id);
    if (!outfit) return;
    state.current = outfit;
    state.returnPage = "closet";
    state.result = "";
    modal(outfit.name, `${outfit.raw?.can_delete ? '<button class="garment-delete" data-action="delete-outfit" aria-label="删除穿搭"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 10v7m4-7v7"/></svg></button>' : ''}<span class="sheet-handle" aria-hidden="true"></span>${image(outfit.src,outfit.name,'garment-sheet-image')}<button class="primary garment-sheet-cta" data-action="try">立即试穿</button>`);
    $("#sheet").classList.add("garment-sheet", "outfit-sheet");
  }
  function openNotePreview(id) {
    const note = lookup(id);
    if (!note?.src) return notify("这张图片暂时无法打开，请刷新后重试。");
    modal(esc(note.name || "穿搭大图"), image(note.src, note.name || "穿搭大图", "note-preview-image"));
    $("#sheet").classList.add("note-preview-sheet");
  }
  function showDetail(id) {
    state.current = lookup(id);
    state.result = "";

    if (!state.current) return;
    if (state.page === "closet" && state.current.kind !== "note") {openOutfitSheet(id);return;}
    state.returnPage = state.page;
    go("detail");
  }
  function modal(title, body) {
    delete $("#sheet").dataset.importFlow;
    $("#sheet").classList.remove("garment-sheet", "outfit-sheet", "model-sheet", "mirror-binding-sheet", "note-preview-sheet");
    $("#sheet").innerHTML =
      `<h2 id="sheetTitle">${esc(title)}</h2><button class="close" data-action="close" aria-label="关闭">×</button>${body}`;
    if (!$("#sheet").open) $("#sheet").showModal();
  }
  async function loadModels() {
    const data = await api("/selfit/try-on/models");
    state.modelLibrary = (data.items || []).filter(model => model.gender === "female");
  }
  function modelSheet(content) {
    modal('选择试穿模特', `<p class="model-sheet-intro">选一个与你体型接近的模特，看看上身的感觉。</p><div class="model-sheet-scroll">${content}</div><footer class="model-sheet-footer"><button class="secondary" ${state.personalPhoto ? 'data-model-id="self"' : 'data-action="upload-photo"'}>${state.personalPhoto ? '使用我的照片' : '上传我的全身照'}<span aria-hidden="true"> ↗</span></button><p>用自己的照片，试穿更有代入感</p></footer>`);
    $('#sheet').classList.add('model-sheet');
    requestAnimationFrame(() => {
      const library = $('#sheet.model-sheet .model-library');
      const selected = library?.querySelector('[aria-pressed="true"]') || library?.querySelector('.model-option');
      if (!selected) return;
      const width = library.clientWidth;
      const cardWidth = Math.min(230, width * .64);
      library.style.setProperty('--model-card-width', `${cardWidth}px`);
      library.style.setProperty('--model-edge', `${(width - cardWidth) / 2}px`);
      const viewport = library.getBoundingClientRect();
      const card = selected.getBoundingClientRect();
      library.scrollLeft += card.left + card.width / 2 - viewport.left - viewport.width / 2;
    });
  }
  async function models() {
    modelSheet('<div class="model-sheet-status" role="status">正在为你准备模特…</div>');
    try {
      await loadModels();
      if (!$('#sheet').open || !$('#sheet').classList.contains('model-sheet')) return;
      modelSheet(`<div class="model-library" aria-label="试穿模特">${state.modelLibrary.map(m => `<button class="model-option" data-model-id="${esc(m.id)}" aria-label="选择${esc(m.name)}" aria-pressed="${state.modelId === m.id}"><div class="model-portrait">${image(m.image_url, m.name)}${state.modelId === m.id ? '<span class="model-selected-mark">✓ <span>使用中</span></span>' : ''}</div><div class="model-option-copy"><span>${esc(m.name)}</span></div></button>`).join('')}</div>${!state.modelLibrary.length ? '<div class="model-sheet-status">模特正在准备中<br>可以先使用自己的全身照</div>' : ''}`);
    } catch {
      if (!$('#sheet').open || !$('#sheet').classList.contains('model-sheet')) return;
      modelSheet('<div class="model-sheet-status"><p>模特暂时没有加载出来</p><button class="secondary" data-action="model">重新加载</button></div>');
    }
  }
  async function selectModel(id) {
    const selected = state.modelLibrary.find((x) => x.id === id);
    if (id !== "self" && !selected) return models();
    if (id === "self" && !state.personalPhoto)
      return notify("请先上传自己的照片。");
    const saved = reference
      ? { model: selected }
      : await api("/selfit/try-on/model", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ model_id: id }),
        });
    state.modelId = id;
    state.photo = id === "self" ? state.personalPhoto : saved.model.image_url;
    state.file = id === "self" ? state.personalFile : null;
    state.result = "";

    $("#sheet").close();
    render();
    if (state.pendingTry) {
      state.pendingTry = false;
      await startTry();
    }
  }
  function chooseItem(id) {
    const x = lookup(id);
    if (!x) return;
    // Selecting within the mirror updates its canvas, not the browsing position.
    const scrollPosition = state.page === "mirror" ? {
      strip: $(".strip")?.scrollLeft || 0,
      categories: $(".categories")?.scrollLeft || 0,
      screen: $("#screen").scrollTop,
    } : null;
    if (!reference) rememberCanvas();
    state.result = "";
    if (reference) {
      if (x.category === "top") state.top = x.id;
      else if (x.category === "bottom") state.bottom = x.id;
    } else {
      const previousItems=state.page === "closet" ? [] : (state.current?.items || []);
      const nextItems=window.SelfitOutfitLayout.replacePiece(previousItems,x);
      const replaced=previousItems.filter(p=>!nextItems.some(next=>next.id===p.id));
      const sameSlot=replaced.length===1 && window.SelfitMirrorLayout.category(replaced[0])===window.SelfitMirrorLayout.category(x);
      state.current = {
        id: "",
        name: "我的搭配",
        // Keep the presentation slot separate from the real item ID used by try-on.
        items: nextItems.map(p=>p.id===x.id && sameSlot ? {...p,mirrorLayoutId:replaced[0].mirrorLayoutId || replaced[0].id} : p),
        mirrorLayout:state.page === 'closet' ? [] : state.current?.mirrorLayout,
        src: x.src,
      };
    }
    state.selected = new Set(reference ? [id] : state.current.items.map(item => item.id));

    state.styling = true;
    go("mirror");
    if (scrollPosition) {
      if ($(".strip")) $(".strip").scrollLeft = scrollPosition.strip;
      if ($(".categories")) $(".categories").scrollLeft = scrollPosition.categories;
      $("#screen").scrollTop = scrollPosition.screen;
    }
    notify(`已选${x.name}`);
  }
  async function tryFromCard(id) {
    if (generationBusy || (state.job && !["completed", "failed"].includes(state.job.status)))
      return notify("上一张试穿图还在生成，请稍等。");
    const target = lookup(id);
    if (!target) return notify("这套搭配暂时无法打开，请刷新后重试。");
    const scrollLeft = state.page === "mirror" ? $(".strip")?.scrollLeft : null;
    if (state.page === "mirror") rememberCanvas();
    state.current = target;
    state.selected = new Set((target.items || []).map(item => item.id));
    state.result = "";
    state.completedTryon = null;
    const pending = startTry();
    if (state.page === "mirror" && scrollLeft != null && $(".strip")) $(".strip").scrollLeft = scrollLeft;
    await pending;
    if (state.page === "mirror" && scrollLeft != null && $(".strip")) $(".strip").scrollLeft = scrollLeft;
  }
  async function photoFile(photo = state.photo, file = state.file, modelId = state.modelId) {
    if (file) return file;
    if (!photo) throw Error("先选择模特或上传全身照。");
    const response = await fetch(mediaURL(photo));
    if (!response.ok) throw Error("这张照片暂时无法使用，请重新上传。");
    const blob = await response.blob();
    return new File(
      [blob],
      modelId && modelId !== "self"
        ? new URL(photo, location.origin).pathname.split("/").pop()
        : "my-photo.png",
      {
        type: blob.type || "image/png",
      },
    );
  }
  async function startTry() {
    if (
      generationBusy ||
      (state.job && !["completed", "failed"].includes(state.job.status))
    )
      return notify("上一张试穿图还在生成，请稍等。");
    if (!state.current) return notify("先选择一套搭配。");
    if (!state.photo) {
      state.pendingTry = true;
      models();
      return;
    }
    if (!reference && !state.personalPhoto && !state.exampleAccepted && !state.modelId) {
      state.pendingTry = true;
      modal("用你的照片，看看是否适合你", '<p>上传一张清晰全身照，试穿更贴近自己的效果。也可以先用示例模特看看。</p><button class="primary" data-action="upload-photo">上传我的全身照</button><button class="secondary" data-action="use-example">先用示例模特试穿</button>');
      return;
    }
    if (reference) {
      modal(
        "试穿预览",
        `${image(state.current.src, "原稿示例", "progress-art")}<p>当前是设计稿示例。正式试穿将使用你的照片和衣橱单品生成结果。</p><button class="primary" data-action="reference-result">查看原稿效果</button>`,
      );
      return;
    }
    const target = state.current;
    if (target.kind === "note") {
      await generateNote();
      return;
    }
    await generate();
  }
  function beginMirrorGeneration(target, photo) {
    state.generating = {target, photo};
    state.job = null;
    state.completedTryon = null;
    state.viewRecordId = "";
    state.current = target;
    state.jobPhoto = photo;
    state.result = "";
    state.resultOriginal = "";
    state.styling = false;
    state.category = "set";
    $("#sheet").close();
    go("mirror");
  }
  async function generateNote() {
    if (generationBusy || state.current?.kind !== "note") return;
    generationBusy = true;
    const target = state.current, photo = state.photo;
    const signature = `${target.id}:${photo}`;
    if (state.noteRequest?.signature !== signature) state.noteRequest={signature,id:crypto.randomUUID()};
    beginMirrorGeneration(target, photo);
    try {
      const file = await photoFile();
      const body = new FormData();
      body.append("person_image", file);
      body.append("note_id", target.id);
      body.append("client_request_id", state.noteRequest.id);
      state.job = await api("/selfit/try-on/inspiration-jobs", {method:"POST",body});
      sessionStorage.setItem("selfit.studio.job",JSON.stringify({job_id:state.job.job_id}));
      poll();
    } catch (e) { failure(e.message); }
    finally { generationBusy = false; }
  }
  async function generate() {
    if (generationBusy) return;
    const target = state.current, photo = state.photo, inputFile = state.file, modelId = state.modelId;
    const itemIds = [...new Set((target?.items || []).map(item => item.id).filter(Boolean))];
    if (!itemIds.length) return notify("这套搭配还没有可试穿的单品，请换一套。");
    generationBusy = true;
    state.selected = new Set(itemIds);
    const signature = JSON.stringify([target.id, itemIds, photo]);
    if (state.outfitRequest?.signature !== signature)
      state.outfitRequest = {signature, id: crypto.randomUUID()};
    const submissionId = state.outfitRequest.id;
    const loadingStartedAt = Date.now();
    beginMirrorGeneration(target, photo);
    try {
      const file = await photoFile(photo, inputFile, modelId);
      if (!target.id) {
        const saved = await api("/selfit/try-on/outfits", {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({item_ids: itemIds, title: "我的搭配"}),
        });
        target.id = saved.outfit_id;
        state.outfitRequest.signature = JSON.stringify([target.id, itemIds, photo]);
      }
      const body = new FormData();
      body.append("person_image", file);
      body.append("outfit_id", target.id);
      body.append("photo_mode", "standard");
      body.append("selected_item_ids", JSON.stringify(itemIds));
      body.append("wear_all_items", "true");
      if (modelId && modelId !== "self" && !inputFile) body.append("model_id", modelId);
      body.append("client_request_id", submissionId);
      state.job = await api("/selfit/try-on/jobs", {method: "POST", body});
      sessionStorage.setItem("selfit.studio.job", JSON.stringify({job_id: state.job.job_id, outfit_id: target.id}));
      state.jobPhoto = photo;
      const submitted = state.job;
      if (submitted.result?.generation_strategy === "preset") {
        await waitForPresetResult(submitted, loadingStartedAt);
        if (state.job?.job_id !== submitted.job_id) return;
        await poll(submitted);
      } else poll();
    } catch (e) {
      failure(e.message);
    } finally {
      generationBusy = false;
    }
  }
  async function waitForPresetResult(job, startedAt) {
    const preview = new Image();
    preview.src = mediaURL(job.result.result.image_path);
    try {
      await Promise.all([
        preview.decode(),
        new Promise(resolve => setTimeout(resolve, Math.max(0, 3000 - (Date.now() - startedAt)))),
      ]);
    } catch (_) { throw Error("试穿图片暂时无法加载，请稍后重试。"); }
  }
  function failure(message) {
    state.generating = null;
    if (state.page === "mirror") render();
    modal(
      "试穿暂未完成",
      `<p>${esc(message || "请稍后重试，你选择的照片和搭配都已保留。")}</p><button class="primary" data-action="${state.job?.job_id && state.job.result?.generation_strategy !== 'preset' ? "retry-job" : "try"}">重新尝试</button><button class="secondary" data-action="model">更换照片</button>`,
    );
  }
  async function poll(completedJob = null) {
    clearTimeout(pollTimer);
    if (!state.job?.job_id) return;
    const requestedJobId = state.job.job_id;
    try {
      const job = completedJob || await api(
        `/selfit/try-on/jobs/${encodeURIComponent(requestedJobId)}`,
      );
      if (state.job?.job_id !== requestedJobId) return;
      state.job = job;
      const sourceNote = job.result?.note || job.note;
      const note = sourceNote ? {id:sourceNote.id,kind:"note",name:sourceNote.title,src:sourceNote.image_url,
        byline:sourceNote.byline,sourceUrl:sourceNote.source_url,width:sourceNote.width,height:sourceNote.height,
        flat:false,saved:lookup(sourceNote.id)?.saved ?? sourceNote.favorite,items:[]} : null;
      if ($("#jobProgress"))
        $("#jobProgress").style.setProperty(
          "--progress",
          `${Math.min(98, Math.max(5, Number(job.progress) || 5))}%`,
        );
      if (job.status === "completed") {
        const src = job.result?.result?.image_path;
        if (!src) throw Error("未能取得试穿图，请重新尝试。");
        state.generating = null;
        const completed = {src,job,original:job.original_image_path || state.jobPhoto || '',
          outfit:note || (job.result?.outfit ? normalizeOutfit(job.result.outfit,state.items) : lookup(job.outfit_id) || {id:job.outfit_id,name:'这次试穿',items:[],src})};
        const reportOutfit = state.source === "report" && state.reportOutfits?.find(outfit => outfit.id === completed.outfit.id);
        if (reportOutfit) completed.outfit = {...completed.outfit, name: reportOutfit.name, reportNote: reportOutfit.reportNote};
        const requestedViewerJob = state.page === "result-viewer" && !state.viewerPhoto &&
          !state.viewRecordId && state.viewerJobId === job.job_id;
        if (job.result?.generation_strategy === "preset" && !requestedViewerJob &&
            (state.current?.id !== job.outfit_id || state.modelId !== job.model_id)) {
          state.noteRequest=null;
          state.outfitRequest=null;
          sessionStorage.removeItem("selfit.studio.job");
          if (state.page === "mirror") render();
          return;
        }
        if (!["mirror","result-viewer"].includes(state.page) ||
            (state.page === "result-viewer" && (state.viewerPhoto || state.viewerLoading || state.viewRecordId))) {
          state.completedTryon=completed;
          state.noteRequest=null;
          state.outfitRequest=null;
          sessionStorage.removeItem("selfit.studio.job");
          if ($("#completionNotice")) $("#completionNotice").hidden=false;
          if (state.page === "mirror") render();
          return;
        }
        state.completedTryon=null;
        state.result = src;
        state.current = completed.outfit;
        state.noteRequest = null;
        state.outfitRequest = null;
        state.resultOriginal = job.original_image_path || state.jobPhoto || '';
        state.photo = state.resultOriginal || state.photo;
        if (requestedViewerJob && job.result?.generation_strategy === "preset") {
          state.modelId = job.model_id;
          state.file = null;
        }
        state.styling = false;
        $("#sheet").close();
        sessionStorage.removeItem("selfit.studio.job");
        go(state.page === "result-viewer" ? "result-viewer" : "mirror", state.page !== "result-viewer");
        return;
      }
      if (job.status === "failed") {
        sessionStorage.removeItem("selfit.studio.job");
        throw Error("这次没有生成成功，可以更换照片后再试。");
      }
      if (!state.generating) {
        state.generating = {photo:job.original_image_path || state.jobPhoto || state.photo,
          target:note || lookup(job.outfit_id) || state.current};
        if (state.page === "mirror") render();
      }
      pollTimer = setTimeout(poll, 1800);
    } catch (e) {
      if (state.job?.job_id !== requestedJobId) return;
      failure(e.message);
    }
  }
  async function importGarment(retry = false) {
    if (!importFile && !importJob) return;
    const epoch = ++importEpoch;
    const file = importFile;
    clearTimeout(importTimer);
    if (!retry) importJob = null;
    modal(
      "正在拆分单品",
      '<p id="importCopy" role="status">正在上传图片，稍等一下…</p><button class="secondary" data-action="close">继续浏览</button>',
    );
    $("#sheet").dataset.importFlow = 'true';
    try {
      let submitted;
      if (retry && importJob)
        submitted = await api(
          `/closet/import/jobs/${encodeURIComponent(importJob.job_id)}/retry`,
          { method: "POST" },
        );
      else {
        const body = new FormData();
        body.append("images", file);
        body.append("require_confirmation", "true");
        submitted = await api("/closet/import/jobs", { method: "POST", body });
      }
      if (epoch !== importEpoch) return;
      importJob = submitted;
      if (!retry) {state.importSelection=new Set();state.importReviewJobId="";}
      rememberImport();
      if (state.page === "closet") render();
      pollImport();
    } catch (e) {
      if (epoch !== importEpoch) return;
      importFailure(e.message);
    }
  }
  function importFailure(message) {
    if (!$("#sheet").open || $("#sheet").dataset.importFlow !== 'true') {
      if (state.page === 'closet') render();
      notify('拆款暂未完成，可回衣帽间查看并重试。');
      return;
    }
    modal(
      "衣服暂未加入",
      `<p>${esc(message)}</p><button class="primary" data-action="retry-import">重新尝试</button><button class="secondary" data-action="upload-garment">换张衣服图</button>`,
    );
  }
  async function pollImport() {
    clearTimeout(importTimer);
    const epoch = importEpoch, jobId = importJob?.job_id;
    if (!jobId) return;
    try {
      const job = await api(
        `/closet/import/jobs/${encodeURIComponent(jobId)}`,
      );
      if (epoch !== importEpoch || jobId !== importJob?.job_id) return;
      importJob = job;
      rememberImport();
      if (job.status === "failed")
        return importFailure(
          "这张图片暂时无法提取衣服，可以换一张清楚的图片。",
        );
      if (job.status === "awaiting_confirmation") {
        const sameJob=state.importReviewJobId === job.job_id;
        state.importItems=(job.result?.items || []).map(normalizeItem);
        state.importPhoto=job.preview_images?.[0] || state.importPhoto;
        if (!sameJob) state.importSelection=new Set(state.importItems.map(x=>x.id));
        state.importReviewJobId=job.job_id; state.importError=''; rememberImport();
        if (state.page === 'import-review' || ($("#sheet").open && $("#sheet").dataset.importFlow === 'true')) {
          $("#sheet").close(); go('import-review');
        } else {
          if (state.page === 'closet') render();
          notify('单品已拆好，可回衣帽间确认添加。');
        }
        return;
      }
      if (job.status === "completed") {
        sessionStorage.removeItem('selfit.studio.import');
        await load();
        $("#sheet").close();
        state.closetCategory = "all";
        go("closet");
        notify("衣服已加入衣帽间。");
        return;
      }
      if ($("#importCopy"))
        $("#importCopy").textContent =
          `正在识别并分离单品 · ${Number(job.progress) || 0}%\n通常需要约一分钟，你可以先继续浏览。`;
      importTimer = setTimeout(pollImport, 1500);
    } catch (e) {
      if (epoch !== importEpoch || jobId !== importJob?.job_id) return;
      importFailure(e.message);
    }
  }
  function normalizeItem(x) {
    return {
      id: x.item_id,
      approximate: x.extraction?.reconstruction_method === "approximate",
      name: x.category_label || x.title || "衣橱单品",
      category: x.slot || x.category,
      src:
        x.assets?.cutout_path ||
        x.assets?.preview_path ||
        x.cutout_path ||
        x.transparent_path ||
        x.image_path ||
        x.source_image_path ||
        "",
      raw: x,
    };
  }
  function normalizeOutfit(x, items) {
    return {
      id: x.outfit_id,
      name: x.source === "published_content_v2" || /^(MUTE|ICED|HEIR|EASE|MELT|WABI|FLOU|NEON|EDGE|BOLT|FILM|JADE|LOOP|NOIR|VOID|OOPS)\b/.test(x.title || "")
        ? window.SelfitOutfitCopy.create(x).title : x.title || "我的搭配",
      src:
        x.layout_snapshot_path || x.cover_path || x.cover || x.image_path || "",
      saved: Boolean(x.favorite),
      flat: Boolean(x.layout_snapshot_path || x.source === "published_content_v2"),
      kind: "outfit",
      items: (x.items || []).map(normalizeItem).length
        ? (x.items || []).map(normalizeItem)
        : (x.item_ids || [])
            .map((id) => items.find((i) => i.id === id))
            .filter(Boolean),
      raw: x,
    };
  }
  async function loadHomeNotes() {
    if (state.homeOutfits.length) return;
    state.homeNotesError = "";
    const request = new URLSearchParams();
    const selected = new URLSearchParams(location.search).get("outfit");
    if (selected) request.set("selected_outfit_id", selected);
    try {
      const response = await api(`/selfit/try-on/report-outfits/random?${request}`);
      state.homeOutfits = response.outfits.map(row => ({
        ...normalizeOutfit(row, state.items),
        name: row.report_note.title, src: row.report_note.image_url, homeNote: row.report_note,
      }));
    } catch (error) {
      state.homeNotesError = "穿搭笔记暂时无法加载，请稍后重试。";
    }
  }
  async function loadReportOutfits() {
    const query = new URLSearchParams(location.search);
    if (query.get("from") !== "report" || !query.has("report_notes")) return;
    const request = new URLSearchParams({persona: query.get("persona") || "", note_ids: query.get("report_notes")});
    if (query.has("report_template")) request.set("template_id", query.get("report_template"));
    if (query.has("report_assets")) request.set("note_assets", query.get("report_assets"));
    state.reportOutfits = [];
    state.reportOutfitsKey = "";
    state.current = null;
    state.source = "report";
    const response = await api(`/selfit/try-on/report-outfits?${request}`);
    state.reportOutfits = response.outfits.map((row) => ({
      ...normalizeOutfit(row, state.items),
      name: `${row.report_note.title}${response.mode === "mock" ? " · 示例搭配" : ""}`,
      reportNote: row.report_note,
    }));
    state.reportOutfitsMode = response.mode;
    if (response.resolved_legacy_assets) {
      const assets = response.outfits.map(row => row.report_note.image_asset_id).join(',');
      const url = new URL(location.href);
      url.searchParams.set('report_assets', assets);
      url.searchParams.set('report_template', response.template_id);
      history.replaceState(history.state, '', url);
      request.set('note_assets', assets);
      request.set('template_id', response.template_id);
    }
    state.reportOutfitsKey = request.toString();
  }
  async function restoreSelectedOutfit(id, job) {
    if (state.source === "report") {
      state.current = state.reportOutfits.find((row) => row.id === id) || state.reportOutfits[0] || null;
      state.selected = new Set((state.current?.items || []).map((item) => item.id));
    } else if (id) {
      const existing = [...(state.homeOutfits || []), ...state.outfits, ...state.feed, ...(state.topics || []).flatMap(x=>x.entries), ...state.savedNotes].find((row) => row.id === id);
      state.current = existing || (job?.job_id ? null : normalizeOutfit(
        await api(`/closet/outfits/${encodeURIComponent(id)}`), state.items,
      ));
    } else state.current ||= state.homeOutfits?.[0] || null;
  }
  async function loadPhoto() {
    if (state.photo) return;
    try {
      const r = await fetch("/api/v1/selfit/me/photos/body", {
        headers: { Authorization: `Bearer ${savedSession.accessToken}` },
        cache: "reload",
      });
      if (r.ok && r.status !== 204) {
        const file = await r.blob();
        if (file.size) {
          state.photo = URL.createObjectURL(file);
          state.uploadURLs.push(state.photo);
          state.file = new File([file], "my-photo.jpg", { type: file.type });
        }
      }
    } catch {
      /* Saved wardrobe photo remains a usable fallback. */
    }
  }
  async function loadFeed(append = false) {
    if (state.feedBusy || (append && !state.feedMore)) return;
    state.feedBusy = true;
    state.feedError = "";
    try {
      const month = new Date().getMonth() + 1;
      const season =
        month <= 2 || month === 12
          ? "winter"
          : month <= 5
            ? "spring"
            : month <= 8
              ? "summer"
              : "autumn";
      const responses = await Promise.allSettled([api("/closet/recommendations/outfits", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source: "inspiration",
          persona: {},
          context: { season_tags: [season] },
          limit: 12,
          offset: append ? state.feedOffset : 0,
          session_id: append ? state.feedSession : null,
          cursor: append ? state.feedCursor : null,
          exclude_outfit_ids: append ? state.feed.filter(x => x.kind !== "note").map((x) => x.id) : [],
        }),
      }), append ? Promise.resolve({notes:[]}) : api("/selfit/try-on/inspiration-notes"),
        append ? Promise.resolve(null) : api("/selfit/try-on/inspiration-topics")]);
      if (append && responses[0].status === "rejected") throw responses[0].reason;
      if (!append) state.topicsError = responses[2].status === "rejected" ? "主题合集暂未加载，点击重试。" : "";
      if (responses.every(r => r.status === "rejected")) throw responses[0].reason;
      const data = responses[0].value || {};
      const normalizeNote = x => ({
        id:x.id, kind:"note", name:x.title, src:x.image_url, byline:x.byline, sourceUrl:x.source_url,
        width:x.width, height:x.height, flat:false, saved:x.favorite, items:[]
      });
      const notes = (responses[1].value?.notes || []).map(normalizeNote);
      if (!append && responses[1].status === "fulfilled")
        state.savedNotes = (responses[1].value.saved_notes || []).map(normalizeNote);
      if (!append && responses[2].status === "fulfilled")
        state.topics = (responses[2].value?.topics || []).map(topic => ({
          ...topic, entries: (topic.outfits || []).map(row => normalizeOutfit(row, state.items)),
        }));
      state.feedError = responses.some(r => r.status === "rejected") ? "部分灵感暂未加载，点击重试。" : "";
      const incoming = [
        ...(append ? [] : (state.topics || []).flatMap(topic => topic.outfits || [])),
        ...(append ? [] : data.carousel || []),
        ...(data.outfits || []),
      ].map((x) => normalizeOutfit(x, state.items));
      const mixed = [];
      for (let i=0; i<Math.max(incoming.length, notes.length*2); i++) {
        if (i % 2 === 0 && notes[i/2]) mixed.push(notes[i/2]);
        if (incoming[i]) mixed.push(incoming[i]);
      }
      state.feed = uniqueItems([...(append ? state.feed : []), ...mixed]);
      for (const row of [...state.feed, ...(state.topics || []).flatMap(topic=>topic.entries)]) {
        const ids = row.items
          .map((x) => x.id)
          .sort()
          .join("|");
        const own = state.outfits.find(
          (x) =>
            x.id === row.id ||
            (ids &&
              x.items
                .map((i) => i.id)
                .sort()
                .join("|") === ids),
        );
        if (own) {
          row.saved = own.saved;
          row.personalId = own.id;
        }
      }
      state.feedSession = data.session_id || null;
      state.feedCursor = data.next_cursor || null;
      state.feedOffset = data.next_offset || 0;
      state.feedMore = Boolean(data.has_more);
      state.profileRequired = Boolean(data.profile_required);
    } finally {
      state.feedBusy = false;
    }
  }
  async function load() {
    if (reference) return;
    state.loading = true;
    state.error = "";
    state.modelLoadFailed = false;
    render();
    try {
      const visitor = window.SelfitAuth.createClient({ mode: 'live' });
      await ensureVisitorSession();
      const loadVisitorData = () => Promise.allSettled([
        api("/selfit/try-on/wardrobe"),
        api("/closet/preferences"),
      ]);
      let results = await loadVisitorData();
      if (results.some((r) => r.status === "rejected" && r.reason.status === 401)) {
        visitor.clear();
        savedSession = await visitor.ensureVisitor();
        results = await loadVisitorData();
      }
      state.wardrobeError = results[0].status === "rejected" ? "衣帽间暂时无法加载，请重试。" : "";
      state.items = (results[0].value?.items || []).map(normalizeItem);
      state.outfits = (results[0].value?.outfits || []).map((x) =>
        normalizeOutfit(x, state.items),
      );
      const preferences = results[1].value || {};
      const fallback = preferences.self_model_path;
      if (state.modelId && state.modelId !== "self") {
        state.photo = state.personalPhoto;
        state.file = state.personalFile;
      }
      await Promise.all([
        loadModels().catch(() => {
          state.modelLoadFailed = true;
        }),
        loadPhoto(),
        loadHomeNotes(),
        loadFeed().catch(() => {
          state.feed = [];
          state.feedError = "推荐暂时无法加载，请稍后重试。";
          notify("穿搭库暂时无法更新，可重试加载。");
        }),
      ]);
      await loadReportOutfits();
      if (!state.photo) state.photo = fallback || "";
      state.personalPhoto = state.photo;
      state.personalFile = state.file;
      if (state.personalPhoto && params.get("from") === "onboarding") {
        preferences.current_model_id = "self";
        await api("/selfit/try-on/model", {
          method: "PUT", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ model_id: "self" }),
        }).catch(() => notify("这次先使用你的照片，模特偏好暂未保存。"));
        params.delete("from");
        const url = new URL(location.href);
        url.searchParams.delete("from");
        history.replaceState(null, "", url);
      }
      const preferred = state.modelLibrary.find(
        (x) => x.id === preferences.current_model_id,
      );
      if (preferences.current_model_id === "self" && state.personalPhoto)
        state.modelId = "self";
      else if (preferred) {
        state.modelId = preferred.id;
        state.photo = preferred.image_url;
        state.file = null;
      } else if (state.personalPhoto) state.modelId = "self";
      else if (state.modelLibrary.length) {
        state.modelId = state.modelLibrary[0].id;
        state.photo = state.modelLibrary[0].image_url;
        state.file = null;
      }

      let job;
      try {
        job = JSON.parse(sessionStorage.getItem("selfit.studio.job") || "null");
      } catch {}
      state.viewerJobId = state.page === 'result-viewer' && !state.viewerPhoto && !params.get('record') ? params.get('job') || '' : '';
      if (state.viewerJobId) job={job_id:state.viewerJobId};
      const id = new URLSearchParams(location.search).get("outfit");
      await restoreSelectedOutfit(id, job);
      state.error = "";
      if (job?.job_id && !params.get("record") && !state.viewerPhoto) {
        state.job = job;
        state.jobPhoto = job.original_image_path || "";
        poll();
      }
      if (state.page === 'result-viewer' && params.get('record')) {
        await restoreHistoryRoute(params.get('record'));
      }
      if (pendingImport()?.job_id) {
        let pending;
        try {pending=JSON.parse(sessionStorage.getItem('selfit.studio.import') || 'null');} catch {}
        if (pending?.job_id) {
          importJob={job_id:pending.job_id};state.importReviewJobId=pending.reviewed ? pending.job_id : '';
          state.importSelection=new Set(pending.selected || []); await pollImport();
        }
      }
    } catch (e) {
      state.error = e.message;
    } finally {
      state.loading = false;
      render();
    }
  }
  $("#sheet").addEventListener("click", e => {
    if(e.target !== $("#sheet")) return;
    const rect=$("#sheet").getBoundingClientRect();
    if(e.clientX<rect.left || e.clientX>rect.right || e.clientY<rect.top || e.clientY>rect.bottom) $("#sheet").close();
  });
  $("#studio").addEventListener("input", e=>{if(e.target.id==='chatInput'){state.chatDraft=e.target.value;const send=$('#chatComposer button[type=submit]');if(send)send.disabled=state.chatBusy||state.chatLoading||!state.chatDraft.trim();}});
  $("#studio").addEventListener("input", e => {
    if (e.target.id !== "mirrorDeviceCode") return;
    const digits = e.target.value.replace(/\D/g, "").slice(0, 4);
    if (e.target.value !== digits) e.target.value = digits;
  });
  $("#studio").addEventListener("submit", e=>{if(e.target.id==='chatComposer'){e.preventDefault();sendChat();}});
  $("#studio").addEventListener("click", async (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.profileEdit) {
      state.profileEditingField=b.dataset.profileEdit;
      state.profileFeatureValue=(state.profileDraft || state.profile.manual)[state.profileEditingField] || '';
      render(); $('#screen').scrollTop=0; return;
    }
    if (b.dataset.profileChoice) {state.profileFeatureValue=b.dataset.profileChoice;render();return;}
    if (b.dataset.action==='cancel-profile-feature' || b.dataset.action==='confirm-profile-feature') {
      if(b.dataset.action==='confirm-profile-feature') {
        state.profileDraft={...(state.profileDraft || state.profile.manual),[state.profileEditingField]:state.profileFeatureValue};
        state.profileEditingField=null;state.profileFeatureValue=null;
        await saveProfile();return;
      }
      state.profileEditingField=null;state.profileFeatureValue=null;state.profileDraft=null;go('profile');return;
    }

    if (b.dataset.chatPrompt !== undefined) {
      state.chatDraft = chatPrompts[Number(b.dataset.chatPrompt)][2];
      const input = $('#chatInput'); input.value = state.chatDraft; input.focus();
      $('#chatComposer button[type=submit]').disabled = state.chatBusy || state.chatLoading;
      return;
    }
    try {
      if (b.dataset.builderMatch!==undefined) {
        if(state.builderSaving)return;
        selectBuilderMatch(Number(b.dataset.builderMatch));render();return;
      }
      if(['save-builder','try-builder'].includes(b.dataset.action)){await saveBuilder(b.dataset.action==='try-builder');return;}
      if (b.dataset.record) {
        const record=(state.historyRecords || []).find(row=>row.record_id===b.dataset.record);
        if (!record) return;
        restoreTryonRecord(record);state.viewerReturnPage="tryon-history";go("result-viewer");return;
      }
      if (b.dataset.topic) {state.topicId=b.dataset.topic;go("topic");return;}
      if (b.dataset.importPiece) {
        if (state.importSaving) return;
        const id=b.dataset.importPiece;
        if(state.importSelection.has(id))state.importSelection.delete(id);else state.importSelection.add(id);
        rememberImport(); render(); return;
      }
      if (b.dataset.canvasPiece) {
        state.canvasSelection=state.canvasSelection===b.dataset.canvasPiece ? "" : b.dataset.canvasPiece;
        render(); return;
      }
      if (['adjust-mirror-piece','classify-pieces'].includes(b.dataset.action)) {
        adjustMirrorPiece(b.dataset.action==='classify-pieces'?'':state.canvasSelection); return;
      }
      if(b.dataset.mirrorCategory) {
        const id=b.dataset.id,category=b.dataset.mirrorCategory;
        const piece=state.current?.items.find(p=>p.id===id);
        if(!window.SelfitMirrorLayout.LABELS[category] || !piece) return;
        if(window.SelfitMirrorLayout.category(piece)===category) return;
        rememberCanvas();
        state.current={...state.current,items:state.current.items.map(p=>p.id===id?{...p,mirrorCategory:category}:p),mirrorLayout:[]};
        state.canvasSelection=id;
        render();
        const unknown=state.current.items.find(p=>!window.SelfitMirrorLayout.category(p));
        adjustMirrorPiece(unknown?.id || id); return;
      }
      if(b.dataset.mirrorSize) {
        const id=b.dataset.id,box=state.current?.mirrorLayout?.find(b=>b.id===id);
        if(!box) return;
        const scale=Math.max(.5,Math.min(1.5,Math.round((box.manualScale+Number(b.dataset.mirrorSize)*.1)*10)/10));
        rememberCanvas();
        state.current={...state.current,mirrorLayout:state.current.mirrorLayout.map(b=>b.id===id?{...b,manualScale:scale}:b)};
        state.canvasSelection=id;
        render(); adjustMirrorPiece(id); return;
      }
      if (b.dataset.action === "remove-piece") {
        const id=state.canvasSelection;
        if(!state.current?.items.some(p=>p.id===id)) return;
        rememberCanvas();
        state.current={...state.current,id:"",name:"我的搭配",items:state.current.items.filter(p=>p.id!==id)};
        state.selected=new Set(state.current.items.map(p=>p.id));
        state.result="";
        render(); notify("已从画布移除，可撤回恢复"); return;
      }
      if (["undo-canvas","redo-canvas"].includes(b.dataset.action)) {
        const redo=b.dataset.action === "redo-canvas";
        const source=redo ? state.canvasFuture : state.canvasHistory;
        const target=redo ? state.canvasHistory : state.canvasFuture;
        const previous=source.pop();
        if(!previous) return;
        target.push(canvasSnapshot());
        state.current=previous.current;
        state.canvasSelection=previous.selection;
        state.selected=new Set((state.current?.items || []).map(p=>p.id));
        state.result="";
        $("#sheet").close(); state.styling=true;
        render(); notify(redo ? "已重做上一步" : "已撤回上一步"); return;
      }
      if(b.dataset.action === "edit-profile") {state.profileDraft={...state.profile.manual};state.profilePhotoDraft={};state.profileError='';go('profile-edit');return;}
      if(b.dataset.action === "reload-profile") {await loadProfile(true);return;}
      if(b.dataset.action === "save-profile") {await saveProfile();return;}
      if (b.dataset.action === "open-chat") { state.chatReturn=state.page; go("chat"); return; }
      if (b.dataset.modelId) {
        b.disabled = true;
        await selectModel(b.dataset.modelId);
        return;
      }
      if (b.dataset.page) {
        go(b.dataset.page);
        return;
      }
      if (b.dataset.category) {
        state[b.dataset.location === "closet" ? "closetCategory" : "category"] =
          b.dataset.category;
        render();
        return;
      }
      if (b.dataset.source) {
        state.source = b.dataset.source;
        render();
        return;
      }
      if (b.dataset.notePreview) {openNotePreview(b.dataset.notePreview);return;}
      if (b.dataset.detail) {
        showDetail(b.dataset.detail);
        return;
      }
      if (b.dataset.outfit) {
        if (!reference && state.page === "mirror") {
          const scrollLeft = $(".strip")?.scrollLeft || 0;
          rememberCanvas();
          state.current = lookup(b.dataset.outfit);
          state.selected = new Set((state.current?.items || []).map(item => item.id));
          state.result = "";

          go("mirror");
          if ($(".strip")) $(".strip").scrollLeft = scrollLeft;
          return;
        }
        showDetail(b.dataset.outfit);
        return;
      }
      if (b.dataset.item) {
        if (state.page !== "closet") chooseItem(b.dataset.item);
        return;
      }
      if (b.dataset.try) {
        await tryFromCard(b.dataset.try);
        return;
      }
      if (b.dataset.slot) {
        state.category = b.dataset.slot;
        render();
        return;
      }
      switch (b.dataset.action) {
        case "confirm-import": await confirmImport(); break;
        case "retry-history-viewer": await restoreHistoryRoute(state.viewRecordId); break;
        case "open-viewer": state.viewerReturnPage="mirror"; state.viewerError=""; state.viewerPhoto=!state.result; go('result-viewer'); break;
        case "close-viewer": go(state.viewerReturnPage || "mirror"); break;
        case "leave-import": go('closet'); break;
        case "resume-import": await resumeImport(); break;
        case "view-current":
          state.returnPage = "mirror";
          go("detail");
          break;
        case "use-example":
          state.exampleAccepted = true;
          state.pendingTry = false;
          $("#sheet").close();
          await startTry();
          break;
        case "item-style":
          $("#sheet").close();
          chooseItem(b.dataset.id);
          break;
        case "item-try":
          state.current = { id: "", name: "单品试穿", items: [lookup(b.dataset.id)], src: lookup(b.dataset.id).src };
          state.styling = false;
          go("mirror");
          await startTry();
          break;
        case "delete-item":
          await deleteWardrobeItem(b.dataset.id);
          break;
        case "retry-item-match":
          await generateForItem(state.builderAnchor?.id);
          break;
        case "item-generate":
          await generateForItem(b.dataset.id);
          break;
        case "toggle":
          await turnMirror();
          break;
        case "model":
          await models();
          break;
        case "upload-photo":
          $("#photoInput").click();
          break;
        case "close":
          state.pendingTry = false;
          $("#sheet").close();
          break;
        case "back":
          go(state.returnPage);
          break;
        case "favorite": {
          const target = b.dataset?.favoriteId ? lookup(b.dataset.favoriteId) : state.current;
          if (!target) return;
          const saved = !target.saved;
          b.disabled = true;
          if (target.kind === "note") {
            if (!reference) await api(`/selfit/try-on/inspiration-notes/${encodeURIComponent(target.id)}/favorite`, {
              method:"PATCH", headers:{"Content-Type":"application/json"}, body:JSON.stringify({favorite:saved})
            });
            target.saved = saved;
            state.savedNotes = state.savedNotes.filter(row=>row.id !== target.id);
            if (saved) state.savedNotes.push({...target});
            for (const row of state.feed) if(row.id === target.id) row.saved = saved;
            render(); notify(saved ? "收藏成功" : "已取消收藏", saved && state.page === "detail" && state.current?.id === target.id ? "favorite" : ""); break;
          }
          if (!reference) {
            const own = state.outfits.find((x) => x.id === (target.personalId || target.id));
            if (!own && saved) {
              const result = await api("/selfit/try-on/outfits", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  item_ids: target.items.map((x) => x.id),
                  title: target.name,
                  favorite: true,
                }),
              });
              const copy = normalizeOutfit(result, state.items);
              state.outfits = uniqueItems([...state.outfits, copy]);
              target.personalId = copy.id;
            } else
              await api(
                `/closet/outfits/${encodeURIComponent(target.personalId || target.id)}`,
                {
                  method: "PATCH",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ favorite: saved }),
                },
              );
          }
          const ownCopy = state.outfits.find(
            (x) => x.id === (target.personalId || target.id),
          );
          if (ownCopy) ownCopy.saved = saved;
          target.saved = saved;
          if (!reference) {
            const wardrobe = await api("/selfit/try-on/wardrobe");
            state.items = (wardrobe.items || []).map(normalizeItem);
            state.outfits = (wardrobe.outfits || []).map(x => normalizeOutfit(x, state.items));
          }
          for (const row of [...state.feed, ...(state.topics || []).flatMap(topic=>topic.entries)])
            if (row.id === target.id || row.personalId === (target.personalId || target.id)) {
              row.saved = saved;
              if (target.personalId) row.personalId = target.personalId;
            }
          render();
          notify(saved ? "收藏成功" : "已取消收藏", saved && state.page === "detail" && state.current?.id === target.id ? "favorite" : "");
          break;
        }
        case "delete-outfit": {
          const target = state.current;
          if (!target?.raw?.can_delete) return;
          modal(
            "删除这套穿搭？",
            `<p>删除后将从我的穿搭中移除，衣橱单品和已生成的试穿图片会保留。</p><button class="secondary" data-action="cancel-delete-outfit">取消</button><button class="primary" data-action="confirm-delete" data-delete-id="${esc(target.id)}">确认删除</button>`,
          );
          break;
        }
        case "cancel-delete-outfit":
          if (state.page === "closet") openOutfitSheet(state.current?.id);
          else $("#sheet").close();
          break;
        case "confirm-delete": {
          const id = b.dataset.deleteId;
          b.disabled = true;
          try {
            if (!reference) await api(`/closet/outfits/${encodeURIComponent(id)}`, {
              method: "DELETE",
            });
          } catch {
            b.disabled = false;
            notify("删除没有完成，请重试。");
            return;
          }
          state.outfits = state.outfits.filter((x) => x.id !== id);
          state.feed = state.feed.filter((x) => x.id !== id);
          for (const x of state.feed)
            if (x.personalId === id) {
              x.saved = false;
              delete x.personalId;
            }
          state.current = null;
          state.selected.clear();

          state.result = "";
          $("#sheet").close();
          go("closet", false);
          const nextURL = new URL(location.href);
          nextURL.searchParams.delete("outfit");
          nextURL.searchParams.set("screen", "closet");
          // Replace the detail entry so browser refresh/back does not reopen the deleted outfit.
          history.replaceState({ page: "closet" }, "", nextURL);
          notify("穿搭已删除，衣橱单品已保留。");
          break;
        }
        case "style":
          state.styling = true;
          state.result = "";
          go("mirror");
          break;
        case "try":
          await startTry();
          break;
        case "more":
          b.disabled = true;
          try {
            await loadFeed(true);
            render();
          } finally {
            b.disabled = false;
          }
          break;
        case "retry-mirror":
          mirrorImages.delete(state.result || state.photo);
          await load();
          break;
        case "reload":
          await load();
          break;
        case "retry-import":
          await importGarment(true);
          break;
        case "add":
          modal(
            "添加衣服",
            '<p>选一张清楚的衣服图片，加入衣帽间。</p><button class="primary" data-action="upload-garment">上传衣服图</button><a href="/wearwow/demo?tab=closet">从链接导入衣服</a>',
          );
          break;
        case "upload-garment":
          $("#garmentInput").click();
          break;
        case "reference-result":
          $("#sheet").close();
          state.styling = false;
          state.result = asset("model");
          go("mirror");
          notify("原稿示例效果，未调用生成服务。");
          break;
        case "retry-job":
          if (!state.job?.job_id) return;
          b.disabled=true;
          state.job=await api(`/selfit/try-on/jobs/${encodeURIComponent(state.job.job_id)}/retry`,{method:"POST"});
          sessionStorage.setItem("selfit.studio.job",JSON.stringify({job_id:state.job.job_id}));
          $("#sheet").close(); go("mirror"); await poll();
          break;
        case "view-completed": go("mirror"); break;
        case "tryon-history": go("tryon-history"); break;
        case "reload-tryon-history": await loadTryonHistory(); break;
        case "result-actions":
          modal("绑定你的智能穿衣镜", '<p id="mirrorBindingDescription">每日记录身材和穿搭</p><input id="mirrorDeviceCode" class="mirror-device-code" type="text" inputmode="numeric" minlength="4" maxlength="4" pattern="[0-9]{4}" autocomplete="off" placeholder="请输入设备码" aria-label="设备码" aria-describedby="mirrorBindingDescription" required>');
          $("#sheet").classList.add("mirror-binding-sheet");
          break;
        case "bind-phone":
          modal("绑定手机号", '<p id="bindPhoneDescription">绑定后，换设备或清理浏览器也能用手机号找回你的试穿数据和内测资格。</p><input id="bindPhoneInput" class="mirror-device-code" type="tel" inputmode="numeric" maxlength="11" autocomplete="tel-national" placeholder="请输入手机号" aria-label="手机号" aria-describedby="bindPhoneDescription" required><button class="primary" data-action="confirm-bind-phone">绑定</button>');
          break;
        case "confirm-bind-phone": {
          const input = $("#bindPhoneInput");
          const phone = (input?.value || "").replace(/\D/g, "");
          if (!/^1[3-9]\d{9}$/.test(phone)) { notify("请输入正确的手机号"); input?.focus(); return; }
          const deviceId = (() => { try { return localStorage.getItem("selfit.device.v1") || undefined; } catch { return undefined; } })();
          const payload = await api("/auth/bind-phone", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ phone, device_id: deviceId }) });
          $("#sheet").close();
          if (savedSession && payload?.user) savedSession = { ...savedSession, user: payload.user };
          notify(payload?.merged ? "绑定成功，两个账号的数据已合并" : "绑定成功，数据已同步到云端");
          if (state.page === "profile") render();
          break;
        }
        case "result-compare":
          $("#sheet").close();
          if (!state.resultOriginal && !reference) return notify("这张历史试穿图没有保留原图。");
          notify("按住人物照片查看原图，松开返回试穿效果。");
          break;
        case "result-styling":
          $("#sheet").close(); state.result=""; state.styling=true; go("mirror");
          break;
        case "save-result": {
          if (!state.result) return;
          const a = document.createElement("a");
          const response = await fetch(mediaURL(state.result));
          if (!response.ok) throw Error("图片暂时无法保存，请重试。");
          const downloadURL = URL.createObjectURL(await response.blob());
          a.href = downloadURL;
          a.download = "selfit-tryon.png";
          a.click();
          setTimeout(() => URL.revokeObjectURL(downloadURL), 60000);
          break;
        }
        case "logout": {
          // 二次确认防误触：确认后才执行登出清理。
          modal("退出登录？", '<p>退出后需要重新登录，才能查看你的衣橱和试穿记录。</p><button class="primary" data-action="confirm-logout">退出登录</button><button class="secondary" data-action="close">取消</button>');
          break;
        }
        case "confirm-logout": {
          b.disabled = true;
          try {
            if (savedSession?.accessToken) await api("/auth/logout", { method: "POST" });
          } catch {}
          savedSession = null;
          visitorReady = null;
          try {
            localStorage.removeItem("selfit.auth.session.v2");
            localStorage.removeItem("selfit.auth.invite.v1");
            sessionStorage.removeItem("selfit.auth.session.v1");
          } catch {}
          sessionStorage.removeItem("selfit.studio.job");
          sessionStorage.removeItem("selfit.studio.import");
          localStorage.removeItem("selfit.onboarding.session.v1");
          window.location.replace("/selfit?entry=login");
          break;
        }
      }
    } catch (error) {
      b.disabled = false;
      notify(error.message || "请稍后再试。");
    }
  });
  $("#photoInput").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (
      !/^image\/(jpeg|png|webp)$/.test(file.type) ||
      file.size > 20 * 1024 * 1024
    )
      return notify("请选择 20MB 以内的 JPG、PNG 或 WebP 图片。");
    const u = URL.createObjectURL(file);
    try {
      const im = new Image();
      im.src = u;
      await im.decode();
      state.uploadURLs.push(u);
      state.photo = u;
      state.file = file;
      state.personalPhoto = u;
      state.personalFile = file;
      state.modelId = "self";
      state.result = "";
      $("#sheet").close();
      render();
      if (!reference) {
        try {
          const body = new FormData();
          body.append("image", file);
          await api("/closet/preferences/model-photo", {
            method: "POST",
            body,
          });
          await api("/selfit/try-on/model", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ model_id: "self" }),
          });
        } catch {
          notify("照片可用于这次试穿，但未能保存到档案。");
        }
      }
      if (state.pendingTry) {
        state.pendingTry = false;
        await startTry();
      } else notify("照片已准备好，选择一套搭配开始试穿。");
    } catch {
      URL.revokeObjectURL(u);
      notify("这张图片无法读取，请换一张照片。");
    }
    e.target.value = "";
  });
  $("#garmentInput").addEventListener("change", async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    if (!/^image\/(jpeg|png|webp)$/.test(f.type) || f.size > 20 * 1024 * 1024)
      return notify("请选择 20MB 以内的衣服图片。");
    if (!reference) {
      importFile = f;
      await importGarment();
      e.target.value = "";
      return;
    }
    const u = URL.createObjectURL(f);
    try {
      const im = new Image();
      im.src = u;
      await im.decode();
      state.uploadURLs.push(u);
      state.importPhoto=u;
      state.importItems=[{id:`upload-${Date.now()}`,src:u,category:'top',name:'上传的图片（预览）'}];
      state.importSelection=new Set(state.importItems.map(x=>x.id));
      $("#sheet").close(); go('import-review');
      notify('设计预览仅展示原图，未调用单品识别。');
    } catch {
      URL.revokeObjectURL(u);
      notify("图片无法读取，请换一张。");
    }
    e.target.value = "";
  });
  $("#studio").addEventListener("pointerdown", (e) => {
    if (e.target.closest("[data-action=compare]")) {
      const im = $(".model-photo");
      if (im) window.SelfitMirrorPhoto.show(im, mediaURL(state.resultOriginal || (reference ? state.photo : "")));
    }
  });
  const restore = () => {
    const im = $(".model-photo");
    if (im && state.result) window.SelfitMirrorPhoto.show(im, mediaURL(state.result));
  };
  window.addEventListener("pointerup", restore);
  window.addEventListener("pointercancel", restore);
  window.addEventListener("blur", restore);
  $("#studio").addEventListener("keydown", (e) => {
    if (e.key === "Escape" && state.page === "result-viewer") {go(state.viewerReturnPage || "mirror"); return;}
    if (
      e.target.closest("[data-action=compare]") &&
      [" ", "Enter"].includes(e.key)
    ) {
      e.preventDefault();
      const im = $(".model-photo");
      if (im) window.SelfitMirrorPhoto.show(im, mediaURL(state.resultOriginal || (reference ? state.photo : "")));
    }
  });
  $("#studio").addEventListener("keyup", restore);
  window.addEventListener("popstate", async () => {
    const p = new URLSearchParams(location.search);
    if (!reference && p.get("from") === "report" && p.has("report_notes")) {
      try {
        const request = new URLSearchParams({persona: p.get("persona") || "", note_ids: p.get("report_notes")});
        if (p.has("report_template")) request.set("template_id", p.get("report_template"));
        if (p.has("report_assets")) request.set("note_assets", p.get("report_assets"));
        const key = request.toString();
        if (key !== state.reportOutfitsKey) await loadReportOutfits();
        state.source = "report";
        state.error = "";
        await restoreSelectedOutfit(p.get("outfit"));
      } catch (error) { state.error = error.message; state.current = null; }
    } else if (state.source === "report") state.source = "inspiration";
    state.viewerReturnPage = p.get("viewer_from") === "history" ? "tryon-history" : "mirror";
    state.viewerPhoto = p.get("preview") === "photo";
    state.viewerJobId = "";
    state.styling = p.get("mode") === "styling";
    if (!reference && p.get("screen") === "result-viewer" && !state.viewerPhoto && p.get("record")) {
      state.viewerLoading = true;
      state.viewerError = "";
      go("result-viewer", false);
      await restoreHistoryRoute(p.get("record"));
      return;
    }
    if (!reference && p.get("screen") === "result-viewer" && !state.viewerPhoto && p.get("job")) {
      state.viewerRequest = (state.viewerRequest || 0) + 1;
      state.viewerLoading = false;
      state.viewerError = "";
      state.viewRecordId = "";
      state.result = "";
      state.resultOriginal = "";
      state.jobPhoto = "";
      state.job = {job_id:p.get("job")};
      state.viewerJobId = p.get("job");
      go("result-viewer", false);
      await poll();
      return;
    }
    if (!reference && state.source !== "report" && p.get("outfit")) {
      try {
        state.current =
          lookup(p.get("outfit")) ||
          normalizeOutfit(
            await api(`/closet/outfits/${encodeURIComponent(p.get("outfit"))}`),
            state.items,
          );
      } catch (e) {
        notify(e.message);
      }
    }
    go(
      ["mirror", "closet", "inspiration", "detail", "chat", "profile", "profile-edit", "import-review", "result-viewer", "tryon-history", "topic", "builder"].includes(p.get("screen"))
        ? p.get("screen")
        : "mirror",
      false,
    );
  });
  $("#studio").addEventListener("change", async (event)=>{
    const field=event.target.dataset.profileField;
    if(field) {state.profileDraft={...(state.profileDraft || state.profile.manual),[field]:event.target.value};render();return;}
    const kind=event.target.dataset.profilePhoto;
    if(!kind) return;
    const file=event.target.files?.[0];if(!file)return;
    const maxMB=kind==='body' ? 15 : 20;
    if(file.size>maxMB*1024*1024) {notify(`请选择 ${maxMB}MB 以内的照片。`);return;}
    if(state.page!=='profile-edit') { await replaceProfilePhoto(kind,file); return; }
    const url=URL.createObjectURL(file);
    try {const photo=new Image();photo.src=url;await photo.decode();if(kind==='body' && (photo.naturalWidth<240 || photo.naturalHeight<320)) {URL.revokeObjectURL(url);notify('全身照分辨率偏低，请选择更清晰的照片。');return;}state.uploadURLs.push(url);state.profilePhotoDraft[kind]={file,url};render();}
    catch {URL.revokeObjectURL(url);notify('照片无法读取，请换一张。');}
  });
  const wardrobeGestures = window.SelfitWardrobeGestures.bind($("#studio"));
  window.addEventListener("pagehide", () => {
    wardrobeGestures.reset();
    clearTimeout(pollTimer);
    clearTimeout(importTimer);
    window.SelfitMirrorPhoto.clear();
    state.uploadURLs.forEach(URL.revokeObjectURL);
  });
  render();
  if(state.page === "tryon-history") loadTryonHistory();
  if(state.page === "chat") loadChat();
  if(["profile","profile-edit"].includes(state.page)) loadProfile();
  load();
})();
