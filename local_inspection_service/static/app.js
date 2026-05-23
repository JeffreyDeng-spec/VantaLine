const state = {
  config: null,
  classes: [],
  models: [],
  activeModelId: null,
  progressTimer: null,
  progressValue: 0,
};

const $ = (id) => document.getElementById(id);

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
  failed: "失败",
  active: "启用",
};

function zhLabel(label) {
  return CLASS_LABEL_ZH[label] || label || "-";
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
  button.disabled = busy;
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
  const usesOcr = selectedModel()?.uses_ocr !== false;
  const phases = isVideo
    ? [
        [18, "上传视频", "正在上传视频文件。"],
        [38, "抽帧处理中", "正在抽取关键帧并准备检测。"],
        [68, "模型检测中", "正在识别瓶子和说明书位置。"],
        [90, "规则判断中", "正在汇总每一帧的检测结果。"],
      ]
    : usesOcr
      ? [
          [18, "上传图片", "正在上传图片文件。"],
          [42, "模型检测中", "正在识别瓶子和说明书位置。"],
          [76, "OCR 识别中", "正在判断四张说明书分别属于哪一类。"],
          [90, "规则判断中", "正在检查五个配件是否齐全。"],
        ]
      : [
          [20, "上传图片", "正在上传图片文件。"],
          [68, "五类模型检测中", "正在直接识别瓶子和四类说明书。"],
          [90, "规则判断中", "正在检查五个配件是否齐全。"],
        ];
  const startTime = performance.now();
  const expectedMs = isVideo ? 36000 : 18000;
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
  setProgress(100, success ? "检测完成" : "检测失败", success ? "检测结果已生成。" : "请检查文件或服务状态。");
  setTimeout(() => $("progressPanel").classList.remove("active"), 1400);
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
  const rows = [...(rule.present || []), ...(rule.missing || [])];
  for (const row of rows) {
    const tr = document.createElement("tr");
    const isMissing = (rule.missing || []).some((m) => m.class_id === row.class_id);
    if (isMissing) tr.classList.add("missing");
    tr.innerHTML = `
      <td>${zhLabel(row.label)}</td>
      <td>${row.found}</td>
      <td>${row.required}</td>
      <td>${row.max_confidence === undefined ? "-" : Number(row.max_confidence).toFixed(3)}</td>
    `;
    tbody.appendChild(tr);
  }
}

function renderImageResult(result) {
  setBadge(result.passed);
  $("decisionText").textContent = result.passed ? "通过" : "不通过";
  $("detectionCount").textContent = result.detections?.length ?? "-";
  $("passRate").textContent = "-";
  renderParts(result.rule);
  const img = $("previewImage");
  img.src = `${result.annotated_url}?t=${Date.now()}`;
  img.style.display = "block";
  $("emptyPreview").style.display = "none";
}

function renderVideoResult(result) {
  setBadge(result.passed);
  $("decisionText").textContent = result.passed ? "通过" : "不通过";
  $("detectionCount").textContent = `${result.passed_frames}/${result.sampled_frames} 帧`;
  $("passRate").textContent = `${Math.round(result.pass_rate * 1000) / 10}%`;
  const missing = [];
  for (const frame of result.frames || []) {
    for (const item of frame.missing || []) {
      if (!missing.find((x) => x.class_id === item.class_id)) missing.push(item);
    }
  }
  renderParts({ present: [], missing });
  if (result.preview_url) {
    const img = $("previewImage");
    img.src = `${result.preview_url}?t=${Date.now()}`;
    img.style.display = "block";
    $("emptyPreview").style.display = "none";
  }
}

function renderRules() {
  const wrap = $("classRules");
  wrap.innerHTML = "";
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
}

function renderAccessories(items) {
  const list = $("accessoryList");
  list.innerHTML = "";
  for (const item of items) {
    const row = document.createElement("div");
    row.className = "accessory-item";
    row.innerHTML = `<strong>${zhLabel(item.name)}</strong><span>类别 ${item.class_id} · ${STATUS_ZH[item.status] || item.status}</span>`;
    list.appendChild(row);
  }
  const select = $("accessoryClass");
  select.innerHTML = "";
  for (const item of state.classes) {
    const option = document.createElement("option");
    option.value = item.class_id;
    option.textContent = `${item.class_id} · ${zhLabel(item.label)}`;
    select.appendChild(option);
  }
}

