const state = {
  config: null,
  aiConfig: null,
  aiKeyMenuOpen: false,
  aiKeyAdding: false,
  classes: [],
  models: [],
  specializedModels: [],
  specializedModelTasks: [],
  selectedTaskId: "__default__",
  selectedModelId: "",
  trainingResources: null,
  trainingResourceDetail: null,
  activeModelId: null,
  accessories: [],
  trainingPreview: null,
  accessoryCandidate: null,
  pendingDeleteAccessoryId: null,
  imageJobs: [],
  imageJobPollTimer: null,
  progressTimer: null,
  trainingProgressTimer: null,
  trainingRequestInFlight: false,
  selectedTrainingDatasetId: "",
  backgroundSets: [],
  selectedBackgroundSetId: "",
  progressValue: 0,
  inspectInput: {
    kind: "",
    url: "",
    fileName: "",
  },
  lastResult: null,
  labelExperimentResult: null,
  accessoryPendingFiles: [],
  accessoryPendingFileUrls: new Map(),
  accessoryDetailItem: null,
  accessoryDetailPendingFiles: [],
  accessoryDetailPendingFileUrls: new Map(),
  promptEntries: [],
  crop: null,
  camera: {
    devices: [],
    stream: null,
    selectedDeviceId: "",
    starting: false,
  },
  imageViewer: {
    items: [],
    index: 0,
  },
};

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value);
}

function isActiveImageJobStatus(status) {
  return status === "queued_for_codex_image_worker" || status === "queued" || status === "running";
}

const CLASS_LABEL_ZH = {
  Bottle: "瓶子",
  "Warranty Service Manual": "保修说明书",
  "Battery Instruction Manual": "电池说明书",
  "Download Service Manual": "下载说明书",
  "Service QR Manual": "二维码说明书",
  Manual: "说明书",
  "Unknown Manual": "未知说明书",
};

const STATUS_ZH = {
  running: "运行中",
  idle: "空闲",
  pending: "等待中",
  queued: "排队中",
  queued_for_codex_image_worker: "排队中",
  failed: "失败",
  stopped: "已停止",
  completed: "已完成",
  active: "启用",
  sample_generation_requested: "样本生成已请求",
  reference_uploaded: "素材已上传",
  normalized_text_ready: "文字规范化完成",
  needs_crop: "等待裁剪图",
  image_tool_plan_ready: "生成计划就绪",
  preview_ready: "预览已生成",
  requested: "训练已请求",
};

const PAPER_PRESETS = {
  A4: [210, 297],
  A5: [148, 210],
  A6: [105, 148],
};

const TEXT_CROP_BASE_SHORT_PX = 1240;
const TEXT_CROP_MAX_LONG_PX = 4096;
const TRAINING_IMAGE_SIZE_OPTIONS = [
  { value: "320", label: "320 px", meta: "快速验证" },
  { value: "416", label: "416 px", meta: "轻量训练" },
  { value: "512", label: "512 px", meta: "均衡" },
  { value: "640", label: "640 px", meta: "YOLO 常用" },
  { value: "768", label: "768 px", meta: "小物体更稳" },
  { value: "960", label: "960 px", meta: "高精度" },
  { value: "1024", label: "1024 px", meta: "高精度" },
  { value: "1280", label: "1280 px", meta: "更慢" },
];
const AI_PROVIDER_DEFAULTS = {
  gemini: {
    model: "gemini-2.5-flash-lite",
    base_url: "https://generativelanguage.googleapis.com/v1beta",
  },
};

function zhLabel(label) {
  return CLASS_LABEL_ZH[label] || label || "-";
}

function userJobLabel(label) {
  return String(label || "多角度视图")
    .replaceAll("Pose Collection", "多角度视图")
    .replaceAll("ImageWorker", "生成任务")
    .replaceAll("Image worker", "生成任务")
    .replaceAll("Codex CLI", "本地生成");
}

function toast(message) {
  const node = $("toast");
  node.textContent = message;
  node.classList.add("visible");
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => node.classList.remove("visible"), 2600);
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || response.statusText);
  }
  return response.json();
}

function setBusy(button, busy) {
  if (!button) return;
  button.disabled = busy;
  button.classList.toggle("is-busy", busy);
  if (busy) {
    button.setAttribute("aria-busy", "true");
  } else {
    button.removeAttribute("aria-busy");
  }
}

function modelVariantLabel(model) {
  if (model?.is_ai_detection || model?.variant === "ai_detection" || String(model?.id || "").startsWith("ai_detection")) return model?.label || "AI 检测";
  return model?.variant === "yolo_ocr" || model?.uses_ocr ? "YOLO + OCR" : "YOLO";
}

function taskAccessoryLabel(task) {
  const names = task?.accessory_names || [];
  return names.length ? names.join(" + ") : task?.label || task?.task_id || "通用配件合集";
}

function aiProviderMeta(status) {
  if (!status) return "";
  if (status.status === "ready") return `${status.model || "AI"} · 已配置`;
  if (status.status === "disabled") return "未启用 · 将返回结构化缺失";
  if (status.status === "missing_api_key") return "缺少 API Key · 将返回结构化缺失";
  if (status.status === "unsupported_provider") return "Provider 不支持";
  return status.message || status.status || "";
}

function aiStatusText(status) {
  if (status === "ready") return "已配置";
  if (status === "disabled") return "未启用";
  if (status === "missing_api_key") return "缺少 Key";
  if (status === "unsupported_provider") return "Provider 不支持";
  if (status === "invalid_base_url") return "URL 无效";
  return status || "未知";
}

function aiKeySourceText(source) {
  if (source === "env") return "环境变量";
  if (source === "local") return "本地";
  return "未设置";
}

function renderAiModelOptions(config) {
  const options = config.model_options?.length
    ? config.model_options
    : [
        { id: "gemini-2.5-flash-lite", label: "Gemini 2.5 Flash-Lite" },
        { id: "gemini-2.5-flash", label: "Gemini 2.5 Flash" },
        { id: "gemini-2.5-pro", label: "Gemini 2.5 Pro" },
        { id: "gemini-2.0-flash", label: "Gemini 2.0 Flash" },
        { id: "gemini-3.5-flash", label: "Gemini 3.5 Flash" },
      ];
  $("aiModel").innerHTML = options
    .map((item) => `<option value="${escapeAttr(item.id)}">${escapeHtml(item.label || item.id)}</option>`)
    .join("");
}

function localAiKeys(config = state.aiConfig || {}) {
  return Array.isArray(config.api_keys) ? config.api_keys : [];
}

function activeLocalAiKey(config = state.aiConfig || {}) {
  return localAiKeys(config).find((item) => item.id === config.active_key_id) || null;
}

function aiKeyMetaText(config, activeKey) {
  const keySource = aiKeySourceText(config.key_source);
  if (config.key_source === "env") {
    const sourceName = config.key_source_name ? ` · ${config.key_source_name}` : "";
    const localText = activeKey ? ` · 本地候选：${activeKey.label || "API Key"}` : "";
    return `当前来源：${keySource}${sourceName}${localText}`;
  }
  if (activeKey) return `当前来源：${keySource} · ${activeKey.masked_key || "****"}`;
  if (config.key_present) return `当前来源：${keySource} · ${config.masked_key || "****"}`;
  return "未设置 Key";
}

function renderAiKeyControl(config = state.aiConfig || {}) {
  const control = $("aiKeyControl");
  if (!control) return;
  const keys = localAiKeys(config);
  const activeKey = activeLocalAiKey(config);
  const isOpen = state.aiKeyMenuOpen || state.aiKeyAdding;
  const selectedLabel = activeKey
    ? `${activeKey.label || "API Key"} · ${activeKey.masked_key || "****"}`
    : config.key_source === "env" && config.masked_key
      ? `环境变量 · ${config.masked_key}`
      : "暂无本地 API Key";
  const keyRows = keys.length
    ? keys
        .map((item) => {
          const isActive = item.id === config.active_key_id;
          return `
            <div class="ai-key-option-row${isActive ? " active" : ""}">
              <button class="ai-key-option" type="button" data-select-ai-key="${escapeAttr(item.id)}">
                <span class="ai-key-option-copy">
                  <strong>${escapeHtml(item.label || "API Key")}</strong>
                  <small>${escapeHtml(item.masked_key || "****")}</small>
                </span>
                ${isActive ? `<span class="ai-key-current">当前</span>` : ""}
              </button>
              <button
                class="ai-key-delete"
                type="button"
                data-delete-ai-key="${escapeAttr(item.id)}"
                aria-label="删除 ${escapeAttr(item.label || "API Key")}"
                title="删除"
              >删除</button>
            </div>
          `;
        })
        .join("")
    : `<div class="ai-key-empty-row">暂无本地 API Key</div>`;
  const addRow = state.aiKeyAdding
    ? `
      <div class="ai-key-add-editor">
        <input id="aiKeyNewValue" type="password" autocomplete="off" placeholder="粘贴新的 API Key" />
        <button id="confirmAddAiKey" class="mini-secondary" type="button">添加</button>
        <button id="cancelAddAiKey" class="mini-secondary" type="button">取消</button>
      </div>
    `
    : `
      <button id="addAiKeyRow" class="ai-key-add-row" type="button">
        <span>+</span>
        <strong>添加 API Key</strong>
      </button>
    `;

  control.className = `ai-key-select${isOpen ? " open" : ""}`;
  control.innerHTML = `
    <button id="aiKeyTrigger" class="ai-key-trigger" type="button" aria-haspopup="listbox" aria-expanded="${isOpen ? "true" : "false"}">
      <span class="ai-key-trigger-copy">
        <strong>${escapeHtml(selectedLabel)}</strong>
        <small>${escapeHtml(aiKeyMetaText(config, activeKey))}</small>
      </span>
      <span class="ai-key-trigger-icon">⌄</span>
    </button>
    <div class="ai-key-menu" role="listbox" aria-label="API Key 列表">
      ${keyRows}
      ${addRow}
    </div>
  `;
  bindAiKeyControl();
  if (state.aiKeyAdding) requestAnimationFrame(() => $("aiKeyNewValue")?.focus());
}

function renderAiConfig() {
  if (!$("aiProvider")) return;
  const config = state.aiConfig || {};
  const defaults = AI_PROVIDER_DEFAULTS[config.provider] || AI_PROVIDER_DEFAULTS.gemini;
  $("aiProvider").value = "gemini";
  renderAiModelOptions(config);
  $("aiModel").value = config.model || defaults.model;
  $("aiBaseUrl").value = config.base_url || defaults.base_url;
  $("aiTimeout").value = config.timeout_seconds || 5;
  $("aiConfigStatus").textContent = aiStatusText(config.status);
  $("aiConfigStatus").className = `pill ${config.status === "ready" ? "ok" : config.status === "missing_api_key" ? "neutral" : "fail"}`;
  renderAiKeyControl(config);
}

async function refreshStatusAfterAiConfig() {
  const status = await api("/api/status");
  state.classes = status.classes;
  renderModels(status);
}

function currentAiSettingsPayload(extra = {}) {
  return {
    provider: "gemini",
    model: $("aiModel").value,
    base_url: $("aiBaseUrl").value.trim(),
    timeout_seconds: Number($("aiTimeout").value || 5),
    ...extra,
  };
}

async function postAiConfig(payload) {
  const result = await api("/api/ai/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  state.aiConfig = result;
  state.aiKeyAdding = false;
  state.aiKeyMenuOpen = false;
  renderAiConfig();
  await refreshStatusAfterAiConfig();
  return result;
}

async function saveAiConfig() {
  await postAiConfig(currentAiSettingsPayload());
}

async function selectAiKey(keyId, button = null) {
  if (!keyId) return;
  if (keyId === state.aiConfig?.active_key_id) {
    state.aiKeyMenuOpen = false;
    state.aiKeyAdding = false;
    renderAiKeyControl();
    return;
  }
  setBusy(button, true);
  try {
    await postAiConfig({ active_key_id: keyId });
    toast("API Key 已切换。");
  } catch (error) {
    toast(`切换 API Key 失败：${error.message}`);
  } finally {
    setBusy(button, false);
  }
}

async function addAiKeyFromControl(button = null) {
  const input = $("aiKeyNewValue");
  const apiKey = input?.value.trim() || "";
  if (!apiKey) {
    input?.focus();
    return toast("请输入新的 API Key。");
  }
  setBusy(button, true);
  try {
    await postAiConfig(currentAiSettingsPayload({ api_key: apiKey }));
    if (input) input.value = "";
    toast("API Key 已添加并启用。");
  } catch (error) {
    toast(`添加 API Key 失败：${error.message}`);
  } finally {
    setBusy(button, false);
  }
}

async function deleteAiKeyById(keyId, button = null) {
  const key = localAiKeys().find((item) => item.id === keyId);
  if (!key) return toast("要删除的 API Key 不存在。");
  if (!window.confirm(`确认删除 ${key.label || "API Key"}？`)) return;
  setBusy(button, true);
  try {
    if (keyId !== state.aiConfig?.active_key_id) {
      await api("/api/ai/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active_key_id: keyId }),
      });
    }
    const result = await api("/api/ai/config/key", { method: "DELETE" });
    state.aiConfig = result;
    state.aiKeyAdding = false;
    state.aiKeyMenuOpen = true;
    renderAiConfig();
    await refreshStatusAfterAiConfig();
    toast(result.active_key_id ? "API Key 已删除，已切换到下一把 Key。" : "API Key 已删除。");
  } catch (error) {
    toast(`删除 API Key 失败：${error.message}`);
  } finally {
    setBusy(button, false);
  }
}

function closeAiKeyControl() {
  if (!state.aiKeyMenuOpen && !state.aiKeyAdding) return;
  state.aiKeyMenuOpen = false;
  state.aiKeyAdding = false;
  renderAiKeyControl();
}

function bindAiKeyControl() {
  $("aiKeyTrigger")?.addEventListener("click", (event) => {
    event.stopPropagation();
    state.aiKeyMenuOpen = !state.aiKeyMenuOpen;
    state.aiKeyAdding = false;
    renderAiKeyControl();
  });
  document.querySelectorAll("[data-select-ai-key]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      selectAiKey(button.dataset.selectAiKey, button);
    });
  });
  document.querySelectorAll("[data-delete-ai-key]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      deleteAiKeyById(button.dataset.deleteAiKey, button);
    });
  });
  $("addAiKeyRow")?.addEventListener("click", (event) => {
    event.stopPropagation();
    state.aiKeyMenuOpen = true;
    state.aiKeyAdding = true;
    renderAiKeyControl();
  });
  $("cancelAddAiKey")?.addEventListener("click", (event) => {
    event.stopPropagation();
    state.aiKeyAdding = false;
    state.aiKeyMenuOpen = true;
    renderAiKeyControl();
  });
  $("confirmAddAiKey")?.addEventListener("click", (event) => {
    event.stopPropagation();
    addAiKeyFromControl($("confirmAddAiKey"));
  });
  $("aiKeyNewValue")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      addAiKeyFromControl($("confirmAddAiKey"));
    }
    if (event.key === "Escape") {
      event.preventDefault();
      closeAiKeyControl();
    }
  });
}

function accessoryAiProfileText(item) {
  const status = item?.ai_profile_status || {};
  if (status.source === "provider") return "AI画像已生成";
  if (item?.ai_profile) return "AI画像本地回退";
  return "AI画像待生成";
}

function closeCustomMenus(except = null) {
  document.querySelectorAll(".custom-menu.open").forEach((menu) => {
    if (menu !== except) {
      menu.classList.remove("open");
      menu.querySelector(".custom-menu-trigger")?.setAttribute("aria-expanded", "false");
    }
  });
}

function renderCustomMenu(menuId, options, selectedValue, onSelect) {
  const menu = $(menuId);
  if (!menu) return "";
  const enabledOptions = options.filter((item) => !item.disabled);
  const selected = options.find((item) => item.value === selectedValue && !item.disabled) || enabledOptions[0] || options[0] || null;
  menu.dataset.value = selected && !selected.disabled ? selected.value : "";
  menu.classList.toggle("is-empty", !options.length);
  menu.classList.toggle("is-disabled", !enabledOptions.length);
  menu.classList.toggle("has-thumbnails", options.some((item) => item.thumbnail));
  menu.classList.toggle("has-option-actions", options.some((item) => item.actionLabel));
  const selectedThumb = selected?.thumbnail
    ? `<img class="custom-menu-thumb" src="${escapeAttr(selected.thumbnail)}" alt="" loading="lazy" />`
    : "";
  menu.innerHTML = `
    <button class="custom-menu-trigger" type="button" aria-haspopup="listbox" aria-expanded="false" ${enabledOptions.length ? "" : "disabled"}>
      ${selectedThumb}
      <span>${escapeHtml(selected?.label || "暂无可选项")}</span>
      <small>${escapeHtml(selected?.meta || "")}</small>
    </button>
    <div class="custom-menu-popover" role="listbox">
      ${
        options.length
          ? options
              .map(
                (item) => `
                  <button
                    class="custom-menu-option${item.value === selected?.value ? " active" : ""}"
                    type="button"
                    role="option"
                    aria-selected="${item.value === selected?.value ? "true" : "false"}"
                    data-value="${escapeAttr(item.value)}"
                    ${item.disabled ? "disabled" : ""}
                  >
                    ${item.thumbnail ? `<img class="custom-menu-thumb" src="${escapeAttr(item.thumbnail)}" alt="" loading="lazy" />` : ""}
                    <span>${escapeHtml(item.label)}</span>
                    ${item.meta ? `<small>${escapeHtml(item.meta)}</small>` : ""}
                    ${item.actionLabel ? `<span class="custom-menu-option-action" role="button" tabindex="0" data-option-action="${escapeAttr(item.value)}">${escapeHtml(item.actionLabel)}</span>` : ""}
                  </button>
                `,
              )
              .join("")
          : `<div class="custom-menu-empty">暂无可选项</div>`
      }
    </div>
  `;
  menu.querySelector(".custom-menu-trigger")?.addEventListener("click", () => {
    const isOpen = menu.classList.toggle("open");
    closeCustomMenus(menu);
    menu.querySelector(".custom-menu-trigger")?.setAttribute("aria-expanded", isOpen ? "true" : "false");
  });
  menu.querySelector(".custom-menu-trigger")?.addEventListener("keydown", (event) => {
    if (!["ArrowDown", "Enter", " "].includes(event.key)) return;
    event.preventDefault();
    closeCustomMenus(menu);
    menu.classList.add("open");
    menu.querySelector(".custom-menu-trigger")?.setAttribute("aria-expanded", "true");
    menu.querySelector(".custom-menu-option:not(:disabled)")?.focus();
  });
  menu.querySelectorAll(".custom-menu-option").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.disabled) return;
      closeCustomMenus();
      onSelect(button.dataset.value || "");
    });
    button.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        button.click();
        return;
      }
      if (!["ArrowDown", "ArrowUp"].includes(event.key)) return;
      event.preventDefault();
      const enabled = Array.from(menu.querySelectorAll(".custom-menu-option:not(:disabled)"));
      const index = enabled.indexOf(button);
      const next = event.key === "ArrowDown" ? enabled[index + 1] || enabled[0] : enabled[index - 1] || enabled[enabled.length - 1];
      next?.focus();
    });
  });
  menu.querySelectorAll(".custom-menu-option-action").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
    });
    button.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      event.stopPropagation();
      button.click();
    });
  });
  return menu.dataset.value;
}

function setProgress(value, title, detail) {
  state.progressValue = Math.max(0, Math.min(100, value));
  $("nativeProgress").value = state.progressValue;
  $("nativeProgress").textContent = `${Math.round(state.progressValue)}%`;
  $("progressPercent").textContent = `${Math.round(state.progressValue)}%`;
  if (title) $("progressTitle").textContent = title;
  if (detail) $("progressDetail").textContent = detail;
  $("progressPanel").classList.toggle("active", state.progressValue > 0);
}

