import { createBatchController } from "./batch.js";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const canvas = $("#templateCanvas");
const ctx = canvas.getContext("2d", { alpha: false, willReadFrequently: true });
const shell = $("#canvasShell");
const emptyOverlay = $("#emptyOverlay");
const photoInput = $("#photoInput");
const lutInput = $("#lutInput");

const templates = {
  wineClassic: {
    name: "酒红硬边框",
    width: 1080,
    height: 1440,
    slot: { x: 356, y: 417, w: 370, h: 604 },
    overlayUrl: "/assets/templates/material-single/wine-classic.png",
  },
  silverClassic: {
    name: "银灰硬边框",
    width: 1080,
    height: 1440,
    slot: { x: 356, y: 417, w: 370, h: 604 },
    overlayUrl: "/assets/templates/material-single/silver-classic.png",
  },
  silverLace: {
    name: "银灰蕾丝框",
    width: 1080,
    height: 1440,
    slot: { x: 356, y: 422, w: 370, h: 600 },
    overlayUrl: "/assets/templates/material-single/silver-lace.png",
  },
  wineLace: {
    name: "酒红蕾丝框",
    width: 1080,
    height: 1440,
    slot: { x: 356, y: 422, w: 370, h: 600 },
    overlayUrl: "/assets/templates/material-single/wine-lace.png",
  },
};

const state = {
  view: "library",
  template: "wineClassic",
  sourceImage: null,
  sourceUrl: "",
  processedCanvas: null,
  skinLut: null,
  backgroundLut: null,
  customCube: null,
  customLutName: "",
  lutStrength: 80,
  vignette: 50,
  softness: 10,
  grain: 50,
  exposure: 0,
  photoScale: 100,
  offsetX: 0,
  offsetY: 0,
  previewZoom: 56,
  compare: false,
  headline: "此刻，刚刚好",
  subline: "MIRRO PORTRAIT · SHANGHAI",
  showDate: true,
  renderToken: 0,
  isDragging: false,
  dragStart: null,
};

let batchController;

const clamp = (value, min = 0, max = 1) => Math.min(max, Math.max(min, value));

function drawCover(context, image, slot, scale = 1, offsetX = 0, offsetY = 0) {
  const sourceW = image.width;
  const sourceH = image.height;
  const baseScale = Math.max(slot.w / sourceW, slot.h / sourceH) * scale;
  const drawW = sourceW * baseScale;
  const drawH = sourceH * baseScale;
  const availableX = Math.max(0, (drawW - slot.w) / 2);
  const availableY = Math.max(0, (drawH - slot.h) / 2);
  const dx = slot.x + (slot.w - drawW) / 2 + (offsetX / 100) * availableX;
  const dy = slot.y + (slot.h - drawH) / 2 + (offsetY / 100) * availableY;
  context.drawImage(image, dx, dy, drawW, drawH);
}

function drawMaterialTemplate(context, image, raw = false) {
  const template = templates[state.template] || templates.wineClassic;
  const slot = template.slot;
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, template.width, template.height);
  context.save();
  context.beginPath();
  context.rect(slot.x, slot.y, slot.w, slot.h);
  context.clip();
  drawCover(context, image, slot, state.photoScale / 100, state.offsetX, state.offsetY);
  if (!raw && state.vignette > 0) {
    const gradient = context.createRadialGradient(
      slot.x + slot.w / 2,
      slot.y + slot.h / 2,
      Math.min(slot.w, slot.h) * 0.18,
      slot.x + slot.w / 2,
      slot.y + slot.h / 2,
      Math.max(slot.w, slot.h) * 0.7,
    );
    gradient.addColorStop(0, "rgba(22,14,10,0)");
    gradient.addColorStop(1, `rgba(22,14,10,${(state.vignette / 100) * 0.22})`);
    context.fillStyle = gradient;
    context.fillRect(slot.x, slot.y, slot.w, slot.h);
  }
  context.restore();
  if (template.overlayImage) context.drawImage(template.overlayImage, 0, 0, template.width, template.height);
}

function renderTemplate() {
  const template = templates[state.template];
  if (canvas.width !== template.width || canvas.height !== template.height) {
    canvas.width = template.width;
    canvas.height = template.height;
  }
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!state.sourceImage) {
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    if (template.overlayImage) ctx.drawImage(template.overlayImage, 0, 0, template.width, template.height);
    return;
  }
  const image = state.compare ? state.sourceImage : (state.processedCanvas || state.sourceImage);
  drawMaterialTemplate(ctx, image, state.compare);
}

