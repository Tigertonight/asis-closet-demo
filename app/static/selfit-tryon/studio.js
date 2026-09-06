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
  const fixtureOutfits = Array.from({ length: 12 }, (_, i) => ({
    id: `reference-${i}`,
    name: "灵感套装",
    src: asset("outfit"),
    items: fixtures,
    saved: [0, 4, 5, 7].includes(i),
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
    items: fixtures,
    saved: [2, 3].includes(i),
  }));
  let savedSession = null;
  try {
    savedSession = JSON.parse(
      sessionStorage.getItem("selfit.auth.session.v1") || "null",
    );
  } catch {}
  if (
    savedSession?.expiresAt &&
    Date.parse(savedSession.expiresAt) <= Date.now()
  )
    savedSession = null;
  function mediaURL(path) {
    if (!path) return "";
    try {
      const url = new URL(path, location.origin);
      if (!["http:", "https:", "blob:"].includes(url.protocol)) return "";
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
    page: ["mirror", "closet", "inspiration", "detail"].includes(
      params.get("screen"),
    )
      ? params.get("screen")
      : "mirror",
    styling: params.get("mode") === "styling",
    source: "inspiration",
    category: "all",
    closetCategory: "set",
    items: reference ? fixtures : [],
    outfits: reference ? fixtureOutfits : [],
    feed: reference ? feedFixtures : [],
    current: reference ? feedFixtures[3] : null,
    photo: reference ? asset("model") : "",
    file: null,
    modelId: "",
    modelLibrary: [],
    personalPhoto: "",
    personalFile: null,
    top: "top",
    bottom: "pants",
    result: "",
    loading: !reference,
    error: "",
    selected: new Set(),
    canvasSelection: "",
    canvasHistory: [],
    canvasFuture: [],
    uploadURLs: [],
    returnPage: "inspiration",
    job: null,
    feedSession: null,
    feedCursor: null,
    feedMore: false,
    feedBusy: false,
    feedOffset: 0,
    pendingTry: false,
    profileRequired: false,
  };
  let toastTimer,
    pollTimer,
    importTimer,
    requestId = "",
    preflight = null,
    importFile = null,
    importJob = null,
    generationBusy = false;
  function notify(text) {
    $("#notice").textContent = text;
    $("#notice").classList.add("visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(
      () => $("#notice").classList.remove("visible"),
      3200,
    );
  }
  async function api(path, options = {}) {
    const controller = new AbortController(),
      timer = setTimeout(() => controller.abort(), 30000);
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
          sessionStorage.removeItem("selfit.auth.session.v1");
        }
        const e = Error(
          r.status === 401
            ? "请先登录，再查看你的衣橱。"
            : "这次操作没有完成，请稍后重试。",
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
    const visible = state.page !== "detail";
    $("#navigation").hidden = !visible;
    $("#navigation").innerHTML = [
      ["mirror", "试衣镜"],
      ["closet", "衣帽间"],
      ["inspiration", "灵感库"],
    ]
      .map(
        ([id, label]) =>
          `<button class="nav-item" data-page="${id}" ${state.page === id ? 'aria-current="page"' : ""}><span>${label}</span>${state.page === id ? (id === "mirror" ? image(asset("mirror"), "", "nav-ornament") : id === "inspiration" ? image(asset("butterfly"), "", "nav-ornament butterfly") : image(`${A}closet-shirt.svg`, "", "nav-shirt")) : ""}</button>`,
      )
      .join("");
  }
  function card(x, kind = "item", i = 0) {
    const activeOutfit = !reference && state.page === "mirror" && kind === "outfit" && state.current?.id === x.id;
    return `<button class="card ${kind === "outfit" ? "outfit-card" : "item-card"}" data-${kind}="${esc(x.id)}" data-kind="${esc(x.id)}" aria-label="${esc(x.name)}"${activeOutfit || state.selected.has(x.id) ? ' aria-pressed="true"' : ' aria-pressed="false"'}>${image(reference && state.page === "closet" && kind === "outfit" ? `${A}closet-outfit.svg` : x.src, x.name)}${x.saved ? image(asset("star"), "已收藏", "favorite-star") : ""}${activeOutfit ? '<span class="outfit-selected-label">✓ 已选</span>' : ""}</button>`;
  }
  function empty(text) {
    return `<div class="empty">${esc(text)}<br>${!reference && !savedSession?.accessToken ? '<a href="/selfit">登录 selfit</a>' : state.error ? '<button class="secondary" data-action="reload">重新加载</button>' : '<button class="secondary" data-action="add">添加衣服</button>'}</div>`;
  }
  function categories(compact = true) {
    return `<div class="${compact ? "categories" : "category-tabs"}" role="tablist" aria-label="服装分类">${(compact
      ? [
          ["all", "全部"],
          ["set", "套装"],
          ["top", "上装"],
          ["bottom", "下装"],
          ["shoes", "鞋子"],
          ["accessory", "配饰"],
        ]
      : [
          ["set", "套装"],
          ["top", "上装"],
          ["bottom", "下装"],
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
    const styling = state.styling,
      collection = reference
        ? state.outfits.map((x) => ({ ...x, saved: false }))
        : state.source === "closet"
          ? state.outfits
          : state.feed;
    const availableItems =
      reference || state.source === "closet"
        ? state.items
        : uniqueItems([
            ...state.feed.flatMap((x) => x.items),
            ...(state.current?.items || []),
          ]);
    const items =
      state.category === "set"
        ? collection
        : availableItems.filter(
            (x) =>
              state.category === "all" ||
              categoryGroup(x.category) === state.category,
          );
    return `<section class="mirror-screen" aria-label="试衣镜"><div class="mirror-stage ${styling ? "styling" : ""}">${image(`${A}mirror-${styling ? "styling" : "model"}-background.svg?v=20260905-7`, "", "stage-background")}<div class="arch"></div>${
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
          : state.photo
            ? image(
                state.result || state.photo,
                "当前试穿效果",
                `model-photo ${!reference || state.file || state.result ? "personal" : ""}`,
              )
            : '<div class="empty-stage"><span>先放入你的全身照</span><button data-action="model">选择模特</button></div>'
    }${styling && !reference ? canvasTools() : ""}<button class="stage-control mode-control" data-action="toggle" aria-label="${styling ? "切换到模特试穿" : "切换到自由搭配"}"></button><button class="stage-control model-control" data-action="model" aria-label="选择模特或上传我的照片"></button>${!reference && !state.result && state.current?.items?.length ? '<div class="result-tools try-outfit-tools"><button data-action="try">试穿这套搭配</button></div>' : ""}${state.result ? '<div class="result-tools"><button data-action="compare">按住查看原图</button><button data-action="save-result">保存试穿图</button></div>' : ""}</div><div class="source-tabs" role="tablist" aria-label="搭配来源">${[
      ["inspiration", "灵感库"],
      ["closet", "衣帽间"],
    ]
      .map(
        ([id, n]) =>
          `<button role="tab" aria-selected="${state.source === id}" data-source="${id}">${n}</button>`,
      )
      .join("")}</div>${styling ? categories() : ""}${
      state.loading
        ? empty("正在整理你的搭配…")
        : state.error
          ? empty(state.error)
          : `<div class="strip" aria-label="${styling ? "选择单品" : "选择套装"}">${(styling ? items : collection).map((x, i) => card(x, styling && state.category !== "set" ? "item" : "outfit", i)).join("") || empty("这里还没有搭配，先添加一件喜欢的衣服。")}</div><div class="dots" aria-label="搭配分页">${Array.from(
              {
                length: reference
                  ? 4
                  : Math.max(
                      1,
                      Math.ceil((styling ? items : collection).length / 3),
                    ),
              },
              (_, i) => i,
            )
              .map(
                (i) =>
                  `<button data-dot="${i}" aria-label="第 ${i + 1} 页" aria-current="${i === 0}"></button>`,
              )
              .join("")}</div>`
    }</section>`;
  }
  const trimmedPieces = new Map();
  function preparePiece(src) {
    if (trimmedPieces.has(src)) return;
    trimmedPieces.set(src, {ready:false, src});
    const img = new Image();
    img.crossOrigin = "anonymous";
    let done = false;
    const finish = output => {
      if(done) return;
      done = true; clearTimeout(timer);
      trimmedPieces.set(src, {ready:true, src:output || src});
      if(state.page === "mirror" && state.styling) render();
    };
    const timer = setTimeout(()=>finish(src), 15000);
    img.onerror = ()=>finish(src);
    img.onload = ()=>{
      try {
        const scale = Math.min(1, 512 / Math.max(img.naturalWidth,img.naturalHeight));
        const probe = document.createElement("canvas");
        probe.width = Math.max(1,Math.round(img.naturalWidth*scale));
        probe.height = Math.max(1,Math.round(img.naturalHeight*scale));
        const ctx=probe.getContext("2d",{willReadFrequently:true});
        ctx.drawImage(img,0,0,probe.width,probe.height);
        const pixels=ctx.getImageData(0,0,probe.width,probe.height).data;
        let left=probe.width,top=probe.height,right=-1,bottom=-1;
        for(let y=0;y<probe.height;y++)for(let x=0;x<probe.width;x++){
          if(pixels[(y*probe.width+x)*4+3]>20){left=Math.min(left,x);right=Math.max(right,x);top=Math.min(top,y);bottom=Math.max(bottom,y);}
        }
        if(right<left) return finish(src);
        left=Math.max(0,left-2);top=Math.max(0,top-2);
        right=Math.min(probe.width-1,right+2);bottom=Math.min(probe.height-1,bottom+2);
        const crop=document.createElement("canvas");
        crop.width=Math.ceil((right-left+1)/scale);crop.height=Math.ceil((bottom-top+1)/scale);
        crop.getContext("2d").drawImage(img,left/scale,top/scale,crop.width,crop.height,0,0,crop.width,crop.height);
        crop.toBlob(blob=>{if(!blob || done)return finish(src);const url=URL.createObjectURL(blob);state.uploadURLs.push(url);finish(url);},"image/png");
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
    return `<div class="canvas-tools" aria-label="画布操作"><button data-action="undo-canvas" aria-label="撤回上一步" ${state.canvasHistory.length ? "" : "disabled"}>↶<span>撤回</span></button><button data-action="redo-canvas" aria-label="重做上一步" ${state.canvasFuture.length ? "" : "disabled"}>↷<span>重做</span></button></div>`;
  }
  function livePieces() {
    const pieces = state.current?.items || [];
    if (!pieces.length) return '<div class="empty-stage"><span>选择下方单品，搭出你喜欢的样子</span></div>';
    pieces.forEach(p=>preparePiece(p.src));
    if(pieces.some(p=>!trimmedPieces.get(p.src)?.ready)) return '<div class="empty-stage" role="status"><span>正在整理搭配…</span></div>';
    const boxes=window.SelfitOutfitLayout.layout(pieces);
    const selectedBox=boxes.find(box=>box.id===state.canvasSelection);
    return `<div class="outfit-composition" aria-label="当前搭配">${boxes.map(box=>{
      const p=pieces.find(p=>p.id===box.id);
      return `<button class="composition-piece" data-canvas-piece="${esc(p.id)}" aria-label="选择画布单品：${esc(p.name)}" aria-pressed="${state.canvasSelection === p.id}" style="left:${box.x}%;top:${box.y}%;width:${box.w}%;height:${box.h}%;z-index:${box.z}">${image(trimmedPieces.get(p.src).src,p.name)}</button>`;
    }).join("")}</div>${selectedBox ? `<div class="composition-actions"><button class="canvas-remove" data-action="remove-piece" aria-label="从画布移除选中单品" style="left:${selectedBox.x+selectedBox.w}%;top:${selectedBox.y}%"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 10v7m4-7v7"/></svg></button></div>` : ""}`;
  }
  function closet() {
    if (state.loading)
      return `<section class="closet-screen"><p class="empty" role="status">正在打开衣帽间…</p></section>`;
    const list =
      state.closetCategory === "set"
        ? state.outfits
        : state.items.filter(
            (x) => categoryGroup(x.category) === state.closetCategory,
          );
    return `<section class="closet-screen" aria-label="衣帽间">${categories(false)}<div class="closet-grid"><button class="add-garment" data-action="add" aria-label="添加衣服"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg></button>${list.map((x) => card(x, state.closetCategory === "set" ? "outfit" : "item")).join("")}</div>${!list.length ? empty(state.error || "把喜欢的衣服放进衣帽间。") : ""}</section>`;
  }
  function feedCard(x) {
    return `<article class="feed-card ${x.flat ? "flat" : ""}"><button class="feed-open" data-detail="${esc(x.id)}" aria-label="查看${esc(x.name)}">${image(reference && state.page === "closet" && kind === "outfit" ? `${A}closet-outfit.svg` : x.src, x.name)}</button>${x.saved ? image(asset("star"), "已收藏", "favorite-star") : ""}<button class="try-chip" data-try="${esc(x.id)}">试穿</button></article>`;
  }
  function inspiration() {
    if (state.loading)
      return `<section class="inspiration-screen"><p class="empty" role="status">正在整理穿搭库…</p></section>`;
    return `<section class="inspiration-screen" aria-label="灵感库"><div class="feed">${[
      0, 1,
    ]
      .map(
        (col) =>
          `<div class="feed-column">${state.feed
            .filter((_, i) => i % 2 === col)
            .map(feedCard)
            .join("")}</div>`,
      )
      .join(
        "",
      )}</div>${!state.feed.length ? empty(state.error || (state.profileRequired ? "完成风格测试后，为你推荐穿搭。" : "暂时没有可用穿搭，可以重新加载或添加衣服。")) : ""}${!reference && state.feedMore ? `<button class="secondary load-more" data-action="more">${state.feedBusy ? "正在加载…" : "查看更多穿搭"}</button>` : ""}</section>`;
  }
  function detail() {
    if (state.loading)
      return `<section class="detail-screen"><p class="empty" role="status">正在打开这套穿搭…</p></section>`;
    const x = state.current;
    if (!x) return empty("先选择一套搭配。");
    const items = x.items || state.items;
    return `<section class="detail-screen" aria-label="套装详情"><div class="detail-top"><button class="back" data-action="back" aria-label="返回"><svg viewBox="0 0 24 24"><path d="m15 4-7 8 7 8"/></svg></button><button class="favorite" data-action="favorite" aria-label="${x.saved ? "取消收藏" : "收藏套装"}" aria-pressed="${Boolean(x.saved)}">${image(asset("star"), "")}</button></div>${x.raw?.can_delete ? '<button class="delete-outfit" data-action="delete-outfit">删除穿搭</button>' : ""}${image(x.src, x.name, "detail-photo")}<div class="detail-items">${(reference ? [...items, items[2], items[0], items[1], items[2], items[0], items[1]] : items).map((i) => card(i)).join("")}</div></section><div class="detail-dock"><button class="secondary" data-action="style">自由搭配</button><button class="primary" data-action="try">试穿套装</button></div>`;
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
  function render() {
    if (reference) $("#studio").setAttribute("data-reference", "true");
    nav();
    $("#screen").innerHTML = { mirror: readyMirror, closet, inspiration, detail }[
      state.page
    ]();
    $("#studio").dataset.screen = state.page;
    $("#studio").dataset.mode = state.styling ? "styling" : "model";
    bindScroll();
  }
  function go(page, push = true) {
    state.page = page;
    render();
    $("#screen").scrollTop = 0;
    if (push) {
      const u = new URL(location.href);
      u.searchParams.set("screen", page);
      if (state.current?.id && !reference)
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
      ...state.feed,
      ...state.outfits,
      ...state.items,
      ...state.feed.flatMap((x) => x.items),
      ...(state.current?.items || []),
    ].find((x) => x.id === id);
  }
  function openAppDetail(id, replace = false) {
    const url = new URL("/wearwow/demo", location.origin);
    url.searchParams.set("outfit", id);
    url.searchParams.set("from", "tryon");
    url.searchParams.set("return_screen", ["closet", "inspiration", "mirror"].includes(state.page) ? state.page : "closet");
    if (replace) location.replace(url.href);
    else location.assign(url.href);
  }
  function showDetail(id) {
    if (!reference) return openAppDetail(id);
    state.current = lookup(id);
    state.result = "";
    preflight = null;
    if (!state.current) return;
    state.returnPage = state.page;
    go("detail");
  }
  function modal(title, body) {
    $("#sheet").innerHTML =
      `<h2 id="sheetTitle">${esc(title)}</h2><button class="close" data-action="close" aria-label="关闭">×</button>${body}`;
    if (!$("#sheet").open) $("#sheet").showModal();
  }
  async function loadModels() {
    const data = await api("/selfit/try-on/models");
    state.modelLibrary = data.items || [];
  }
  async function models() {
    modal("选择模特", '<p role="status">正在打开模特库…</p>');
    try {
      await loadModels();
      modal(
        "选择模特",
        `<div class="model-library">${state.modelLibrary.map((m) => `<button class="model-option" data-model-id="${esc(m.id)}" aria-label="选择${esc(m.name)}" aria-pressed="${state.modelId === m.id}">${image(m.image_url, m.name)}<span>${esc(m.name)}</span><small>${esc(m.gender_label || "")}${m.body_type_label ? " · " + esc(m.body_type_label) : ""}</small></button>`).join("")}</div>${!state.modelLibrary.length ? "<p>模特库暂无可用模特，可以先上传自己的照片。</p>" : ""}<div class="model-personal">${state.personalPhoto ? `<button class="secondary" data-model-id="self">使用我的照片</button>` : ""}<button class="secondary" data-action="upload-photo">${state.personalPhoto ? "更换我的照片" : "上传我的照片"}</button></div><p>选择与你体型接近的模特，或使用自己的全身照。</p>`,
      );
    } catch {
      modal(
        "选择模特",
        '<p>模特库暂时无法读取，请重试。</p><button class="primary" data-action="model">重新加载</button>',
      );
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
    preflight = null;
    $("#sheet").close();
    render();
    notify(id === "self" ? "已选择我的照片" : `已选择${saved.model.name}`);
    if (state.pendingTry) {
      state.pendingTry = false;
      await startTry();
    }
  }
  function chooseItem(id) {
    const x = lookup(id);
    if (!x) return;
    if (!reference) rememberCanvas();
    state.result = "";
    if (reference) {
      if (x.category === "top") state.top = x.id;
      else if (x.category === "bottom") state.bottom = x.id;
    } else {
      state.current = {
        id: "",
        name: "我的搭配",
        items: window.SelfitOutfitLayout.replacePiece(
          state.page === "closet" ? [] : (state.current?.items || []), x,
        ),
        src: x.src,
      };
    }
    state.selected = new Set(reference ? [id] : state.current.items.map(item => item.id));
    preflight = null;
    state.styling = true;
    go("mirror");
    notify(`已选${x.name}`);
  }
  async function photoFile() {
    if (state.file) return state.file;
    if (!state.photo) throw Error("先选择模特或上传全身照。");
    const response = await fetch(mediaURL(state.photo));
    if (!response.ok) throw Error("这张照片暂时无法使用，请重新上传。");
    const blob = await response.blob();
    return new File(
      [blob],
      state.modelId && state.modelId !== "self"
        ? new URL(state.photo, location.origin).pathname.split("/").pop()
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
    if (reference) {
      modal(
        "试穿预览",
        `${image(state.current.src, "原稿示例", "progress-art")}<p>当前是设计稿示例。正式试穿将使用你的照片和衣橱单品生成结果。</p><button class="primary" data-action="reference-result">查看原稿效果</button>`,
      );
      return;
    }
    const target = state.current;
    modal("确认试穿", '<p role="status">正在确认照片中可替换的单品…</p>');
    try {
      if (!target.id) {
        const saved = await api("/selfit/try-on/outfits", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            item_ids: (target.items || []).map((x) => x.id),
            title: "我的搭配",
          }),
        });
        target.id = saved.outfit_id;
      }
      const file = await photoFile(),
        body = new FormData();
      body.append("person_image", file);
      body.append("outfit_id", target.id);
      body.append("photo_mode", "standard");
      const plan = await api("/selfit/try-on/preview-plan", {
        method: "POST",
        body,
      });
      preflight = { plan, file, outfitId: target.id, photo: state.photo };
      requestId = crypto.randomUUID();
      state.selected = new Set(
        (plan.pieces || [])
          .filter((p) => p.status !== "not_visible")
          .map((p) => String(p.item_id)),
      );
      modal(
        "确认试穿",
        `<p>${esc(plan.photo_summary || "选择这次想替换的单品")}</p><div class="piece-options">${(plan.pieces || []).map((p) => `<label><input type="checkbox" data-piece="${esc(p.item_id)}" ${p.status === "not_visible" ? "disabled" : "checked"}>${p.image_path ? image(p.image_path, "") : ""}<span>${esc(p.category_label || p.slot)}${p.status === "not_visible" ? " · 未入镜" : ""}</span></label>`).join("")}</div><button class="primary" data-action="generate">生成试穿图</button>`,
      );
    } catch (e) {
      modal(
        "这次还不能试穿",
        `<p>${esc(e.message)}</p><button class="secondary" data-action="model">更换照片</button><button class="primary" data-action="try">重新尝试</button>`,
      );
    }
  }
  async function generate() {
    if (!preflight || !state.selected.size)
      return notify("至少选择一件可替换的单品。");
    const slots = new Set(
      preflight.plan.pieces
        .filter((p) => state.selected.has(String(p.item_id)))
        .map((p) => p.slot),
    );
    if (
      slots.has("dress") &&
      ["top", "outer", "bottom", "skirt"].some((s) => slots.has(s))
    )
      return notify("连衣装与上下装只能选择一种穿法。");
    if (generationBusy) return;
    generationBusy = true;
    const submission = preflight;
    modal(
      "正在生成试穿图",
      `${image("/static/selfit/assets/loading-stage-25@2x.png", "", "progress-art")}<p id="jobCopy">正在让这套搭配更像你…</p><div class="progress"><i id="jobProgress"></i></div><button class="secondary" data-action="close">继续浏览</button>`,
    );
    try {
      const body = new FormData();
      body.append("person_image", submission.file);
      body.append("outfit_id", submission.outfitId);
      body.append("photo_mode", "standard");
      body.append("selected_item_ids", JSON.stringify([...state.selected]));
      body.append("client_request_id", requestId);
      state.job = await api("/selfit/try-on/jobs", { method: "POST", body });
      sessionStorage.setItem(
        "selfit.studio.job",
        JSON.stringify({
          job_id: state.job.job_id,
          outfit_id: submission.outfitId,
        }),
      );
      state.jobPhoto = submission.photo;
      poll();
    } catch (e) {
      failure(e.message);
    } finally {
      generationBusy = false;
    }
  }
  function failure(message) {
    modal(
      "试穿暂未完成",
      `<p>${esc(message || "请稍后重试，你选择的照片和搭配都已保留。")}</p><button class="primary" data-action="try">重新尝试</button><button class="secondary" data-action="model">更换照片</button>`,
    );
  }
  async function poll() {
    clearTimeout(pollTimer);
    if (!state.job?.job_id) return;
    try {
      const job = await api(
        `/selfit/try-on/jobs/${encodeURIComponent(state.job.job_id)}`,
      );
      state.job = job;
      if ($("#jobProgress"))
        $("#jobProgress").style.setProperty(
          "--progress",
          `${Math.min(98, Math.max(5, Number(job.progress) || 5))}%`,
        );
      if (job.status === "completed") {
        const src = job.result?.result?.image_path;
        if (!src) throw Error("未能取得试穿图，请重新尝试。");
        state.result = src;
        state.current =
          lookup(job.outfit_id) ||
          normalizeOutfit(
            await api(`/closet/outfits/${encodeURIComponent(job.outfit_id)}`),
            state.items,
          );
        state.photo = state.jobPhoto || state.photo;
        state.styling = false;
        $("#sheet").close();
        sessionStorage.removeItem("selfit.studio.job");
        go("mirror");
        notify("试穿图已经好了，按住可查看原图。");
        return;
      }
      if (job.status === "failed") {
        sessionStorage.removeItem("selfit.studio.job");
        throw Error("这次没有生成成功，可以更换照片后再试。");
      }
      pollTimer = setTimeout(poll, 1800);
    } catch (e) {
      failure(e.message);
    }
  }
  async function importGarment(retry = false) {
    if (!importFile && !importJob) return;
    modal(
      "正在整理这件衣服",
      '<p id="importCopy" role="status">正在上传图片，稍等一下…</p><button class="secondary" data-action="close">继续浏览</button>',
    );
    try {
      if (retry && importJob)
        importJob = await api(
          `/closet/import/jobs/${encodeURIComponent(importJob.job_id)}/retry`,
          { method: "POST" },
        );
      else {
        const body = new FormData();
        body.append("images", importFile);
        importJob = await api("/closet/import/jobs", { method: "POST", body });
      }
      pollImport();
    } catch (e) {
      importFailure(e.message);
    }
  }
  function importFailure(message) {
    modal(
      "衣服暂未加入",
      `<p>${esc(message)}</p><button class="primary" data-action="retry-import">重新尝试</button><button class="secondary" data-action="upload-garment">换张衣服图</button>`,
    );
  }
  async function pollImport() {
    clearTimeout(importTimer);
    try {
      const job = await api(
        `/closet/import/jobs/${encodeURIComponent(importJob.job_id)}`,
      );
      importJob = job;
      if (job.status === "failed")
        return importFailure(
          "这张图片暂时无法提取衣服，可以换一张清楚的图片。",
        );
      if (job.status === "completed") {
        await load();
        $("#sheet").close();
        state.closetCategory = "top";
        go("closet");
        notify("衣服已加入衣帽间。");
        return;
      }
      if ($("#importCopy"))
        $("#importCopy").textContent =
          `正在整理衣服 · ${Number(job.progress) || 0}%`;
      importTimer = setTimeout(pollImport, 1500);
    } catch (e) {
      importFailure(e.message);
    }
  }
  function normalizeItem(x) {
    return {
      id: x.item_id,
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
      name: x.title || "我的搭配",
      src:
        x.layout_snapshot_path || x.cover_path || x.cover || x.image_path || "",
      saved: Boolean(x.favorite),
      flat: Boolean(x.layout_snapshot_path),
      items: (x.items || []).map(normalizeItem).length
        ? (x.items || []).map(normalizeItem)
        : (x.item_ids || [])
            .map((id) => items.find((i) => i.id === id))
            .filter(Boolean),
      raw: x,
    };
  }
  async function loadPhoto() {
    if (state.photo) return;
    try {
      const r = await fetch("/api/v1/selfit/me/photos/body", {
        headers: { Authorization: `Bearer ${savedSession.accessToken}` },
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
      const data = await api("/closet/recommendations/outfits", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          persona: {},
          context: { season_tags: [season] },
          limit: 12,
          offset: append ? state.feedOffset : 0,
          session_id: append ? state.feedSession : null,
          cursor: append ? state.feedCursor : null,
          exclude_outfit_ids: append ? state.feed.map((x) => x.id) : [],
        }),
      });
      const incoming = [
        ...(append ? [] : data.carousel || []),
        ...(data.outfits || []),
      ].map((x) => normalizeOutfit(x, state.items));
      state.feed = uniqueItems([...(append ? state.feed : []), ...incoming]);
      for (const row of state.feed) {
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
      if (!savedSession?.accessToken)
        throw Error("登录后，查看你的衣橱与灵感搭配。");
      const results = await Promise.allSettled([
        api("/closet/items"),
        api("/closet/outfits"),
        api("/closet/preferences"),
      ]);
      if (
        results.some((r) => r.status === "rejected" && r.reason.status === 401)
      )
        throw Error("登录已过期，请重新登录。");
      state.items = (results[0].value?.items || []).map(normalizeItem);
      state.outfits = (results[1].value?.outfits || []).map((x) =>
        normalizeOutfit(x, state.items),
      );
      const preferences = results[2].value || {};
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
        loadFeed().catch(() => {
          state.feed = state.outfits;
          notify("穿搭库暂时无法更新，可重试加载。");
        }),
      ]);
      if (!state.photo) state.photo = fallback || "";
      state.personalPhoto = state.photo;
      state.personalFile = state.file;
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

      const id = new URLSearchParams(location.search).get("outfit");
      if (id) {
        const existing = [...state.outfits, ...state.feed].find(
          (x) => x.id === id,
        );
        state.current =
          existing ||
          normalizeOutfit(
            await api(`/closet/outfits/${encodeURIComponent(id)}`),
            state.items,
          );
      } else state.current ||= state.feed[0] || state.outfits[0] || null;
      state.error = "";
      if (id && state.current)
        state.page = ["mirror", "closet", "inspiration"].includes(params.get("screen")) ? params.get("screen") : "mirror";
      let job;
      try {
        job = JSON.parse(sessionStorage.getItem("selfit.studio.job") || "null");
      } catch {}
      if (job?.job_id) {
        state.job = job;
        poll();
      }
    } catch (e) {
      state.error = e.message;
    } finally {
      state.loading = false;
      render();
    }
  }
  function bindScroll() {
    const strip = $(".strip");
    if (strip)
      strip.addEventListener(
        "scroll",
        () => {
          const max = strip.scrollWidth - strip.clientWidth;
          const index =
            max > 0
              ? Math.min(
                  document.querySelectorAll("[data-dot]").length - 1,
                  Math.round(
                    (strip.scrollLeft / max) *
                      (document.querySelectorAll("[data-dot]").length - 1),
                  ),
                )
              : 0;
          document
            .querySelectorAll("[data-dot]")
            .forEach((b, i) =>
              b.setAttribute("aria-current", String(i === index)),
            );
        },
        { passive: true },
      );
  }
  $("#studio").addEventListener("click", async (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    try {
      if (b.dataset.canvasPiece) {
        state.canvasSelection=state.canvasSelection===b.dataset.canvasPiece ? "" : b.dataset.canvasPiece;
        render(); return;
      }
      if (b.dataset.action === "remove-piece") {
        const id=state.canvasSelection;
        if(!state.current?.items.some(p=>p.id===id)) return;
        rememberCanvas();
        state.current={...state.current,id:"",name:"我的搭配",items:state.current.items.filter(p=>p.id!==id)};
        state.selected=new Set(state.current.items.map(p=>p.id));
        state.result=""; preflight=null;
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
        state.result=""; preflight=null;
        render(); notify(redo ? "已重做上一步" : "已撤回上一步"); return;
      }
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
      if (b.dataset.detail) {
        showDetail(b.dataset.detail);
        return;
      }
      if (b.dataset.outfit) {
        if (!reference && state.page === "mirror") {
          const scrollLeft = $(".strip")?.scrollLeft || 0;
          rememberCanvas();
          state.current = lookup(b.dataset.outfit);
          state.result = "";
          preflight = null;
          go("mirror");
          if ($(".strip")) $(".strip").scrollLeft = scrollLeft;
          return;
        }
        showDetail(b.dataset.outfit);
        return;
      }
      if (b.dataset.item) {
        chooseItem(b.dataset.item);
        return;
      }
      if (b.dataset.try) {
        state.current = lookup(b.dataset.try);
        state.result = "";
        preflight = null;
        await startTry();
        return;
      }
      if (b.dataset.slot) {
        state.category = b.dataset.slot;
        render();
        return;
      }
      if (b.dataset.dot) {
        const strip = $(".strip");
        strip?.scrollTo({
          left:
            ((strip.scrollWidth - strip.clientWidth) * Number(b.dataset.dot)) /
            Math.max(1, document.querySelectorAll("[data-dot]").length - 1),
          behavior: "smooth",
        });
        return;
      }
      switch (b.dataset.action) {
        case "toggle":
          state.styling = !state.styling;
          go("mirror");
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
          const saved = !state.current.saved;
          b.disabled = true;
          if (!reference) {
            const own = state.outfits.find((x) => x.id === state.current.id);
            if (!own && saved) {
              const result = await api("/selfit/try-on/outfits", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  item_ids: state.current.items.map((x) => x.id),
                  title: state.current.name,
                  favorite: true,
                }),
              });
              const copy = normalizeOutfit(result, state.items);
              state.outfits = uniqueItems([...state.outfits, copy]);
              state.current.personalId = copy.id;
              state.items = uniqueItems([...state.items, ...copy.items]);
            } else
              await api(
                `/closet/outfits/${encodeURIComponent(state.current.personalId || state.current.id)}`,
                {
                  method: "PATCH",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ favorite: saved }),
                },
              );
          }
          const ownCopy = state.outfits.find(
            (x) => x.id === (state.current.personalId || state.current.id),
          );
          if (ownCopy) ownCopy.saved = saved;
          state.current.saved = saved;
          render();
          notify(saved ? "已收藏这套搭配" : "已取消收藏");
          break;
        }
        case "delete-outfit": {
          const target = state.current;
          if (!target?.raw?.can_delete) return;
          modal(
            "删除这套穿搭？",
            `<p>删除后将从我的穿搭中移除，衣橱单品和已生成的试穿图片会保留。</p><button class="secondary" data-action="close">取消</button><button class="primary" data-action="confirm-delete" data-delete-id="${esc(target.id)}">确认删除</button>`,
          );
          break;
        }
        case "confirm-delete": {
          const id = b.dataset.deleteId;
          b.disabled = true;
          try {
            await api(`/closet/outfits/${encodeURIComponent(id)}`, {
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
          preflight = null;
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
        case "generate":
          b.disabled = true;
          await generate();
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
      }
    } catch (error) {
      b.disabled = false;
      notify(error.message || "请稍后再试。");
    }
  });
  $("#sheet").addEventListener("change", (e) => {
    if (e.target.dataset.piece) {
      if (e.target.checked) state.selected.add(e.target.dataset.piece);
      else state.selected.delete(e.target.dataset.piece);
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
      state.items.unshift({
        id: `upload-${Date.now()}`,
        src: u,
        category: "top",
        name: "上传的上衣",
      });
      state.closetCategory = "top";
      $("#sheet").close();
      go("closet");
      notify("已加入本次预览的衣帽间。");
    } catch {
      URL.revokeObjectURL(u);
      notify("图片无法读取，请换一张。");
    }
    e.target.value = "";
  });
  $("#studio").addEventListener("pointerdown", (e) => {
    if (e.target.closest("[data-action=compare]")) {
      const im = $(".model-photo");
      if (im) im.src = mediaURL(state.photo);
    }
  });
  const restore = () => {
    const im = $(".model-photo");
    if (im && state.result) im.src = mediaURL(state.result);
  };
  window.addEventListener("pointerup", restore);
  window.addEventListener("pointercancel", restore);
  window.addEventListener("blur", restore);
  $("#studio").addEventListener("keydown", (e) => {
    if (
      e.target.closest("[data-action=compare]") &&
      [" ", "Enter"].includes(e.key)
    ) {
      e.preventDefault();
      const im = $(".model-photo");
      if (im) im.src = mediaURL(state.photo);
    }
  });
  $("#studio").addEventListener("keyup", restore);
  window.addEventListener("popstate", async () => {
    const p = new URLSearchParams(location.search);
    state.styling = p.get("mode") === "styling";
    if (!reference && p.get("outfit")) {
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
      ["mirror", "closet", "inspiration", "detail"].includes(p.get("screen"))
        ? p.get("screen")
        : "mirror",
      false,
    );
  });
  window.addEventListener("pagehide", () => {
    clearTimeout(pollTimer);
    clearTimeout(importTimer);
    state.uploadURLs.forEach(URL.revokeObjectURL);
  });
  if (!reference && state.page === "detail" && params.get("outfit")) {
    openAppDetail(params.get("outfit"), true);
  } else {
    render();
    load();
  }
})();