function startProgress(kind) {
  if (state.progressTimer) cancelAnimationFrame(state.progressTimer);
  const isVideo = kind === "video";
  const model = selectedModel();
  const isAi = model?.is_ai_detection || model?.variant === "ai_detection";
  const usesOcr = model?.uses_ocr !== false;
  const phases = isVideo
    ? [
        [18, "上传视频", "正在上传视频文件。"],
        [38, "抽取关键帧", "正在选取可用画面。"],
        [68, "识别配件", isAi ? "正在逐帧调用 AI 检测。" : "正在定位瓶子和说明书。"],
        [90, "汇总结果", "正在合并帧级判断。"],
      ]
    : isAi
      ? [
          [20, "上传图片", "正在上传图片文件。"],
          [58, "AI 检测", "正在核对配件画像与当前画面。"],
          [88, "结构化结果", "正在整理存在/缺失判断。"],
        ]
    : usesOcr
      ? [
          [18, "上传图片", "正在上传图片文件。"],
          [42, "识别配件", "正在定位瓶子和说明书。"],
          [76, "读取文字", "正在区分四类说明书。"],
          [90, "核对规则", "正在检查配件是否齐全。"],
        ]
      : [
          [20, "上传图片", "正在上传图片文件。"],
          [68, "识别配件", "正在检测瓶子和四类说明书。"],
          [90, "核对规则", "正在检查配件是否齐全。"],
        ];
  const startTime = performance.now();
  const expectedMs = isVideo ? 36000 : isAi ? 6500 : 18000;
  setProgress(3, phases[0][1], phases[0][2]);

  const tick = (now) => {
    const elapsed = now - startTime;
    const ratio = Math.min(elapsed / expectedMs, 1);
    const eased = 1 - Math.pow(1 - ratio, 2.4);
    const value = Math.min(95, 3 + eased * 92);
    let phase = phases[0];
    for (const item of phases) {
      if (value >= item[0] - 6) phase = item;
    }
    setProgress(value, phase[1], phase[2]);
    state.progressTimer = requestAnimationFrame(tick);
  };
  state.progressTimer = requestAnimationFrame(tick);
}

function finishProgress(success = true) {
  if (state.progressTimer) cancelAnimationFrame(state.progressTimer);
  state.progressTimer = null;
  setProgress(100, success ? "检测完成" : "检测结果不可用", success ? "结果已更新。" : "请检查文件或服务状态。");
  setTimeout(() => $("progressPanel").classList.remove("active"), 1400);
}

function setTaskProgress(prefix, value, title, detail, options = {}) {
  const panel = $(`${prefix}Progress`);
  const native = $(`${prefix}NativeProgress`);
  const percent = $(`${prefix}ProgressPercent`);
  const titleNode = $(`${prefix}ProgressTitle`);
  const detailNode = $(`${prefix}ProgressDetail`);
  const safeValue = Math.max(0, Math.min(100, value));
  native.value = safeValue;
  native.textContent = `${Math.round(safeValue)}%`;
  percent.textContent = `${Math.round(safeValue)}%`;
  if (title) titleNode.textContent = title;
  if (detail) detailNode.textContent = detail;
  panel.classList.toggle("active", safeValue > 0 && (safeValue < 100 || options.keepVisible));
  panel.classList.toggle("complete", safeValue >= 100);
}

function startTaskProgress(prefix, expectedMs, phases) {
  const timerKey = `${prefix}ProgressTimer`;
  if (state[timerKey]) cancelAnimationFrame(state[timerKey]);
  const startTime = performance.now();
  setTaskProgress(prefix, 3, phases[0][1], phases[0][2]);
  const tick = (now) => {
    const elapsed = now - startTime;
    const ratio = Math.min(elapsed / expectedMs, 1);
    const value = Math.min(94, 3 + (1 - Math.pow(1 - ratio, 2.2)) * 91);
    let phase = phases[0];
    for (const item of phases) {
      if (value >= item[0] - 6) phase = item;
    }
    setTaskProgress(prefix, value, phase[1], phase[2]);
    state[timerKey] = requestAnimationFrame(tick);
  };
  state[timerKey] = requestAnimationFrame(tick);
}

function finishTaskProgress(prefix, success = true) {
  const timerKey = `${prefix}ProgressTimer`;
  if (state[timerKey]) cancelAnimationFrame(state[timerKey]);
  state[timerKey] = null;
  setTaskProgress(prefix, 100, success ? "生成完成" : "生成不可用", success ? "结果已准备好。" : "请检查服务状态。");
  setTimeout(() => $(`${prefix}Progress`).classList.remove("active"), 1200);
}

function setImageWorkerProgress(job) {
  const timerKey = "imageWorkerProgressTimer";
  if (state[timerKey]) cancelAnimationFrame(state[timerKey]);
  state[timerKey] = null;
  if (!job) {
    $("imageWorkerProgress").classList.remove("active");
    return;
  }
  const progress = Math.max(0, Math.min(100, Number(job.progress || 0)));
  if (job.status === "completed") {
    setTaskProgress("imageWorker", 100, "视角素材已完成", "18 个可用视角已准备好，可以确认添加。", { keepVisible: true });
    return;
  }
  if (job.status === "failed") {
    setTaskProgress("imageWorker", 100, "生成不可用", job.error || "请检查生成状态或重新生成。", { keepVisible: true });
    return;
  }
  if (job.status === "stopped") {
    setTaskProgress("imageWorker", 100, "任务已停止", "该生成任务已手动停止。", { keepVisible: true });
    return;
  }
  if (job.status === "running") {
    setTaskProgress("imageWorker", Math.max(progress, 12), "正在生成视角素材", "系统正在根据参考素材生成多角度视图。", { keepVisible: true });
    return;
  }
  setTaskProgress("imageWorker", progress, "等待生成", "参考素材和生成说明已进入队列。", { keepVisible: true });
}

function candidateJobs(candidate) {
  if (!candidate) return [];
  if (Array.isArray(candidate.codex_image_jobs) && candidate.codex_image_jobs.length) return candidate.codex_image_jobs;
  return candidate.codex_image_job ? [candidate.codex_image_job] : [];
}

function anchorProvenanceText(job) {
  if (job.generation_step !== "anchor_replacement") return "";
  const basename = job.anchor_image_basename || (job.anchor_image_path || "").split(/[\\/]/).pop() || "anchor";
  if (job.anchor_provenance === "legacy_path_only" || job.anchor_image_sha256 === null) {
    return `${basename} · legacy path only`;
  }
  if (job.anchor_image_sha256) {
    return `${basename} · ${String(job.anchor_image_sha256).slice(0, 12)}`;
  }
  return `${basename} · provenance pending`;
}

function summarizeCandidateJobs(jobs) {
  if (!jobs.length) return null;
  const completed = jobs.filter((job) => job.status === "completed").length;
  const failed = jobs.find((job) => job.status === "failed");
  const running = jobs.find((job) => job.status === "running") || jobs.find((job) => isActiveImageJobStatus(job.status));
  if (failed) return { ...failed, progress: 100, status: "failed", error: `${userJobLabel(failed.label)}：${failed.error || "生成失败"}` };
  if (completed === jobs.length) return { ...jobs[jobs.length - 1], progress: 100, status: "completed" };
  if (running) {
    const avgProgress = jobs.reduce((sum, job) => sum + Number(job.progress || 0), 0) / jobs.length;
    return { ...running, progress: avgProgress, status: running.status };
  }
  return jobs[0];
}

function setBadge(passed, waiting = false) {
  const badge = $("resultBadge");
  badge.className = "result-badge";
  if (waiting) {
    badge.classList.add("waiting");
    badge.textContent = "等待输入";
    return;
  }
  badge.classList.add(passed ? "pass" : "fail");
  badge.textContent = passed ? "通过" : "不通过";
}

function renderParts(rule) {
  const tbody = $("partsTable");
  tbody.innerHTML = "";
  if (rule?.match_policy === "ai_presence") {
    const present = new Set((rule.present || []).map(String));
    const missing = new Set((rule.missing || []).map(String));
    const rows = [...present, ...missing];
    for (const accessoryId of rows) {
      const det = (state.lastResult?.detections || []).find((item) => String(item.accessory_id) === accessoryId) || {};
      const accessory = state.accessories.find((item) => String(item.id) === accessoryId);
      const isMissing = missing.has(accessoryId);
      const tr = document.createElement("tr");
      tr.classList.add(isMissing ? "missing-row" : "present-row");
      if (isMissing) tr.classList.add("missing");
      tr.innerHTML = `
        <td>${escapeHtml(zhLabel(det.label || accessory?.name || accessoryId))}</td>
        <td>${isMissing ? "否" : "是"}</td>
        <td>是</td>
        <td>${det.confidence === undefined ? "-" : Number(det.confidence).toFixed(3)}</td>
      `;
      tbody.appendChild(tr);
    }
    return;
  }
  const rows = [...(rule.present || []), ...(rule.missing || [])];
  for (const row of rows) {
    const tr = document.createElement("tr");
    const rowKey = typeof row === "string" ? row : row.class_id;
    const isMissing = (rule.missing || []).some((m) => (typeof m === "string" ? m : m.class_id) === rowKey);
    tr.classList.add(isMissing ? "missing-row" : "present-row");
    if (isMissing) tr.classList.add("missing");
    const label = typeof row === "string" ? row : row.label;
    tr.innerHTML = `
      <td>${zhLabel(label)}</td>
      <td>${typeof row === "string" ? (isMissing ? "否" : "是") : row.found}</td>
      <td>${typeof row === "string" ? "是" : row.required}</td>
      <td>${typeof row === "string" || row.max_confidence === undefined ? "-" : Number(row.max_confidence).toFixed(3)}</td>
    `;
    tbody.appendChild(tr);
  }
}

function aiResultMetaText(result) {
  if (!result?.ai) return "-";
  if (result.ai.timed_out) return `AI 超时：${result.ai.error || "超过检测时间"}`;
  if (result.ai.error) return `AI 错误：${result.ai.error}`;
  const pieces = [];
  const provider = aiProviderMeta({ status: result.ai.provider_status, model: result.model?.provider_model });
  if (provider) pieces.push(provider);
  if (result.ai.latency_ms !== undefined) pieces.push(`${result.ai.latency_ms} ms`);
  if (result.ai.fallback_model) pieces.push(`备用 ${result.ai.fallback_model}`);
  return pieces.join(" / ") || "-";
}

function aiDebugPayload(result = state.lastResult) {
  if (!result) return { message: "暂无检测结果。" };
  const payload = {
    request_id: result.request_id,
    passed: result.passed,
    model: result.model,
    ai: result.ai || null,
    rule: result.rule || null,
    detections: result.detections || [],
    missing_required: result.missing_required || [],
    annotated_url: result.annotated_url || result.preview_url || "",
  };
  if (Array.isArray(result.frames)) {
    payload.video = {
      sampled_frames: result.sampled_frames || 0,
      passed_frames: result.passed_frames || 0,
      pass_rate: result.pass_rate || 0,
      preview_url: result.preview_url || "",
    };
    payload.video_frames = result.frames.map((frame) => ({
      frame_index: frame.frame_index,
      timestamp_seconds: frame.timestamp_seconds,
      passed: frame.passed,
      missing: frame.missing || [],
      detections: frame.detections,
      annotated_url: frame.annotated_url || "",
      model: frame.model || null,
      ai: frame.ai || null,
      rule: frame.rule || null,
      detection_items: frame.detection_items || [],
    }));
  }
  return payload;
}

function openAiDebugModal() {
  const body = $("aiDebugBody");
  if (body) body.textContent = JSON.stringify(aiDebugPayload(), null, 2);
  $("aiDebugModal").classList.add("visible");
  $("aiDebugModal").setAttribute("aria-hidden", "false");
}

function closeAiDebugModal() {
  $("aiDebugModal").classList.remove("visible");
  $("aiDebugModal").setAttribute("aria-hidden", "true");
}

function renderImageResult(result) {
  state.lastResult = result;
  setBadge(result.passed);
  $("decisionText").textContent = result.passed ? "通过" : "不通过";
  $("detectionCount").textContent = result.detections?.length ?? "-";
  $("passRate").textContent = aiResultMetaText(result);
  renderParts(result.rule);
  const img = $("previewImage");
  img.src = `${result.annotated_url}?t=${Date.now()}`;
  img.style.display = "block";
  $("emptyPreview").style.display = "none";
  syncInspectFullscreen();
}

function renderVideoResult(result) {
  state.lastResult = result;
  setBadge(result.passed);
  $("decisionText").textContent = result.passed ? "通过" : "不通过";
  $("detectionCount").textContent = `${result.passed_frames}/${result.sampled_frames} 帧`;
  $("passRate").textContent = `${Math.round(result.pass_rate * 1000) / 10}%`;
  const missing = [];
  for (const frame of result.frames || []) {
    for (const item of frame.missing || []) {
      const key = typeof item === "string" ? item : item.class_id;
      if (!missing.find((x) => (typeof x === "string" ? x : x.class_id) === key)) missing.push(item);
    }
  }
  renderParts({ match_policy: missing.some((item) => typeof item === "string") ? "ai_presence" : "exact_count", present: [], missing });
  if (result.preview_url) {
    const img = $("previewImage");
    img.src = `${result.preview_url}?t=${Date.now()}`;
    img.style.display = "block";
    $("emptyPreview").style.display = "none";
  }
  syncInspectFullscreen();
}

function setCameraStatus(message, isError = false) {
  const node = $("cameraStatus");
  if (!node) return;
  node.textContent = message;
  node.classList.toggle("danger-text", isError);
}

function setCameraPreviewActive(active) {
  const video = $("cameraVideo");
  const empty = $("cameraEmpty");
  if (!video || !empty) return;
  video.classList.toggle("active", active);
  empty.style.display = active ? "none" : "grid";
}

function stopCameraStream() {
  if (!state.camera.stream) return;
  for (const track of state.camera.stream.getTracks()) track.stop();
  state.camera.stream = null;
  const video = $("cameraVideo");
  if (video) video.srcObject = null;
  setCameraPreviewActive(false);
}

function renderCameraMenu() {
  const devices = state.camera.devices || [];
  const options = devices.length
    ? devices.map((device, index) => ({
        value: device.deviceId,
        label: device.label || `摄像头 ${index + 1}`,
        meta: device.label ? "可用" : "等待授权后显示名称",
      }))
    : [{ value: "", label: "未检测到摄像头", meta: "请检查设备连接或浏览器权限", disabled: true }];
  state.camera.selectedDeviceId = renderCustomMenu("cameraMenu", options, state.camera.selectedDeviceId, (value) => {
    state.camera.selectedDeviceId = value;
    if (value) startCamera(value);
  });
}

async function refreshCameraDevices() {
  if (!navigator.mediaDevices?.enumerateDevices) {
    state.camera.devices = [];
    renderCameraMenu();
    setCameraStatus("当前浏览器不支持摄像头枚举。请使用 localhost 下的 Chrome/Edge。", true);
    return [];
  }
  const devices = await navigator.mediaDevices.enumerateDevices();
  state.camera.devices = devices.filter((device) => device.kind === "videoinput");
  if (!state.camera.selectedDeviceId && state.camera.devices.length) {
    state.camera.selectedDeviceId = state.camera.devices[0].deviceId;
  }
  renderCameraMenu();
  return state.camera.devices;
}

async function startCamera(deviceId = state.camera.selectedDeviceId) {
  if (state.camera.starting) return;
  if (!navigator.mediaDevices?.getUserMedia) {
    setCameraStatus("当前浏览器不支持摄像头预览。请使用 localhost 下的 Chrome/Edge。", true);
    return;
  }
  state.camera.starting = true;
  setCameraStatus("正在打开摄像头...");
  try {
    stopCameraStream();
    const videoConstraints = deviceId ? { deviceId: { exact: deviceId } } : true;
    const stream = await navigator.mediaDevices.getUserMedia({ video: videoConstraints, audio: false });
    state.camera.stream = stream;
    const video = $("cameraVideo");
    video.srcObject = stream;
    await video.play();
    const track = stream.getVideoTracks()[0];
    const settings = track?.getSettings?.() || {};
    if (settings.deviceId) state.camera.selectedDeviceId = settings.deviceId;
    await refreshCameraDevices();
    setCameraPreviewActive(true);
    const label = track?.label || "当前摄像头";
    setCameraStatus(`摄像头已连接：${label}`);
  } catch (error) {
    stopCameraStream();
    setCameraStatus(`摄像头不可用：${error.message}`, true);
    toast(`摄像头不可用：${error.message}`);
  } finally {
    state.camera.starting = false;
  }
}

async function captureCameraFrame() {
  if (!state.camera.stream) await startCamera();
  const video = $("cameraVideo");
  if (!state.camera.stream || !video.videoWidth || !video.videoHeight) {
    throw new Error("摄像头画面尚未准备好");
  }
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (!blob) {
        reject(new Error("拍照失败"));
        return;
      }
      resolve(new File([blob], `camera_capture_${Date.now()}.jpg`, { type: "image/jpeg" }));
    }, "image/jpeg", 0.92);
  });
}

async function runCameraDetection(button) {
  const modelId = selectedModelId();
  if (!modelId) return toast("当前任务没有可用模型。");
  setBusy(button, true);
  startProgress("image");
  try {
    const file = await captureCameraFrame();
    setInspectInput("camera");
    const form = new FormData();
    form.append("file", file);
    form.append("model_id", modelId);
    const result = await api("/api/analyze/image", { method: "POST", body: form });
    renderImageResult(result);
    finishProgress(true);
    toast("摄像头拍照检测完成。");
  } catch (error) {
    finishProgress(false);
    toast(`摄像头检测失败：${error.message}`);
  } finally {
    setBusy(button, false);
  }
}


function labelExperimentStatusText(status) {
  if (status === "pass") return "通过";
  if (status === "review") return "复核";
  if (status === "fail") return "异常";
  if (status === "unknown") return "未知";
  return status || "-";
}

function labelExperimentBadgeClass(status) {
  if (status === "pass") return "pass";
  if (status === "fail") return "fail";
  return "waiting";
}

function labelExperimentPillClass(status) {
  if (["pass", "fail", "review", "unknown"].includes(status)) return status;
  return "neutral";
}

function updateLabelExperimentFileName(inputId, labelId, fallback) {
  const file = $(inputId)?.files?.[0];
  const label = $(labelId);
  if (!label) return;
  label.textContent = file ? file.name : fallback;
}

function setLabelExperimentImage(frameId, imageId, url) {
  const frame = $(frameId);
  const image = $(imageId);
  if (!frame || !image) return;
  if (!url) {
    image.removeAttribute("src");
    frame.classList.remove("has-image");
    return;
  }
  image.src = cacheBustImageUrl(url);
  frame.classList.add("has-image");
}

function renderLabelExperimentSummary(result) {
  const summary = result.summary || {};
  const abnormal = Number(summary.fail || 0) + Number(summary.review || 0) + Number(summary.unknown || 0);
  $("labelExperimentSummary").innerHTML = `
    <div><label>来料候选</label><strong>${Number(result.incoming_candidate_count || 0)}</strong></div>
    <div><label>切分框</label><strong>${Number(result.split_count || 0)}</strong></div>
    <div><label>异常</label><strong>${abnormal}</strong></div>
    <div><label>缺失</label><strong>${Number(summary.missing || 0)}</strong></div>
  `;
}

