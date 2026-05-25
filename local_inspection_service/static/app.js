const state = {
  config: null,
  classes: [],
  models: [],
  activeModelId: null,
  accessories: [],
  trainingPreview: null,
  accessoryCandidate: null,
  pendingDeleteAccessoryId: null,
  imageJobs: [],
  imageJobPollTimer: null,
  progressTimer: null,
  trainingProgressTimer: null,
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
  image_tool_plan_ready: "Image tool 计划就绪",
  preview_ready: "预览已生成",
  requested: "训练已请求",
};

const PAPER_PRESETS = {
  A4: [210, 297],
  A5: [148, 210],
  A6: [105, 148],
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
  setTaskProgress(prefix, 100, success ? "生成完成" : "生成失败", success ? "结果已准备好。" : "请检查服务状态。");
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
    setTaskProgress("imageWorker", 100, "生成完成", "Pose Collection 已写入本地输出路径，可以确认添加。", { keepVisible: true });
    return;
  }
  if (job.status === "failed") {
    setTaskProgress("imageWorker", 100, "生成失败", job.error || "请检查 ImageWorker 日志或重新生成。", { keepVisible: true });
    return;
  }
  if (job.status === "stopped") {
    setTaskProgress("imageWorker", 100, "任务已停止", "该 ImageWorker 任务已手动停止。", { keepVisible: true });
    return;
  }
  if (job.status === "running") {
    setTaskProgress("imageWorker", Math.max(progress, 12), "正在生成", "Codex CLI 正在根据原图生成 Pose Collection。", { keepVisible: true });
    return;
  }
  setTaskProgress("imageWorker", progress, "任务已排队", "已把原图和固定 Prompt 交给 ImageWorker 队列。", { keepVisible: true });
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
        <strong>${zhLabel(item.name)}</strong>
        <span>${material} · 类别 ${item.class_id} · ${files} 个素材 · ${size} · ${STATUS_ZH[item.status] || item.status}</span>
      </div>
      <button class="mini-secondary" data-view-accessory="${item.id}" type="button">查看</button>
      <button class="mini-danger" data-delete-accessory="${item.id}" type="button">删除</button>
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
    $("accessoryDetailTitle").textContent = zhLabel(item.name || "配件素材");
    $("accessoryDetailSummary").innerHTML = `
      <strong>${zhLabel(item.name || "配件")} · ${item.material_type === "text" ? "文字类" : "物品类"}</strong>
      <span>这里展示该配件当前可用的原始素材、规范化图片以及 Pose Collection。</span>
      <span>尺寸：${formatPhysicalSize(item.physical_size)}</span>
    `;
    const grid = $("accessoryDetailGrid");
    grid.innerHTML = "";
    if (!gallery.length) {
      grid.innerHTML = `<div class="empty-state light">当前配件还没有可查看的图片素材</div>`;
    }
    for (const [index, asset] of gallery.entries()) {
      const card = document.createElement("figure");
      card.className = "training-preview-card";
      card.innerHTML = `
        <button class="preview-open" type="button" data-preview-url="${asset.url}">
          <img src="${asset.url}?t=${Date.now()}" alt="${asset.label || `素材 ${index + 1}`}" />
        </button>
        <figcaption>
          <strong>${asset.label || `素材 ${index + 1}`}</strong>
          <span>${asset.kind === "pose_collection" ? "Pose Collection" : "参考素材"}</span>
        </figcaption>
      `;
      grid.appendChild(card);
    }
    document.querySelectorAll("#accessoryDetailGrid [data-preview-url]").forEach((button) => {
      button.addEventListener("click", () => openImageViewer(button.dataset.previewUrl));
    });
    $("accessoryDetailModal").classList.add("visible");
    $("accessoryDetailModal").setAttribute("aria-hidden", "false");
  } catch (error) {
    toast(`打开配件失败：${error.message}`);
  }
}

function closeAccessoryDetail() {
  $("accessoryDetailModal").classList.remove("visible");
  $("accessoryDetailModal").setAttribute("aria-hidden", "true");
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
  const trainingPlan = await api("/api/training/plan");
  state.config = config;
  state.classes = status.classes;
  $("serviceState").textContent = STATUS_ZH[status.service] || status.service;
  $("serviceState").className = `pill ${status.service === "running" ? "ok" : "fail"}`;
  $("modelState").textContent = status.model_exists ? "模型已加载" : "模型缺失";
  $("modelState").className = `pill ${status.model_exists ? "ok" : "fail"}`;
  renderModels(status);
  renderRules();
  renderAccessories(accessories.items);
  renderTrainingPlan(trainingPlan);
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
  } catch {
    // Keep the UI quiet if the queue endpoint is temporarily unavailable.
  }
}