function getPixel(data, width, height, x, y) {
  const px = clamp(Math.round(x), 0, width - 1);
  const py = clamp(Math.round(y), 0, height - 1);
  const index = (py * width + px) * 4;
  return [data[index], data[index + 1], data[index + 2]];
}

function samplePngLut(lut, r, g, b) {
  const blue = b * 63;
  const b0 = Math.floor(blue);
  const b1 = Math.ceil(blue);
  const sampleSlice = (slice) => {
    const qx = slice % 8;
    const qy = Math.floor(slice / 8);
    const x = qx * 64 + 0.5 + 63 * r;
    // The source shader flips Y because OpenGL texture coordinates start at
    // the bottom. Canvas pixel rows already start at the top, so no flip is
    // needed here.
    const y = qy * 64 + 0.5 + 63 * g;
    return getPixel(lut.data, lut.width, lut.height, x, y);
  };
  const a = sampleSlice(b0);
  const c = sampleSlice(b1);
  const mix = blue - b0;
  return [
    (a[0] + (c[0] - a[0]) * mix) / 255,
    (a[1] + (c[1] - a[1]) * mix) / 255,
    (a[2] + (c[2] - a[2]) * mix) / 255,
  ];
}

function sampleCubeLut(cube, r, g, b) {
  const n = cube.size;
  const cr = clamp(r) * (n - 1);
  const cg = clamp(g) * (n - 1);
  const cb = clamp(b) * (n - 1);
  const r0 = Math.floor(cr), r1 = Math.min(r0 + 1, n - 1);
  const g0 = Math.floor(cg), g1 = Math.min(g0 + 1, n - 1);
  const b0 = Math.floor(cb), b1 = Math.min(b0 + 1, n - 1);
  const fr = cr - r0, fg = cg - g0, fb = cb - b0;
  const at = (ri, gi, bi) => cube.data[(bi * n * n) + (gi * n) + ri];
  const lerp = (a, c, t) => a + (c - a) * t;
  const output = [0, 0, 0];
  for (let channel = 0; channel < 3; channel += 1) {
    const c00 = lerp(at(r0, g0, b0)[channel], at(r1, g0, b0)[channel], fr);
    const c10 = lerp(at(r0, g1, b0)[channel], at(r1, g1, b0)[channel], fr);
    const c01 = lerp(at(r0, g0, b1)[channel], at(r1, g0, b1)[channel], fr);
    const c11 = lerp(at(r0, g1, b1)[channel], at(r1, g1, b1)[channel], fr);
    output[channel] = lerp(lerp(c00, c10, fg), lerp(c01, c11, fg), fb);
  }
  return output;
}

function skinProbability(r, g, b) {
  const red = r * 255, green = g * 255, blue = b * 255;
  const max = Math.max(red, green, blue);
  const min = Math.min(red, green, blue);
  const rgbRule = red > 70 && green > 35 && blue > 20 && red > green && red > blue && (max - min) > 12;
  if (!rgbRule) return 0;
  const cb = 128 - 0.168736 * red - 0.331264 * green + 0.5 * blue;
  const cr = 128 + 0.5 * red - 0.418688 * green - 0.081312 * blue;
  const distance = Math.sqrt(((cb - 105) / 38) ** 2 + ((cr - 154) / 30) ** 2);
  return clamp(1.35 - distance, 0, 1);
}