function renderLabelExperimentResult(result) {
  state.labelExperimentResult = result;
  const badge = $("labelExperimentBadge");
  const badgeClass = labelExperimentBadgeClass(result.status);
  badge.className = `result-badge ${badgeClass}`;
  badge.textContent = result.status === "pass" ? "通过" : result.status === "fail" ? "发现异常" : "需复核";
  renderLabelExperimentSummary(result);
  setLabelExperimentImage("labelReferenceOverlayFrame", "labelReferenceOverlay", result.reference_overlay_url);
  setLabelExperimentImage("labelIncomingOverlayFrame", "labelIncomingOverlay", result.incoming_overlay_url);

  const grid = $("labelExperimentCandidates");
  const items = result.items || [];
  const missing = result.missing_references || [];
  if (!items.length && !missing.length) {
    grid.innerHTML = `<p class="hint">没有可展示的来料候选。</p>`;
    return;
  }
  const cards = items
    .map((item) => {
      const status = item.status || "unknown";
      const score = Number(item.score || 0).toFixed(3);
      return `
        <article class="label-exp-card ${escapeAttr(status)}">
          <header class="label-exp-card-head">
            <div>
              <strong>${escapeHtml(item.id || "候选")}</strong>
              <span>匹配 ${escapeHtml(item.reference_id || "-")}</span>
            </div>
            <span class="pill ${labelExperimentPillClass(status)}">${labelExperimentStatusText(status)}</span>
          </header>
          <div class="label-exp-card-images">
            <button class="preview-open" type="button" data-preview-url="${escapeAttr(item.candidate_url || "")}">
              <img src="${escapeAttr(cacheBustImageUrl(item.candidate_url || ""))}" alt="${escapeAttr(item.id || "候选标签")}" />
            </button>
            <button class="preview-open" type="button" data-preview-url="${escapeAttr(item.diff_url || "")}">
              <img src="${escapeAttr(cacheBustImageUrl(item.diff_url || ""))}" alt="${escapeAttr(item.id || "候选差异")} 差异图" />
            </button>
          </div>
          <div class="label-exp-card-body">
            <dl class="label-exp-card-meta">
              <div><dt>分数</dt><dd>${score}</dd></div>
              <div><dt>位置</dt><dd>${escapeHtml(item.bbox_text || "-")}</dd></div>
            </dl>
            <p class="label-exp-reason">${escapeHtml(item.reason || "-")}</p>
          </div>
        </article>
      `;
    })
    .join("");
  const missingCards = missing
    .map((item) => `
      <article class="label-exp-card fail">
        <header class="label-exp-card-head">
          <div>
            <strong>${escapeHtml(item.reference_id || "标准")}</strong>
            <span>最佳候选 ${escapeHtml(item.best_incoming_id || "无")}</span>
          </div>
          <span class="pill fail">缺失</span>
        </header>
        <div class="label-exp-card-body">
          <dl class="label-exp-card-meta">
            <div><dt>最佳分数</dt><dd>${Number(item.best_score || 0).toFixed(3)}</dd></div>
            <div><dt>状态</dt><dd>${escapeHtml(item.status || "missing")}</dd></div>
          </dl>
          <p class="label-exp-reason">标准图中存在该候选，但来料图里没有确认匹配项。</p>
        </div>
      </article>
    `)
    .join("");
  grid.innerHTML = cards + missingCards;
  bindImagePreviewTriggers(grid);
}

async function runLabelExperiment() {
  const referenceFile = $("labelReferenceFile")?.files?.[0];
  const incomingFile = $("labelIncomingFile")?.files?.[0];
  if (!referenceFile) return toast("请先选择标准标签图。");
  if (!incomingFile) return toast("请先选择来料整页图。");
  const button = $("runLabelExperiment");
  const badge = $("labelExperimentBadge");
  setBusy(button, true);
  badge.className = "result-badge waiting";
  badge.textContent = "处理中";
  try {
    const form = new FormData();
    form.append("reference_file", referenceFile);
    form.append("incoming_file", incomingFile);
    form.append("sensitivity", $("labelSensitivity")?.value || "0.72");
    const result = await api("/api/experimental/label-inspector/analyze", { method: "POST", body: form });
    renderLabelExperimentResult(result);
    toast("标签切分比对完成。");
  } catch (error) {
    badge.className = "result-badge fail";
    badge.textContent = "失败";
    toast(`标签实验失败：${error.message}`);
  } finally {
    setBusy(button, false);
  }
}

function renderRules() {
  const wrap = $("classRules");
  wrap.innerHTML = "";
  const selectedTask = state.specializedModelTasks.find((item) => item.task_id === state.selectedTaskId);
  if (selectedTask) {
    const model = selectedModel() || selectedTask.models?.[0] || {};
    const counts = model.required_accessory_counts || {};
    const ids = Object.keys(counts);
    const names = selectedTask.accessory_names || [];
    const labelsById = {};
    (model.selected_accessory_ids || []).forEach((id, index) => {
      labelsById[id] = names[index] || id;
    });
    for (const id of ids.length ? ids : (model.selected_accessory_ids || [])) {
      const row = document.createElement("label");
      row.className = "check-row";
      const required = counts[id] || 1;
      row.innerHTML = `
        <input type="checkbox" checked disabled />
        <span>${escapeHtml(zhLabel(labelsById[id] || id))}</span>
        <input type="number" min="0" value="${required}" disabled />
      `;
      wrap.appendChild(row);
    }
    if (!ids.length && !(model.selected_accessory_ids || []).length) {
      wrap.innerHTML = `<p class="hint">当前任务没有配件集合，无法自动生成通过条件。</p>`;
    }
    $("threshold").value = state.config.confidence_threshold;
    $("thresholdValue").textContent = Number(state.config.confidence_threshold).toFixed(2);
    $("saveRules").textContent = "保存置信度阈值";
    return;
  }
  const required = new Set((state.config.required_classes || []).map(Number));
  const minCounts = state.config.min_counts || {};
  for (const item of state.classes) {
    const row = document.createElement("label");
    row.className = "check-row";
    row.innerHTML = `
      <input type="checkbox" data-class="${item.class_id}" ${required.has(item.class_id) ? "checked" : ""} />
      <span>${zhLabel(item.label)}</span>
      <input type="number" min="1" value="${minCounts[String(item.class_id)] || 1}" data-count="${item.class_id}" />
    `;
    wrap.appendChild(row);
  }
  $("threshold").value = state.config.confidence_threshold;
  $("thresholdValue").textContent = Number(state.config.confidence_threshold).toFixed(2);
  $("saveRules").textContent = "保存规则";
}

function renderAccessories(items) {
  state.accessories = items || [];
  const list = $("accessoryList");
  list.innerHTML = "";
  for (const item of state.accessories) {
    const row = document.createElement("div");
    row.className = "accessory-item";
    const material = item.material_type === "text" ? "文字类" : "物品类";
    const files = item.source_files?.length || 0;
    const size = formatPhysicalSize(item.physical_size);
    row.innerHTML = `
      <div>
        <strong>${escapeHtml(zhLabel(item.name))}</strong>
        <span>${material} · 类别 ${item.class_id} · ${files} 个素材 · ${size} · ${STATUS_ZH[item.status] || item.status} · ${accessoryAiProfileText(item)}</span>
      </div>
      <button class="mini-secondary" data-view-accessory="${escapeAttr(item.id)}" type="button">查看</button>
      <button class="mini-danger" data-delete-accessory="${escapeAttr(item.id)}" type="button">删除</button>
    `;
    list.appendChild(row);
  }
  renderTrainingAccessories();
  bindAccessoryViews();
  bindAccessoryDeletes();
}

function formatPhysicalSize(size) {
  if (!size) return "尺寸未设置";
  if (size.kind === "paper") return `${size.preset || "自定义"} ${size.width_mm}×${size.height_mm}mm`;
  if (size.kind === "object") return `${size.length_mm || "-"}×${size.width_mm || "-"}×${size.height_mm || "-"}mm`;
  return "尺寸未设置";
}

function bindAccessoryViews() {
  document.querySelectorAll("[data-view-accessory]").forEach((button) => {
    button.addEventListener("click", () => openAccessoryDetail(button.dataset.viewAccessory));
  });
}

async function openAccessoryDetail(accessoryId) {
  try {
    const result = await api(`/api/accessories/${encodeURIComponent(accessoryId)}/detail`);
    const item = result.item || {};
    const gallery = result.gallery || [];
    state.accessoryDetailItem = item;
    renderAccessoryDetailFileQueue();
    $("accessoryDetailTitle").textContent = zhLabel(item.name || "配件素材");
    $("accessoryDetailSummary").innerHTML = `
      <strong>${escapeHtml(zhLabel(item.name || "配件"))} · ${item.material_type === "text" ? "文字类" : "物品类"}</strong>
      <span>这里展示该配件当前可用的原始素材、规范化图片以及多角度视图。</span>
      <span>尺寸：${escapeHtml(formatPhysicalSize(item.physical_size))}</span>
      <span>${escapeHtml(accessoryAiProfileText(item))}${item.ai_profile_status?.message ? `：${escapeHtml(item.ai_profile_status.message)}` : ""}</span>
      ${item.material_type === "object" ? `<span>透明策略：${escapeHtml(alphaPolicyLabel(item.material_alpha_policy))}</span>` : ""}
      ${item.clean_sprite_count ? `<span>${escapeHtml(`无背景素材：${item.clean_sprite_count}/${item.clean_sprite_expected_count || item.clean_sprite_count}${item.clean_sprite_failed_cells?.length ? `，失败 ${item.clean_sprite_failed_cells.length} 格` : ""}`)}</span>` : ""}
    `;
    const grid = $("accessoryDetailGrid");
    grid.innerHTML = "";
    for (const [index, asset] of gallery.entries()) {
      const card = document.createElement("figure");
      card.className = `training-preview-card asset-thumb-card${asset.ai_reference ? " ai-reference" : ""}`;
      const assetLabel = userJobLabel(asset.label || `素材 ${index + 1}`);
      card.innerHTML = `
        <button class="preview-open" type="button" data-preview-url="${escapeAttr(asset.url)}">
          <img src="${escapeAttr(asset.url)}?t=${Date.now()}" alt="${escapeHtml(assetLabel)}" />
        </button>
        <button class="asset-ai-select" type="button" data-set-ai-reference="${escapeAttr(asset.source_path)}" aria-label="设为 AI 素材"></button>
        ${asset.deletable ? `<button class="asset-delete" type="button" data-delete-accessory-file="${escapeAttr(asset.source_path)}" aria-label="删除照片">×</button>` : ""}
      `;
      grid.appendChild(card);
    }
    const addCard = document.createElement("button");
    addCard.className = "asset-add-card";
    addCard.type = "button";
    addCard.dataset.addAccessoryFile = "true";
    addCard.setAttribute("aria-label", "添加照片");
    addCard.textContent = "+";
    grid.appendChild(addCard);
    bindImagePreviewTriggers(grid);
    bindAccessoryFileDeletes(grid);
    bindAccessoryAiReferenceButtons(grid);
    bindAccessoryFileAdd(grid);
    $("accessoryDetailModal").classList.add("visible");
    $("accessoryDetailModal").setAttribute("aria-hidden", "false");
  } catch (error) {
    toast(`打开配件失败：${error.message}`);
  }
}

function clearAccessoryDetailFileQueue() {
  for (const url of state.accessoryDetailPendingFileUrls.values()) URL.revokeObjectURL(url);
  state.accessoryDetailPendingFileUrls.clear();
  state.accessoryDetailPendingFiles = [];
  if ($("accessoryDetailFiles")) $("accessoryDetailFiles").value = "";
  renderAccessoryDetailFileQueue();
}

function addAccessoryDetailPendingFiles(fileList) {
  const existing = new Set(state.accessoryDetailPendingFiles.map(accessoryFileKey));
  for (const file of Array.from(fileList || [])) {
    if (!file.type.startsWith("image/")) continue;
    const key = accessoryFileKey(file);
    if (existing.has(key)) continue;
    state.accessoryDetailPendingFiles.push(file);
    existing.add(key);
  }
  if ($("accessoryDetailFiles")) $("accessoryDetailFiles").value = "";
  renderAccessoryDetailFileQueue();
}

function removeAccessoryDetailPendingFile(index) {
  const file = state.accessoryDetailPendingFiles[Number(index)];
  if (!file) return;
  const key = accessoryFileKey(file);
  const url = state.accessoryDetailPendingFileUrls.get(key);
  if (url) URL.revokeObjectURL(url);
  state.accessoryDetailPendingFileUrls.delete(key);
  state.accessoryDetailPendingFiles.splice(Number(index), 1);
  renderAccessoryDetailFileQueue();
}

function renderAccessoryDetailFileQueue() {
  const queue = $("accessoryDetailFileQueue");
  if (!queue) return;
  if (!state.accessoryDetailPendingFiles.length) {
    const material = state.accessoryDetailItem?.material_type === "text" ? "文档照片会先进入四角裁切" : "物体照片会直接保存";
    queue.innerHTML = `<div class="upload-thumb-empty">${material}</div>`;
    return;
  }
  queue.innerHTML = "";
  const title = document.createElement("div");
  title.className = "upload-thumb-summary";
  title.textContent = `待添加照片 ${state.accessoryDetailPendingFiles.length} 张`;
  queue.appendChild(title);
  const grid = document.createElement("div");
  grid.className = "upload-thumb-grid";
  for (const [index, file] of state.accessoryDetailPendingFiles.entries()) {
    const key = accessoryFileKey(file);
    if (!state.accessoryDetailPendingFileUrls.has(key)) {
      state.accessoryDetailPendingFileUrls.set(key, URL.createObjectURL(file));
    }
    const url = state.accessoryDetailPendingFileUrls.get(key);
    const card = document.createElement("div");
    card.className = "upload-thumb-card";
    card.innerHTML = `
      <button type="button" class="upload-thumb-remove" data-remove-detail-pending-file="${index}" aria-label="移除照片">×</button>
      <img src="${escapeAttr(url)}" alt="${escapeHtml(file.name)}" />
      <span title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</span>
      <em>图片</em>
    `;
    grid.appendChild(card);
  }
  queue.appendChild(grid);
  queue.querySelectorAll("[data-remove-detail-pending-file]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      removeAccessoryDetailPendingFile(button.dataset.removeDetailPendingFile);
    });
  });
}

function applyDetailPaperSizeForCrop(item) {
  const size = item?.physical_size || {};
  const previous = {
    preset: $("paperPreset")?.value,
    width: $("paperWidthMm")?.value,
    height: $("paperHeightMm")?.value,
  };
  if (size.kind === "paper") {
    $("paperPreset").value = PAPER_PRESETS[size.preset] ? size.preset : "custom";
    $("paperWidthMm").value = size.width_mm || PAPER_PRESETS.A4[0];
    $("paperHeightMm").value = size.height_mm || PAPER_PRESETS.A4[1];
    updatePaperDimensionLock();
  }
  return () => {
    if (previous.preset !== undefined) $("paperPreset").value = previous.preset;
    if (previous.width !== undefined) $("paperWidthMm").value = previous.width;
    if (previous.height !== undefined) $("paperHeightMm").value = previous.height;
    updatePaperDimensionLock();
  };
}

async function uploadAccessoryDetailFiles() {
  const item = state.accessoryDetailItem;
  if (!item?.id) return toast("请先打开一个配件。");
  if (!state.accessoryDetailPendingFiles.length) return toast("请先选择要添加的照片。");
  const button = $("addAccessoryDetailFiles");
  setBusy(button, true);
  let restorePaperSize = null;
  try {
    const form = new FormData();
    let uploadFiles = state.accessoryDetailPendingFiles;
    if (item.material_type === "text") {
      restorePaperSize = applyDetailPaperSizeForCrop(item);
      uploadFiles = await prepareTextAccessoryFiles(state.accessoryDetailPendingFiles);
    }
    for (const file of uploadFiles) form.append("files", file);
    const result = await api(`/api/accessories/${encodeURIComponent(item.id)}/files`, { method: "POST", body: form });
    renderAccessories(result.items);
    clearAccessoryDetailFileQueue();
    await openAccessoryDetail(item.id);
    toast("照片已添加到当前配件。");
  } catch (error) {
    toast(`添加照片失败：${error.message}`);
  } finally {
    if (restorePaperSize) restorePaperSize();
    setBusy(button, false);
  }
}

function bindAccessoryFileDeletes(scope) {
  scope.querySelectorAll("[data-delete-accessory-file]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const item = state.accessoryDetailItem;
      if (!item?.id) return;
      const sourcePath = button.dataset.deleteAccessoryFile;
      if (!window.confirm("删除这张照片？")) return;
      setBusy(button, true);
      try {
        const result = await api(`/api/accessories/${encodeURIComponent(item.id)}/files`, {
          method: "DELETE",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ source_path: sourcePath }),
        });
        renderAccessories(result.items);
        await openAccessoryDetail(item.id);
        toast("照片已删除。");
      } catch (error) {
        toast(`删除照片失败：${error.message}`);
      } finally {
        setBusy(button, false);
      }
    });
  });
}

function bindAccessoryAiReferenceButtons(scope) {
  scope.querySelectorAll("[data-set-ai-reference]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const item = state.accessoryDetailItem;
      if (!item?.id) return;
      const sourcePath = button.dataset.setAiReference;
      setBusy(button, true);
      try {
        const result = await api(`/api/accessories/${encodeURIComponent(item.id)}/ai-reference`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ source_path: sourcePath }),
        });
        renderAccessories(result.items);
        await openAccessoryDetail(item.id);
        toast("AI 素材已切换。");
      } catch (error) {
        toast(`切换 AI 素材失败：${error.message}`);
      } finally {
        setBusy(button, false);
      }
    });
  });
}

function bindAccessoryFileAdd(scope) {
  scope.querySelectorAll("[data-add-accessory-file]").forEach((button) => {
    button.addEventListener("click", () => {
      $("accessoryDetailFiles")?.click();
    });
  });
}

function closeAccessoryDetail() {
  clearAccessoryDetailFileQueue();
  state.accessoryDetailItem = null;
  $("accessoryDetailModal").classList.remove("visible");
  $("accessoryDetailModal").setAttribute("aria-hidden", "true");
}

function renderModels(status) {
  state.models = status.available_models || [];
  state.specializedModels = status.specialized_models || [];
  state.specializedModelTasks = status.specialized_model_tasks || [];
  state.activeModelId = status.active_model_id || state.models[0]?.id || "";
  const requiredNames = (status.rule?.required_classes || [])
    .map((classId) => status.classes?.find((item) => Number(item.class_id) === Number(classId))?.label)
    .filter(Boolean);
  const taskOptions = [
    {
      value: "__default__",
      label: requiredNames.length ? requiredNames.join(" + ") : "通用配件合集",
      meta: "通用检测任务",
      models: state.models,
    },
    ...state.specializedModelTasks.map((task) => ({
      value: task.task_id,
      label: taskAccessoryLabel(task),
      meta: `${task.models?.length || 0} 个模型`,
      models: task.models || [],
    })),
  ];
  if (!taskOptions.some((item) => item.value === state.selectedTaskId)) {
    state.selectedTaskId = "__default__";
  }
  state.selectedTaskId = renderCustomMenu("taskMenu", taskOptions, state.selectedTaskId, (value) => {
    state.selectedTaskId = value;
    state.selectedModelId = "";
    renderModelMenu();
    renderRules();
    renderModels({ ...status, available_models: state.models, specialized_models: state.specializedModels, specialized_model_tasks: state.specializedModelTasks });
  }) || "__default__";
  renderModelMenu();
  renderRules();
}

function currentTaskModels() {
  if (state.selectedTaskId === "__default__") return state.models;
  return state.specializedModelTasks.find((item) => item.task_id === state.selectedTaskId)?.models || [];
}

function renderModelMenu() {
  const models = currentTaskModels();
  const modelOptions = models.map((model) => ({
    value: model.id,
    label: modelVariantLabel(model),
    meta: model.is_ai_detection ? aiProviderMeta(model.provider_status) : model.exists ? model.label || "" : `${model.label || ""} 文件缺失`.trim(),
    disabled: !model.exists && !model.is_ai_detection,
  }));
  if (!modelOptions.some((item) => item.value === state.selectedModelId)) {
    state.selectedModelId = state.selectedTaskId === "__default__" ? state.activeModelId : "";
  }
  state.selectedModelId = renderCustomMenu("modelMenu", modelOptions, state.selectedModelId, (value) => {
    state.selectedModelId = value;
    renderModelMenu();
  });
}

function selectedModelId() {
  return state.selectedModelId || "";
}

function selectedModel() {
  const modelId = selectedModelId();
  return [...state.models, ...state.specializedModels].find((item) => item.id === modelId) || null;
}

function setInspectInput(kind, file = null) {
  if (state.inspectInput.url) URL.revokeObjectURL(state.inspectInput.url);
  state.inspectInput = { kind, url: file ? URL.createObjectURL(file) : "", fileName: file?.name || "" };
  syncInspectFullscreen();
}