function syncOpenAccessoryJobProgress() {
  if (!state.accessoryCandidate?.id) return;
  const job = state.imageJobs.find((item) => item.candidate_id === state.accessoryCandidate.id);
  if (!job) return;
  state.accessoryCandidate.codex_image_job = job;
  setImageWorkerProgress(job);
}

function renderImageJobs(result) {
  const items = result.items || [];
  const active = result.active || [];
  $("imageJobCount").textContent = active.length;
  $("imageJobSummary").textContent = active.length ? `${active.length} 个任务进行中` : "空闲";
  const list = $("imageJobList");
  list.innerHTML = "";
  if (!items.length) {
    list.innerHTML = `<div class="job-empty">暂无 Image worker 任务</div>`;
    return;
  }
  for (const job of items.slice(0, 12)) {
    const row = document.createElement("div");
    row.className = "job-item";
    row.innerHTML = `
      <span>
        <strong>${zhLabel(job.candidate_name || "Accessory")}</strong>
        <em>${STATUS_ZH[job.status] || job.status}</em>
      </span>
      <progress value="${job.progress || 0}" max="100">${job.progress || 0}%</progress>
      <div class="job-actions">
        <button type="button" data-open-job="${job.candidate_id}">打开</button>
        ${job.status !== "completed" && job.status !== "stopped" ? `<button type="button" data-stop-job="${job.job_id}">停止</button>` : ""}
        <button type="button" data-delete-job="${job.job_id}">删除</button>
      </div>
    `;
    row.querySelector("span").addEventListener("click", () => openImageJobCandidate(job.candidate_id));
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

function bindImageJobActions() {
  document.querySelectorAll("[data-open-job]").forEach((button) => {
    button.addEventListener("click", () => openImageJobCandidate(button.dataset.openJob));
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

function updateOpenAccessoryCandidateFromJobs() {
  if (!state.accessoryCandidate?.id) return;
  const job = state.imageJobs.find((item) => item.candidate_id === state.accessoryCandidate.id);
  if (!job || job.status !== "completed" || !job.output_url) return;
  if (document.querySelector(`[data-preview-url="${job.output_url}"]`)) return;
  const grid = $("accessoryThumbGrid");
  const card = document.createElement("figure");
  card.className = "training-preview-card";
  card.innerHTML = `
    <button class="preview-open" type="button" data-preview-url="${job.output_url}">
      <img src="${job.output_url}?t=${Date.now()}" alt="Pose Collection 生成结果" />
    </button>
    <figcaption>
      <strong>Pose Collection</strong>
      <span>Image worker 生成结果</span>
    </figcaption>
  `;
  grid.prepend(card);
  card.querySelector("[data-preview-url]").addEventListener("click", () => openImageViewer(job.output_url));
  setImageWorkerProgress(job);
}

function renderAccessoryProcess() {
  const type = $("accessoryMaterialType").value;
  const node = $("accessoryProcess");
  $("textDimensionFields").classList.toggle("hidden", type !== "text");
  $("objectDimensionFields").classList.toggle("hidden", type !== "object");
  if (type === "text") {
    node.innerHTML = `
      <strong>文字类预处理</strong>
      <span>先上传裁剪后的文档图像，系统会做透视校正，生成规整数字化说明书，并为 OCR 训练保留文字区域。</span>
    `;
  } else {
    if (!$("objectLengthMm").value) $("objectLengthMm").value = 170;
    if (!$("objectWidthMm").value) $("objectWidthMm").value = 38;
    if (!$("objectHeightMm").value) $("objectHeightMm").value = 38;
    node.innerHTML = `
      <strong>物品类预处理</strong>
      <span>系统会让 ImageWorker 先推理物体的空间结构和物理摆放状态，再生成多视角、站立、横放、斜放等辅助素材。</span>
    `;
  }
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
        <strong>${zhLabel(item.name)}</strong>
        <em>${material} · ${STATUS_ZH[item.status] || item.status}</em>
      </span>
    `;
    row.addEventListener("click", () => {
      row.classList.toggle("selected");
      renderSelectedTrainingList(new Set(selectedTrainingAccessoryIds()));
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
      document.querySelector(`[data-training-accessory="${item.id}"]`)?.classList.remove("selected");
      renderSelectedTrainingList(new Set(selectedTrainingAccessoryIds()));
    });
    list.appendChild(chip);
  }
}

function renderTrainingPlan(plan) {
  const training = plan.training || state.config?.training || {};
  $("trainingStatus").textContent = STATUS_ZH[training.status] || training.status || "空闲";
  $("trainingNote").textContent = training.note || "等待生成预览样本。";
  $("trainingSampleCount").value = training.sample_count || 4000;
  $("trainingMode").value = training.mode || "yolo_ocr";
  renderTrainingAccessories(training.selected_accessory_ids);
  if (training.preview_urls?.length) {
    renderTrainingPreview(
      { id: training.last_preview_id || "latest", previews: training.preview_urls.map((url) => ({ url, labels: [] })) },
      { openModal: false },
    );
  }
}

function renderTrainingPreview(preview, options = { openModal: true }) {
  state.trainingPreview = preview;
  const grid = $("trainingPreviewGrid");
  grid.innerHTML = "";
  for (const [index, item] of (preview.previews || []).entries()) {
    const card = document.createElement("figure");
    card.className = "training-preview-card";
    const names = (item.labels || []).slice(0, 4).map((label) => zhLabel(label.name)).join(" / ");
    card.innerHTML = `
      <button class="preview-open" type="button" data-preview-url="${item.url}">
        <img src="${item.url}?t=${Date.now()}" alt="训练样本预览 ${index + 1}" />
      </button>
      <figcaption>
        <strong>样本 ${index + 1}</strong>
        <span>${names || "合成样本预览"}</span>
      </figcaption>
    `;
    grid.appendChild(card);
  }
  document.querySelectorAll("[data-preview-url]").forEach((button) => {
    button.addEventListener("click", () => openImageViewer(button.dataset.previewUrl));
  });
  renderPreviewSummary(preview);
  if (options.openModal) openPreviewModal();
}

function estimateDataset(sampleCount) {
  const minutes = Math.max(4, Math.round(sampleCount * 0.08));
  const gb = Math.round(sampleCount * 1.8 / 1024 * 100) / 100;
  return { minutes, gb };
}

function renderPreviewSummary(preview) {
  const sampleCount = preview.sample_count || Number($("trainingSampleCount").value || 4000);
  const estimate = estimateDataset(sampleCount);
  const selectedCount = preview.selected_accessories?.length || selectedTrainingAccessoryIds().length;
  $("previewSummary").innerHTML = `
    <div><label>总样本</label><strong>${sampleCount}</strong></div>
    <div><label>已选配件</label><strong>${selectedCount}</strong></div>
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

function openImageViewer(url) {
  $("imageViewerImg").src = `${url}?t=${Date.now()}`;
  $("imageViewerModal").classList.add("visible");
  $("imageViewerModal").setAttribute("aria-hidden", "false");
}

function closeImageViewer() {
  $("imageViewerModal").classList.remove("visible");
  $("imageViewerModal").setAttribute("aria-hidden", "true");
  $("imageViewerImg").removeAttribute("src");
}

function openAccessoryReview(candidate) {
  state.accessoryCandidate = candidate;
  const type = candidate.material_type === "text" ? "文字类" : "物品类";
  const aiNote = candidate.ai_generation_required
    ? `<span>检测到单张物品参考图：已创建 Codex image-to-image 任务，用于生成 Pose Collection 后再切分成干净视角素材。</span>`
    : `<span>系统已生成规范化缩略图，请确认边界、文字和背景质量。</span>`;
  const jobNote = candidate.codex_image_job
    ? `<span>生图任务状态：${candidate.codex_image_job.status}</span>`
    : "";
  $("accessoryReviewSummary").innerHTML = `
    <strong>${zhLabel(candidate.name)} · ${type}</strong>
    ${aiNote}
    ${jobNote}
    ${candidate.pose_collection_prompt ? `<span class="prompt-line">${candidate.pose_collection_prompt}</span>` : ""}
  `;
  const grid = $("accessoryThumbGrid");
  grid.innerHTML = "";
  for (const [index, thumb] of (candidate.thumbnails || []).entries()) {
    const card = document.createElement("figure");
    card.className = "training-preview-card";
    card.innerHTML = `
      <button class="preview-open" type="button" data-preview-url="${thumb.url}">
        <img src="${thumb.url}?t=${Date.now()}" alt="配件缩略图 ${index + 1}" />
      </button>
      <figcaption>
        <strong>缩略图 ${index + 1}</strong>
        <span>${thumb.angle === undefined ? "规范化预览" : `角度 ${thumb.angle}°`}</span>
      </figcaption>
    `;
    grid.appendChild(card);
  }
  document.querySelectorAll("#accessoryThumbGrid [data-preview-url]").forEach((button) => {
    button.addEventListener("click", () => openImageViewer(button.dataset.previewUrl));
  });
  $("accessoryReviewModal").classList.add("visible");
  $("accessoryReviewModal").setAttribute("aria-hidden", "false");
  updateOpenAccessoryCandidateFromJobs();
  if (candidate.codex_image_job) {
    setImageWorkerProgress(candidate.codex_image_job);
  } else {
    $("imageWorkerProgress").classList.remove("active");
  }
}

function closeAccessoryReview() {
  state.accessoryCandidate = null;
  if (state.imageWorkerProgressTimer) cancelAnimationFrame(state.imageWorkerProgressTimer);
  state.imageWorkerProgressTimer = null;
  $("imageWorkerProgress").classList.remove("active");
  $("accessoryReviewModal").classList.remove("visible");
  $("accessoryReviewModal").setAttribute("aria-hidden", "true");
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

function bindAccessoryDeletes() {
  document.querySelectorAll("[data-delete-accessory]").forEach((button) => {
    button.addEventListener("click", () => openDeleteConfirm(button.dataset.deleteAccessory));
  });
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
  $("accessoryMaterialType").addEventListener("change", renderAccessoryProcess);
  $("paperPreset").addEventListener("change", () => {
    const preset = $("paperPreset").value;
    if (PAPER_PRESETS[preset]) {
      $("paperWidthMm").value = PAPER_PRESETS[preset][0];
      $("paperHeightMm").value = PAPER_PRESETS[preset][1];
    }
  });
  $("openAccessoryPicker").addEventListener("click", () => {
    $("accessoryPicker").classList.toggle("visible");
  });
  $("closePreviewModal").addEventListener("click", closePreviewModal);
  $("cancelPreviewModal").addEventListener("click", closePreviewModal);
  $("closeImageViewer").addEventListener("click", closeImageViewer);
  $("closeAccessoryDetail").addEventListener("click", closeAccessoryDetail);
  $("closeAccessoryReview").addEventListener("click", closeAccessoryReview);
  $("cancelAccessoryReview").addEventListener("click", closeAccessoryReview);
  $("confirmAccessoryAdd").addEventListener("click", async () => {
    if (!state.accessoryCandidate?.id) return closeAccessoryReview();
    try {
      const result = await api(`/api/accessories/confirm/${encodeURIComponent(state.accessoryCandidate.id)}`, { method: "POST" });
      renderAccessories(result.items);
      closeAccessoryReview();
      $("accessoryName").value = "";
      $("accessoryFiles").value = "";
      $("objectLengthMm").value = "";
      $("objectWidthMm").value = "";
      $("objectHeightMm").value = "";
      toast("配件已确认添加。");
    } catch (error) {
      toast(`确认添加失败：${error.message}`);
    }
  });
  $("closeConfirmDelete").addEventListener("click", closeDeleteConfirm);
  $("cancelDeleteAccessory").addEventListener("click", closeDeleteConfirm);
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
    const materialType = $("accessoryMaterialType").value;
    form.append("material_type", materialType);
    form.append("training_role", materialType === "text" ? "detect_then_ocr" : "detect_shape");
    if (materialType === "text") {
      form.append("paper_preset", $("paperPreset").value);
      form.append("paper_width_mm", $("paperWidthMm").value);
      form.append("paper_height_mm", $("paperHeightMm").value);
    } else {
      form.append("object_length_mm", $("objectLengthMm").value);
      form.append("object_width_mm", $("objectWidthMm").value);
      form.append("object_height_mm", $("objectHeightMm").value);
    }
    for (const file of $("accessoryFiles").files) form.append("files", file);
    const button = $("addAccessory");
    setBusy(button, true);
    try {
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
    };
    const button = $("buildTrainingPreview");
    setBusy(button, true);
    startTaskProgress("training", 12000, [
      [22, "准备样本计划", "正在读取训练集配件和生成参数。"],
      [55, "生成预览图", "正在合成 5 张真实预览样本。"],
      [84, "计算摘要", "正在估算样本数量、时间和文件体积。"],
      [94, "打开确认窗口", "预览图即将显示。"],
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
    const selectedIds = selectedTrainingAccessoryIds();
    if (!selectedIds.length) return toast("请先点击加号添加训练集配件。");
    const payload = {
      selected_accessory_ids: selectedIds,
      sample_count: Number($("trainingSampleCount").value || 4000),
      train_mode: $("trainingMode").value,
      approved_preview_id: state.trainingPreview?.id || null,
    };
    const result = await api("/api/training/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    $("trainingStatus").textContent = STATUS_ZH[result.status] || result.status;
    $("trainingNote").textContent = result.note;
    closePreviewModal();
    toast("完整样本生成请求已记录。");
  }

  $("startTraining").addEventListener("click", async () => {
    const selectedIds = selectedTrainingAccessoryIds();
    if (!selectedIds.length) return toast("请先点击加号添加训练集配件。");
    const payload = {
      selected_accessory_ids: selectedIds,
      sample_count: Number($("trainingSampleCount").value || 4000),
      train_mode: $("trainingMode").value,
      approved_preview_id: state.trainingPreview?.id || null,
    };
    const result = await api("/api/training/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    $("trainingStatus").textContent = STATUS_ZH[result.status] || result.status;
    $("trainingNote").textContent = result.note;
    toast("训练请求已记录。");
  });
}

bindViews();
bindTabs();
bindActions();
renderAccessoryProcess();
loadInitial().catch((error) => toast(`启动失败：${error.message}`));