async function createProcessedImage(token) {
  if (!state.sourceImage) return;
  const source = state.sourceImage;
  const maxSide = 1600;
  const ratio = Math.min(1, maxSide / Math.max(source.width, source.height));
  const width = Math.max(1, Math.round(source.width * ratio));
  const height = Math.max(1, Math.round(source.height * ratio));
  const work = document.createElement("canvas");
  work.width = width;
  work.height = height;
  const workCtx = work.getContext("2d", { willReadFrequently: true });
  workCtx.imageSmoothingEnabled = true;
  workCtx.imageSmoothingQuality = "high";
  const blurPx = (state.softness / 30) * 1.4;
  workCtx.filter = blurPx > 0.05 ? `blur(${blurPx}px)` : "none";
  const bleed = Math.ceil(blurPx * 3);
  workCtx.drawImage(source, -bleed, -bleed, width + bleed * 2, height + bleed * 2);
  workCtx.filter = "none";
  const imageData = workCtx.getImageData(0, 0, width, height);
  const data = imageData.data;
  const strength = state.lutStrength / 100;
  const exposure = 2 ** (state.exposure / 100);
  const grainStrength = (state.grain / 100) * 4.8;

  for (let i = 0; i < data.length; i += 4) {
    let r = clamp((data[i] / 255) * exposure);
    let g = clamp((data[i + 1] / 255) * exposure);
    let b = clamp((data[i + 2] / 255) * exposure);
    let mapped = [r, g, b];
    if (state.customCube) {
      mapped = sampleCubeLut(state.customCube, r, g, b);
    } else if (state.backgroundLut && state.skinLut) {
      const background = samplePngLut(state.backgroundLut, r, g, b);
      const skin = samplePngLut(state.skinLut, r, g, b);
      const skinMix = skinProbability(r, g, b);
      mapped = background.map((value, channel) => value + (skin[channel] - value) * skinMix);
    }
    r += (mapped[0] - r) * strength;
    g += (mapped[1] - g) * strength;
    b += (mapped[2] - b) * strength;
    const px = i / 4;
    const noise = ((((px * 9301 + 49297) % 233280) / 233280) - 0.5) * grainStrength;
    data[i] = clamp(r * 255 + noise, 0, 255);
    data[i + 1] = clamp(g * 255 + noise, 0, 255);
    data[i + 2] = clamp(b * 255 + noise, 0, 255);
  }

  if (token !== state.renderToken) return;
  workCtx.putImageData(imageData, 0, 0);
  state.processedCanvas = work;
  renderTemplate();
}

let processTimer;
function scheduleProcessing(immediate = false) {
  state.renderToken += 1;
  const token = state.renderToken;
  clearTimeout(processTimer);
  if (!state.sourceImage) {
    renderTemplate();
    return;
  }
  processTimer = setTimeout(() => createProcessedImage(token), immediate ? 0 : 90);
}

async function loadImageFromUrl(url) {
  const image = new Image();
  image.decoding = "async";
  image.src = url;
  await image.decode();
  return image;
}

async function loadLutImage(url) {
  const image = await loadImageFromUrl(url);
  const lutCanvas = document.createElement("canvas");
  lutCanvas.width = image.width;
  lutCanvas.height = image.height;
  const lutCtx = lutCanvas.getContext("2d", { willReadFrequently: true });
  lutCtx.drawImage(image, 0, 0);
  return lutCtx.getImageData(0, 0, image.width, image.height);
}

async function initializeLuts() {
  try {
    const [skin, background] = await Promise.all([
      loadLutImage("/assets/luts/filter-skin.png"),
      loadLutImage("/assets/luts/filter-bg.png"),
    ]);
    state.skinLut = skin;
    state.backgroundLut = background;
    if (state.sourceImage) scheduleProcessing(true);
  } catch (error) {
    showToast("LUT 资源加载失败，请刷新后重试");
    console.error(error);
  }
}

async function initializeTemplateAssets() {
  await Promise.all(Object.values(templates).map(async (template) => {
    template.overlayImage = await loadImageFromUrl(template.overlayUrl);
  }));
  renderTemplate();
}

async function loadPhoto(file) {
  if (!file || !file.type.startsWith("image/")) {
    showToast("请选择 JPG、PNG 或 WEBP 图片");
    return;
  }
  if (file.size > 25 * 1024 * 1024) {
    showToast("图片请控制在 25MB 以内");
    return;
  }
  const url = URL.createObjectURL(file);
  try {
    const image = await loadImageFromUrl(url);
    if (state.sourceUrl?.startsWith("blob:")) URL.revokeObjectURL(state.sourceUrl);
    state.sourceUrl = url;
    state.sourceImage = image;
    state.offsetX = 0;
    state.offsetY = 0;
    state.photoScale = 100;
    $("#photoScale").value = "100";
    updateRange($("#photoScale"));
    $("#photoScaleValue").value = "100%";
    $("#photoThumb").src = url;
    $("#photoButton").classList.add("has-photo");
    emptyOverlay.hidden = true;
    $("#dragHint").classList.add("is-visible");
    setTimeout(() => $("#dragHint").classList.remove("is-visible"), 1800);
    scheduleProcessing(true);
    showToast("照片已导入，正在套用撕拉片色彩");
  } catch (error) {
    URL.revokeObjectURL(url);
    showToast("无法读取这张图片，请换一张重试");
    console.error(error);
  }
}