function syncInspectFullscreen() {
  const stage = $("inspectFullscreenStage");
  if (!stage) return;
  const inputImage = $("fullscreenInputImage");
  const inputVideo = $("fullscreenInputVideo");
  const inputEmpty = $("fullscreenInputEmpty");
  inputImage.style.display = "none";
  inputVideo.style.display = "none";
  inputVideo.pause?.();
  inputVideo.removeAttribute("src");
  inputVideo.srcObject = null;
  const activeInputTab = document.querySelector(".mode-tab[data-tab].active")?.dataset.tab || state.inspectInput.kind;
  if (activeInputTab === "camera" && state.camera.stream) {
    inputVideo.srcObject = state.camera.stream;
    inputVideo.controls = false;
    inputVideo.style.display = "block";
    inputVideo.play?.();
    inputEmpty.style.display = "none";
  } else if (state.inspectInput.kind === "image" && state.inspectInput.url) {
    inputImage.src = state.inspectInput.url;
    inputImage.style.display = "block";
    inputEmpty.style.display = "none";
  } else if (state.inspectInput.kind === "video" && state.inspectInput.url) {
    inputVideo.src = state.inspectInput.url;
    inputVideo.controls = true;
    inputVideo.style.display = "block";
    inputEmpty.style.display = "none";
  } else {
    inputEmpty.style.display = "grid";
  }

  const preview = $("previewImage");
  const resultImage = $("fullscreenResultImage");
  const resultEmpty = $("fullscreenResultEmpty");
  if (preview?.src && preview.style.display !== "none") {
    resultImage.src = preview.src;
    resultImage.style.display = "block";
    resultEmpty.style.display = "none";
  } else {
    resultImage.style.display = "none";
    resultEmpty.style.display = "grid";
  }
  $("fullscreenDecision").textContent = $("resultBadge")?.textContent || "等待输入";
  $("fullscreenDecisionText").textContent = $("decisionText")?.textContent || "-";
  $("fullscreenDetectionCount").textContent = $("detectionCount")?.textContent || "-";
  $("fullscreenPassRate").textContent = $("passRate")?.textContent || "-";
  $("fullscreenPartsTable").innerHTML = $("partsTable")?.innerHTML || "";
}

async function openInspectFullscreen() {
  const stage = $("inspectFullscreenStage");
  syncInspectFullscreen();
  stage.classList.add("active");
  stage.setAttribute("aria-hidden", "false");
  try {
    if (stage.requestFullscreen && document.fullscreenElement !== stage) await stage.requestFullscreen();
  } catch {
    // Keep the fixed fallback visible if browser fullscreen is blocked.
  }
}

function closeInspectFullscreen() {
  const stage = $("inspectFullscreenStage");
  if (document.fullscreenElement === stage) {
    document.exitFullscreen?.();
    return;
  }
  stage.classList.remove("active");
  stage.setAttribute("aria-hidden", "true");
}

function handleFullscreenChange() {
  const stage = $("inspectFullscreenStage");
  if (document.fullscreenElement === stage) return;
  stage.classList.remove("active");
  stage.setAttribute("aria-hidden", "true");
}

async function loadInitial() {
  const status = await api("/api/status");
  const config = await api("/api/config");
  const aiConfig = await api("/api/ai/config");
  const accessories = await api("/api/accessories");
  const trainingPlan = await api("/api/training/plan");
  state.config = config;
  state.aiConfig = aiConfig;
  state.classes = status.classes;
  $("serviceState").textContent = STATUS_ZH[status.service] || status.service;
  $("serviceState").className = `pill ${status.service === "running" ? "ok" : "fail"}`;
  $("modelState").textContent = status.model_exists ? "模型已加载" : "模型缺失";
  $("modelState").className = `pill ${status.model_exists ? "ok" : "fail"}`;
  renderModels(status);
  renderAiConfig();
  renderRules();
  renderAccessories(accessories.items);
  renderTrainingPlan(trainingPlan);
  await refreshTrainingLibrary();
  await refreshImageJobs();
  state.imageJobPollTimer = setInterval(refreshImageJobs, 5000);
}

async function refreshImageJobs() {
  try {
    const result = await api("/api/image-jobs");
    state.imageJobs = result.items || [];
    renderImageJobs(result);
    syncOpenAccessoryJobProgress();
    updateOpenAccessoryCandidateFromJobs();
    const trainingItems = (result.items || []).filter((item) => item.queue_kind === "training");
    const modalNeedsLiveEpoch =
      $("trainingResourceModal")?.classList.contains("visible") &&
      state.trainingResourceDetail &&
      ["task", "modelRun"].includes(state.trainingResourceDetail.kind) &&
      trainingItems.some((item) => ["queued", "running"].includes(item.status));
    if (trainingItems.some((item) => ["completed", "failed"].includes(item.status)) || modalNeedsLiveEpoch) {
      refreshTrainingLibrary();
    }
  } catch {
    // Keep the UI quiet if the queue endpoint is temporarily unavailable.
  }
}

async function refreshTrainingLibrary() {
  try {
    const result = await api("/api/training/resources");
    state.trainingResources = result;
    renderTrainingLibrary(result);
    renderTrainingDatasetMenu();
    if ($("trainingResourceModal")?.classList.contains("visible") && state.trainingResourceDetail) {
      openTrainingResourceDetail(state.trainingResourceDetail.kind, state.trainingResourceDetail.id);
    }
    const status = await api("/api/status");
    renderModels(status);
  } catch (error) {
    toast(`刷新训练库失败：${error.message}`);
  }
}

function modelRunGroups(models, tasks) {
  const trainTasks = tasks.filter((task) => task.action === "train_model" || (task.models || []).length);
  const taskById = new Map(trainTasks.map((task) => [String(task.job_id || task.task_id || ""), task]));
  const groups = new Map();
  for (const task of trainTasks) {
    const id = String(task.job_id || task.task_id || "");
    if (!id) continue;
    groups.set(id, { id, task, models: [] });
  }
  for (const model of models) {
    const id = String(model.run_id || model.task_id || model.id || "");
    if (!id) continue;
    const group = groups.get(id) || { id, task: taskById.get(String(model.task_id || "")) || null, models: [] };
    group.models.push(model);
    groups.set(id, group);
  }
  return Array.from(groups.values()).filter((group) => group.models.length).sort((a, b) => {
    const aTime = Math.max(Number(a.task?.created_at || 0), ...a.models.map((item) => Number(item.created_at || 0)));
    const bTime = Math.max(Number(b.task?.created_at || 0), ...b.models.map((item) => Number(item.created_at || 0)));
    return bTime - aTime;
  });
}

function modelRunLabel(group) {
  const names = [
    ...(group.task?.accessory_names || []),
    ...group.models.flatMap((model) => model.accessory_names || []),
  ].filter(Boolean);
  if (names.length) return [...new Set(names)].join(" + ");
  return group.task?.label || group.models[0]?.label || group.id || "训练模型";
}

function modelRunAccessoryText(group) {
  const names = [...new Set(group.models.flatMap((model) => model.accessory_names || []).filter(Boolean))];
  const ids = [...new Set(group.models.flatMap((model) => model.selected_accessory_ids || []).filter(Boolean))];
  return names.length ? names.join("、") : ids.length ? ids.join(", ") : "配件信息缺失";
}

function renderTrainingLibrary(resources) {
  const datasets = resources?.datasets || [];
  const models = resources?.models || [];
  const tasks = resources?.training_tasks || resources?.tasks || [];
  const modelGroups = modelRunGroups(models, tasks);
  const datasetList = $("datasetLibraryList");
  const modelList = $("modelLibraryList");
  if (datasetList) {
    datasetList.innerHTML = datasets.length ? "" : `<div class="job-empty">暂无样本库</div>`;
    for (const dataset of datasets) {
      const samples = dataset.samples || [];
      const sampleButtons = samples.slice(0, 8).map((sample) => {
        const name = (sample.image || "").split(/[\\/]/).pop() || "sample";
        return `<button type="button" data-delete-dataset-sample="${escapeAttr(dataset.id)}" data-sample-name="${escapeAttr(name)}">${escapeHtml(name)} ×</button>`;
      }).join("");
      const row = document.createElement("article");
      row.className = "resource-card";
      row.innerHTML = `
        <div>
          <strong>${escapeHtml(dataset.display_name || dataset.id)}</strong>
          <span>${dataset.sample_count || 0} 个样本 · ${dataset.missing_files ? "文件缺失" : "已归档"} · ${escapeHtml((dataset.selected_accessory_ids || []).join(", "))}</span>
          ${dataset.note ? `<span>${escapeHtml(dataset.note)}</span>` : ""}
          <small>${escapeHtml(dataset.manifest_path || "")}</small>
          <div class="sample-chip-row">${sampleButtons}</div>
        </div>
        <div class="resource-actions">
          <button type="button" data-open-dataset="${escapeAttr(dataset.id)}">查看</button>
          <button type="button" class="danger-action compact-danger" data-delete-dataset="${escapeAttr(dataset.id)}">删除样本库</button>
        </div>
      `;
      row.querySelector("div").addEventListener("click", () => openTrainingResourceDetail("dataset", dataset.id));
      datasetList.appendChild(row);
    }
  }
  if (modelList) {
    modelList.innerHTML = modelGroups.length ? "" : `<div class="job-empty">暂无训练模型资源</div>`;
    for (const group of modelGroups) {
      const task = group.task || {};
      const taskModels = group.models;
      const dataset = task.dataset;
      const missingCount = taskModels.filter((item) => !item.exists).length;
      const row = document.createElement("article");
      row.className = "resource-card";
      row.innerHTML = `
        <div>
          <strong>${escapeHtml(modelRunLabel(group))}</strong>
          <span>${escapeHtml(group.id)} · ${task.status ? STATUS_ZH[task.status] || task.status : "历史模型"} · ${task.sample_count || 0} 个样本</span>
          <span>配件：${escapeHtml(modelRunAccessoryText(group))}</span>
          <span>样本库：${dataset ? "已归档" : "未生成"} · 模型：${taskModels.length ? taskModels.map((item) => `${modelVariantLabel(item)}${item.exists ? "" : "（文件缺失）"}`).join(" / ") : "无"}${missingCount ? ` · 缺失 ${missingCount}` : ""}</span>
          ${task.note ? `<span>${escapeHtml(task.note)}</span>` : ""}
        </div>
        <div class="resource-actions">
          <button type="button" data-open-model-run="${escapeAttr(group.id)}">查看</button>
          ${taskModels.length ? `<button type="button" class="danger-action compact-danger" data-delete-model-run="${escapeAttr(group.id)}">删除整组模型</button>` : ""}
        </div>
      `;
      row.querySelector("div").addEventListener("click", () => openTrainingResourceDetail("modelRun", group.id));
      modelList.appendChild(row);
    }
  }
  bindTrainingLibraryActions();
  renderTrainingDatasetMenu();
}

function trainingDatasetOptions() {
  const datasets = state.trainingResources?.datasets || [];
  return datasets
    .filter((dataset) => !dataset.missing_files && Number(dataset.sample_count || 0) > 0)
    .map((dataset) => ({
      value: dataset.id,
      label: dataset.display_name || dataset.id,
      meta: `${dataset.sample_count || 0} 个样本`,
    }));
}

function renderTrainingDatasetMenu() {
  const menu = $("trainingDatasetMenu");
  if (!menu) return;
  const options = trainingDatasetOptions();
  if (!options.some((item) => item.value === state.selectedTrainingDatasetId)) {
    state.selectedTrainingDatasetId = options[0]?.value || "";
  }
  state.selectedTrainingDatasetId = renderCustomMenu("trainingDatasetMenu", options, state.selectedTrainingDatasetId, (value) => {
    state.selectedTrainingDatasetId = value;
    renderTrainingDatasetMenu();
    updateTrainingEstimates();
  });
  updateTrainingEstimates();
}

function backgroundSetOptions() {
  return (state.backgroundSets || [])
    .filter((item) => Number(item.image_count || 0) > 0 && (item.status || "ready") === "ready")
    .map((item) => ({
      value: item.id,
      label: item.name || item.id,
      meta: `${item.image_count || 0} 张背景`,
      thumbnail: item.images?.[0]?.url || "",
      actionLabel: "查看",
    }));
}

function renderTrainingBackgroundMenu() {
  const menu = $("trainingBackgroundMenu");
  if (!menu) return;
  const options = backgroundSetOptions();
  if (!options.some((item) => item.value === state.selectedBackgroundSetId)) {
    state.selectedBackgroundSetId = options[0]?.value || "";
  }
  state.selectedBackgroundSetId = renderCustomMenu("trainingBackgroundMenu", options, state.selectedBackgroundSetId, (value) => {
    state.selectedBackgroundSetId = value;
    state.trainingPreview = null;
    $("trainingPreviewGrid").innerHTML = "";
    closeCustomMenus();
    renderTrainingBackgroundMenu();
    updateTrainingEstimates();
  });
  const popover = menu.querySelector(".custom-menu-popover");
  if (popover) {
    const actions = document.createElement("div");
    actions.className = "background-menu-actions";
    actions.innerHTML = `<button type="button" class="background-menu-action add" data-background-action="add" aria-label="添加背景">+</button>`;
    popover.appendChild(actions);
    actions.querySelector('[data-background-action="add"]')?.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      closeCustomMenus();
      openBackgroundUploadModal();
    });
    menu.querySelectorAll(".custom-menu-option-action").forEach((button) => {
      button.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        closeCustomMenus();
        openBackgroundSetViewer(button.dataset.optionAction || "");
      });
    });
  }
}

function selectedBackgroundSet() {
  return (state.backgroundSets || []).find((item) => item.id === state.selectedBackgroundSetId);
}

function openBackgroundSetViewer(setId = "") {
  const set = (state.backgroundSets || []).find((item) => item.id === setId) || selectedBackgroundSet();
  const images = (set?.images || []).filter((item) => item.url);
  if (!images.length) return toast("当前背景集没有可预览的图片。");
  $("backgroundGalleryTitle").textContent = set.name || set.id || "背景预览";
  $("backgroundGalleryCount").textContent = `${images.length} 张背景`;
  $("backgroundGalleryGrid").innerHTML = images
    .map((item, index) => {
      const name = item.name || `background_${index + 1}`;
      return `
        <figure class="training-preview-card">
          <button class="preview-open" type="button" data-preview-url="${escapeAttr(item.url)}">
            <img src="${escapeAttr(item.url)}" alt="${escapeHtml(name)}" />
          </button>
          <figcaption>
            <strong>${escapeHtml(name)}</strong>
            <span>${escapeHtml(set.id || "")}</span>
          </figcaption>
        </figure>
      `;
    })
    .join("");
  bindImagePreviewTriggers($("backgroundGalleryGrid"));
  $("backgroundGalleryModal").classList.add("visible");
  $("backgroundGalleryModal").setAttribute("aria-hidden", "false");
}

function closeBackgroundGalleryModal() {
  $("backgroundGalleryModal").classList.remove("visible");
  $("backgroundGalleryModal").setAttribute("aria-hidden", "true");
  $("backgroundGalleryGrid").innerHTML = "";
  $("backgroundGalleryCount").textContent = "";
}

function openBackgroundUploadModal() {
  $("backgroundUploadModal").classList.add("visible");
  $("backgroundUploadModal").setAttribute("aria-hidden", "false");
}

function closeBackgroundUploadModal() {
  $("backgroundUploadModal").classList.remove("visible");
  $("backgroundUploadModal").setAttribute("aria-hidden", "true");
  if ($("trainingBackgroundFile")) $("trainingBackgroundFile").value = "";
}

function renderTrainingImageSizeMenu(selectedValue = null) {
  const current = String(selectedValue || $("trainingImageSizeMenu")?.dataset.value || "640");
  renderCustomMenu("trainingImageSizeMenu", TRAINING_IMAGE_SIZE_OPTIONS, current, (value) => {
    renderTrainingImageSizeMenu(value);
    updateTrainingEstimates();
  });
}

function bindTrainingLibraryActions() {
  document.querySelectorAll("[data-delete-dataset]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!window.confirm(`确认删除样本库 ${button.dataset.deleteDataset}？`)) return;
      await api(`/api/training/resources/datasets/${encodeURIComponent(button.dataset.deleteDataset)}`, { method: "DELETE" });
      await refreshTrainingLibrary();
      await refreshImageJobs();
      toast("样本库已删除。");
    });
  });
  document.querySelectorAll("[data-open-dataset]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      openTrainingResourceDetail("dataset", button.dataset.openDataset);
    });
  });
  document.querySelectorAll("[data-delete-dataset-sample]").forEach((button) => {
    button.addEventListener("click", async () => {
      await api(
        `/api/training/resources/datasets/${encodeURIComponent(button.dataset.deleteDatasetSample)}/samples/${encodeURIComponent(button.dataset.sampleName)}`,
        { method: "DELETE" },
      );
      await refreshTrainingLibrary();
      toast("样本已删除。");
    });
  });
  document.querySelectorAll("[data-delete-model-run]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!window.confirm(`确认删除模型组 ${button.dataset.deleteModelRun}？这会删除该训练 run 下的所有模型变体。`)) return;
      await api(`/api/training/resources/models/${encodeURIComponent(button.dataset.deleteModelRun)}`, { method: "DELETE" });
      await refreshTrainingLibrary();
      await refreshImageJobs();
      toast("模型组已删除。");
    });
  });
  document.querySelectorAll("[data-open-model-run]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      openTrainingResourceDetail("modelRun", button.dataset.openModelRun);
    });
  });
}

function closeTrainingResourceModal() {
  state.trainingResourceDetail = null;
  $("trainingResourceModal").classList.remove("visible");
  $("trainingResourceModal").setAttribute("aria-hidden", "true");
  $("trainingResourceBody").innerHTML = "";
}

function trainingTaskById(taskId) {
  return (state.trainingResources?.training_tasks || state.trainingResources?.tasks || []).find((item) => item.job_id === taskId);
}

function trainingModelRunById(runId) {
  return modelRunGroups(state.trainingResources?.models || [], state.trainingResources?.training_tasks || state.trainingResources?.tasks || [])
    .find((group) => group.id === runId);
}

function samplePublicUrl(sample) {
  if (sample.annotated_url) return sample.annotated_url;
  if (sample.url) return sample.url;
  const image = String(sample.image || "");
  const marker = "/data/outputs/";
  if (image.includes(marker)) return `/outputs/${image.split(marker).pop()}`;
  return "";
}

