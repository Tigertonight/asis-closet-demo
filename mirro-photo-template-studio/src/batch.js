import JSZip from "jszip";

const $ = (selector, root = document) => root.querySelector(selector);

const statusCopy = {
  pending: "未处理",
  processing: "处理中",
  completed: "已完成",
  failed: "处理失败",
};

const formatBytes = (bytes) => {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
};

const escapeHtml = (value) => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

const safeFileBase = (name) => name
  .replace(/\.[^.]+$/, "")
  .replace(/[\\/:*?"<>|]/g, "-")
  .trim() || "mirro-photo";

export function createBatchController(options) {
  const {
    templates,
    processItem,
    openStudio,
    showToast,
    setBusy,
  } = options;

  const batch = {
    items: [],
    selected: new Set(),
    template: "wineClassic",
    processing: false,
    exporting: false,
    sequence: 0,
  };

  const input = $("#batchInput");
  const rows = $("#batchRows");
  const selectAll = $("#selectAllBatch");
  const templateSelect = $("#batchTemplate");
  const processButton = $("#batchProcessButton");
  const exportButton = $("#batchExportButton");

  function counts() {
    const completed = batch.items.filter((item) => item.status === "completed").length;
    const processing = batch.items.filter((item) => item.status === "processing").length;
    return {
      total: batch.items.length,
      completed,
      processing,
      pending: batch.items.length - completed,
      selected: batch.selected.size,
      selectedCompleted: batch.items.filter((item) => batch.selected.has(item.id) && item.status === "completed").length,
    };
  }

  function render() {
    const summary = counts();
    $("#totalCount").textContent = summary.total;
    $("#pendingCount").textContent = summary.pending;
    $("#completedCount").textContent = summary.completed;
    $("#selectedCount").textContent = `已选 ${summary.selected} 张`;
    $("#batchEmpty").hidden = summary.total > 0;
    $("#batchTableWrap").hidden = summary.total === 0;
    $("#batchFoot").hidden = summary.total === 0;
    $("#batchFootSummary").textContent = summary.processing
      ? `${summary.processing} 张正在处理`
      : `${summary.completed} 张已完成 · ${summary.pending} 张未完成`;

    selectAll.checked = summary.total > 0 && summary.selected === summary.total;
    selectAll.indeterminate = summary.selected > 0 && summary.selected < summary.total;
    processButton.disabled = batch.processing || batch.exporting || summary.selected === 0;
    processButton.textContent = batch.processing ? "正在处理…" : `处理选中${summary.selected ? ` · ${summary.selected}` : ""}`;
    exportButton.disabled = batch.processing || batch.exporting || summary.selectedCompleted === 0;
    exportButton.lastChild.textContent = batch.exporting ? " 正在打包…" : ` 批量导出${summary.selectedCompleted ? ` · ${summary.selectedCompleted}` : ""}`;
    templateSelect.disabled = batch.processing;

    rows.innerHTML = batch.items.map((item) => {
      const selected = batch.selected.has(item.id);
      const templateId = item.status === "completed" ? item.template : batch.template;
      const template = templates[templateId] || templates.wineClassic;
      const disabled = batch.processing ? "disabled" : "";
      return `
        <tr class="${selected ? "is-selected" : ""}" data-id="${item.id}">
          <td>
            <label class="row-check" aria-label="选择 ${escapeHtml(item.name)}">
              <input type="checkbox" data-action="select" ${selected ? "checked" : ""} ${disabled} />
              <i></i>
            </label>
          </td>
          <td>
            <div class="batch-photo-info">
              <img src="${item.url}" alt="" />
              <span><b title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</b><small>${formatBytes(item.size)}</small></span>
            </div>
          </td>
          <td><span class="batch-template-name">${escapeHtml(template.name)}<br>${template.width} × ${template.height}</span></td>
          <td><span class="status-badge ${item.status}">${statusCopy[item.status]}</span></td>
          <td>
            <div class="batch-progress ${item.status}">
              <span class="batch-progress-track"><i style="width:${item.progress}%"></i></span>
              <small>${item.progress}%</small>
            </div>
          </td>
          <td>
            <div class="row-actions">
              <button class="row-icon-button" data-action="edit" ${disabled}>Studio</button>
              <button class="row-icon-button" data-action="remove" ${disabled} aria-label="移除 ${escapeHtml(item.name)}">移除</button>
            </div>
          </td>
        </tr>`;
    }).join("");
  }

  function addFiles(fileList) {
    const files = [...fileList];
    const valid = files.filter((file) => file.type.startsWith("image/") && file.size <= 25 * 1024 * 1024);
    const available = Math.max(0, 100 - batch.items.length);
    const accepted = valid.slice(0, available);
    accepted.forEach((file) => {
      batch.sequence += 1;
      const id = `photo-${Date.now()}-${batch.sequence}`;
      batch.items.push({
        id,
        file,
        name: file.name,
        size: file.size,
        url: URL.createObjectURL(file),
        status: "pending",
        progress: 0,
        template: batch.template,
        outputBlob: null,
      });
      batch.selected.add(id);
    });
    render();
    if (accepted.length) showToast(`已加入 ${accepted.length} 张照片`);
    if (accepted.length < files.length) showToast(`已加入 ${accepted.length} 张；非图片、超出 25MB 或超过 100 张的文件已跳过`);
  }

  function updateItem(item, patch) {
    Object.assign(item, patch);
    render();
  }

  async function processSelected() {
    if (batch.processing) return;
    const queue = batch.items.filter((item) => batch.selected.has(item.id));
    if (!queue.length) return;
    batch.processing = true;
    render();

    for (const item of queue) {
      if (item.outputBlob) item.outputBlob = null;
      updateItem(item, { status: "processing", progress: 3, template: batch.template });
      try {
        const blob = await processItem(item, batch.template, (progress) => {
          item.progress = progress;
          render();
        });
        updateItem(item, { status: "completed", progress: 100, outputBlob: blob, error: "" });
      } catch (error) {
        console.error(error);
        updateItem(item, { status: "failed", progress: 0, outputBlob: null, error: error.message });
      }
    }

    batch.processing = false;
    render();
    const summary = counts();
    showToast(`处理完成：${summary.completed} 张可导出`);
  }

  async function exportSelected() {
    if (batch.exporting) return;
    const completed = batch.items.filter((item) => batch.selected.has(item.id) && item.status === "completed" && item.outputBlob);
    if (!completed.length) return;
    batch.exporting = true;
    render();
    setBusy(true, `正在打包 0 / ${completed.length} 张…`);

    try {
      const zip = new JSZip();
      const usedNames = new Map();
      completed.forEach((item, index) => {
        const base = `${safeFileBase(item.name)}-${item.template}`;
        const seen = usedNames.get(base) || 0;
        usedNames.set(base, seen + 1);
        const filename = `${base}${seen ? `-${seen + 1}` : ""}.png`;
        zip.file(filename, item.outputBlob);
        setBusy(true, `正在打包 ${index + 1} / ${completed.length} 张…`);
      });
      const blob = await zip.generateAsync(
        { type: "blob", compression: "DEFLATE", compressionOptions: { level: 6 } },
        (meta) => setBusy(true, `正在生成 ZIP · ${Math.round(meta.percent)}%`),
      );
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `mirro-batch-${new Date().toISOString().slice(0, 10)}.zip`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(link.href), 1200);
      showToast(`已导出 ${completed.length} 张成片`);
    } catch (error) {
      console.error(error);
      showToast("批量导出失败，请重试");
    } finally {
      batch.exporting = false;
      setBusy(false);
      render();
    }
  }

  function removeItem(id) {
    const index = batch.items.findIndex((item) => item.id === id);
    if (index < 0) return;
    const [item] = batch.items.splice(index, 1);
    URL.revokeObjectURL(item.url);
    batch.selected.delete(id);
    render();
  }

  rows.addEventListener("change", (event) => {
    const action = event.target.dataset.action;
    if (action !== "select") return;
    const id = event.target.closest("tr").dataset.id;
    if (event.target.checked) batch.selected.add(id);
    else batch.selected.delete(id);
    render();
  });

  rows.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button || batch.processing) return;
    const id = button.closest("tr").dataset.id;
    const item = batch.items.find((candidate) => candidate.id === id);
    if (!item) return;
    if (button.dataset.action === "remove") removeItem(id);
    if (button.dataset.action === "edit") openStudio(item, item.status === "completed" ? item.template : batch.template);
  });

  selectAll.addEventListener("change", () => {
    if (selectAll.checked) batch.items.forEach((item) => batch.selected.add(item.id));
    else batch.selected.clear();
    render();
  });
  templateSelect.addEventListener("change", () => {
    batch.template = templateSelect.value;
    render();
  });
  processButton.addEventListener("click", processSelected);
  exportButton.addEventListener("click", exportSelected);
  [$("#batchImportButton"), $("#batchEmptyButton")].forEach((button) => button.addEventListener("click", () => input.click()));
  input.addEventListener("change", () => {
    addFiles(input.files);
    input.value = "";
  });

  render();
  return {
    addFiles,
    hasItems: () => batch.items.length > 0,
    isBusy: () => batch.processing || batch.exporting,
  };
}