function parseCube(text) {
  let size = 0;
  const values = [];
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    if (line.startsWith("LUT_3D_SIZE")) {
      size = Number(line.split(/\s+/)[1]);
      continue;
    }
    if (/^[+-]?(\d*\.)?\d+\s+[+-]?(\d*\.)?\d+\s+[+-]?(\d*\.)?\d+/.test(line)) {
      values.push(line.split(/\s+/).slice(0, 3).map(Number));
    }
  }
  if (!size || values.length !== size ** 3) throw new Error("Invalid .cube LUT");
  return { size, data: values };
}

async function loadCustomLut(file) {
  if (!file) return;
  try {
    if (file.name.toLowerCase().endsWith(".cube")) {
      state.customCube = parseCube(await file.text());
    } else if (file.type === "image/png") {
      const url = URL.createObjectURL(file);
      const lut = await loadLutImage(url);
      URL.revokeObjectURL(url);
      if (lut.width !== 512 || lut.height !== 512) throw new Error("PNG LUT must be 512×512");
      state.backgroundLut = lut;
      state.skinLut = lut;
      state.customCube = null;
    } else {
      throw new Error("Unsupported LUT");
    }
    state.customLutName = file.name;
    $("#lutMeta").textContent = `自定义 · ${file.name}`;
    scheduleProcessing(true);
    showToast("自定义 LUT 已应用");
  } catch (error) {
    showToast("LUT 无法识别，请检查格式或尺寸");
    console.error(error);
  }
}

function updateTemplateUi() {
  const template = templates[state.template];
  $$(".template-card").forEach((button) => {
    const active = button.dataset.template === state.template;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-checked", String(active));
  });
  const ratio = template.width / template.height;
  shell.style.aspectRatio = `${template.width} / ${template.height}`;
  shell.style.width = `${Math.round((state.previewZoom / 100) * Math.min(724, template.height * ratio))}px`;
  $("#canvasSize").textContent = `${template.width} × ${template.height} px`;
  renderTemplate();
}

function updateRange(input) {
  const min = Number(input.min || 0);
  const max = Number(input.max || 100);
  const value = Number(input.value);
  const progress = ((value - min) / (max - min)) * 100;
  input.style.setProperty("--range-progress", `${progress}%`);
}

function bindRange(id, key, suffix = "") {
  const input = $(`#${id}`);
  const output = $(`#${id}Value`);
  updateRange(input);
  input.addEventListener("input", () => {
    state[key] = Number(input.value);
    updateRange(input);
    output.value = `${input.value}${suffix}`;
    if (["lutStrength", "softness", "grain", "exposure"].includes(key)) scheduleProcessing();
    else renderTemplate();
  });
}

let toastTimer;
function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("is-visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("is-visible"), 2200);
}

function setBusy(visible, message = "正在生成高清图片…") {
  const exporting = $("#exporting");
  exporting.classList.toggle("is-visible", visible);
  exporting.setAttribute("aria-hidden", String(!visible));
  $("#exporting b").textContent = message;
}

function switchView(view) {
  state.view = view;
  document.body.classList.toggle("library-mode", view === "library");
  $("#libraryView").hidden = view !== "library";
  $("#studioView").hidden = view !== "studio";
  history.replaceState(null, "", view === "studio" ? "#studio" : "#library");
  if (view === "studio") renderTemplate();
}

function clearStudioPhoto() {
  if (state.sourceUrl?.startsWith("blob:")) URL.revokeObjectURL(state.sourceUrl);
  state.sourceUrl = "";
  state.sourceImage = null;
  state.processedCanvas = null;
  state.offsetX = 0;
  state.offsetY = 0;
  state.photoScale = 100;
  $("#photoInput").value = "";
  $("#photoThumb").removeAttribute("src");
  $("#photoButton").classList.remove("has-photo");
  emptyOverlay.hidden = false;
  renderTemplate();
}

async function openBatchPhotoInStudio(item, templateId) {
  state.template = templateId;
  switchView("studio");
  updateTemplateUi();
  $("#projectName").value = item.name.replace(/\.[^.]+$/, "");
  await loadPhoto(item.file);
}