function openTrainingResourceDetail(kind, id) {
  state.trainingResourceDetail = { kind, id };
  const title = $("trainingResourceTitle");
  const body = $("trainingResourceBody");
  if (kind === "dataset") {
    const dataset = (state.trainingResources?.datasets || []).find((item) => item.id === id);
    if (!dataset) return toast("样本库不存在。");
    const samples = dataset.samples || [];
    title.textContent = dataset.display_name || dataset.id;
    body.innerHTML = `
      <div class="summary-grid resource-summary">
        <div><label>样本数量</label><strong>${samples.length || dataset.sample_count || 0}</strong></div>
        <div><label>Dataset ID</label><strong>${escapeHtml(dataset.id)}</strong></div>
        <div><label>配件</label><strong>${escapeHtml((dataset.selected_accessory_ids || []).join(", ") || "-")}</strong></div>
      </div>
      <div class="resource-edit-row">
        <input id="resourceRenameInput" type="text" value="${escapeAttr(dataset.display_name || dataset.id)}" />
        <input id="resourceNoteInput" type="text" value="${escapeAttr(dataset.note || "")}" placeholder="备注" />
        <button id="saveResourceRename" class="secondary" type="button">保存</button>
      </div>
      ${dataset.missing_files ? `<div class="job-empty">样本文件缺失或已被删除。后续新任务完成后会自动归档到这里。</div>` : ""}
      <div class="training-resource-thumb-grid">
        ${samples.map((sample) => {
          const url = samplePublicUrl(sample);
          const name = (sample.image || "").split(/[\\/]/).pop() || "sample";
          return `
            <figure class="training-preview-card">
              <button class="preview-open" type="button" data-preview-url="${escapeAttr(url)}">
                <img src="${escapeAttr(url)}" alt="${escapeHtml(name)}" />
              </button>
              <figcaption>
                <strong>${escapeHtml(name)}</strong>
                <span>${sample.is_true ? "True" : "False"} · ${escapeHtml(sample.split || "-")} · 缺 ${sample.missing_count || 0}</span>
                <button type="button" class="mini-danger" data-delete-detail-sample="${escapeAttr(name)}">删除</button>
              </figcaption>
            </figure>
          `;
        }).join("")}
      </div>
    `;
    $("saveResourceRename").addEventListener("click", () => saveTrainingResourceRename("dataset", dataset.id));
    bindImagePreviewTriggers(body);
    body.querySelectorAll("[data-delete-detail-sample]").forEach((button) => {
      button.addEventListener("click", async () => {
        await api(`/api/training/resources/datasets/${encodeURIComponent(dataset.id)}/samples/${encodeURIComponent(button.dataset.deleteDetailSample)}`, { method: "DELETE" });
        await refreshTrainingLibrary();
        openTrainingResourceDetail("dataset", dataset.id);
        toast("样本已删除。");
      });
    });
  } else {
    const group = kind === "modelRun" ? trainingModelRunById(id) : trainingModelRunById(id);
    const task = group?.task || trainingTaskById(id) || {};
    const models = group?.models || task.models || (state.trainingResources?.models || []).filter((model) => model.task_id === id);
    if (!group && !task.job_id) return toast("训练模型不存在。");
    title.textContent = group ? modelRunLabel(group) : task.label || task.job_id;
    const isBackgroundTask = task.action === "generate_background_set";
    const currentEpoch = Number(task.current_epoch || 0);
    const totalEpochs = Number(task.total_epochs || task.epochs || 0);
    body.innerHTML = `
      <div class="summary-grid resource-summary">
        <div><label>状态</label><strong>${escapeHtml(task.status ? STATUS_ZH[task.status] || task.status : "历史模型")}</strong></div>
        <div><label>${isBackgroundTask ? "背景" : "样本"}</label><strong>${isBackgroundTask ? `${task.generated_image_count || 0} 张` : `${task.completed_samples || task.sample_count || 0}/${task.sample_count || 0}`}</strong></div>
        <div><label>当前 Epoch</label><strong>${totalEpochs ? `${currentEpoch}/${totalEpochs}` : "-"}</strong></div>
        <div><label>总 Epoch</label><strong>${task.epochs || totalEpochs || "-"}</strong></div>
        <div><label>分辨率</label><strong>${task.image_size || "-"}</strong></div>
        <div><label>模型</label><strong>${models.length}</strong></div>
      </div>
      <div class="resource-edit-row">
        <input id="resourceRenameInput" type="text" value="${escapeAttr(task.label || models[0]?.label || id)}" />
        <input id="resourceNoteInput" type="text" value="${escapeAttr(task.note || models[0]?.note || "")}" placeholder="备注" />
        <button id="saveResourceRename" class="secondary" type="button">保存</button>
      </div>
      <div class="resource-detail-list">
        <p><strong>Run ID</strong><span>${escapeHtml(group?.id || id)}</span></p>
        <p><strong>Task ID</strong><span>${escapeHtml(task.job_id || models[0]?.task_id || "-")}</span></p>
        ${isBackgroundTask ? `<p><strong>背景集</strong><span>${escapeHtml(task.background_set_id || "-")}</span></p>` : ""}
        <p><strong>配件</strong><span>${escapeHtml(group ? modelRunAccessoryText(group) : "-")}</span></p>
        <p><strong>Epoch 进度</strong><span>${totalEpochs ? `${currentEpoch}/${totalEpochs}` : "-"}</span></p>
        <p><strong>Manifest</strong><span>${escapeHtml(task.manifest_path || "-")}</span></p>
        <p><strong>训练日志</strong><span>${escapeHtml(task.training_log_path || "-")}</span></p>
        ${models.map((model) => `<p><strong>${modelVariantLabel(model)}${model.exists ? "" : "（文件缺失）"}</strong><span>${escapeHtml(model.path || "")}</span></p>`).join("")}
      </div>
    `;
    $("saveResourceRename").addEventListener("click", () => saveTrainingResourceRename(group ? "modelRun" : "task", group?.id || task.job_id));
  }
  $("trainingResourceModal").classList.add("visible");
  $("trainingResourceModal").setAttribute("aria-hidden", "false");
}