function renderModels(status) {
  state.models = status.available_models || [];
  state.activeModelId = status.active_model_id || state.models[0]?.id || "";
  const select = $("modelSelect");
  select.innerHTML = "";
  for (const item of state.models) {
    const option = document.createElement("option");
    option.value = item.id;
    option.disabled = !item.exists;
    option.textContent = `${item.label}${item.exists ? "" : "（文件缺失）"}`;
    select.appendChild(option);
  }
  select.value = state.activeModelId;
}

function selectedModelId() {
  return $("modelSelect")?.value || state.activeModelId || "";
}

function selectedModel() {
  const modelId = selectedModelId();
  return state.models.find((item) => item.id === modelId) || null;
}

async function loadInitial() {
  const status = await api("/api/status");
  const config = await api("/api/config");
  const accessories = await api("/api/accessories");
  state.config = config;
  state.classes = status.classes;
  $("serviceState").textContent = STATUS_ZH[status.service] || status.service;
  $("serviceState").className = `pill ${status.service === "running" ? "ok" : "fail"}`;
  $("modelState").textContent = status.model_exists ? "模型已加载" : "模型缺失";
  $("modelState").className = `pill ${status.model_exists ? "ok" : "fail"}`;
  renderModels(status);
  renderRules();
  renderAccessories(accessories.items);
  $("trainingStatus").textContent = STATUS_ZH[config.training?.status] || config.training?.status || "空闲";
}

function bindTabs() {
  document.querySelectorAll(".mode-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".mode-tab").forEach((x) => x.classList.remove("active"));
      document.querySelectorAll(".tabpane").forEach((x) => x.classList.remove("active"));
      tab.classList.add("active");
      $(`${tab.dataset.tab}Tab`).classList.add("active");
    });
  });
}

function bindViews() {
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.addEventListener("click", () => {
      document.querySelectorAll(".nav-item").forEach((x) => x.classList.remove("active"));
      document.querySelectorAll(".view").forEach((x) => x.classList.remove("active"));
      item.classList.add("active");
      $(`${item.dataset.view}View`).classList.add("active");
    });
  });
}

function bindActions() {
  $("threshold").addEventListener("input", (event) => {
    $("thresholdValue").textContent = Number(event.target.value).toFixed(2);
  });

  $("runImage").addEventListener("click", async () => {
    const file = $("imageFile").files[0];
    if (!file) return toast("请先选择一张图片。");
    const button = $("runImage");
    setBusy(button, true);
    startProgress("image");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("model_id", selectedModelId());
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
    const button = $("runVideo");
    setBusy(button, true);
    startProgress("video");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("model_id", selectedModelId());
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

  $("saveRules").addEventListener("click", async () => {
    const required = [];
    const counts = {};
    document.querySelectorAll("[data-class]").forEach((input) => {
      const cls = Number(input.dataset.class);
      if (input.checked) required.push(cls);
    });
    document.querySelectorAll("[data-count]").forEach((input) => {
      counts[input.dataset.count] = Math.max(1, Number(input.value || 1));
    });
    const payload = {
      confidence_threshold: Number($("threshold").value),
      required_classes: required,
      min_counts: counts,
    };
    const result = await api("/api/config/rules", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.config = result.rule;
    toast("规则已保存。");
  });

  $("saveStream").addEventListener("click", async () => {
    await api("/api/stream/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        enabled: false,
        source: $("streamSource").value,
        url: $("streamUrl").value,
      }),
    });
    toast("实时流接口已保存。");
  });

  $("addAccessory").addEventListener("click", async () => {
    const name = $("accessoryName").value.trim();
    if (!name) return toast("请输入参考素材名称。");
    const form = new FormData();
    form.append("name", name);
    form.append("class_id", $("accessoryClass").value);
    for (const file of $("accessoryFiles").files) form.append("files", file);
    await api("/api/accessories", { method: "POST", body: form });
    const accessories = await api("/api/accessories");
    renderAccessories(accessories.items);
    $("accessoryName").value = "";
    $("accessoryFiles").value = "";
    toast("参考素材已保存。");
  });

  $("startTraining").addEventListener("click", async () => {
    const result = await api("/api/training/start", { method: "POST" });
    $("trainingStatus").textContent = `${result.status}: ${result.note}`;
    toast("训练请求已记录。");
  });
}

bindViews();
bindTabs();
bindActions();
loadInitial().catch((error) => toast(`启动失败：${error.message}`));