const waitForPaint = () => new Promise((resolve) => requestAnimationFrame(() => resolve()));
const canvasToBlob = (targetCanvas) => new Promise((resolve, reject) => {
  targetCanvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error("Canvas export failed")), "image/png");
});

async function processBatchPhoto(item, templateId, onProgress) {
  onProgress(8);
  await waitForPaint();
  const image = await loadImageFromUrl(item.url);
  onProgress(20);
  state.template = templateId;
  state.sourceImage = image;
  state.processedCanvas = null;
  state.photoScale = 100;
  state.offsetX = 0;
  state.offsetY = 0;
  state.compare = false;
  state.renderToken += 1;
  const token = state.renderToken;
  await waitForPaint();
  onProgress(34);
  await createProcessedImage(token);
  if (!state.processedCanvas) throw new Error("Photo processing failed");
  onProgress(82);
  renderTemplate();
  await waitForPaint();
  onProgress(94);
  return canvasToBlob(canvas);
}

function resetAdjustments() {
  const defaults = { lutStrength: 80, vignette: 50, softness: 10, grain: 50, exposure: 0 };
  Object.entries(defaults).forEach(([key, value]) => {
    state[key] = value;
    const input = $(`#${key}`);
    input.value = String(value);
    updateRange(input);
    $(`#${key}Value`).value = String(value);
  });
  scheduleProcessing(true);
  showToast("已恢复原效果参数");
}

function resetProject() {
  resetAdjustments();
  state.template = "wineClassic";
  state.photoScale = 100;
  state.offsetX = 0;
  state.offsetY = 0;
  state.headline = "此刻，刚刚好";
  state.subline = "MIRRO PORTRAIT · SHANGHAI";
  state.showDate = true;
  $("#photoScale").value = "100";
  $("#headline").value = state.headline;
  $("#subline").value = state.subline;
  $("#showDate").checked = true;
  updateRange($("#photoScale"));
  $("#photoScaleValue").value = "100%";
  updateTemplateUi();
}