async function saveTrainingResourceRename(kind, id) {
  const displayName = $("resourceRenameInput")?.value || "";
  const note = $("resourceNoteInput")?.value || "";
  if (kind === "dataset") {
    await api(`/api/training/resources/datasets/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_name: displayName, note }),
    });
  } else if (kind === "modelRun") {
    const task = trainingTaskById(id);
    if (task && task.action !== "trained_model") {
      await api(`/api/training/tasks/${encodeURIComponent(id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label: displayName, note }),
      }).catch(() => null);
    }
    await api(`/api/training/resources/models/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_name: displayName, note }),
    });
  } else {
    await api(`/api/training/tasks/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label: displayName, note }),
    }).catch(() => null);
    await api(`/api/training/resources/models/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_name: displayName, note }),
    });
  }
  await refreshTrainingLibrary();
  await refreshImageJobs();
  openTrainingResourceDetail(kind, id);
  toast("已保存。");
}

function syncOpenAccessoryJobProgress() {
  if (!state.accessoryCandidate?.id) return;
  const jobs = state.imageJobs.filter((item) => item.candidate_id === state.accessoryCandidate.id);
  if (!jobs.length) return;
  state.accessoryCandidate.codex_image_jobs = jobs;
  state.accessoryCandidate.codex_image_job = jobs[0];
  setImageWorkerProgress(summarizeCandidateJobs(jobs));
}

function renderImageJobs(result) {
  const items = result.items || [];
  const groups = groupImageJobsByCandidate(items);
  const active = groups.filter((group) => group.jobs.some((job) => isActiveImageJobStatus(job.status)));
  $("imageJobCount").textContent = active.length;
  $("imageJobSummary").textContent = active.length ? `${active.length} 个任务进行中` : "空闲";
  const list = $("imageJobList");
  list.innerHTML = "";
  if (!groups.length) {
    list.innerHTML = `<div class="job-empty">暂无生成任务</div>`;
    return;
  }
  for (const group of groups.slice(0, 12)) {
    const summary = summarizeCandidateJobs(group.jobs) || group.jobs[0];
    const statusText = STATUS_ZH[summary.status] || summary.status;
    const isTrainingTask = summary.queue_kind === "training";
    const isBackgroundTask = summary.action === "generate_background_set";
    const taskIds = group.jobs.map((job) => job.task_id || job.job_id || "task");
    const taskIdHtml = taskIds.map((id) => `<code class="task-id-chip">${escapeHtml(id)}</code>`).join("");
    const detail = group.jobs.map((job) => {
      const provenance = anchorProvenanceText(job);
      const estimate = job.estimated_minutes ? ` · 预计 ${job.estimated_minutes} 分钟` : "";
      const sampleInfo = job.action === "generate_background_set"
        ? ` · ${job.generated_image_count || 0} 张背景`
        : job.sample_count ? ` · ${job.sample_count} samples` : "";
      const epochInfo = job.action === "train_model" ? ` · Epoch ${job.current_epoch || 0}/${job.total_epochs || job.epochs || "-"}` : "";
      const trainingParams = job.action === "train_model" ? ` · ${job.epochs || "-"} epoch · ${job.image_size || "-"}px${epochInfo}` : "";
      return `${userJobLabel(job.label || job.pose_family)} · ${STATUS_ZH[job.status] || job.status}${sampleInfo}${trainingParams}${estimate}${provenance ? ` · ${provenance}` : ""}`;
    }).join("；");
    const activeJobs = group.jobs.filter((job) => isActiveImageJobStatus(job.status));
    const row = document.createElement("div");
    row.className = "job-item";
    row.innerHTML = `
      <span>
        <strong>${escapeHtml(zhLabel(group.candidate_name || "Accessory"))}</strong>
        <em>${escapeHtml(statusText)} · ${isBackgroundTask ? `${summary.generated_image_count || 0} 张背景` : isTrainingTask ? `${summary.sample_count || 0} 个样本` : `${group.jobs.length} 张图`}</em>
        <span class="task-id-row" aria-label="Task IDs">${taskIdHtml}</span>
        <small>${escapeHtml(detail)}</small>
      </span>
      <progress value="${summary.progress || 0}" max="100">${summary.progress || 0}%</progress>
      <div class="job-actions">
        ${isTrainingTask ? `<button type="button" class="queue-icon-button" data-view-training-task="${escapeAttr(summary.job_id)}" title="查看任务">i</button>` : `<button type="button" data-open-job="${escapeAttr(group.candidate_id)}">打开</button>`}
        ${!isTrainingTask && activeJobs.length ? `<button type="button" data-stop-candidate="${escapeAttr(group.candidate_id)}">停止</button>` : ""}
        ${isTrainingTask ? `<button type="button" class="queue-icon-button" data-delete-training-task="${escapeAttr(summary.job_id)}" title="删除任务">Del</button>` : `<button type="button" data-delete-candidate="${escapeAttr(group.candidate_id)}">删除</button>`}
      </div>
    `;
    row.querySelector("span").addEventListener("click", () => {
      if (isTrainingTask) openTrainingTaskDetail(summary.job_id);
      else openImageJobCandidate(group.candidate_id);
    });
    list.appendChild(row);
  }
  bindImageJobActions();
}

async function openImageJobCandidate(candidateId) {
  try {
    const result = await api(`/api/accessories/candidates/${encodeURIComponent(candidateId)}`);
    openAccessoryReview(result.candidate);
    await refreshImageJobs();
    updateOpenAccessoryCandidateFromJobs();
  } catch (error) {
    toast(`打开任务失败：${error.message}`);
  }
}

async function openTrainingTaskDetail(jobId) {
  try {
    await refreshTrainingLibrary();
    openTrainingResourceDetail("task", jobId);
  } catch (error) {
    toast(`打开任务失败：${error.message}`);
  }
}

function bindImageJobActions() {
  document.querySelectorAll("[data-open-job]").forEach((button) => {
    button.addEventListener("click", () => openImageJobCandidate(button.dataset.openJob));
  });
  document.querySelectorAll("[data-view-training-task]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      openTrainingTaskDetail(button.dataset.viewTrainingTask);
    });
  });
  document.querySelectorAll("[data-delete-training-task]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.stopPropagation();
      if (!window.confirm(`确认删除任务 ${button.dataset.deleteTrainingTask}？`)) return;
      await api(`/api/training/tasks/${encodeURIComponent(button.dataset.deleteTrainingTask)}`, { method: "DELETE" });
      await refreshImageJobs();
      toast("任务已删除。");
    });
  });
  document.querySelectorAll("[data-stop-candidate]").forEach((button) => {
    button.addEventListener("click", async () => {
      await api(`/api/image-job-candidates/${encodeURIComponent(button.dataset.stopCandidate)}/stop`, { method: "POST" });
      await refreshImageJobs();
      toast("任务已停止。");
    });
  });
  document.querySelectorAll("[data-delete-candidate]").forEach((button) => {
    button.addEventListener("click", async () => {
      await api(`/api/image-job-candidates/${encodeURIComponent(button.dataset.deleteCandidate)}`, { method: "DELETE" });
      await refreshImageJobs();
      toast("任务已删除。");
    });
  });
  document.querySelectorAll("[data-stop-job]").forEach((button) => {
    button.addEventListener("click", async () => {
      await api(`/api/image-jobs/${encodeURIComponent(button.dataset.stopJob)}/stop`, { method: "POST" });
      await refreshImageJobs();
      toast("任务已停止。");
    });
  });
  document.querySelectorAll("[data-delete-job]").forEach((button) => {
    button.addEventListener("click", async () => {
      await api(`/api/image-jobs/${encodeURIComponent(button.dataset.deleteJob)}`, { method: "DELETE" });
      await refreshImageJobs();
      toast("任务已删除。");
    });
  });
}

function groupImageJobsByCandidate(items) {
  const groups = new Map();
  for (const job of items || []) {
    const candidateId = job.candidate_id || job.job_id || "unknown";
    if (!groups.has(candidateId)) {
      groups.set(candidateId, {
        candidate_id: candidateId,
        candidate_name: job.candidate_name || "Accessory",
        jobs: [],
        created_at: job.created_at || 0,
      });
    }
    const group = groups.get(candidateId);
    group.jobs.push(job);
    group.created_at = Math.max(group.created_at || 0, job.created_at || 0);
  }
  return Array.from(groups.values()).sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
}

function updateOpenAccessoryCandidateFromJobs() {
  if (!state.accessoryCandidate?.id) return;
  const jobs = state.imageJobs.filter((item) => item.candidate_id === state.accessoryCandidate.id);
  if (!jobs.length) return;
  const grid = $("accessoryThumbGrid");
  for (const job of [...jobs].reverse()) {
    if (job.status !== "completed" || !job.output_url) continue;
    const alreadyRendered = Array.from(document.querySelectorAll("[data-preview-url]")).some((button) => button.dataset.previewUrl === job.output_url);
    if (alreadyRendered) continue;
    const card = document.createElement("figure");
    card.className = "training-preview-card";
    const title = userJobLabel(job.label || (job.pose_family === "upright" ? "正立多角度视图" : job.pose_family === "lying" ? "平躺多角度视图" : "多角度视图"));
    card.innerHTML = `
      <button class="preview-open" type="button" data-preview-url="${escapeAttr(job.output_url)}">
        <img src="${escapeAttr(job.output_url)}?t=${Date.now()}" alt="${escapeHtml(title)} 生成结果" />
      </button>
      <figcaption>
        <strong>${escapeHtml(title)}</strong>
        <span>生成结果</span>
        ${anchorProvenanceText(job) ? `<small>${escapeHtml(anchorProvenanceText(job))}</small>` : ""}
      </figcaption>
    `;
    grid.prepend(card);
    bindImagePreviewTriggers(card);
  }
  setImageWorkerProgress(summarizeCandidateJobs(jobs));
}

function renderAccessoryProcess() {
  const type = $("accessoryMaterialType").value;
  const node = $("accessoryProcess");
  $("textDimensionFields").classList.toggle("hidden", type !== "text");
  $("objectDimensionFields").classList.toggle("hidden", type !== "object");
  if (type === "text") {
    updatePaperDimensionLock();
    node.innerHTML = `
      <strong>文字类预处理</strong>
      <span>可上传拍摄到四角的文档照片，系统会按纸张规格做四边形裁切、透视纠偏，并为 OCR 训练保留文字区域。</span>
    `;
  } else {
    if (!$("objectLengthMm").value) $("objectLengthMm").value = 170;
    if (!$("objectWidthMm").value) $("objectWidthMm").value = 38;
    if (!$("objectHeightMm").value) $("objectHeightMm").value = 38;
    node.innerHTML = `
      <strong>物品类预处理</strong>
      <span>系统会先分析物体结构和摆放状态，再生成可用于训练的多角度参考素材。</span>
    `;
  }
}

function alphaPolicyLabel(policy) {
  return policy === "transparent" ? "透明" : policy === "opaque" ? "不透明" : "未选择";
}

function updatePaperDimensionLock() {
  const preset = $("paperPreset").value;
  const locked = Boolean(PAPER_PRESETS[preset]);
  if (locked) {
    $("paperWidthMm").value = PAPER_PRESETS[preset][0];
    $("paperHeightMm").value = PAPER_PRESETS[preset][1];
  }
  $("paperWidthMm").disabled = locked;
  $("paperHeightMm").disabled = locked;
  $("paperWidthMm").title = locked ? "标准纸张规格由预设锁定" : "";
  $("paperHeightMm").title = locked ? "标准纸张规格由预设锁定" : "";
}

function averageLength(points, pairs) {
  const lengths = pairs.map(([a, b]) => Math.hypot(points[a].x - points[b].x, points[a].y - points[b].y));
  return lengths.reduce((sum, value) => sum + value, 0) / Math.max(1, lengths.length);
}

function textPaperOutputSize(image = null, displayPoints = null, displayScale = 1) {
  const widthMm = Math.max(1, Number($("paperWidthMm").value || PAPER_PRESETS.A4[0]));
  const heightMm = Math.max(1, Number($("paperHeightMm").value || PAPER_PRESETS.A4[1]));
  let width;
  let height;
  if (image && Array.isArray(displayPoints) && displayPoints.length === 4 && displayScale > 0) {
    const sourcePoints = displayPoints.map((point) => ({ x: point.x / displayScale, y: point.y / displayScale }));
    const sourceWidth = averageLength(sourcePoints, [[0, 1], [3, 2]]);
    const sourceHeight = averageLength(sourcePoints, [[0, 3], [1, 2]]);
    const pxPerMm = Math.max(sourceWidth / widthMm, sourceHeight / heightMm);
    width = Math.round(widthMm * pxPerMm);
    height = Math.round(heightMm * pxPerMm);
  } else {
    if (widthMm <= heightMm) {
      width = TEXT_CROP_BASE_SHORT_PX;
      height = Math.round(width * (heightMm / widthMm));
    } else {
      height = TEXT_CROP_BASE_SHORT_PX;
      width = Math.round(height * (widthMm / heightMm));
    }
  }
  const shortSide = Math.min(width, height);
  if (shortSide < TEXT_CROP_BASE_SHORT_PX) {
    const scale = TEXT_CROP_BASE_SHORT_PX / Math.max(1, shortSide);
    width = Math.max(1, Math.round(width * scale));
    height = Math.max(1, Math.round(height * scale));
  }
  const longSide = Math.max(width, height);
  if (longSide > TEXT_CROP_MAX_LONG_PX) {
    const scale = TEXT_CROP_MAX_LONG_PX / longSide;
    width = Math.max(1, Math.round(width * scale));
    height = Math.max(1, Math.round(height * scale));
  }
  return { width, height, widthMm, heightMm };
}

function updateDocumentCropOutputLabel() {
  const crop = state.crop;
  const output = crop ? textPaperOutputSize(crop.image, crop.points, crop.displayScale) : textPaperOutputSize();
  $("documentCropOutput").textContent = `输出 ${output.width} × ${output.height}px`;
}

function loadCropImage(file) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    const url = URL.createObjectURL(file);
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error(`无法读取图片：${file.name}`));
    };
    image.src = url;
  });
}

function resetCropPoints() {
  const crop = state.crop;
  if (!crop) return;
  const marginX = crop.displayWidth * 0.08;
  const marginY = crop.displayHeight * 0.08;
  crop.points = [
    { x: marginX, y: marginY },
    { x: crop.displayWidth - marginX, y: marginY },
    { x: crop.displayWidth - marginX, y: crop.displayHeight - marginY },
    { x: marginX, y: crop.displayHeight - marginY },
  ];
  updateDocumentCropOutputLabel();
  drawCropCanvas();
}

function drawCropCanvas() {
  const crop = state.crop;
  if (!crop) return;
  const canvas = $("documentCropCanvas");
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(crop.image, 0, 0, crop.displayWidth, crop.displayHeight);
  ctx.fillStyle = "rgba(0, 0, 0, 0.28)";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.save();
  ctx.beginPath();
  crop.points.forEach((point, index) => {
    if (index === 0) ctx.moveTo(point.x, point.y);
    else ctx.lineTo(point.x, point.y);
  });
  ctx.closePath();
  ctx.clip();
  ctx.drawImage(crop.image, 0, 0, crop.displayWidth, crop.displayHeight);
  ctx.restore();
  ctx.beginPath();
  crop.points.forEach((point, index) => {
    if (index === 0) ctx.moveTo(point.x, point.y);
    else ctx.lineTo(point.x, point.y);
  });
  ctx.closePath();
  ctx.strokeStyle = "#1f7a4d";
  ctx.lineWidth = 3;
  ctx.stroke();
  crop.points.forEach((point, index) => {
    ctx.beginPath();
    ctx.arc(point.x, point.y, 8, 0, Math.PI * 2);
    ctx.fillStyle = "#ffffff";
    ctx.fill();
    ctx.lineWidth = 3;
    ctx.strokeStyle = index === crop.activePoint ? "#111315" : "#1f7a4d";
    ctx.stroke();
  });
}

function nearestCropPoint(x, y) {
  const crop = state.crop;
  if (!crop) return -1;
  let bestIndex = -1;
  let bestDistance = 18;
  crop.points.forEach((point, index) => {
    const distance = Math.hypot(point.x - x, point.y - y);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  });
  return bestIndex;
}

function cropPointerPosition(event) {
  const canvas = $("documentCropCanvas");
  const rect = canvas.getBoundingClientRect();
  const scaleX = canvas.width / Math.max(rect.width, 1);
  const scaleY = canvas.height / Math.max(rect.height, 1);
  return {
    x: Math.max(0, Math.min(canvas.width, (event.clientX - rect.left) * scaleX)),
    y: Math.max(0, Math.min(canvas.height, (event.clientY - rect.top) * scaleY)),
  };
}

function solveLinearSystem(matrix, values) {
  const n = values.length;
  const rows = matrix.map((row, index) => [...row, values[index]]);
  for (let col = 0; col < n; col += 1) {
    let pivot = col;
    for (let row = col + 1; row < n; row += 1) {
      if (Math.abs(rows[row][col]) > Math.abs(rows[pivot][col])) pivot = row;
    }
    [rows[col], rows[pivot]] = [rows[pivot], rows[col]];
    const divisor = rows[col][col] || 1e-12;
    for (let cell = col; cell <= n; cell += 1) rows[col][cell] /= divisor;
    for (let row = 0; row < n; row += 1) {
      if (row === col) continue;
      const factor = rows[row][col];
      for (let cell = col; cell <= n; cell += 1) rows[row][cell] -= factor * rows[col][cell];
    }
  }
  return rows.map((row) => row[n]);
}

function homographyFromRectToQuad(width, height, quad) {
  const src = [
    [0, 0],
    [width - 1, 0],
    [width - 1, height - 1],
    [0, height - 1],
  ];
  const matrix = [];
  const values = [];
  for (let i = 0; i < 4; i += 1) {
    const [x, y] = src[i];
    const point = quad[i];
    matrix.push([x, y, 1, 0, 0, 0, -point.x * x, -point.x * y]);
    values.push(point.x);
    matrix.push([0, 0, 0, x, y, 1, -point.y * x, -point.y * y]);
    values.push(point.y);
  }
  return solveLinearSystem(matrix, values);
}

function cropQuadArea(points) {
  let area = 0;
  for (let index = 0; index < points.length; index += 1) {
    const current = points[index];
    const next = points[(index + 1) % points.length];
    area += current.x * next.y - next.x * current.y;
  }
  return Math.abs(area) / 2;
}

function segmentOrientation(a, b, c) {
  const value = (b.y - a.y) * (c.x - b.x) - (b.x - a.x) * (c.y - b.y);
  if (Math.abs(value) < 1e-6) return 0;
  return value > 0 ? 1 : 2;
}

function segmentsIntersect(a, b, c, d) {
  const o1 = segmentOrientation(a, b, c);
  const o2 = segmentOrientation(a, b, d);
  const o3 = segmentOrientation(c, d, a);
  const o4 = segmentOrientation(c, d, b);
  return o1 !== o2 && o3 !== o4;
}

function validateCropQuad(points, width, height) {
  if (!points.every((point) => Number.isFinite(point.x) && Number.isFinite(point.y))) {
    return "四角坐标无效，请重置后重新拖动。";
  }
  for (let index = 0; index < points.length; index += 1) {
    const current = points[index];
    const next = points[(index + 1) % points.length];
    if (Math.hypot(current.x - next.x, current.y - next.y) < 24) {
      return "相邻角点太近，请拉开四个角覆盖纸张。";
    }
  }
  if (segmentsIntersect(points[0], points[1], points[2], points[3]) || segmentsIntersect(points[1], points[2], points[3], points[0])) {
    return "四角顺序交叉，请按纸张外轮廓拖成不交叉四边形。";
  }
  if (cropQuadArea(points) < width * height * 0.04) {
    return "裁切区域太小，请覆盖完整文档纸面。";
  }
  return "";
}

function sampleBilinear(data, width, height, x, y) {
  const clampedX = Math.max(0, Math.min(width - 1, x));
  const clampedY = Math.max(0, Math.min(height - 1, y));
  const x0 = Math.floor(clampedX);
  const y0 = Math.floor(clampedY);
  const x1 = Math.min(width - 1, x0 + 1);
  const y1 = Math.min(height - 1, y0 + 1);
  const dx = clampedX - x0;
  const dy = clampedY - y0;
  const base00 = (y0 * width + x0) * 4;
  const base10 = (y0 * width + x1) * 4;
  const base01 = (y1 * width + x0) * 4;
  const base11 = (y1 * width + x1) * 4;
  const out = [0, 0, 0, 255];
  for (let channel = 0; channel < 4; channel += 1) {
    const top = data[base00 + channel] * (1 - dx) + data[base10 + channel] * dx;
    const bottom = data[base01 + channel] * (1 - dx) + data[base11 + channel] * dx;
    out[channel] = top * (1 - dy) + bottom * dy;
  }
  return out;
}

function rectifyCropToBlob(image, displayPoints, displayScale, outputSize) {
  const sourceCanvas = document.createElement("canvas");
  sourceCanvas.width = image.naturalWidth;
  sourceCanvas.height = image.naturalHeight;
  const sourceCtx = sourceCanvas.getContext("2d", { willReadFrequently: true });
  sourceCtx.drawImage(image, 0, 0);
  const source = sourceCtx.getImageData(0, 0, sourceCanvas.width, sourceCanvas.height);
  const quad = displayPoints.map((point) => ({ x: point.x / displayScale, y: point.y / displayScale }));
  const h = homographyFromRectToQuad(outputSize.width, outputSize.height, quad);
  const outputCanvas = document.createElement("canvas");
  outputCanvas.width = outputSize.width;
  outputCanvas.height = outputSize.height;
  const outputCtx = outputCanvas.getContext("2d");
  const output = outputCtx.createImageData(outputSize.width, outputSize.height);
  for (let y = 0; y < outputSize.height; y += 1) {
    for (let x = 0; x < outputSize.width; x += 1) {
      const denom = h[6] * x + h[7] * y + 1;
      const sx = (h[0] * x + h[1] * y + h[2]) / denom;
      const sy = (h[3] * x + h[4] * y + h[5]) / denom;
      const pixel = sampleBilinear(source.data, source.width, source.height, sx, sy);
      const offset = (y * outputSize.width + x) * 4;
      output.data[offset] = pixel[0];
      output.data[offset + 1] = pixel[1];
      output.data[offset + 2] = pixel[2];
      output.data[offset + 3] = pixel[3];
    }
  }
  outputCtx.putImageData(output, 0, 0);
  return new Promise((resolve) => outputCanvas.toBlob(resolve, "image/png"));
}

async function openDocumentCropModal(file, index, total) {
  const image = await loadCropImage(file);
  const maxWidth = Math.min(760, window.innerWidth - 56);
  const maxHeight = Math.min(560, window.innerHeight - 250);
  const scale = Math.min(maxWidth / image.naturalWidth, maxHeight / image.naturalHeight, 1);
  const canvas = $("documentCropCanvas");
  canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
  canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
  $("documentCropTitle").textContent = `文档四角裁切 ${index + 1}/${total}`;
  $("documentCropDetail").textContent = `${file.name} · 原图 ${image.naturalWidth} × ${image.naturalHeight}px，拖动四个角点贴合纸张边缘`;
  $("documentCropOutput").textContent = "输出按原图裁切区域计算";
  $("documentCropModal").classList.add("visible");
  $("documentCropModal").setAttribute("aria-hidden", "false");
  return new Promise((resolve, reject) => {
    state.crop = {
      file,
      image,
      displayWidth: canvas.width,
      displayHeight: canvas.height,
      displayScale: scale,
      activePoint: -1,
      resolve,
      reject,
    };
    resetCropPoints();
  });
}

function closeDocumentCropModal() {
  $("documentCropModal").classList.remove("visible");
  $("documentCropModal").setAttribute("aria-hidden", "true");
  state.crop = null;
}

async function confirmDocumentCrop() {
  const crop = state.crop;
  if (!crop) return;
  const validationError = validateCropQuad(crop.points, crop.displayWidth, crop.displayHeight);
  if (validationError) {
    toast(validationError);
    return;
  }
  const outputSize = textPaperOutputSize(crop.image, crop.points, crop.displayScale);
  const blob = await rectifyCropToBlob(crop.image, crop.points, crop.displayScale, outputSize);
  if (!blob) {
    crop.reject(new Error("裁切输出失败"));
    closeDocumentCropModal();
    return;
  }
  const filename = crop.file.name.replace(/\.[^.]+$/, "") || "document";
  const rectified = new File([blob], `${filename}_rectified.png`, { type: "image/png" });
  crop.resolve(rectified);
  closeDocumentCropModal();
}

function cancelDocumentCrop() {
  if (state.crop?.reject) state.crop.reject(new Error("已取消文档裁切"));
  closeDocumentCropModal();
}

async function prepareTextAccessoryFiles(files) {
  const prepared = [];
  const imageFiles = files.filter((file) => file.type.startsWith("image/"));
  let imageIndex = 0;
  for (const file of files) {
    if (!file.type.startsWith("image/")) {
      prepared.push(file);
      continue;
    }
    prepared.push(await openDocumentCropModal(file, imageIndex, imageFiles.length));
    imageIndex += 1;
  }
  return prepared;
}

function finishCropPointer(event) {
  const crop = state.crop;
  if (!crop) return;
  crop.activePoint = -1;
  const canvas = $("documentCropCanvas");
  if (canvas.hasPointerCapture?.(event.pointerId)) {
    canvas.releasePointerCapture(event.pointerId);
  }
  drawCropCanvas();
}

function selectedTrainingAccessoryIds() {
  return Array.from(document.querySelectorAll("[data-training-accessory].selected")).map((item) => item.dataset.trainingAccessory);
}

function renderTrainingAccessories(selectedIds = null) {
  const wrap = $("trainingAccessoryList");
  if (!wrap) return;
  const selected = new Set(selectedIds || state.config?.training?.selected_accessory_ids || []);
  renderSelectedTrainingList(selected);
  wrap.innerHTML = "";
  for (const item of state.accessories) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = `training-accessory ${selected.has(item.id) ? "selected" : ""}`;
    row.dataset.trainingAccessory = item.id;
    const material = item.material_type === "text" ? "文字" : "物品";
    row.innerHTML = `
      <span>
        <strong>${escapeHtml(zhLabel(item.name))}</strong>
        <em>${material} · ${escapeHtml(STATUS_ZH[item.status] || item.status)}</em>
      </span>
    `;
    row.addEventListener("click", () => {
      row.classList.toggle("selected");
      renderSelectedTrainingList(new Set(selectedTrainingAccessoryIds()));
      updateTrainingEstimates();
    });
    wrap.appendChild(row);
  }
}

function renderSelectedTrainingList(selected) {
  const list = $("selectedTrainingList");
  if (!list) return;
  const ids = new Set(selected || selectedTrainingAccessoryIds());
  const items = state.accessories.filter((item) => ids.has(item.id));
  if (!items.length) {
    list.innerHTML = `<span class="empty-inline">尚未添加配件</span>`;
    return;
  }
  list.innerHTML = "";
  for (const item of items) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "selected-chip";
    chip.dataset.removeTrainingAccessory = item.id;
    chip.textContent = `${zhLabel(item.name)} ×`;
    chip.addEventListener("click", () => {
      Array.from(document.querySelectorAll("[data-training-accessory]")).find((button) => button.dataset.trainingAccessory === item.id)?.classList.remove("selected");
      renderSelectedTrainingList(new Set(selectedTrainingAccessoryIds()));
      updateTrainingEstimates();
    });
    list.appendChild(chip);
  }
}

function renderTrainingPlan(plan) {
  const training = plan.training || state.config?.training || {};
  state.backgroundSets = plan.background_sets || state.backgroundSets || [];
  state.selectedBackgroundSetId = training.background_set_id || plan.default_background_set_id || state.selectedBackgroundSetId || "";
  $("trainingStatus").textContent = STATUS_ZH[training.status] || training.status || "空闲";
  $("trainingNote").textContent = training.preview_stale_reason
    ? "当前预览已过期，请重新生成预览图。"
    : compactTrainingStatusNote(training.note);
  $("trainingSampleCount").value = training.sample_count || 4000;
  $("trainingMode").value = training.mode || "yolo_ocr";
  if ($("trainingEpochs")) $("trainingEpochs").value = training.epochs || 80;
  if ($("trainingPreviewPose")) $("trainingPreviewPose").value = training.preview_pose_family_policy || "auto";
  renderTrainingImageSizeMenu(training.image_size || 640);
  renderTrainingBackgroundMenu();
  renderTrainingAccessories(training.selected_accessory_ids);
  updateTrainingEstimates();
  if (training.preview_stale_reason) {
    state.trainingPreview = null;
    $("trainingPreviewGrid").innerHTML = "";
    renderPreviewSummary({ sample_count: training.sample_count || 4000, selected_accessories: [] });
    return;
  }
  if (training.previews?.length && !training.preview_stale_reason) {
    renderTrainingPreview(
      {
        id: training.last_preview_id || "latest",
        previews: training.previews,
        preview_cache_key: training.preview_cache_key,
        preview_sprite_versions: training.preview_sprite_versions,
        preview_pose_family_policy: training.preview_pose_family_policy,
        preview_pose_family_label: training.preview_pose_family_label,
      },
      { openModal: false },
    );
  }
}

function showTrainingFlowTab(tab) {
  document.querySelectorAll("[data-training-flow-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.trainingFlowTab === tab);
  });
  $("sampleFlowPane")?.classList.toggle("active", tab === "samples");
  $("modelFlowPane")?.classList.toggle("active", tab === "model");
  $("buildTrainingPreview")?.classList.toggle("hidden", tab !== "samples");
  $("confirmGenerateSamples")?.classList.toggle("hidden", tab !== "samples");
  $("sampleEstimateBox")?.classList.toggle("hidden", tab !== "samples");
  $("modelEstimateBox")?.classList.toggle("hidden", tab !== "model");
  renderTrainingDatasetMenu();
  renderTrainingBackgroundMenu();
  updateTrainingEstimates();
}

function previewPoseLabel(item) {
  const family = item.pose_family_policy || item.labels?.find((label) => label.preview_pose_family_policy)?.preview_pose_family_policy;
  if (!family) return "受控视角";
  return family === "upright" || family.includes("top") ? "正立/顶视图" : "平躺视图";
}

function previewPolicyLabel(preview) {
  const policy = preview.preview_pose_family_policy || "auto";
  const family = preview.preview_pose_family_label || preview.previews?.find((item) => item.pose_family_policy)?.pose_family_policy;
  if (policy === "lying") return "仅平躺视角";
  if (policy === "upright") return "仅正立/顶视角";
  if (family) return `自动 · ${previewPoseLabel({ pose_family_policy: family })}`;
  return "自动";
}

function previewAuditText(item) {
  const objectLabel = (item.labels || []).find((label) => label.sprite_path || label.render_pose_policy);
  const documentLabel = (item.labels || []).find(
    (label) => label.material_type === "text" && (label.document_mask_crop_bypassed || label.document_asset_path || label.render_resize_policy),
  );
  const sections = [];
  if (documentLabel) {
    const physical = documentLabel.physical_size || {};
    const footprint = documentLabel.render_box_px || documentLabel.render_footprint_px || documentLabel.render_visible_footprint_px;
    const parts = [
      documentLabel.document_asset_path ? "document direct-paste" : "document placeholder",
      documentLabel.document_asset_method ? `asset ${documentLabel.document_asset_method}` : null,
      documentLabel.document_asset_source ? `source ${documentLabel.document_asset_source}` : null,
      documentLabel.document_full_asset_pasted ? "full asset pasted" : null,
      documentLabel.document_asset_policy ? `policy ${documentLabel.document_asset_policy}` : null,
      documentLabel.document_physical_scale_basis ? `basis ${documentLabel.document_physical_scale_basis}` : null,
      physical.width_mm && physical.height_mm ? `paper ${physical.width_mm}x${physical.height_mm}mm` : null,
      Array.isArray(footprint) && footprint.length >= 2 ? `paper-scale ${footprint[0]}x${footprint[1]}px` : null,
      Array.isArray(documentLabel.canonical_asset_dimensions_px) && documentLabel.canonical_asset_dimensions_px.length >= 2
        ? `asset ${documentLabel.canonical_asset_dimensions_px[0]}x${documentLabel.canonical_asset_dimensions_px[1]}px`
        : null,
      documentLabel.document_mask_crop_bypassed ? "mask-crop bypass" : null,
      documentLabel.object_alpha_pipeline_bypassed ? "object-alpha bypass" : null,
      documentLabel.render_resize_policy ? `resize ${documentLabel.render_resize_policy}` : null,
    ].filter(Boolean);
    if (parts.length) sections.push(`document: ${parts.join(" · ")}`);
  }
  if (objectLabel) {
    const footprint = objectLabel.render_box_px || objectLabel.render_footprint_px || objectLabel.render_visible_footprint_px;
    const footprintBefore = objectLabel.render_footprint_px_before_correction;
    const footprintAfter = objectLabel.render_footprint_px_after_correction;
    const parts = [
      objectLabel.sprite_index ? `sprite #${objectLabel.sprite_index}` : null,
      objectLabel.task_id ? `task ${objectLabel.task_id}` : null,
      objectLabel.pose_source_family ? `pose ${objectLabel.pose_source_family}` : null,
      objectLabel.source_position ? `source ${objectLabel.source_position}` : null,
      objectLabel.target_position ? `target ${objectLabel.target_position}` : null,
      objectLabel.render_pose_policy ? `policy ${objectLabel.render_pose_policy}` : null,
      objectLabel.render_scale_basis ? `scale ${objectLabel.render_scale_basis}` : null,
      objectLabel.upright_scale_correction ? `upright scale ${objectLabel.upright_scale_correction}` : null,
      objectLabel.upright_scale_visual_adjustment ? `adjust ${objectLabel.upright_scale_visual_adjustment}x` : null,
      objectLabel.upright_scale_adjustment_percent ? `adjust ${objectLabel.upright_scale_adjustment_percent}%` : null,
      objectLabel.upright_scale_visually_adjusted ? "visual-adjusted yes" : null,
      Array.isArray(footprintBefore) && footprintBefore.length >= 2 ? `before ${footprintBefore[0]}x${footprintBefore[1]}px` : null,
      Array.isArray(footprintAfter) && footprintAfter.length >= 2 ? `after ${footprintAfter[0]}x${footprintAfter[1]}px` : null,
      Array.isArray(footprint) && footprint.length >= 2 ? `footprint ${footprint[0]}x${footprint[1]}px` : null,
      objectLabel.render_resize_policy ? `resize ${objectLabel.render_resize_policy}` : null,
      objectLabel.non_uniform_scaling_applied !== undefined && objectLabel.non_uniform_scaling_applied !== null
        ? `non-uniform ${objectLabel.non_uniform_scaling_applied ? "yes" : "no"}`
        : null,
      objectLabel.clean_sprite_preprocessed_at ? `v${objectLabel.clean_sprite_preprocessed_at}` : null,
    ].filter(Boolean);
    if (parts.length) sections.push(`object: ${parts.join(" · ")}`);
  }
  return sections.join(" | ");
}

function renderTrainingPreview(preview, options = { openModal: true }) {
  state.trainingPreview = preview;
  const grid = $("trainingPreviewGrid");
  grid.innerHTML = "";
  for (const [index, item] of (preview.previews || []).entries()) {
    const card = document.createElement("figure");
    card.className = "training-preview-card";
    const names = (item.labels || []).slice(0, 4).map((label) => zhLabel(label.name)).join(" / ");
    const poseText = previewPoseLabel(item);
    const auditText = previewAuditText(item);
    card.innerHTML = `
      <button class="preview-open" type="button" data-preview-url="${escapeAttr(item.url)}">
        <img src="${escapeAttr(item.url)}?v=${escapeAttr(preview.preview_cache_key || preview.id || Date.now())}" alt="训练样本预览 ${index + 1}" />
      </button>
      <figcaption>
        <strong>样本 ${index + 1} · ${escapeHtml(poseText)}</strong>
        <span>${escapeHtml(names || "合成样本预览")}</span>
        ${auditText ? `<small>${escapeHtml(auditText)}</small>` : ""}
      </figcaption>
    `;
    grid.appendChild(card);
  }
  bindImagePreviewTriggers(grid);
  renderPreviewSummary(preview);
  if (options.openModal) openPreviewModal();
}

function estimateDataset(sampleCount, options = {}) {
  const count = Math.max(1, Math.min(20000, Number(sampleCount || 1)));
  const accessoryCount = Math.max(1, Number(options.accessoryCount || selectedTrainingAccessoryIds().length || 1));
  const poseFactor = options.posePolicy && options.posePolicy !== "auto" ? 0.012 : 0.018;
  const seconds = 8 + count * (0.12 + accessoryCount * 0.025 + poseFactor);
  const minutes = Math.max(1, Math.ceil(seconds / 60));
  const gb = Math.round((count * (1.28 + accessoryCount * 0.08) / 1024) * 100) / 100;
  return { minutes, seconds, gb };
}

function estimateTrainingRun(sampleCount, epochs, imageSize, trainMode = "yolo") {
  const count = Math.max(1, Math.min(20000, Number(sampleCount || 1)));
  const epochCount = Math.max(1, Math.min(500, Number(epochs || 1)));
  const size = Math.max(320, Math.min(1280, Number(imageSize || 640)));
  const sizeFactor = Math.pow(size / 640, 2);
  const modeFactor = trainMode === "yolo_ocr" ? 1.03 : 1;
  const seconds = 75 + epochCount * 7 + count * epochCount * 0.085 * sizeFactor * modeFactor;
  const minutes = Math.max(2, Math.ceil(seconds / 60));
  return { minutes, seconds };
}

function formatEstimateMinutes(minutes) {
  return `约 ${Math.max(1, Math.round(minutes))} 分钟`;
}

function selectedTrainingDataset() {
  const datasetId = state.selectedTrainingDatasetId || $("trainingDatasetMenu")?.dataset.value || "";
  return (state.trainingResources?.datasets || []).find((item) => item.id === datasetId);
}

function compactTrainingStatusNote(note) {
  return String(note || "等待生成预览样本。")
    .replace(/[，,]\s*预计\s*\d+\s*分钟。?/g, "。")
    .replace(/\s*预计\s*\d+\s*分钟。?/g, "")
    .replace(/。。+/g, "。")
    .trim() || "等待生成预览样本。";
}

function updateTrainingEstimates() {
  const sampleCount = Number($("trainingSampleCount")?.value || 4000);
  const selectedCount = selectedTrainingAccessoryIds().length;
  const posePolicy = $("trainingPreviewPose")?.value || "auto";
  const backgroundSet = (state.backgroundSets || []).find((item) => item.id === state.selectedBackgroundSetId);
  const sampleEstimate = estimateDataset(sampleCount, { accessoryCount: selectedCount || 1, posePolicy });
  if ($("sampleEstimateTime")) $("sampleEstimateTime").textContent = formatEstimateMinutes(sampleEstimate.minutes);
  if ($("sampleEstimateDetail")) {
    $("sampleEstimateDetail").textContent = `${sampleCount} 张 · ${selectedCount || 0} 个配件 · ${backgroundSet?.name || "默认背景集"} · ${previewPolicyLabel({ preview_pose_family_policy: posePolicy })} · 约 ${sampleEstimate.gb} GB`;
  }

  const dataset = selectedTrainingDataset();
  const epochs = Math.max(1, Math.min(500, Number($("trainingEpochs")?.value || 80)));
  const imageSize = Number($("trainingImageSizeMenu")?.dataset.value || 640);
  const modelEstimate = estimateTrainingRun(dataset?.sample_count || sampleCount, epochs, imageSize, $("trainingMode")?.value || "yolo");
  if ($("modelEstimateTime")) $("modelEstimateTime").textContent = formatEstimateMinutes(modelEstimate.minutes);
  if ($("modelEstimateDetail")) {
    $("modelEstimateDetail").textContent = `${dataset?.sample_count || sampleCount} 张 · ${epochs} epoch · ${imageSize}px · ${$("trainingMode")?.value || "yolo"}`;
  }
}

function trainingActionConfirmText(actionLabel, includeTraining = false) {
  const sampleCount = Number($("trainingSampleCount").value || 4000);
  const estimate = estimateDataset(sampleCount, {
    accessoryCount: selectedTrainingAccessoryIds().length || 1,
    posePolicy: $("trainingPreviewPose")?.value || "auto",
  });
  const selectedItems = state.accessories.filter((item) => selectedTrainingAccessoryIds().includes(item.id));
  const selectedText = selectedItems.map((item) => zhLabel(item.name)).join("、") || "未选择";
  const backgroundSet = (state.backgroundSets || []).find((item) => item.id === state.selectedBackgroundSetId);
  const trainExtra = includeTraining ? `\n训练阶段：生成完成后会继续启动 YOLO 训练进程。` : "";
  return [
    `确认${actionLabel}？`,
    "",
    `Detail:`,
    `- 样本数量：${sampleCount}`,
    `- 已选配件：${selectedText}`,
    `- 背景集：${backgroundSet?.name || state.selectedBackgroundSetId || "默认背景集"}`,
    `- 训练方式：${$("trainingMode").value}`,
    `- 预览 ID：${state.trainingPreview?.id || "未生成"}`,
    `- 预计时间：${estimate.minutes} 分钟`,
    `- 预计体积：${estimate.gb} GB`,
    "",
    `确认后会创建 Task ID，并放进任务队列后台执行。${trainExtra}`,
  ].join("\n");
}

function renderPreviewSummary(preview) {
  const sampleCount = preview.sample_count || Number($("trainingSampleCount").value || 4000);
  const selectedCount = preview.selected_accessories?.length || selectedTrainingAccessoryIds().length;
  const estimate = estimateDataset(sampleCount, {
    accessoryCount: selectedCount || 1,
    posePolicy: preview.preview_pose_family_policy || $("trainingPreviewPose")?.value || "auto",
  });
  $("previewSummary").innerHTML = `
    <div><label>总样本</label><strong>${sampleCount}</strong></div>
    <div><label>已选配件</label><strong>${selectedCount}</strong></div>
    <div><label>预览视角</label><strong>${escapeHtml(previewPolicyLabel(preview))}</strong></div>
    <div><label>预估时间</label><strong>${estimate.minutes} 分钟</strong></div>
    <div><label>预估体积</label><strong>${estimate.gb} GB</strong></div>
  `;
}

function openPreviewModal() {
  $("previewModal").classList.add("visible");
  $("previewModal").setAttribute("aria-hidden", "false");
}

function closePreviewModal() {
  $("previewModal").classList.remove("visible");
  $("previewModal").setAttribute("aria-hidden", "true");
}

function previewButtonTitle(button, fallbackIndex = 0) {
  const imgAlt = button.querySelector("img")?.getAttribute("alt");
  const captionTitle = button.closest("figure")?.querySelector("figcaption strong")?.textContent;
  return (captionTitle || imgAlt || `图片 ${fallbackIndex + 1}`).trim();
}

function imageViewerContextRoot(trigger) {
  if (!trigger) return null;
  return trigger.closest(".training-preview-grid, .asset-gallery-grid, .job-list, .modal-panel, .view.active");
}

function imageViewerItems(url, trigger) {
  const root = imageViewerContextRoot(trigger);
  const buttons = root ? Array.from(root.querySelectorAll("[data-preview-url]")) : [];
  const items = buttons
    .map((button, index) => ({ url: button.dataset.previewUrl, title: previewButtonTitle(button, index), trigger: button }))
    .filter((item) => item.url);
  if (!items.length) return [{ url, title: "预览大图" }];
  if (!trigger && !items.some((item) => item.url === url)) {
    items.unshift({ url, title: "预览大图" });
  }
  return items;
}

function cacheBustImageUrl(url) {
  return `${url}${url.includes("?") ? "&" : "?"}t=${Date.now()}`;
}

function renderImageViewerItem() {
  const viewer = state.imageViewer;
  const item = viewer.items[viewer.index];
  if (!item) return;
  const hasNavigation = viewer.items.length > 1;
  $("imageViewerImg").src = cacheBustImageUrl(item.url);
  $("imageViewerImg").alt = item.title || "样本预览大图";
  $("imageViewerTitle").textContent = item.title || "预览大图";
  $("imageViewerCount").textContent = hasNavigation ? `${viewer.index + 1} / ${viewer.items.length}` : "";
  $("imageViewerPrev").classList.toggle("hidden", !hasNavigation);
  $("imageViewerNext").classList.toggle("hidden", !hasNavigation);
  $("imageViewerPrev").disabled = !hasNavigation;
  $("imageViewerNext").disabled = !hasNavigation;
}

function navigateImageViewer(direction) {
  const viewer = state.imageViewer;
  if (viewer.items.length <= 1) return;
  viewer.index = (viewer.index + direction + viewer.items.length) % viewer.items.length;
  renderImageViewerItem();
}

function openImageViewer(url, trigger = null) {
  state.imageViewer.items = imageViewerItems(url, trigger);
  const triggerIndex = trigger ? state.imageViewer.items.findIndex((item) => item.trigger === trigger) : -1;
  const urlIndex = state.imageViewer.items.findIndex((item) => item.url === url);
  state.imageViewer.index = Math.max(0, triggerIndex >= 0 ? triggerIndex : urlIndex);
  renderImageViewerItem();
  $("imageViewerModal").classList.add("visible");
  $("imageViewerModal").setAttribute("aria-hidden", "false");
}

function closeImageViewer() {
  $("imageViewerModal").classList.remove("visible");
  $("imageViewerModal").setAttribute("aria-hidden", "true");
  $("imageViewerImg").removeAttribute("src");
  $("imageViewerCount").textContent = "";
  state.imageViewer.items = [];
  state.imageViewer.index = 0;
}

function bindImagePreviewTriggers(root = document) {
  root.querySelectorAll("[data-preview-url]").forEach((button) => {
    if (button.dataset.previewBound === "true") return;
    button.dataset.previewBound = "true";
    button.addEventListener("click", (event) => {
      event.preventDefault();
      openImageViewer(button.dataset.previewUrl, button);
    });
  });
}

function promptTitle(key) {
  if (key === "upright") return "正立生成说明";
  if (key === "lying") return "平躺生成说明";
  return key;
}

function openPromptDetailModal() {
  if (!state.promptEntries.length) return;
  $("promptDetailBody").innerHTML = state.promptEntries
    .map(([key, prompt]) => `
      <section>
        <strong>${escapeHtml(promptTitle(key))}</strong>
        <pre>${escapeHtml(prompt)}</pre>
      </section>
    `)
    .join("");
  $("promptDetailModal").classList.add("visible");
  $("promptDetailModal").setAttribute("aria-hidden", "false");
}

function closePromptDetailModal() {
  $("promptDetailModal").classList.remove("visible");
  $("promptDetailModal").setAttribute("aria-hidden", "true");
  $("promptDetailBody").innerHTML = "";
}

function openAccessoryReview(candidate) {
  state.accessoryCandidate = candidate;
  const type = candidate.material_type === "text" ? "文字类" : "物品类";
  const aiNote = candidate.ai_generation_required
    ? `<span>已创建正立和平躺两组视角任务。视频素材会先抽取关键帧，再生成 18 个视角。</span>`
    : `<span>系统已生成规范化缩略图，请确认边界、文字和背景质量。</span>`;
  const jobs = candidateJobs(candidate);
  const jobNote = jobs.length
    ? `<span>任务状态：${escapeHtml(jobs.map((job) => `${job.task_id || job.job_id || "task"} · ${userJobLabel(job.label || job.pose_family)} · ${STATUS_ZH[job.status] || job.status}`).join("；"))}</span>`
    : "";
  state.promptEntries = Object.entries(candidate.pose_collection_prompts || {}).filter(([, prompt]) => prompt);
  const promptDetail = state.promptEntries.length
    ? `<button class="prompt-icon-button" type="button" data-open-prompt-detail title="查看生成说明" aria-label="查看生成说明">i</button>`
    : "";
  $("accessoryReviewSummary").innerHTML = `
    <strong>${escapeHtml(zhLabel(candidate.name))} · ${type}</strong>
    ${candidate.material_type === "object" ? `<span>透明策略：${escapeHtml(alphaPolicyLabel(candidate.material_alpha_policy))}</span>` : ""}
    ${aiNote}
    ${jobNote}
    ${promptDetail}
  `;
  document.querySelector("[data-open-prompt-detail]")?.addEventListener("click", openPromptDetailModal);
  const grid = $("accessoryThumbGrid");
  grid.innerHTML = "";
  for (const [index, thumb] of (candidate.thumbnails || []).entries()) {
    const card = document.createElement("figure");
    card.className = "training-preview-card";
    card.innerHTML = `
      <button class="preview-open" type="button" data-preview-url="${escapeAttr(thumb.url)}">
        <img src="${escapeAttr(thumb.url)}?t=${Date.now()}" alt="配件缩略图 ${index + 1}" />
      </button>
      <figcaption>
        <strong>缩略图 ${index + 1}</strong>
        <span>${thumb.angle === undefined ? "规范化预览" : `角度 ${thumb.angle}°`}</span>
      </figcaption>
    `;
    grid.appendChild(card);
  }
  bindImagePreviewTriggers(grid);
  $("accessoryReviewModal").classList.add("visible");
  $("accessoryReviewModal").setAttribute("aria-hidden", "false");
  updateOpenAccessoryCandidateFromJobs();
  if (jobs.length) {
    setImageWorkerProgress(summarizeCandidateJobs(jobs));
  } else {
    $("imageWorkerProgress").classList.remove("active");
  }
}

function closeAccessoryReview() {
  state.accessoryCandidate = null;
  state.promptEntries = [];
  closePromptDetailModal();
  if (state.imageWorkerProgressTimer) cancelAnimationFrame(state.imageWorkerProgressTimer);
  state.imageWorkerProgressTimer = null;
  $("imageWorkerProgress").classList.remove("active");
  $("accessoryReviewModal").classList.remove("visible");
  $("accessoryReviewModal").setAttribute("aria-hidden", "true");
}

function accessoryFileKey(file) {
  return `${file.name}::${file.size}::${file.lastModified}`;
}

function clearAccessoryFileQueue() {
  for (const url of state.accessoryPendingFileUrls.values()) URL.revokeObjectURL(url);
  state.accessoryPendingFileUrls.clear();
  state.accessoryPendingFiles = [];
  $("accessoryFiles").value = "";
  renderAccessoryFileQueue();
}

function addAccessoryPendingFiles(fileList) {
  const existing = new Set(state.accessoryPendingFiles.map(accessoryFileKey));
  for (const file of Array.from(fileList || [])) {
    const key = accessoryFileKey(file);
    if (existing.has(key)) continue;
    state.accessoryPendingFiles.push(file);
    existing.add(key);
  }
  $("accessoryFiles").value = "";
  renderAccessoryFileQueue();
}

function removeAccessoryPendingFile(index) {
  const file = state.accessoryPendingFiles[Number(index)];
  if (!file) return;
  const key = accessoryFileKey(file);
  const url = state.accessoryPendingFileUrls.get(key);
  if (url) URL.revokeObjectURL(url);
  state.accessoryPendingFileUrls.delete(key);
  state.accessoryPendingFiles.splice(Number(index), 1);
  renderAccessoryFileQueue();
}

function renderAccessoryFileQueue() {
  const queue = $("accessoryFileQueue");
  if (!queue) return;
  if (!state.accessoryPendingFiles.length) {
    queue.innerHTML = `<div class="upload-thumb-empty">还没有添加素材</div>`;
    return;
  }
  queue.innerHTML = "";
  const title = document.createElement("div");
  title.className = "upload-thumb-summary";
  title.textContent = `待上传素材 ${state.accessoryPendingFiles.length} 个`;
  queue.appendChild(title);
  const grid = document.createElement("div");
  grid.className = "upload-thumb-grid";
  for (const [index, file] of state.accessoryPendingFiles.entries()) {
    const key = accessoryFileKey(file);
    if (!state.accessoryPendingFileUrls.has(key) && file.type.startsWith("image/")) {
      state.accessoryPendingFileUrls.set(key, URL.createObjectURL(file));
    }
    const card = document.createElement("div");
    card.className = "upload-thumb-card";
    const url = state.accessoryPendingFileUrls.get(key);
    const kind = file.type.startsWith("video/") ? "视频" : file.type.startsWith("image/") ? "图片" : "文件";
    card.innerHTML = `
      <button type="button" class="upload-thumb-remove" data-remove-pending-file="${index}" aria-label="移除素材">×</button>
      ${url ? `<img src="${url}" alt="${escapeHtml(file.name)}" />` : `<div class="upload-thumb-file">${kind}</div>`}
      <span title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</span>
      <em>${kind}</em>
    `;
    grid.appendChild(card);
  }
  queue.appendChild(grid);
  queue.querySelectorAll("[data-remove-pending-file]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      removeAccessoryPendingFile(button.dataset.removePendingFile);
    });
  });
}

function openDeleteConfirm(accessoryId) {
  const item = state.accessories.find((accessory) => accessory.id === accessoryId);
  state.pendingDeleteAccessoryId = accessoryId;
  $("confirmDeleteText").textContent = `确认删除“${zhLabel(item?.name || "该配件")}”？删除后它会从当前配件库和训练选择中移除。`;
  $("confirmDeleteModal").classList.add("visible");
  $("confirmDeleteModal").setAttribute("aria-hidden", "false");
}

function closeDeleteConfirm() {
  state.pendingDeleteAccessoryId = null;
  $("confirmDeleteModal").classList.remove("visible");
  $("confirmDeleteModal").setAttribute("aria-hidden", "true");
}

const MODAL_CLOSE_HANDLERS = [
  ["imageViewerModal", closeImageViewer],
  ["documentCropModal", cancelDocumentCrop],
  ["promptDetailModal", closePromptDetailModal],
  ["confirmDeleteModal", closeDeleteConfirm],
  ["accessoryDetailModal", closeAccessoryDetail],
  ["trainingResourceModal", closeTrainingResourceModal],
  ["accessoryReviewModal", closeAccessoryReview],
  ["previewModal", closePreviewModal],
  ["backgroundUploadModal", closeBackgroundUploadModal],
  ["aiDebugModal", closeAiDebugModal],
  ["backgroundGalleryModal", closeBackgroundGalleryModal],
];

function closeTopModal() {
  const active = MODAL_CLOSE_HANDLERS.find(([id]) => $(id)?.classList.contains("visible"));
  if (!active) return false;
  active[1]();
  return true;
}

function bindModalDismissal() {
  for (const [id, close] of MODAL_CLOSE_HANDLERS) {
    const modal = $(id);
    if (!modal) continue;
    modal.addEventListener("click", (event) => {
      if (event.target === modal) close();
    });
  }
  document.addEventListener("keydown", (event) => {
    if ($("imageViewerModal")?.classList.contains("visible")) {
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        navigateImageViewer(-1);
        return;
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        navigateImageViewer(1);
        return;
      }
    }
    if (event.key === "Escape" && closeTopModal()) {
      event.preventDefault();
    }
  });
}

function bindAccessoryDeletes() {
  document.querySelectorAll("[data-delete-accessory]").forEach((button) => {
    button.addEventListener("click", () => openDeleteConfirm(button.dataset.deleteAccessory));
  });
}

function bindTabs() {
  document.querySelectorAll(".mode-tab[data-tab]").forEach((tab) => {
    tab.addEventListener("click", () => {
      if (tab.classList.contains("active")) return;
      const nextPane = $(`${tab.dataset.tab}Tab`);
      if (!nextPane) return;
      document.querySelectorAll(".mode-tab[data-tab]").forEach((x) => x.classList.remove("active"));
      document.querySelectorAll(".tabpane").forEach((x) => x.classList.remove("active"));
      tab.classList.add("active");
      nextPane.classList.add("active");
      if (tab.dataset.tab === "camera") {
        setInspectInput("camera");
        startCamera();
      } else {
        stopCameraStream();
      }
    });
  });
}