async function exportPng() {
  if (!state.sourceImage) {
    showToast("请先导入一张照片");
    photoInput.click();
    return;
  }
  setBusy(true, "正在生成高清图片…");
  await new Promise((resolve) => setTimeout(resolve, 80));
  renderTemplate();
  canvas.toBlob((blob) => {
    if (!blob) {
      setBusy(false);
      showToast("导出失败，请重试");
      return;
    }
    const link = document.createElement("a");
    const name = ($("#projectName").value.trim() || "mirro-photo").replace(/[\\/:*?"<>|]/g, "-");
    link.href = URL.createObjectURL(blob);
    link.download = `${name}-${state.template}.png`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    setBusy(false);
    showToast("高清 PNG 已导出");
  }, "image/png");
}

function pointerPosition(event) {
  const rect = canvas.getBoundingClientRect();
  return { x: event.clientX - rect.left, y: event.clientY - rect.top };
}

function bindEvents() {
  [$("#photoButton"), $("#emptyUploadButton")].forEach((button) => button.addEventListener("click", () => photoInput.click()));
  photoInput.addEventListener("change", () => loadPhoto(photoInput.files[0]));
  $("#lutButton").addEventListener("click", () => lutInput.click());
  lutInput.addEventListener("change", () => loadCustomLut(lutInput.files[0]));
  $("#exportButton").addEventListener("click", exportPng);
  $("#resetButton").addEventListener("click", resetProject);
  $("#backToLibrary").addEventListener("click", () => switchView("library"));
  $("#studioView .brand").addEventListener("click", (event) => { event.preventDefault(); switchView("library"); });
  $("#openBlankStudio").addEventListener("click", () => { clearStudioPhoto(); switchView("studio"); });
  $("#resetAdjustments").addEventListener("click", resetAdjustments);
  $("#centerPhoto").addEventListener("click", () => {
    state.offsetX = 0;
    state.offsetY = 0;
    renderTemplate();
    showToast("照片已居中");
  });

  $$(".template-card").forEach((button) => button.addEventListener("click", () => {
    state.template = button.dataset.template;
    updateTemplateUi();
  }));

  $$(".view-switch button").forEach((button) => button.addEventListener("pointerdown", () => {
    state.compare = button.dataset.view === "compare";
    $$(".view-switch button").forEach((item) => item.classList.toggle("is-active", item === button));
    renderTemplate();
  }));

  bindRange("lutStrength", "lutStrength");
  bindRange("vignette", "vignette");
  bindRange("softness", "softness");
  bindRange("grain", "grain");
  bindRange("exposure", "exposure");
  bindRange("photoScale", "photoScale", "%");

  $$(".inspector-tabs button").forEach((button) => button.addEventListener("click", () => {
    $$(".inspector-tabs button").forEach((item) => item.classList.toggle("is-active", item === button));
    $$(".tab-panel").forEach((panel) => panel.classList.toggle("is-active", panel.dataset.panel === button.dataset.tab));
  }));

  $("#headline").addEventListener("input", (event) => { state.headline = event.target.value; renderTemplate(); });
  $("#subline").addEventListener("input", (event) => { state.subline = event.target.value; renderTemplate(); });
  $("#showDate").addEventListener("change", (event) => { state.showDate = event.target.checked; renderTemplate(); });

  const setPreviewZoom = (next) => {
    state.previewZoom = clamp(next, 38, 82);
    $("#zoomValue").textContent = `${state.previewZoom}%`;
    updateTemplateUi();
  };
  $("#zoomOut").addEventListener("click", () => setPreviewZoom(state.previewZoom - 6));
  $("#zoomIn").addEventListener("click", () => setPreviewZoom(state.previewZoom + 6));

  canvas.addEventListener("pointerdown", (event) => {
    if (!state.sourceImage) return;
    state.isDragging = true;
    canvas.setPointerCapture(event.pointerId);
    state.dragStart = { ...pointerPosition(event), offsetX: state.offsetX, offsetY: state.offsetY };
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!state.isDragging) return;
    const current = pointerPosition(event);
    state.offsetX = clamp(state.dragStart.offsetX + (current.x - state.dragStart.x) * 0.6, -100, 100);
    state.offsetY = clamp(state.dragStart.offsetY + (current.y - state.dragStart.y) * 0.6, -100, 100);
    renderTemplate();
  });
  const endDrag = () => { state.isDragging = false; };
  canvas.addEventListener("pointerup", endDrag);
  canvas.addEventListener("pointercancel", endDrag);

  bindPhotoDrop();
}

function bindPhotoDrop() {
  const overlay = $("#dropOverlay");
  const dropTargets = $$('[data-drop-target="photo"]');
  let dragDepth = 0;

  const hasFiles = (event) => [...(event.dataTransfer?.types || [])].includes("Files");
  const showDropState = () => {
    $("#dropOverlay .drop-card b").textContent = state.view === "library" ? "松开鼠标，加入批次" : "松开鼠标，导入照片";
    $("#dropOverlay .drop-card small").textContent = state.view === "library" ? "可同时拖入多张 JPG、PNG、WEBP" : "支持 JPG、PNG、WEBP";
    overlay.classList.add("is-visible");
    overlay.setAttribute("aria-hidden", "false");
  };
  const clearDropState = () => {
    dragDepth = 0;
    overlay.classList.remove("is-visible");
    overlay.setAttribute("aria-hidden", "true");
    dropTargets.forEach((target) => target.classList.remove("is-dragging"));
  };

  window.addEventListener("dragenter", (event) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    dragDepth += 1;
    showDropState();
  });
  window.addEventListener("dragover", (event) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
  });
  window.addEventListener("dragleave", (event) => {
    if (!hasFiles(event)) return;
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) clearDropState();
  });
  window.addEventListener("drop", (event) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    const files = [...(event.dataTransfer?.files || [])];
    clearDropState();
    const imageFiles = files.filter((file) => file.type.startsWith("image/"));
    if (!imageFiles.length) {
      showToast("这里需要一张 JPG、PNG 或 WEBP 图片");
      return;
    }
    if (state.view === "library") batchController.addFiles(files);
    else loadPhoto(imageFiles[0]);
  });

  dropTargets.forEach((target) => {
    target.addEventListener("dragenter", (event) => {
      if (!hasFiles(event)) return;
      target.classList.add("is-dragging");
    });
    target.addEventListener("dragleave", () => target.classList.remove("is-dragging"));
  });
}

async function boot() {
  updateTemplateUi();
  await Promise.all([initializeLuts(), initializeTemplateAssets()]);
  batchController = createBatchController({
    templates,
    processItem: processBatchPhoto,
    openStudio: openBatchPhotoInStudio,
    showToast,
    setBusy,
  });
  bindEvents();
  switchView(location.hash === "#studio" ? "studio" : "library");
}

boot();