function bindViews() {
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.addEventListener("click", () => {
      if (item.classList.contains("active")) return;
      const nextView = $(`${item.dataset.view}View`);
      if (!nextView) return;
      document.querySelectorAll(".nav-item").forEach((x) => x.classList.remove("active"));
      document.querySelectorAll(".view").forEach((x) => x.classList.remove("active"));
      item.classList.add("active");
      nextView.classList.add("active");
      window.scrollTo({
        top: 0,
        behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ? "auto" : "smooth",
      });
      if (item.dataset.view !== "inspect") stopCameraStream();
    });
  });
}

function bindActions() {
  bindModalDismissal();
  $("accessoryMaterialType").addEventListener("change", renderAccessoryProcess);
  $("paperPreset").addEventListener("change", updatePaperDimensionLock);
  $("openAccessoryPicker").addEventListener("click", () => {
    $("accessoryPicker").classList.toggle("visible");
  });
  $("closePreviewModal").addEventListener("click", closePreviewModal);
  $("cancelPreviewModal").addEventListener("click", closePreviewModal);
  $("closeImageViewer").addEventListener("click", closeImageViewer);
  $("openAiDebug")?.addEventListener("click", openAiDebugModal);
  $("closeAiDebug")?.addEventListener("click", closeAiDebugModal);
  $("toggleInspectFullscreen").addEventListener("click", openInspectFullscreen);
  $("closeInspectFullscreen").addEventListener("click", closeInspectFullscreen);
  document.addEventListener("fullscreenchange", handleFullscreenChange);
  $("imageViewerPrev").addEventListener("click", (event) => {
    event.stopPropagation();
    navigateImageViewer(-1);
  });
  $("imageViewerNext").addEventListener("click", (event) => {
    event.stopPropagation();
    navigateImageViewer(1);
  });
  $("closePromptDetail").addEventListener("click", closePromptDetailModal);
  $("cancelDocumentCrop").addEventListener("click", cancelDocumentCrop);
  $("applyDocumentCrop").addEventListener("click", confirmDocumentCrop);
  $("documentCropCanvas").addEventListener("pointerdown", (event) => {
    const crop = state.crop;
    if (!crop) return;
    const point = cropPointerPosition(event);
    const index = nearestCropPoint(point.x, point.y);
    if (index < 0) return;
    crop.activePoint = index;
    $("documentCropCanvas").setPointerCapture(event.pointerId);
    drawCropCanvas();
  });
  $("documentCropCanvas").addEventListener("pointermove", (event) => {
    const crop = state.crop;
    if (!crop || crop.activePoint < 0) return;
    const point = cropPointerPosition(event);
    crop.points[crop.activePoint] = point;
    updateDocumentCropOutputLabel();
    drawCropCanvas();
  });
  $("documentCropCanvas").addEventListener("pointerup", finishCropPointer);
  $("documentCropCanvas").addEventListener("pointercancel", finishCropPointer);
  $("documentCropCanvas").addEventListener("lostpointercapture", () => {
    if (state.crop) state.crop.activePoint = -1;
  });
  $("closeAccessoryDetail").addEventListener("click", closeAccessoryDetail);
  $("closeTrainingResource")?.addEventListener("click", closeTrainingResourceModal);
  $("closeAccessoryReview").addEventListener("click", closeAccessoryReview);
  $("cancelAccessoryReview").addEventListener("click", closeAccessoryReview);
  $("confirmAccessoryAdd").addEventListener("click", async () => {
    if (!state.accessoryCandidate?.id) return closeAccessoryReview();
    const button = $("confirmAccessoryAdd");
    setBusy(button, true);
    startTaskProgress("imageWorker", 65000, [
      [3, "正在确认添加", "后端正在写入配件并准备训练素材。"],
      [24, "提取 18 个视角", "正在切分单体素材。"],
      [58, "保存视角元数据", "正在记录坐标、尺寸和视角位置。"],
      [82, "更新配件库", "即将刷新本地配件列表。"],
    ]);
    try {
      const result = await api(`/api/accessories/confirm/${encodeURIComponent(state.accessoryCandidate.id)}`, { method: "POST" });
      finishTaskProgress("imageWorker", true);
      renderAccessories(result.items);
      closeAccessoryReview();
      $("accessoryName").value = "";
      clearAccessoryFileQueue();
      $("objectLengthMm").value = "";
      $("objectWidthMm").value = "";
      $("objectHeightMm").value = "";
      $("objectAlphaPolicy").value = "";
      toast("配件已确认添加。");
    } catch (error) {
      finishTaskProgress("imageWorker", false);
      toast(`确认添加失败：${error.message}`);
    } finally {
      setBusy(button, false);
    }
  });
  $("closeConfirmDelete").addEventListener("click", closeDeleteConfirm);
  $("cancelDeleteAccessory").addEventListener("click", closeDeleteConfirm);
  $("accessoryFiles").addEventListener("change", () => addAccessoryPendingFiles($("accessoryFiles").files));
  $("accessoryDetailFiles")?.addEventListener("change", async () => {
    addAccessoryDetailPendingFiles($("accessoryDetailFiles").files);
    if (state.accessoryDetailPendingFiles.length) await uploadAccessoryDetailFiles();
  });
  $("addAccessoryDetailFiles")?.addEventListener("click", uploadAccessoryDetailFiles);
  $("confirmDeleteAccessory").addEventListener("click", async () => {
    const id = state.pendingDeleteAccessoryId;
    if (!id) return closeDeleteConfirm();
    try {
      const result = await api(`/api/accessories/${encodeURIComponent(id)}`, { method: "DELETE" });
      renderAccessories(result.items);
      closeDeleteConfirm();
      toast("配件已删除。");
    } catch (error) {
      toast(`删除失败：${error.message}`);
    }
  });
  $("modalConfirmGenerate").addEventListener("click", () => requestSampleGeneration());
  $("confirmGenerateSamples").addEventListener("click", () => requestSampleGeneration());
  $("refreshTrainingLibrary")?.addEventListener("click", refreshTrainingLibrary);
  $("threshold").addEventListener("input", (event) => {
    $("thresholdValue").textContent = Number(event.target.value).toFixed(2);
  });
  $("imageFile").addEventListener("change", () => {
    const file = $("imageFile").files[0];
    if (file) setInspectInput("image", file);
  });
  $("videoFile").addEventListener("change", () => {
    const file = $("videoFile").files[0];
    if (file) setInspectInput("video", file);
  });

  $("labelSensitivity")?.addEventListener("input", (event) => {
    $("labelSensitivityValue").textContent = Number(event.target.value).toFixed(2);
  });
  $("labelReferenceFile")?.addEventListener("change", () => {
    updateLabelExperimentFileName("labelReferenceFile", "labelReferenceName", "PNG, JPG, JPEG");
  });
  $("labelIncomingFile")?.addEventListener("change", () => {
    updateLabelExperimentFileName("labelIncomingFile", "labelIncomingName", "PNG, JPG, JPEG");
  });
  $("runLabelExperiment")?.addEventListener("click", runLabelExperiment);

  $("runImage").addEventListener("click", async () => {
    const file = $("imageFile").files[0];
    if (!file) return toast("请先选择一张图片。");
    setInspectInput("image", file);
    const modelId = selectedModelId();
    if (!modelId) return toast("当前任务没有可用模型。");
    const button = $("runImage");
    setBusy(button, true);
    startProgress("image");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("model_id", modelId);
      const result = await api("/api/analyze/image", { method: "POST", body: form });
      renderImageResult(result);
      finishProgress(true);
      toast("图片检测完成。");
    } catch (error) {
      finishProgress(false);
      toast(`图片检测失败：${error.message}`);
    } finally {
      setBusy(button, false);
    }
  });

  $("runVideo").addEventListener("click", async () => {
    const file = $("videoFile").files[0];
    if (!file) return toast("请先选择一个视频。");
    setInspectInput("video", file);
    const modelId = selectedModelId();
    if (!modelId) return toast("当前任务没有可用模型。");
    const button = $("runVideo");
    setBusy(button, true);
    startProgress("video");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("model_id", modelId);
      const result = await api("/api/analyze/video", { method: "POST", body: form });
      renderVideoResult(result);
      finishProgress(true);
      toast("视频分析完成。");
    } catch (error) {
      finishProgress(false);
      toast(`视频分析失败：${error.message}`);
    } finally {
      setBusy(button, false);
    }
  });

  $("refreshCameras").addEventListener("click", async () => {
    const button = $("refreshCameras");
    setBusy(button, true);
    try {
      if (!state.camera.stream) {
        await startCamera();
      } else {
        const devices = await refreshCameraDevices();
        setCameraStatus(devices.length ? `检测到 ${devices.length} 个摄像头。` : "未检测到摄像头。", !devices.length);
      }
    } finally {
      setBusy(button, false);
    }
  });

  $("captureCamera").addEventListener("click", () => runCameraDetection($("captureCamera")));
  $("fullscreenCaptureCamera").addEventListener("click", () => runCameraDetection($("fullscreenCaptureCamera")));

  $("saveRules").addEventListener("click", async () => {
    const required = [];
    const counts = {};
    const selectedTask = state.specializedModelTasks.find((item) => item.task_id === state.selectedTaskId);
    if (!selectedTask) {
      document.querySelectorAll("[data-class]").forEach((input) => {
        const cls = Number(input.dataset.class);
        if (input.checked) required.push(cls);
      });
      document.querySelectorAll("[data-count]").forEach((input) => {
        counts[input.dataset.count] = Math.max(1, Number(input.value || 1));
      });
    }
    const payload = {
      confidence_threshold: Number($("threshold").value),
      required_classes: selectedTask ? state.config.required_classes : required,
      min_counts: selectedTask ? state.config.min_counts : counts,
    };
    const result = await api("/api/config/rules", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.config = result.rule;
    renderRules();
    toast(selectedTask ? "当前任务配件规则自动生效，置信度已保存。" : "规则已保存。");
  });

  $("aiProvider")?.addEventListener("change", () => {
    const defaults = AI_PROVIDER_DEFAULTS.gemini;
    const currentBaseUrl = $("aiBaseUrl").value.trim();
    if (!currentBaseUrl || Object.values(AI_PROVIDER_DEFAULTS).some((item) => item.base_url === currentBaseUrl)) {
      $("aiBaseUrl").value = defaults.base_url;
      $("aiModel").value = defaults.model;
    }
  });

  $("saveAiConfig")?.addEventListener("click", async () => {
    const button = $("saveAiConfig");
    setBusy(button, true);
    try {
      await saveAiConfig();
      toast("AI 设置已保存。");
    } catch (error) {
      toast(`AI 设置保存失败：${error.message}`);
    } finally {
      setBusy(button, false);
    }
  });

  $("addAccessory").addEventListener("click", async () => {
    const name = $("accessoryName").value.trim();
    if (!name) return toast("请输入参考素材名称。");
    const form = new FormData();
    form.append("name", name);
    const materialType = $("accessoryMaterialType").value;
    form.append("material_type", materialType);
    form.append("training_role", materialType === "text" ? "detect_then_ocr" : "detect_shape");
    if (materialType === "text") {
      form.append("paper_preset", $("paperPreset").value);
      form.append("paper_width_mm", $("paperWidthMm").value);
      form.append("paper_height_mm", $("paperHeightMm").value);
    } else {
      const alphaPolicy = $("objectAlphaPolicy").value;
      if (!alphaPolicy) return toast("请先选择物品透明或不透明。");
      form.append("material_alpha_policy", alphaPolicy);
      form.append("object_length_mm", $("objectLengthMm").value);
      form.append("object_width_mm", $("objectWidthMm").value);
      form.append("object_height_mm", $("objectHeightMm").value);
    }
    const pendingFiles = state.accessoryPendingFiles.length ? state.accessoryPendingFiles : Array.from($("accessoryFiles").files || []);
    if (!pendingFiles.length) return toast("请先添加至少一张照片或一段视频。");
    const button = $("addAccessory");
    setBusy(button, true);
    try {
      const uploadFiles = materialType === "text" ? await prepareTextAccessoryFiles(pendingFiles) : pendingFiles;
      for (const file of uploadFiles) form.append("files", file);
      const result = await api("/api/accessories/preview", { method: "POST", body: form });
      openAccessoryReview(result.candidate);
      toast("缩略图已生成，请确认质量。");
    } catch (error) {
      toast(`生成失败：${error.message}`);
    } finally {
      setBusy(button, false);
    }
  });

  $("buildTrainingPreview").addEventListener("click", async () => {
    const selectedIds = selectedTrainingAccessoryIds();
    if (!selectedIds.length) return toast("请先点击加号添加训练集配件。");
    const payload = {
      selected_accessory_ids: selectedIds,
      sample_count: Number($("trainingSampleCount").value || 4000),
      train_mode: $("trainingMode").value,
      preview_count: 5,
      preview_pose_family_policy: $("trainingPreviewPose")?.value || "auto",
      background_set_id: state.selectedBackgroundSetId || $("trainingBackgroundMenu")?.dataset.value || "",
    };
    const button = $("buildTrainingPreview");
    setBusy(button, true);
    startTaskProgress("training", 12000, [
      [22, "准备样本计划", "正在读取训练集配件和生成参数。"],
      [55, "生成预览图", "正在合成 5 张预览样本。"],
      [84, "计算摘要", "正在估算样本数量、时间和文件体积。"],
      [94, "准备确认", "预览图即将显示。"],
    ]);
    try {
      const preview = await api("/api/training/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      renderTrainingPreview(preview);
      $("trainingStatus").textContent = STATUS_ZH[preview.status] || preview.status;
      $("trainingNote").textContent = `已生成 ${preview.previews.length} 张预览；确认后可正式请求训练。`;
      finishTaskProgress("training", true);
      toast("训练样本预览已生成。");
    } catch (error) {
      finishTaskProgress("training", false);
      toast(`生成预览失败：${error.message}`);
    } finally {
      setBusy(button, false);
    }
  });

  async function requestSampleGeneration() {
    if (!state.trainingPreview) return toast("请先生成预览图。");
    if (state.trainingRequestInFlight) return toast("训练任务正在提交，请稍等。");
    const selectedIds = selectedTrainingAccessoryIds();
    if (!selectedIds.length) return toast("请先点击加号添加训练集配件。");
    if (!window.confirm(trainingActionConfirmText("生成完整训练样本", false))) return;
    const payload = {
      selected_accessory_ids: selectedIds,
      sample_count: Number($("trainingSampleCount").value || 4000),
      train_mode: $("trainingMode").value,
      approved_preview_id: state.trainingPreview?.id || null,
      background_set_id: state.selectedBackgroundSetId || $("trainingBackgroundMenu")?.dataset.value || "",
    };
    state.trainingRequestInFlight = true;
    const modalButton = $("modalConfirmGenerate");
    const panelButton = $("confirmGenerateSamples");
    setBusy(modalButton, true);
    setBusy(panelButton, true);
    try {
      const result = await api("/api/training/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      $("trainingStatus").textContent = STATUS_ZH[result.status] || result.status;
      $("trainingNote").textContent = compactTrainingStatusNote(result.note);
      closePreviewModal();
      await refreshImageJobs();
      toast(`样本生成已进入任务队列：${result.task_id || result.job_id}`);
    } finally {
      state.trainingRequestInFlight = false;
      setBusy(modalButton, false);
      setBusy(panelButton, false);
    }
  }

  $("startTraining").addEventListener("click", async () => {
    if (state.trainingRequestInFlight) return toast("训练任务正在提交，请稍等。");
    const datasetId = state.selectedTrainingDatasetId || $("trainingDatasetMenu")?.dataset.value || "";
    if (!datasetId) return toast("请先选择一个已生成的样本集。");
    const dataset = (state.trainingResources?.datasets || []).find((item) => item.id === datasetId);
    const epochs = Math.max(1, Math.min(500, Number($("trainingEpochs")?.value || 80)));
    const imageSize = Math.max(320, Math.min(1280, Number($("trainingImageSizeMenu")?.dataset.value || 640)));
    const estimate = estimateTrainingRun(dataset?.sample_count || 1, epochs, imageSize, $("trainingMode").value);
    if (!window.confirm(`确认训练模型？\n\n- 样本集：${dataset?.display_name || datasetId}\n- 样本数量：${dataset?.sample_count || 0}\n- 训练方式：${$("trainingMode").value}\n- Epoch：${epochs}\n- 分辨率：${imageSize}px\n- 预计时间：${estimate.minutes} 分钟`)) return;
    const payload = {
      selected_accessory_ids: dataset?.selected_accessory_ids || [],
      sample_count: Number(dataset?.sample_count || 1),
      train_mode: $("trainingMode").value,
      dataset_id: datasetId,
      epochs,
      image_size: imageSize,
      background_set_id: dataset?.background_set_id || "",
    };
    state.trainingRequestInFlight = true;
    const button = $("startTraining");
    setBusy(button, true);
    try {
      const result = await api("/api/training/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      $("trainingStatus").textContent = STATUS_ZH[result.status] || result.status;
      $("trainingNote").textContent = compactTrainingStatusNote(result.note);
      await refreshImageJobs();
      toast(`训练任务已进入任务队列：${result.task_id || result.job_id}`);
    } finally {
      state.trainingRequestInFlight = false;
      setBusy(button, false);
    }
  });

  $("uploadTrainingBackground")?.addEventListener("click", async () => {
    const file = $("trainingBackgroundFile")?.files?.[0];
    if (!file) return toast("请先选择一张背景图片。");
    const form = new FormData();
    form.append("name", file.name.replace(/\.[^.]+$/, ""));
    form.append("file", file);
    const button = $("uploadTrainingBackground");
    setBusy(button, true);
    try {
      const result = await api("/api/training/background-sets", { method: "POST", body: form });
      state.backgroundSets = result.background_sets || [];
      state.selectedBackgroundSetId = result.default_set_id || state.selectedBackgroundSetId;
      renderTrainingBackgroundMenu();
      updateTrainingEstimates();
      closeBackgroundUploadModal();
      await refreshImageJobs();
      toast(`背景生成已进入任务队列：${result.task_id || result.task?.job_id || result.background_set?.id}`);
    } catch (error) {
      toast(`添加背景集失败：${error.message}`);
    } finally {
      setBusy(button, false);
    }
  });
  $("closeBackgroundUploadModal")?.addEventListener("click", closeBackgroundUploadModal);
  $("cancelBackgroundUploadModal")?.addEventListener("click", closeBackgroundUploadModal);
  $("closeBackgroundGalleryModal")?.addEventListener("click", closeBackgroundGalleryModal);

  document.querySelectorAll("[data-training-flow-tab]").forEach((button) => {
    button.addEventListener("click", () => showTrainingFlowTab(button.dataset.trainingFlowTab));
  });
  ["trainingSampleCount", "trainingPreviewPose", "trainingMode", "trainingEpochs"].forEach((id) => {
    $(id)?.addEventListener("input", updateTrainingEstimates);
    $(id)?.addEventListener("change", updateTrainingEstimates);
  });
  renderTrainingImageSizeMenu();
  renderCameraMenu();
  showTrainingFlowTab("samples");
}

bindViews();
bindTabs();
bindActions();
document.addEventListener("click", (event) => {
  const path = typeof event.composedPath === "function" ? event.composedPath() : [];
  const inCustomMenu = path.some((node) => node?.classList?.contains("custom-menu")) || event.target.closest(".custom-menu");
  const inAiKeySelect = path.some((node) => node?.classList?.contains("ai-key-select")) || event.target.closest(".ai-key-select");
  if (!inCustomMenu) closeCustomMenus();
  if (!inAiKeySelect) closeAiKeyControl();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && $("inspectFullscreenStage")?.classList.contains("active")) {
    event.preventDefault();
    $("fullscreenCaptureCamera").click();
    return;
  }
  if (event.key === "Escape" && $("inspectFullscreenStage")?.classList.contains("active")) {
    closeInspectFullscreen();
    return;
  }
  if (event.key === "Escape") {
    closeCustomMenus();
    closeAiKeyControl();
  }
});
window.addEventListener("beforeunload", stopCameraStream);
renderAccessoryProcess();
renderAccessoryFileQueue();
loadInitial().catch((error) => toast(`启动失败：${error.message}`));
