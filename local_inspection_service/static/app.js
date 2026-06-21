const state = {
  auth: {
    user: null,
    users: [],
    features: {},
    dataUserId: "",
  },
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
  aiTasks: [],
  selectedAiTaskId: "",
  aiTaskDraftCounts: {},
  trainingResources: null,
  trainingResourceDetail: null,
  trainingLibraryTab: "datasets",
  modelLibraryTaskTypeFilter: "all",
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
  aiProgressValue: 0,
  inspectInput: {
    kind: "",
    url: "",
    fileName: "",
  },
  aiInspectInput: {
    kind: "",
    url: "",
    fileName: "",
  },
  lastResult: null,
  aiLastResult: null,
  locateAnythingConfig: null,
  locateAnythingSources: [],
  locateAnythingRules: [],
  locateRecipeExpanded: false,
  locateRecipePickerOpen: false,
  locateRecipeQuery: "",
  locateAnythingLastResult: null,
  locateAnythingInspectInFlight: false,
  locateAnythingInput: {
    kind: "",
    url: "",
    fileName: "",
  },
  dataAnalysis: {
    records: [],
    tasks: [],
    selectedTaskId: "",
    selectedRecordIds: new Set(),
    loading: false,
    running: false,
    progressText: "",
    batchLimit: 25,
  },
  labelSheetReferences: [],
  labelSheetFilterStats: null,
  labelSheetLastResult: null,
  labelSheetInput: {
    kind: "",
    url: "",
    fileName: "",
  },
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
  aiCamera: {
    devices: [],
    stream: null,
    selectedDeviceId: "",
    starting: false,
  },
  labelSheetCamera: {
    devices: [],
    stream: null,
    selectedDeviceId: "",
    starting: false,
  },
  locateCamera: {
    devices: [],
    stream: null,
    selectedDeviceId: "",
    starting: false,
    detecting: false,
    inFlight: false,
    frameCount: 0,
  },
  imageViewer: {
    items: [],
    index: 0,
  },
  fullscreenMode: "inspect",
};

const $ = (id) => document.getElementById(id);
const TEXT_ACCESSORY_MAX_IMAGES = 2;

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
const AI_TASK_MODEL_PREFIX = "ai_detection__task_";
const DEFAULT_PROGRESS_IDS = {
  panel: "progressPanel",
  native: "nativeProgress",
  percent: "progressPercent",
  title: "progressTitle",
  detail: "progressDetail",
};
const AI_PROGRESS_IDS = {
  panel: "aiProgressPanel",
  native: "aiNativeProgress",
  percent: "aiProgressPercent",
  title: "aiProgressTitle",
  detail: "aiProgressDetail",
};
const DEFAULT_RESULT_IDS = {
  badge: "resultBadge",
  decision: "decisionText",
  detectionCount: "detectionCount",
  passRate: "passRate",
  table: "partsTable",
  preview: "previewImage",
  empty: "emptyPreview",
};
const AI_RESULT_IDS = {
  badge: "aiResultBadge",
  decision: "aiDecisionText",
  detectionCount: "aiDetectionCount",
  passRate: "aiPassRate",
  table: "aiPartsTable",
  preview: "aiPreviewImage",
  empty: "aiEmptyPreview",
};
const DEFAULT_USER_PERMISSIONS = [
  "inspection",
  "ai_detection",
  "label_sheet",
  "locate_anything",
  "accessory_library",
  "training_pipeline",
  "model_library",
];
const ADMIN_ONLY_PERMISSIONS = new Set(["user_management"]);

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

function formatRecordTime(value) {
  const raw = Number(value || 0);
  if (!Number.isFinite(raw) || raw <= 0) return "创建时间缺失";
  const millis = raw > 100000000000 ? raw : raw * 1000;
  const date = new Date(millis);
  if (Number.isNaN(date.getTime())) return "创建时间缺失";
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function ownerDisplayName(record) {
  const ownerId = String(record?.owner_user_id || "").trim();
  const username = String(record?.owner_username || "").trim();
  if (ownerId === "legacy_admin" || username === "legacy_admin") return "历史数据";
  if (ownerId === "system" || username === "system") return "系统";
  const user = (state.auth.users || []).find((item) => item.id === ownerId);
  return user?.display_name || user?.username || username || ownerId || "未标注用户";
}

function recordAuditText(record, options = {}) {
  const parts = [`创建 ${formatRecordTime(record?.created_at)}`];
  if (options.includeUpdated && record?.updated_at && Number(record.updated_at) !== Number(record?.created_at || 0)) {
    parts.push(`更新 ${formatRecordTime(record.updated_at)}`);
  }
  if (isAdmin() && options.owner !== false) {
    parts.push(`用户 ${ownerDisplayName(record)}`);
  }
  return parts.join(" · ");
}

function toast(message) {
  const node = $("toast");
  node.textContent = message;
  node.classList.add("visible");
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => node.classList.remove("visible"), 2600);
}

async function api(path, options = {}) {
  const response = await fetch(path, { credentials: "same-origin", ...options });
  if (!response.ok) {
    const body = await response.text();
    const message = apiErrorMessage(response, body, path);
    if (response.status === 401 && !String(path).startsWith("/api/auth/login")) {
      showAuthLogin("登录已过期,请重新登录。");
    }
    throw new Error(message);
  }
  return response.json();
}

function apiErrorMessage(response, body = "", path = "") {
  const cleanPath = String(path || "").split("?", 1)[0];
  let detail = "";
  try {
    const parsed = body ? JSON.parse(body) : null;
    if (typeof parsed?.detail === "string") {
      detail = parsed.detail;
    } else if (Array.isArray(parsed?.detail)) {
      detail = parsed.detail
        .map((item) => item?.msg || item?.message || JSON.stringify(item))
        .filter(Boolean)
        .join("；");
    } else if (parsed?.message) {
      detail = String(parsed.message);
    }
  } catch {
    detail = "";
  }
  const raw = detail || body || response.statusText || `HTTP ${response.status}`;
  if (response.status === 401 && cleanPath === "/api/auth/login" && /invalid username or password/i.test(raw)) {
    return "用户名或密码不正确。";
  }
  if (response.status === 401 && /authentication required/i.test(raw)) {
    return "请先登录。";
  }
  if (response.status === 403 && /permission denied/i.test(raw)) {
    return "没有权限执行此操作。";
  }
  return raw;
}

function authQuery() {
  if (state.auth.user?.role === "admin" && state.auth.dataUserId) {
    return `user_id=${encodeURIComponent(state.auth.dataUserId)}`;
  }
  return "";
}

function withAuthScope(path) {
  const query = authQuery();
  if (!query || !path.startsWith("/api/")) return path;
  return `${path}${path.includes("?") ? "&" : "?"}${query}`;
}

function isAdmin() {
  return state.auth.user?.role === "admin";
}

function hasPermission(permission) {
  if (!permission) return true;
  if (ADMIN_ONLY_PERMISSIONS.has(permission)) return isAdmin();
  if (isAdmin()) return true;
  return (state.auth.user?.permissions || []).includes(permission);
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

function setAuthError(message = "") {
  const node = $("authError");
  if (node) node.textContent = message;
}

function emptyTrainingResources() {
  return { datasets: [], models: [], tasks: [], training_tasks: [], ai_detection_tasks: [] };
}

function resetUserScopedState() {
  clearInterval(state.pipelinePollTimer);
  state.pipelinePollTimer = null;
  clearInterval(state.imageJobPollTimer);
  state.imageJobPollTimer = null;
  state.config = {
    confidence_threshold: 0,
    required_classes: [],
    min_counts: {},
    training: { selected_accessory_ids: [] },
    video: {},
    stream: {},
    ocr: {},
  };
  state.aiConfig = {};
  state.classes = [];
  state.models = [];
  state.specializedModels = [];
  state.specializedModelTasks = [];
  state.selectedTaskId = "__default__";
  state.selectedModelId = "";
  state.aiTasks = [];
  state.selectedAiTaskId = "";
  state.aiTaskDraftCounts = {};
  state.dataAnalysis = {
    records: [],
    tasks: [],
    selectedTaskId: "",
    selectedRecordIds: new Set(),
    loading: false,
    running: false,
    progressText: "",
    batchLimit: 25,
  };
  state.trainingResources = emptyTrainingResources();
  state.trainingResourceDetail = null;
  state.accessories = [];
  state.imageJobs = [];
  state.accessoryCandidate = null;
  state.accessoryDetailItem = null;
  if (state.pipeline) {
    state.pipeline.tasks = [];
    state.pipeline.accessories = [];
    state.pipeline.pendingCandidates = [];
  }
  if ($("accessoryList")) renderAccessories([]);
  if ($("datasetLibraryList") || $("modelLibraryList")) renderTrainingLibrary(state.trainingResources);
  if ($("imageJobList")) renderImageJobs({ items: [] });
  if ($("dataAnalysisList")) renderDataAnalysisRecords();
  if ($("pipelineDraftList")) renderPipeline({ items: [], accessories: [], pending_candidates: [], agent: state.pipeline?.agent || null });
}

function showAuthLogin(message = "") {
  resetUserScopedState();
  document.body.classList.remove("auth-pending", "auth-ready");
  document.body.classList.add("auth-login");
  $("authLoading")?.classList.add("hidden");
  $("authShell")?.classList.remove("hidden");
  $("loginForm")?.classList.remove("hidden");
  $("setupForm")?.classList.add("hidden");
  if ($("authSubtitle")) $("authSubtitle").textContent = "登录视觉质检平台";
  setAuthError(message);
}

function showAuthSetup() {
  document.body.classList.remove("auth-pending", "auth-ready");
  document.body.classList.add("auth-login");
  $("authLoading")?.classList.add("hidden");
  $("authShell")?.classList.remove("hidden");
  $("loginForm")?.classList.add("hidden");
  $("setupForm")?.classList.remove("hidden");
  if ($("authSubtitle")) $("authSubtitle").textContent = "首次使用需要创建管理员";
  setAuthError("");
}

function showAuthedApp(user, features = {}) {
  state.auth.user = user;
  state.auth.features = features || {};
  document.body.classList.remove("auth-pending", "auth-login");
  document.body.classList.add("auth-ready");
  $("authLoading")?.classList.add("hidden");
  $("authShell")?.classList.add("hidden");
  renderCurrentUser();
  applyPermissions();
  renderAdminDataScope();
  startPipelinePolling();
}

function renderCurrentUser() {
  const user = state.auth.user || {};
  if ($("currentUserName")) $("currentUserName").textContent = user.display_name || user.username || "-";
  if ($("currentUserRole")) $("currentUserRole").textContent = user.role === "admin" ? "Admin" : "普通用户";
}

function permissionForView(view) {
  return {
    inspect: "inspection",
    aiInspect: "ai_detection",
    dataAnalysis: "ai_detection",
    labelSheet: "label_sheet",
    locateAnything: "locate_anything",
    accessories: "accessory_library",
    pipeline: "training_pipeline",
    trainingLibrary: "model_library",
    rules: "system_settings",
    userManagement: "user_management",
  }[view] || "";
}

function applyPermissions() {
  document.querySelectorAll(".nav-item[data-view]").forEach((item) => {
    const permission = item.dataset.permission || permissionForView(item.dataset.view);
    item.classList.toggle("permission-hidden", !hasPermission(permission));
  });
  document.querySelectorAll("[data-go]").forEach((item) => {
    item.classList.toggle("permission-hidden", !hasPermission(permissionForView(item.dataset.go)));
  });
  const active = document.querySelector(".nav-item.active.permission-hidden");
  if (active) {
    const firstVisible = document.querySelector(".nav-item:not(.permission-hidden)");
    firstVisible?.click();
  }
  const settingsAllowed = hasPermission("system_settings");
  $("saveRules")?.toggleAttribute("disabled", !settingsAllowed);
  ["threshold", "classRules"].forEach((id) => $(id)?.classList.toggle("is-disabled", !settingsAllowed));
  const aiConfigAllowed = hasPermission("ai_config");
  document.querySelector(".ai-config-panel")?.classList.toggle("permission-hidden", !aiConfigAllowed);
  const agentAllowed = hasPermission("agent_config");
  $("agentConfigStatus")?.closest(".page-panel")?.classList.toggle("permission-hidden", !agentAllowed);
}

async function initAuth() {
  try {
    const result = await api("/api/auth/status");
    state.auth.features = result.features || {};
    if (result.setup_required) {
      showAuthSetup();
      return;
    }
    if (!result.authenticated) {
      showAuthLogin();
      return;
    }
    resetUserScopedState();
    showAuthedApp(result.user, result.features);
    await loadInitial();
    if (isAdmin()) refreshUsers().catch(() => {});
  } catch (error) {
    showAuthLogin(error.message);
  }
}

function bindAuth() {
  $("loginForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = $("loginSubmit");
    setBusy(button, true);
    try {
      const result = await api("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: $("loginUsername").value.trim(),
          password: $("loginPassword").value,
        }),
      });
      resetUserScopedState();
      showAuthedApp(result.user, result.features);
      await loadInitial();
      if (isAdmin()) refreshUsers().catch(() => {});
    } catch (error) {
      setAuthError(error.message);
    } finally {
      setBusy(button, false);
    }
  });
  $("setupForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = $("setupSubmit");
    setBusy(button, true);
    try {
      const result = await api("/api/auth/bootstrap", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: $("setupUsername").value.trim(),
          display_name: $("setupDisplayName").value.trim(),
          password: $("setupPassword").value,
        }),
      });
      resetUserScopedState();
      showAuthedApp(result.user, result.features);
      await loadInitial();
      await refreshUsers();
    } catch (error) {
      setAuthError(error.message);
    } finally {
      setBusy(button, false);
    }
  });
  $("logoutButton")?.addEventListener("click", async () => {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } catch {
      // Logout should return to the login view even if the session is already gone.
    }
    state.auth.user = null;
    showAuthLogin();
  });
  $("createUserForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = $("createUserSubmit");
    setBusy(button, true);
    try {
      await api("/api/auth/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: $("newUserName").value.trim(),
          display_name: $("newUserDisplayName").value.trim(),
          password: $("newUserPassword").value,
          role: $("newUserRole").value,
          permissions: selectedPermissions($("newUserPermissions")),
        }),
      });
      $("createUserForm").reset();
      await refreshUsers();
      toast("用户已创建。");
    } catch (error) {
      toast(`创建用户失败:${error.message}`);
    } finally {
      setBusy(button, false);
    }
  });
  $("userManagementList")?.addEventListener("click", async (event) => {
    const row = event.target.closest(".user-row");
    if (!row) return;
    const userId = row.dataset.userId;
    const user = state.auth.users.find((item) => item.id === userId);
    if (!user) return;
    try {
      if (event.target.closest("[data-user-save]")) {
        await api(`/api/auth/users/${encodeURIComponent(userId)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            role: row.querySelector("[data-user-role]").value,
            permissions: selectedPermissions(row.querySelector("[data-user-permissions]")),
          }),
        });
        toast("用户权限已保存。");
      } else if (event.target.closest("[data-user-toggle]")) {
        await api(`/api/auth/users/${encodeURIComponent(userId)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ active: !user.active }),
        });
        toast(user.active ? "用户已停用。" : "用户已启用。");
      } else if (event.target.closest("[data-user-delete]")) {
        await api(`/api/auth/users/${encodeURIComponent(userId)}`, { method: "DELETE" });
        toast("用户已删除。");
      } else if (event.target.closest("[data-user-password-reset]")) {
        const passwordInput = row.querySelector("[data-user-password]");
        const password = passwordInput?.value || "";
        if (!password.trim()) return toast("请输入新密码，或使用生成临时密码。");
        await api(`/api/auth/users/${encodeURIComponent(userId)}/password`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ password, revoke_sessions: true }),
        });
        if (passwordInput) passwordInput.value = "";
        showTemporaryPassword(row, "");
        await refreshUsers();
        toast("密码已重置，目标用户现有会话已撤销。");
        return;
      } else if (event.target.closest("[data-user-password-generate]")) {
        const result = await api(`/api/auth/users/${encodeURIComponent(userId)}/password`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ generate: true, revoke_sessions: true }),
        });
        await refreshUsers();
        showTemporaryPassword(userRowById(userId) || row, result.temporary_password || "");
        toast("临时密码已生成，仅此一次显示。");
        return;
      } else if (event.target.closest("[data-user-password-copy]")) {
        const value = row.querySelector("[data-user-temp-password]")?.textContent || "";
        if (!value) return toast("没有可复制的临时密码。");
        if (!navigator.clipboard?.writeText) return toast("浏览器不支持一键复制，请手动复制。");
        await navigator.clipboard?.writeText(value);
        toast("临时密码已复制。");
        return;
      } else {
        return;
      }
      await refreshUsers();
    } catch (error) {
      toast(`用户更新失败:${error.message}`);
    }
  });
  document.querySelectorAll("[data-admin-scope-select]").forEach((select) => {
    select.addEventListener("change", async (event) => {
      state.auth.dataUserId = event.currentTarget.value;
      renderAdminDataScope();
      await reloadScopedData();
    });
  });
  $("refreshAdminDataScope")?.addEventListener("click", reloadScopedData);
}

function permissionCheckboxes(container, selected = []) {
  const selectedSet = new Set(selected);
  container.innerHTML = Object.entries(state.auth.features || {})
    .filter(([key]) => !ADMIN_ONLY_PERMISSIONS.has(key))
    .map(([key, label]) => `
      <label class="permission-toggle">
        <input type="checkbox" value="${escapeAttr(key)}" ${selectedSet.has(key) ? "checked" : ""} />
        <span>${escapeHtml(label)}</span>
      </label>
    `)
    .join("");
}

function selectedPermissions(container) {
  return Array.from(container.querySelectorAll('input[type="checkbox"]:checked')).map((input) => input.value);
}

function showTemporaryPassword(row, password) {
  const output = row.querySelector("[data-user-temp-password]");
  const copy = row.querySelector("[data-user-password-copy]");
  if (!output || !copy) return;
  output.textContent = password || "";
  output.classList.toggle("hidden", !password);
  copy.classList.toggle("hidden", !password);
}

function userRowById(userId) {
  return Array.from(document.querySelectorAll(".user-row")).find((row) => row.dataset.userId === userId);
}

async function refreshUsers() {
  if (!isAdmin()) return;
  const result = await api("/api/auth/users");
  state.auth.users = result.users || [];
  state.auth.features = result.features || state.auth.features;
  renderUserManagement();
}

function renderAdminDataScope() {
  document.querySelectorAll("[data-admin-scope-wrap]").forEach((wrap) => {
    wrap.classList.toggle("hidden", !isAdmin());
  });
  const selects = document.querySelectorAll("[data-admin-scope-select]");
  if (!selects.length) return;
  const current = state.auth.dataUserId || "";
  const options = [
    `<option value="">全部用户与历史数据</option>`,
    `<option value="legacy_admin">历史数据</option>`,
    ...state.auth.users.map((user) => `<option value="${escapeAttr(user.id)}">${escapeHtml(user.display_name || user.username)}</option>`),
  ].join("");
  selects.forEach((select) => {
    select.innerHTML = options;
    select.value = current;
  });
}

function renderUserManagement() {
  if (!isAdmin()) return;
  permissionCheckboxes($("newUserPermissions"), DEFAULT_USER_PERMISSIONS);
  renderAdminDataScope();
  const list = $("userManagementList");
  if (!list) return;
  list.innerHTML = state.auth.users.length
    ? state.auth.users.map((user) => `
        <article class="user-row" data-user-id="${escapeAttr(user.id)}">
          <div class="user-row-main">
            <strong>${escapeHtml(user.display_name || user.username)}</strong>
            <span>${escapeHtml(user.username)}</span>
            <span>${escapeHtml(recordAuditText(user, { owner: false, includeUpdated: true }))}</span>
          </div>
          <label class="user-row-role">
            角色
            <select data-user-role>
              <option value="user" ${user.role === "user" ? "selected" : ""}>普通用户</option>
              <option value="admin" ${user.role === "admin" ? "selected" : ""}>Admin</option>
            </select>
          </label>
          <div class="user-row-actions">
            <button class="mini-secondary" type="button" data-user-save>保存</button>
            <button class="mini-secondary danger" type="button" data-user-toggle>${user.active ? "停用" : "启用"}</button>
            <button class="mini-secondary danger" type="button" data-user-delete>删除</button>
          </div>
          <div class="permission-grid" data-user-permissions></div>
          <div class="user-password-reset">
            <label>
              <span>重置密码</span>
              <input type="password" autocomplete="new-password" minlength="8" placeholder="输入新密码，不显示旧密码" data-user-password />
            </label>
            <div class="user-password-actions">
              <button class="mini-secondary" type="button" data-user-password-reset>设置新密码</button>
              <button class="mini-secondary" type="button" data-user-password-generate>生成临时密码</button>
              <button class="mini-secondary hidden" type="button" data-user-password-copy>复制</button>
            </div>
            <code class="user-temp-password hidden" data-user-temp-password></code>
          </div>
        </article>
      `).join("")
    : `<div class="empty-state">暂无用户</div>`;
  list.querySelectorAll(".user-row").forEach((row) => {
    const user = state.auth.users.find((item) => item.id === row.dataset.userId);
    permissionCheckboxes(row.querySelector("[data-user-permissions]"), user?.permissions || []);
  });
}

async function reloadScopedData() {
  await loadInitial();
  await refreshTrainingLibrary();
  await refreshImageJobs();
  await refreshPipeline();
}

function modelVariantLabel(model) {
  if (model?.is_label_sheet_match || model?.variant === "label_sheet_local") return model?.label || "本地标签匹配";
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
  if ($("homeAiState")) {
    $("homeAiState").textContent = $("aiConfigStatus").textContent;
    $("homeAiState").className = $("aiConfigStatus").className;
  }
  renderAiKeyControl(config);
}

function renderWindowsWorkerStatus(worker = {}) {
  const badge = $("homeWorkerState");
  if (!badge) return;
  if (!worker?.configured) {
    badge.textContent = "未配置";
    badge.className = "pill neutral";
    return;
  }
  if (worker.status === "ready" || worker.ok) {
    badge.textContent = "已连接";
    badge.className = "pill ok";
    return;
  }
  if (worker.status === "deferred" || worker.status === "unknown") {
    badge.textContent = "后台检测";
    badge.className = "pill neutral";
    return;
  }
  badge.textContent = worker.status === "unreachable" ? "不可达" : "异常";
  badge.className = "pill fail";
}

async function refreshWindowsWorkerStatus(force = false) {
  if (!hasPermission("worker_settings")) return null;
  try {
    const suffix = force ? "?force=true" : "";
    const worker = await api(`/api/windows-worker/status${suffix}`);
    renderWindowsWorkerStatus(worker);
    return worker;
  } catch (error) {
    renderWindowsWorkerStatus({ configured: true, status: "unreachable" });
    return null;
  }
}

async function refreshStatusAfterAiConfig() {
  await refreshStatusModels();
  renderAiInspectStatus();
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

function setProgress(value, title, detail, options = {}) {
  const ids = options.ids || DEFAULT_PROGRESS_IDS;
  const valueKey = options.valueKey || "progressValue";
  state[valueKey] = Math.max(0, Math.min(100, value));
  const progressValue = state[valueKey];
  $(ids.native).value = progressValue;
  $(ids.native).textContent = `${Math.round(progressValue)}%`;
  $(ids.percent).textContent = `${Math.round(progressValue)}%`;
  if (title) $(ids.title).textContent = title;
  if (detail) $(ids.detail).textContent = detail;
  $(ids.panel).classList.toggle("active", progressValue > 0);
}

function startProgress(kind, options = {}) {
  const timerKey = options.timerKey || "progressTimer";
  if (state[timerKey]) cancelAnimationFrame(state[timerKey]);
  const isVideo = kind === "video";
  const model = (options.getModel || selectedModel)();
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
  setProgress(3, phases[0][1], phases[0][2], options);

  const tick = (now) => {
    const elapsed = now - startTime;
    const ratio = Math.min(elapsed / expectedMs, 1);
    const eased = 1 - Math.pow(1 - ratio, 2.4);
    const value = Math.min(95, 3 + eased * 92);
    let phase = phases[0];
    for (const item of phases) {
      if (value >= item[0] - 6) phase = item;
    }
    setProgress(value, phase[1], phase[2], options);
    state[timerKey] = requestAnimationFrame(tick);
  };
  state[timerKey] = requestAnimationFrame(tick);
}

function finishProgress(success = true, options = {}) {
  const ids = options.ids || DEFAULT_PROGRESS_IDS;
  const timerKey = options.timerKey || "progressTimer";
  if (state[timerKey]) cancelAnimationFrame(state[timerKey]);
  state[timerKey] = null;
  setProgress(100, success ? "检测完成" : "检测结果不可用", success ? "结果已更新。" : "请检查文件或服务状态。", options);
  setTimeout(() => $(ids.panel).classList.remove("active"), 1400);
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

function setBadge(passed, waiting = false, badgeId = "resultBadge") {
  const badge = $(badgeId);
  badge.className = "result-badge";
  if (waiting) {
    badge.classList.add("waiting");
    badge.textContent = "等待输入";
    return;
  }
  badge.classList.add(passed ? "pass" : "fail");
  badge.textContent = passed ? "通过" : "不通过";
}

function renderParts(rule, options = {}) {
  const tbody = $(options.tableId || "partsTable");
  const result = options.result || state.lastResult;
  tbody.innerHTML = "";
  if (rule?.match_policy === "ai_presence") {
    const present = new Set((rule.present || []).map(String));
    const missing = new Set((rule.missing || []).map(String));
    const rows = [...present, ...missing];
    for (const accessoryId of rows) {
      const det = (result?.detections || []).find((item) => String(item.accessory_id) === accessoryId) || {};
      const accessory = state.accessories.find((item) => String(item.id) === accessoryId);
      const isMissing = missing.has(accessoryId);
      const required = options.requiredCounts?.[accessoryId] !== undefined ? options.requiredCounts[accessoryId] : "是";
      const tr = document.createElement("tr");
      tr.classList.add(isMissing ? "missing-row" : "present-row");
      if (isMissing) tr.classList.add("missing");
      tr.innerHTML = `
        <td>${escapeHtml(zhLabel(det.label || accessory?.name || accessoryId))}</td>
        <td>${isMissing ? "否" : "是"}</td>
        <td>${escapeHtml(required)}</td>
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

function openAiDebugModal(result = state.lastResult) {
  const body = $("aiDebugBody");
  if ($("aiDebugTitle")) $("aiDebugTitle").textContent = "接口返回详情";
  if (body) body.textContent = JSON.stringify(aiDebugPayload(result), null, 2);
  $("aiDebugModal").classList.add("visible");
  $("aiDebugModal").setAttribute("aria-hidden", "false");
}

function closeAiDebugModal() {
  $("aiDebugModal").classList.remove("visible");
  $("aiDebugModal").setAttribute("aria-hidden", "true");
}

function openLocateDiagnosticModal() {
  $("locateDiagnosticModal")?.classList.add("visible");
  $("locateDiagnosticModal")?.setAttribute("aria-hidden", "false");
}

function closeLocateDiagnosticModal() {
  $("locateDiagnosticModal")?.classList.remove("visible");
  $("locateDiagnosticModal")?.setAttribute("aria-hidden", "true");
}

function uniqueClientToken(seed = "") {
  const random =
    window.crypto?.randomUUID?.() ||
    `${Math.random().toString(36).slice(2, 10)}${Math.random().toString(36).slice(2, 6)}`;
  return [seed, Date.now(), random].filter(Boolean).join("_");
}

function cacheBustedUrl(url, token = uniqueClientToken()) {
  if (!url) return "";
  return `${url}${url.includes("?") ? "&" : "?"}t=${encodeURIComponent(token)}`;
}

function updatePreviewImage(img, empty, url, token = uniqueClientToken()) {
  if (!img) return "";
  if (!url) {
    img.style.display = "none";
    img.removeAttribute("src");
    if (empty) empty.style.display = "grid";
    return "";
  }
  const nextSrc = cacheBustedUrl(url, token);
  img.style.display = "none";
  img.removeAttribute("src");
  void img.offsetWidth;
  img.src = nextSrc;
  img.style.display = "block";
  if (empty) empty.style.display = "none";
  return nextSrc;
}

function renderImageResult(result, options = {}) {
  const ids = options.ids || DEFAULT_RESULT_IDS;
  const resultKey = options.resultKey || "lastResult";
  state[resultKey] = result;
  setBadge(result.passed, false, ids.badge);
  $(ids.decision).textContent = result.passed ? "通过" : "不通过";
  $(ids.detectionCount).textContent = result.detections?.length ?? "-";
  $(ids.passRate).textContent = aiResultMetaText(result);
  renderParts(result.rule, { tableId: ids.table, result, requiredCounts: options.requiredCounts });
  const img = $(ids.preview);
  updatePreviewImage(img, $(ids.empty), result.annotated_url, result.request_id || uniqueClientToken("image"));
  if (options.syncFullscreen !== false) syncInspectFullscreen();
}

function renderVideoResult(result, options = {}) {
  const ids = options.ids || DEFAULT_RESULT_IDS;
  const resultKey = options.resultKey || "lastResult";
  state[resultKey] = result;
  setBadge(result.passed, false, ids.badge);
  $(ids.decision).textContent = result.passed ? "通过" : "不通过";
  $(ids.detectionCount).textContent = `${result.passed_frames}/${result.sampled_frames} 帧`;
  const aiMeta = aiResultMetaText(result);
  $(ids.passRate).textContent = result.ai ? aiMeta : `${Math.round(result.pass_rate * 1000) / 10}%`;
  const missing = [];
  for (const frame of result.frames || []) {
    for (const item of frame.missing || []) {
      const key = typeof item === "string" ? item : item.class_id;
      if (!missing.find((x) => (typeof x === "string" ? x : x.class_id) === key)) missing.push(item);
    }
  }
  renderParts(
    { match_policy: missing.some((item) => typeof item === "string") ? "ai_presence" : "exact_count", present: [], missing },
    { tableId: ids.table, result, requiredCounts: options.requiredCounts },
  );
  if (result.preview_url) {
    const img = $(ids.preview);
    updatePreviewImage(img, $(ids.empty), result.preview_url, result.request_id || uniqueClientToken("video"));
  }
  if (options.syncFullscreen !== false) syncInspectFullscreen();
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
    if (result.model?.is_ai_detection) refreshDataAnalysisRecords({ quiet: true }).catch(() => {});
    toast("摄像头拍照检测完成。");
  } catch (error) {
    finishProgress(false);
    toast(`摄像头检测失败：${error.message}`);
  } finally {
    setBusy(button, false);
  }
}

function setAiCameraStatus(message, isError = false) {
  const node = $("aiCameraStatus");
  if (!node) return;
  node.textContent = message;
  node.classList.toggle("danger-text", isError);
}

function setAiCameraPreviewActive(active) {
  const video = $("aiCameraVideo");
  const empty = $("aiCameraEmpty");
  if (!video || !empty) return;
  video.classList.toggle("active", active);
  empty.style.display = active ? "none" : "grid";
}

function cameraVideoForCapture(primaryVideo, stream, mode = "") {
  const stage = $("inspectFullscreenStage");
  const fullscreenVideo = $("fullscreenInputVideo");
  if (
    mode &&
    state.fullscreenMode === mode &&
    stage?.classList.contains("active") &&
    fullscreenVideo?.srcObject === stream
  ) {
    return fullscreenVideo;
  }
  return primaryVideo;
}

async function waitForVideoCaptureFrame(video, timeoutMs = 900) {
  if (!video) return;
  if (video.paused && video.srcObject) {
    await video.play?.().catch(() => {});
  }
  if (typeof video.requestVideoFrameCallback === "function") {
    await new Promise((resolve) => {
      const timeout = setTimeout(resolve, timeoutMs);
      video.requestVideoFrameCallback(() => {
        clearTimeout(timeout);
        resolve();
      });
    });
    return;
  }
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
}

async function captureVideoFrameFile(video, filenamePrefix, quality = 0.92) {
  await waitForVideoCaptureFrame(video);
  if (!video?.videoWidth || !video.videoHeight) {
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
      resolve(new File([blob], `${filenamePrefix}_${uniqueClientToken()}.jpg`, { type: "image/jpeg" }));
    }, "image/jpeg", quality);
  });
}

function stopAiCameraStream() {
  if (!state.aiCamera.stream) return;
  for (const track of state.aiCamera.stream.getTracks()) track.stop();
  state.aiCamera.stream = null;
  const video = $("aiCameraVideo");
  if (video) video.srcObject = null;
  setAiCameraPreviewActive(false);
}

function renderAiCameraMenu() {
  const devices = state.aiCamera.devices || [];
  const options = devices.length
    ? devices.map((device, index) => ({
        value: device.deviceId,
        label: device.label || `摄像头 ${index + 1}`,
        meta: device.label ? "可用" : "等待授权后显示名称",
      }))
    : [{ value: "", label: "未检测到摄像头", meta: "请检查设备连接或浏览器权限", disabled: true }];
  state.aiCamera.selectedDeviceId = renderCustomMenu("aiCameraMenu", options, state.aiCamera.selectedDeviceId, (value) => {
    state.aiCamera.selectedDeviceId = value;
    if (value) startAiCamera(value);
  });
}

async function refreshAiCameraDevices() {
  if (!navigator.mediaDevices?.enumerateDevices) {
    state.aiCamera.devices = [];
    renderAiCameraMenu();
    setAiCameraStatus("当前浏览器不支持摄像头枚举。请使用 localhost 下的 Chrome/Edge。", true);
    return [];
  }
  const devices = await navigator.mediaDevices.enumerateDevices();
  state.aiCamera.devices = devices.filter((device) => device.kind === "videoinput");
  if (!state.aiCamera.selectedDeviceId && state.aiCamera.devices.length) {
    state.aiCamera.selectedDeviceId = state.aiCamera.devices[0].deviceId;
  }
  renderAiCameraMenu();
  return state.aiCamera.devices;
}

async function startAiCamera(deviceId = state.aiCamera.selectedDeviceId) {
  if (state.aiCamera.starting) return;
  if (!navigator.mediaDevices?.getUserMedia) {
    setAiCameraStatus("当前浏览器不支持摄像头预览。请使用 localhost 下的 Chrome/Edge。", true);
    return;
  }
  state.aiCamera.starting = true;
  setAiCameraStatus("正在打开摄像头...");
  try {
    stopAiCameraStream();
    const videoConstraints = deviceId ? { deviceId: { exact: deviceId } } : true;
    const stream = await navigator.mediaDevices.getUserMedia({ video: videoConstraints, audio: false });
    state.aiCamera.stream = stream;
    const video = $("aiCameraVideo");
    video.srcObject = stream;
    await video.play();
    const track = stream.getVideoTracks()[0];
    const settings = track?.getSettings?.() || {};
    if (settings.deviceId) state.aiCamera.selectedDeviceId = settings.deviceId;
    await refreshAiCameraDevices();
    setAiCameraPreviewActive(true);
    setAiCameraStatus(`摄像头已连接：${track?.label || "当前摄像头"}`);
  } catch (error) {
    stopAiCameraStream();
    setAiCameraStatus(`摄像头不可用：${error.message}`, true);
    toast(`摄像头不可用：${error.message}`);
  } finally {
    state.aiCamera.starting = false;
  }
}

async function captureAiCameraFrame() {
  if (!state.aiCamera.stream) await startAiCamera();
  if (!state.aiCamera.stream) {
    throw new Error("摄像头画面尚未准备好");
  }
  const video = cameraVideoForCapture($("aiCameraVideo"), state.aiCamera.stream, "ai");
  return captureVideoFrameFile(video, "ai_camera_capture", 0.92);
}

async function runAiCameraDetection(button) {
  const modelId = selectedAiModelId();
  if (!modelId) return toast("请先在训练流水线创建并选择 AI 检测任务。");
  setBusy(button, true);
  startProgress("image", { ids: AI_PROGRESS_IDS, timerKey: "aiProgressTimer", valueKey: "aiProgressValue", getModel: selectedAiModel });
  try {
    const file = await captureAiCameraFrame();
    setAiInspectInput("camera");
    const form = new FormData();
    form.append("file", file);
    form.append("model_id", modelId);
    const result = await api("/api/analyze/image", { method: "POST", body: form });
    renderImageResult(result, {
      ids: AI_RESULT_IDS,
      resultKey: "aiLastResult",
      requiredCounts: currentAiTaskRequiredCounts(),
      syncFullscreen: false,
    });
    if (state.fullscreenMode === "ai") syncInspectFullscreen("ai");
    finishProgress(true, { ids: AI_PROGRESS_IDS, timerKey: "aiProgressTimer", valueKey: "aiProgressValue" });
    refreshDataAnalysisRecords({ quiet: true }).catch(() => {});
    toast("摄像头 AI 检测完成。");
  } catch (error) {
    finishProgress(false, { ids: AI_PROGRESS_IDS, timerKey: "aiProgressTimer", valueKey: "aiProgressValue" });
    toast(`摄像头 AI 检测失败：${error.message}`);
  } finally {
    setBusy(button, false);
  }
}

function labelSheetStatusText(status) {
  if (status === "matched") return "已匹配";
  if (status === "unclear") return "需复核";
  if (status === "no_label_reference") return "无标签参考";
  if (status === "error") return "错误";
  return "等待输入";
}

function setLabelSheetBadge(status) {
  const badge = $("labelSheetBadge");
  if (!badge) return;
  badge.className = "result-badge";
  if (status === "matched") {
    badge.classList.add("pass");
  } else if (status === "unclear" || status === "no_label_reference" || status === "error") {
    badge.classList.add("fail");
  } else {
    badge.classList.add("waiting");
  }
  badge.textContent = labelSheetStatusText(status);
}

function renderLabelSheetReferences() {
  const list = $("labelReferenceList");
  const summary = $("labelReferenceSummary");
  if (!list || !summary) return;
  const stats = state.labelSheetFilterStats || {};
  summary.textContent = `保留 ${stats.kept_count ?? state.labelSheetReferences.length}，过滤 ${stats.filtered_count ?? 0}`;
  if (!state.labelSheetReferences.length) {
    list.innerHTML = `<div class="empty-state compact">没有保留的标签参考</div>`;
    return;
  }
  list.innerHTML = state.labelSheetReferences
    .map((item) => {
      const reason = item.filter?.include_terms?.length ? item.filter.include_terms.join(", ") : item.filter?.reason || "kept";
      return `
        <article class="label-reference-card">
          <img src="${escapeAttr(item.image_url || "")}?t=${Date.now()}" alt="${escapeAttr(item.name || "label reference")}" />
          <div>
            <strong>${escapeHtml(item.name || item.label || item.reference_id)}</strong>
            <small>${escapeHtml(recordAuditText(item))}</small>
            <small>${escapeHtml(reason)}</small>
          </div>
        </article>
      `;
    })
    .join("");
}

async function refreshLabelSheetReferences() {
  const result = await api("/api/label-sheets/references");
  state.labelSheetReferences = result.references || [];
  state.labelSheetFilterStats = result.doc_filter_stats || null;
  renderLabelSheetReferences();
}

async function addLabelSheetReference(button) {
  const files = Array.from($("labelReferenceFiles")?.files || []);
  const annotation = $("labelReferenceAnnotation")?.value.trim() || "";
  if (!annotation) return toast("请填写左列标注。");
  if (!files.length) return toast("请选择标签参考图。");
  setBusy(button, true);
  try {
    const form = new FormData();
    form.append("annotation", annotation);
    for (const file of files) form.append("files", file);
    const result = await api("/api/label-sheets/references", { method: "POST", body: form });
    state.labelSheetReferences = result.references || [];
    state.labelSheetFilterStats = result.doc_filter_stats || null;
    $("labelReferenceFiles").value = "";
    renderLabelSheetReferences();
    toast("标签参考已保存。");
  } catch (error) {
    toast(`保存标签参考失败：${error.message}`);
  } finally {
    setBusy(button, false);
  }
}

function setLabelSheetInput(kind, file = null) {
  if (state.labelSheetInput.url) URL.revokeObjectURL(state.labelSheetInput.url);
  state.labelSheetInput = { kind, url: file ? URL.createObjectURL(file) : "", fileName: file?.name || "" };
}

function renderLabelSheetResult(result) {
  state.labelSheetLastResult = result;
  setLabelSheetBadge(result.status);
  $("labelMatchStatus").textContent = labelSheetStatusText(result.status);
  $("labelMatchScore").textContent = result.score === undefined ? "-" : Number(result.score).toFixed(4);
  $("labelMatchedName").textContent =
    result.matched_reference_name || result.matched_reference_label || result.best_reference_name || result.best_reference_label || "-";
  $("labelReviewState").textContent = result.status === "matched" ? "自动通过" : result.low_confidence_reason || result.review_status || "needs_review";

  const refUrl = result.matched_reference_image_url || result.best_reference_image_url || "";
  const cropUrl = result.input_crop_image_url || "";
  const refImg = $("labelMatchedReferenceImage");
  const cropImg = $("labelInputCropImage");
  refImg.style.display = refUrl ? "block" : "none";
  cropImg.style.display = cropUrl ? "block" : "none";
  if (refUrl) refImg.src = `${refUrl}?t=${Date.now()}`;
  if (cropUrl) cropImg.src = `${cropUrl}?t=${Date.now()}`;
  $("labelMatchedReferenceEmpty").style.display = refUrl ? "none" : "grid";
  $("labelInputCropEmpty").style.display = cropUrl ? "none" : "grid";

  const tbody = $("labelCandidateTable");
  const candidates = result.candidates || [];
  tbody.innerHTML = candidates.length
    ? candidates
        .slice(0, 6)
        .map(
          (item) => `
            <tr>
              <td>${escapeHtml(item.matched_reference_name || item.matched_reference_label || item.reference_id)}</td>
              <td>${Number(item.score || 0).toFixed(4)}</td>
              <td>${escapeHtml(item.candidate_id || "-")}</td>
            </tr>
          `,
        )
        .join("")
    : `<tr><td colspan="3">暂无候选</td></tr>`;
}

async function runLabelSheetMatchWithFile(file, button) {
  if (!file) return toast("请先选择标签纸图片。");
  setLabelSheetInput("image", file);
  setBusy(button, true);
  try {
    const form = new FormData();
    form.append("file", file);
    const result = await api("/api/label-sheets/match", { method: "POST", body: form });
    renderLabelSheetResult(result);
    toast(result.status === "matched" ? "标签纸匹配完成。" : "标签纸需要人工复核。");
  } catch (error) {
    setLabelSheetBadge("error");
    toast(`标签纸匹配失败：${error.message}`);
  } finally {
    setBusy(button, false);
  }
}

function setLabelSheetCameraStatus(message, isError = false) {
  const node = $("labelSheetCameraStatus");
  if (!node) return;
  node.textContent = message;
  node.classList.toggle("danger-text", isError);
}

function setLabelSheetCameraPreviewActive(active) {
  const video = $("labelSheetCameraVideo");
  const empty = $("labelSheetCameraEmpty");
  if (!video || !empty) return;
  video.classList.toggle("active", active);
  empty.style.display = active ? "none" : "grid";
}

function stopLabelSheetCameraStream() {
  if (!state.labelSheetCamera.stream) return;
  for (const track of state.labelSheetCamera.stream.getTracks()) track.stop();
  state.labelSheetCamera.stream = null;
  const video = $("labelSheetCameraVideo");
  if (video) video.srcObject = null;
  setLabelSheetCameraPreviewActive(false);
}

function renderLabelSheetCameraMenu() {
  const devices = state.labelSheetCamera.devices || [];
  const options = devices.length
    ? devices.map((device, index) => ({
        value: device.deviceId,
        label: device.label || `摄像头 ${index + 1}`,
        meta: device.label ? "可用" : "等待授权后显示名称",
      }))
    : [{ value: "", label: "未检测到摄像头", meta: "请检查设备连接或浏览器权限", disabled: true }];
  state.labelSheetCamera.selectedDeviceId = renderCustomMenu(
    "labelSheetCameraMenu",
    options,
    state.labelSheetCamera.selectedDeviceId,
    (value) => {
      state.labelSheetCamera.selectedDeviceId = value;
      if (value) startLabelSheetCamera(value);
    },
  );
}

async function refreshLabelSheetCameraDevices() {
  if (!navigator.mediaDevices?.enumerateDevices) {
    state.labelSheetCamera.devices = [];
    renderLabelSheetCameraMenu();
    setLabelSheetCameraStatus("当前浏览器不支持摄像头枚举。", true);
    return [];
  }
  const devices = await navigator.mediaDevices.enumerateDevices();
  state.labelSheetCamera.devices = devices.filter((device) => device.kind === "videoinput");
  if (!state.labelSheetCamera.selectedDeviceId && state.labelSheetCamera.devices.length) {
    state.labelSheetCamera.selectedDeviceId = state.labelSheetCamera.devices[0].deviceId;
  }
  renderLabelSheetCameraMenu();
  return state.labelSheetCamera.devices;
}

async function startLabelSheetCamera(deviceId = state.labelSheetCamera.selectedDeviceId) {
  if (state.labelSheetCamera.starting) return;
  if (!navigator.mediaDevices?.getUserMedia) {
    setLabelSheetCameraStatus("当前浏览器不支持摄像头预览。", true);
    return;
  }
  state.labelSheetCamera.starting = true;
  setLabelSheetCameraStatus("正在打开摄像头...");
  try {
    stopLabelSheetCameraStream();
    const videoConstraints = deviceId ? { deviceId: { exact: deviceId } } : true;
    const stream = await navigator.mediaDevices.getUserMedia({ video: videoConstraints, audio: false });
    state.labelSheetCamera.stream = stream;
    const video = $("labelSheetCameraVideo");
    video.srcObject = stream;
    await video.play();
    const track = stream.getVideoTracks()[0];
    const settings = track?.getSettings?.() || {};
    if (settings.deviceId) state.labelSheetCamera.selectedDeviceId = settings.deviceId;
    await refreshLabelSheetCameraDevices();
    setLabelSheetCameraPreviewActive(true);
    setLabelSheetCameraStatus(`摄像头已连接：${track?.label || "当前摄像头"}`);
  } catch (error) {
    stopLabelSheetCameraStream();
    setLabelSheetCameraStatus(`摄像头不可用：${error.message}`, true);
    toast(`摄像头不可用：${error.message}`);
  } finally {
    state.labelSheetCamera.starting = false;
  }
}

async function captureLabelSheetCameraFrame() {
  if (!state.labelSheetCamera.stream) await startLabelSheetCamera();
  const video = $("labelSheetCameraVideo");
  if (!state.labelSheetCamera.stream || !video.videoWidth || !video.videoHeight) {
    throw new Error("摄像头画面尚未准备好");
  }
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (!blob) {
        reject(new Error("拍照失败"));
        return;
      }
      resolve(new File([blob], `label_sheet_capture_${Date.now()}.jpg`, { type: "image/jpeg" }));
    }, "image/jpeg", 0.92);
  });
}

async function runLabelSheetCameraMatch(button) {
  setBusy(button, true);
  try {
    const file = await captureLabelSheetCameraFrame();
    await runLabelSheetMatchWithFile(file, button);
  } catch (error) {
    toast(`摄像头标签匹配失败：${error.message}`);
  } finally {
    setBusy(button, false);
  }
}

function locateStatusClass(payload) {
  if (payload?.ok || payload?.status === "ready") return "ok";
  if (payload?.status === "starting" || payload?.status === "reachable") return "neutral";
  if (payload?.configured || payload?.status === "failed" || payload?.status === "unavailable") return "fail";
  return "neutral";
}

function locateStatusText(payload) {
  if (!payload) return "未检查";
  if (payload.ok || payload.status === "ready") return "检测服务就绪";
  if (payload.status === "starting") return "启动中";
  if (payload.status === "reachable") return "需试检确认";
  if (payload.status === "not_configured" || !payload.configured) return "未启动";
  return "不可用";
}

function renderLocateRuntimeStatus(payload = state.locateAnythingConfig || {}) {
  const badge = $("locateStatusBadge");
  const text = $("locateStatusText");
  const startButton = $("startLocateRuntime");
  if (!badge || !text) return;
  badge.textContent = locateStatusText(payload);
  badge.className = `pill ${locateStatusClass(payload)}`;
  if ($("homeLocateState")) {
    $("homeLocateState").textContent = badge.textContent;
    $("homeLocateState").className = badge.className;
  }
  const latency = Number(payload.latency_ms);
  const latencyText = Number.isFinite(latency) && latency > 0 ? ` · ${latency} ms` : "";
  if (payload.ok || payload.status === "ready") {
    text.textContent = `本地检测服务已连接${latencyText}，可以开始相机检测。`;
  } else if (payload.status === "starting") {
    text.textContent = payload.message || "本地模型正在启动，首次加载会比较慢。";
  } else if (payload.status === "reachable") {
    text.textContent = payload.message || "端点可达，但还不能确认模型已加载；请先试检或查看健康检查。";
  } else if (payload.status === "failed") {
    text.textContent = payload.message || "启动条件不完整，请查看高级设置。";
  } else {
    text.textContent = "检测服务未启动。可以先启动本地模型，或使用高级设置检查端点。";
  }
  startButton?.classList.toggle("hidden", Boolean(payload.ok || payload.status === "ready"));
}

function renderLocateConfig(config = state.locateAnythingConfig || {}) {
  state.locateAnythingConfig = { ...(state.locateAnythingConfig || {}), ...config, generation_mode: "fast" };
  if ($("locateEndpointUrl")) $("locateEndpointUrl").value = state.locateAnythingConfig.endpoint_url || "http://127.0.0.1:8000/locate";
  if ($("locateMaxSide")) $("locateMaxSide").value = state.locateAnythingConfig.max_side || 640;
  if ($("locateMaxTokens")) $("locateMaxTokens").value = state.locateAnythingConfig.max_new_tokens || 512;
  renderLocateRuntimeStatus(state.locateAnythingConfig);
}

function readLocateConfigPayload() {
  const endpoint = $("locateEndpointUrl")?.value.trim() || "";
  return {
    enabled: Boolean(endpoint),
    endpoint_url: endpoint,
    generation_mode: "fast",
    max_side: Number($("locateMaxSide")?.value || 640),
    max_new_tokens: Number($("locateMaxTokens")?.value || 512),
  };
}

async function saveLocateConfig(button, options = {}) {
  setBusy(button, true);
  try {
    const result = await api("/api/locateanything/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(readLocateConfigPayload()),
    });
    renderLocateConfig(result);
    if (!options.quiet) toast("检测服务设置已保存。");
    return result;
  } catch (error) {
    if (!options.quiet) toast(`保存检测服务设置失败：${error.message}`);
    throw error;
  } finally {
    setBusy(button, false);
  }
}

async function checkLocateStatus(button = null, options = {}) {
  setBusy(button, true);
  try {
    const endpoint = $("locateEndpointUrl")?.value.trim() || "";
    const suffix = endpoint ? `?endpoint_url=${encodeURIComponent(endpoint)}` : "";
    const result = await api(`/api/locateanything/status${suffix}`);
    state.locateAnythingConfig = { ...(state.locateAnythingConfig || {}), ...readLocateConfigPayload(), ...result };
    renderLocateRuntimeStatus(result);
    if (!options.quiet) toast(result.ok ? "检测服务已就绪。" : "检测服务暂不可用。");
    return result;
  } catch (error) {
    if (!options.quiet) toast(`检查检测服务失败：${error.message}`);
    renderLocateRuntimeStatus({ status: "unavailable", configured: true, message: error.message });
    return { ok: false, status: "unavailable", message: error.message };
  } finally {
    setBusy(button, false);
  }
}

async function startLocateRuntime(button) {
  setBusy(button, true);
  renderLocateRuntimeStatus({ status: "starting", message: "正在启动本地模型..." });
  try {
    const result = await api("/api/locateanything/runtime/start", { method: "POST" });
    state.locateAnythingConfig = { ...(state.locateAnythingConfig || {}), status: result.status, message: result.message, configured: true };
    renderLocateRuntimeStatus(state.locateAnythingConfig);
    toast(result.ok ? result.message || "本地模型已就绪。" : result.message || "本地模型启动失败。");
    setTimeout(() => checkLocateStatus(null, { quiet: true }), 2200);
    return result;
  } catch (error) {
    renderLocateRuntimeStatus({ status: "failed", message: error.message });
    toast(`启动本地模型失败：${error.message}`);
    return { ok: false, status: "failed", message: error.message };
  } finally {
    setBusy(button, false);
  }
}

function locateRuleFromSource(item) {
  return {
    id: item.id,
    label: item.label || item.display_label || item.id,
    display_label: item.display_label || item.label || item.id,
    material_type: item.material_type || "",
    source: item.source || "",
    visual_prompt: item.visual_prompt || "",
    enabled: true,
    expected_present: item.default_expected_present !== false,
    expected_count: Number(item.default_expected_count || 1),
    prompt_override: "",
  };
}

function locateSourceById(id) {
  return state.locateAnythingSources.find((item) => item.id === id) || null;
}

function mergeLocateRuleWithSource(rule) {
  const source = locateSourceById(rule.id);
  if (!source) return rule;
  return {
    ...locateRuleFromSource(source),
    ...rule,
    label: source.label || rule.label || rule.id,
    display_label: source.display_label || source.label || rule.display_label || rule.id,
    material_type: source.material_type || rule.material_type || "",
    source: source.source || rule.source || "",
    visual_prompt: source.visual_prompt || rule.visual_prompt || "",
  };
}

function normalizeLocateRules() {
  const seen = new Set();
  state.locateAnythingRules = state.locateAnythingRules
    .filter((rule) => rule && rule.id && !seen.has(rule.id) && (seen.add(rule.id) || true))
    .map((rule) => mergeLocateRuleWithSource({
      ...rule,
      enabled: rule.enabled !== false,
      expected_present: rule.expected_present !== false,
      expected_count: Number(rule.expected_count ?? 1),
      prompt_override: rule.prompt_override || "",
    }));
}

function selectedLocateRules() {
  normalizeLocateRules();
  return state.locateAnythingRules
    .filter((rule) => rule.enabled !== false)
    .map((rule) => ({
      id: rule.id,
      label: rule.label || rule.display_label || rule.id,
      display_label: rule.display_label || rule.label || rule.id,
      source: rule.source || "",
      material_type: rule.material_type || "",
      visual_prompt: rule.visual_prompt || "",
      expected_present: rule.expected_present !== false,
      expected_count: rule.expected_present === false ? 0 : Number(rule.expected_count || 1),
      prompt_override: String(rule.prompt_override || "").trim(),
    }));
}

function updateLocateRecipeSummary() {
  const configured = state.locateAnythingRules.length;
  const enabledRules = state.locateAnythingRules.filter((rule) => rule.enabled !== false);
  const expectedTotal = enabledRules.reduce((total, rule) => total + (rule.expected_present === false ? 0 : Number(rule.expected_count || 1)), 0);
  if ($("locateRecipeConfiguredCount")) $("locateRecipeConfiguredCount").textContent = String(configured);
  if ($("locateRecipeEnabledCount")) $("locateRecipeEnabledCount").textContent = String(enabledRules.length);
  if ($("locateRecipeExpectedTotal")) $("locateRecipeExpectedTotal").textContent = String(expectedTotal);
  if ($("toggleLocateRecipeDetails")) $("toggleLocateRecipeDetails").textContent = state.locateRecipeExpanded ? "收起" : "展开";
}

function setLocateRecipeExpanded(expanded) {
  state.locateRecipeExpanded = Boolean(expanded);
  $("locateAccessoryList")?.classList.toggle("expanded", state.locateRecipeExpanded);
  updateLocateRecipeSummary();
}

function upsertLocateRule(itemOrId, options = {}) {
  const source = typeof itemOrId === "string" ? locateSourceById(itemOrId) : itemOrId;
  if (!source?.id) return;
  const index = state.locateAnythingRules.findIndex((rule) => rule.id === source.id);
  if (index >= 0) {
    state.locateAnythingRules[index] = mergeLocateRuleWithSource({
      ...state.locateAnythingRules[index],
      enabled: options.enabled ?? true,
    });
  } else {
    state.locateAnythingRules.push(locateRuleFromSource(source));
  }
  renderLocateSources();
}

function updateLocateRule(id, updates) {
  const index = state.locateAnythingRules.findIndex((rule) => rule.id === id);
  if (index < 0) return;
  state.locateAnythingRules[index] = mergeLocateRuleWithSource({ ...state.locateAnythingRules[index], ...updates });
  renderLocateSources();
}

function removeLocateRule(id) {
  state.locateAnythingRules = state.locateAnythingRules.filter((rule) => rule.id !== id);
  renderLocateSources();
}

function locatePickerSearchText(item) {
  return [
    item.label,
    item.display_label,
    item.material_type,
    item.source,
    item.visual_prompt,
    ...(item.search_terms || []),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function renderLocateRecipePicker() {
  const picker = $("locateRecipePicker");
  const list = $("locateRecipePickerList");
  const search = $("locateRecipeSearch");
  if (!picker || !list) return;
  picker.classList.toggle("hidden", !state.locateRecipePickerOpen);
  if (search && search.value !== state.locateRecipeQuery) search.value = state.locateRecipeQuery;
  const selectedById = new Map(state.locateAnythingRules.map((rule) => [rule.id, rule]));
  const query = state.locateRecipeQuery.trim().toLowerCase();
  const matches = state.locateAnythingSources
    .filter((item) => !query || locatePickerSearchText(item).includes(query))
    .slice(0, 40);
  list.innerHTML = matches.length
    ? matches
        .map((item) => {
          const selectedRule = selectedById.get(item.id);
          const configured = Boolean(selectedRule);
          const checked = Boolean(selectedRule && selectedRule.enabled !== false);
          const stateText = configured ? (checked ? "已启用" : "已停用") : "未添加";
          const detailText = [item.visual_prompt || item.material_type || item.source || "", stateText].filter(Boolean).join(" · ");
          return `
            <label class="locate-picker-row" data-locate-picker-item="${escapeAttr(item.id)}">
              <input type="checkbox" data-locate-picker-checkbox ${checked ? "checked" : ""} />
              <span>
                <strong>${escapeHtml(item.display_label || item.label)}</strong>
                <small>${escapeHtml(detailText)}</small>
              </span>
            </label>
          `;
        })
        .join("")
    : `<p class="hint">没有匹配项。</p>`;
  list.querySelectorAll("[data-locate-picker-checkbox]").forEach((checkbox) => {
    checkbox.addEventListener("change", (event) => {
      const id = event.currentTarget.closest("[data-locate-picker-item]")?.dataset.locatePickerItem || "";
      if (event.currentTarget.checked) {
        upsertLocateRule(id, { enabled: true });
      } else {
        updateLocateRule(id, { enabled: false });
      }
    });
  });
}

function renderLocateSources(items = state.locateAnythingSources || []) {
  const wrap = $("locateAccessoryList");
  if (!wrap) return;
  state.locateAnythingSources = items;
  if (!state.locateAnythingRules.length) {
    const defaults = items.filter((item) => item.default_selected).slice(0, 4);
    state.locateAnythingRules = (defaults.length ? defaults : items.slice(0, 2)).map(locateRuleFromSource);
  }
  normalizeLocateRules();
  wrap.classList.toggle("expanded", state.locateRecipeExpanded);
  wrap.innerHTML = state.locateAnythingRules.length
    ? state.locateAnythingRules
        .map((item) => {
          const expectedPresent = item.expected_present !== false;
          const expectedCount = item.expected_count ?? 1;
          return `
            <div class="locate-rule-row ${item.enabled === false ? "disabled" : ""}" data-locate-rule="${escapeAttr(item.id)}" data-locate-label="${escapeAttr(item.display_label || item.label)}">
              <label class="locate-rule-main">
                <input type="checkbox" data-locate-enabled ${item.enabled !== false ? "checked" : ""} />
                <span>
                  <strong>${escapeHtml(item.display_label || item.label)}</strong>
                  <small>${item.source === "accessory" ? "配件" : "类别"} · ${escapeHtml(item.material_type || "-")}</small>
                </span>
              </label>
              <label class="locate-presence-toggle">
                <input type="checkbox" data-locate-expected-present ${expectedPresent ? "checked" : ""} />
                <span>应出现</span>
              </label>
              <label class="locate-count-field">
                <span>数量</span>
                <input type="number" min="0" max="99" data-locate-expected-count value="${escapeAttr(expectedCount)}" />
              </label>
              <button class="icon-button locate-remove-rule" type="button" data-locate-remove title="移除">×</button>
              <details class="locate-rule-advanced">
                <summary>提示词</summary>
                <small>${escapeHtml(item.visual_prompt || "系统会根据配件资料生成英文视觉描述。")}</small>
                <input data-locate-prompt-override type="text" value="${escapeAttr(item.prompt_override || "")}" placeholder="可选：覆盖自动生成提示词" />
              </details>
            </div>
          `;
        })
        .join("")
    : `<p class="hint">还没有检测项。点击“添加”从配件库或类别中选择。</p>`;
  wrap.querySelectorAll("[data-locate-enabled]").forEach((input) => {
    input.addEventListener("change", (event) => updateLocateRule(event.currentTarget.closest("[data-locate-rule]")?.dataset.locateRule || "", { enabled: event.currentTarget.checked }));
  });
  wrap.querySelectorAll("[data-locate-expected-present]").forEach((input) => {
    input.addEventListener("change", (event) => updateLocateRule(event.currentTarget.closest("[data-locate-rule]")?.dataset.locateRule || "", { expected_present: event.currentTarget.checked }));
  });
  wrap.querySelectorAll("[data-locate-expected-count]").forEach((input) => {
    input.addEventListener("change", (event) => updateLocateRule(event.currentTarget.closest("[data-locate-rule]")?.dataset.locateRule || "", { expected_count: Number(event.currentTarget.value || 0) }));
  });
  wrap.querySelectorAll("[data-locate-prompt-override]").forEach((input) => {
    input.addEventListener("change", (event) => updateLocateRule(event.currentTarget.closest("[data-locate-rule]")?.dataset.locateRule || "", { prompt_override: event.currentTarget.value.trim() }));
  });
  wrap.querySelectorAll("[data-locate-remove]").forEach((button) => {
    button.addEventListener("click", (event) => removeLocateRule(event.currentTarget.closest("[data-locate-rule]")?.dataset.locateRule || ""));
  });
  updateLocateRecipeSummary();
  renderLocateRecipePicker();
}

async function refreshLocateSources() {
  try {
    const result = await api("/api/locateanything/accessories");
    renderLocateSources(result.items || []);
  } catch (error) {
    toast(`读取检测配置失败：${error.message}`);
  }
}

function setLocateInput(kind, file = null) {
  if (state.locateAnythingInput.url) URL.revokeObjectURL(state.locateAnythingInput.url);
  state.locateAnythingInput = { kind, url: file ? URL.createObjectURL(file) : "", fileName: file?.name || "" };
  const cameraVideo = $("locateCameraVideo");
  const preview = $("locateSourceImage");
  const empty = $("locateSourceEmpty");
  if (!preview || !empty) return;
  if (kind === "camera" && state.locateCamera.stream) {
    preview.style.display = "none";
    if (cameraVideo) cameraVideo.style.display = "block";
    empty.style.display = "none";
  } else if (state.locateAnythingInput.url) {
    preview.src = state.locateAnythingInput.url;
    preview.style.display = "block";
    if (cameraVideo) cameraVideo.style.display = "none";
    empty.style.display = "none";
  }
  if (state.fullscreenMode === "locate") syncInspectFullscreen("locate");
}

function locateStatusLabel(status) {
  return {
    found: "已找到",
    missing: "缺失",
    count_mismatch: "数量不符",
    uncertain: "不确定",
    unexpected: "不应出现",
    not_expected_absent: "未出现",
  }[status] || status || "-";
}

function setLocateResultBadge(result) {
  const badge = $("locateResultBadge");
  const overall = $("locateOverallResult");
  if (!badge) return;
  badge.className = "result-badge";
  if (result?.overall_pass) {
    badge.classList.add("pass");
    badge.textContent = "通过";
    if (overall) {
      overall.className = "locate-overall pass";
      overall.textContent = "通过";
    }
  } else if (result) {
    badge.classList.add("fail");
    badge.textContent = "不通过";
    if (overall) {
      overall.className = "locate-overall fail";
      overall.textContent = "不通过";
    }
  } else {
    badge.classList.add("waiting");
    badge.textContent = "等待检测";
    if (overall) {
      overall.className = "locate-overall waiting";
      overall.textContent = "等待检测";
    }
  }
}

function renderLocateResult(result) {
  state.locateAnythingLastResult = result;
  setLocateResultBadge(result);
  $("locateResultStatus").textContent = result.overall_pass ? "全部符合" : result.error || "存在异常";
  $("locateBoxCount").textContent = (result.items || []).reduce((total, item) => total + Number(item.box_count || 0), 0);
  $("locateLatencyText").textContent = result.latency_ms ? `${result.latency_ms} ms` : "-";
  $("locateFrameCount").textContent = String(state.locateCamera.frameCount || 0);
  const diagnostics = result.diagnostics || [];
  $("locateDiagnosticText").textContent = diagnostics.length
    ? diagnostics
        .map((item) => [
          `检测项：${item.label || item.id}`,
          `提示词：${item.prompt || "-"}`,
          `回答片段：${item.raw_answer_snippet || "-"}`,
          item.error ? `错误：${item.error}` : `定位框：${item.box_count || 0}`,
        ].join("\n"))
        .join("\n\n")
    : result.diagnostic_url
      ? `诊断文件：${result.diagnostic_url}`
      : result.error || "暂无诊断信息。";

  const preview = $("locatePreviewImage");
  const empty = $("locateEmptyPreview");
  const imageUrl = result.overlay_url || state.locateAnythingInput.url || "";
  if (imageUrl) {
    preview.src = result.overlay_url ? `${result.overlay_url}?t=${Date.now()}` : imageUrl;
    preview.style.display = "block";
    empty.style.display = "none";
  } else {
    preview.style.display = "none";
    empty.style.display = "grid";
  }

  const items = result.items || [];
  $("locateInspectionItems").innerHTML = items.length
    ? items
        .map(
          (item) => `
            <tr>
              <td>${escapeHtml(item.label || item.id)}</td>
              <td><span class="status-dot ${item.passed ? "ok" : "fail"}">${escapeHtml(locateStatusLabel(item.status))}</span></td>
              <td>${item.expected_present ? escapeHtml(String(item.expected_count || 1)) : "不应出现"}</td>
              <td>${Number(item.box_count || 0)}</td>
            </tr>
          `,
        )
        .join("")
    : `<tr><td colspan="4">${escapeHtml(result.error || "暂无检测项")}</td></tr>`;
  if (state.fullscreenMode === "locate") syncInspectFullscreen("locate");
}

function locateInspectForm(file) {
  const rules = selectedLocateRules();
  const form = new FormData();
  const config = readLocateConfigPayload();
  form.append("file", file);
  form.append("rules", JSON.stringify(rules));
  form.append("endpoint_url", config.endpoint_url);
  form.append("max_side", config.max_side);
  form.append("max_new_tokens", config.max_new_tokens);
  return { form, rules };
}

function setLocateInspectControlsBusy(busy) {
  state.locateAnythingInspectInFlight = busy;
  ["captureLocateFrame", "runLocateImage", "startLocateCameraLoop"].forEach((id) => {
    const button = $(id);
    if (button) button.disabled = busy;
  });
  $("locateResultStatus").textContent = busy ? "检测中" : $("locateResultStatus").textContent;
}

async function runLocateInspectWithFile(file, button = null, options = {}) {
  if (!file) return toast("请先选择图片或打开摄像头。");
  if (state.locateAnythingInspectInFlight) {
    if (!options.quiet) toast("检测正在进行，请等待当前帧完成。");
    return null;
  }
  const { form, rules } = locateInspectForm(file);
  if (!rules.length) return toast("请至少选择一个检测项。");
  setLocateInput(options.kind || "image", file);
  setLocateResultBadge(null);
  setLocateInspectControlsBusy(true);
  setBusy(button, true);
  try {
    const result = await api("/api/locateanything/inspect", { method: "POST", body: form });
    renderLocateResult(result);
    if (!options.quiet) toast(result.overall_pass ? "检测通过。" : "检测不通过，请复核。");
    return result;
  } catch (error) {
    const result = { ok: false, overall_pass: false, error: error.message, items: [], latency_ms: 0 };
    renderLocateResult(result);
    if (!options.quiet) toast(`检测失败：${error.message}`);
    return result;
  } finally {
    setBusy(button, false);
    setLocateInspectControlsBusy(false);
  }
}

async function runLocateImage(button) {
  if (state.locateAnythingInspectInFlight) return toast("检测正在进行，请等待当前帧完成。");
  return runLocateInspectWithFile($("locateImageFile")?.files?.[0], button, { kind: "image" });
}

function setLocateCameraPreviewActive(active) {
  const video = $("locateCameraVideo");
  const empty = $("locateSourceEmpty");
  if (!video || !empty) return;
  video.style.display = active ? "block" : "none";
  empty.style.display = active ? "none" : "grid";
}

function stopLocateCameraStream() {
  state.locateCamera.detecting = false;
  state.locateCamera.inFlight = false;
  for (const track of state.locateCamera.stream?.getTracks?.() || []) track.stop();
  state.locateCamera.stream = null;
  const video = $("locateCameraVideo");
  if (video) video.srcObject = null;
  setLocateCameraPreviewActive(false);
  $("startLocateCameraLoop")?.classList.remove("hidden");
  $("stopLocateCameraLoop")?.classList.add("hidden");
}

function renderLocateCameraMenu() {
  const devices = state.locateCamera.devices || [];
  const options = devices.length
    ? devices.map((device, index) => ({
        value: device.deviceId,
        label: device.label || `摄像头 ${index + 1}`,
        meta: device.label ? "可用" : "授权后显示名称",
      }))
    : [{ value: "", label: "未检测到摄像头", meta: "可直接用图片检测", disabled: true }];
  state.locateCamera.selectedDeviceId = renderCustomMenu("locateCameraMenu", options, state.locateCamera.selectedDeviceId, (value) => {
    state.locateCamera.selectedDeviceId = value;
    if (value) startLocateCamera(value);
  });
}

async function refreshLocateCameraDevices() {
  if (!navigator.mediaDevices?.enumerateDevices) {
    state.locateCamera.devices = [];
    renderLocateCameraMenu();
    toast("当前浏览器不支持摄像头枚举。");
    return [];
  }
  const devices = await navigator.mediaDevices.enumerateDevices();
  state.locateCamera.devices = devices.filter((device) => device.kind === "videoinput");
  if (!state.locateCamera.selectedDeviceId && state.locateCamera.devices.length) {
    state.locateCamera.selectedDeviceId = state.locateCamera.devices[0].deviceId;
  }
  renderLocateCameraMenu();
  return state.locateCamera.devices;
}

async function startLocateCamera(deviceId = state.locateCamera.selectedDeviceId) {
  if (state.locateCamera.starting) return;
  if (!navigator.mediaDevices?.getUserMedia) {
    toast("当前浏览器不支持摄像头。");
    return;
  }
  state.locateCamera.starting = true;
  try {
    stopLocateCameraStream();
    const videoConstraints = deviceId ? { deviceId: { exact: deviceId } } : true;
    const stream = await navigator.mediaDevices.getUserMedia({ video: videoConstraints, audio: false });
    state.locateCamera.stream = stream;
    const video = $("locateCameraVideo");
    video.srcObject = stream;
    await video.play();
    const track = stream.getVideoTracks()[0];
    const settings = track?.getSettings?.() || {};
    if (settings.deviceId) state.locateCamera.selectedDeviceId = settings.deviceId;
    await refreshLocateCameraDevices();
    setLocateInput("camera");
    setLocateCameraPreviewActive(true);
  } catch (error) {
    stopLocateCameraStream();
    toast(`摄像头不可用：${error.message}`);
  } finally {
    state.locateCamera.starting = false;
  }
}

async function captureLocateCameraFrame() {
  if (!state.locateCamera.stream) await startLocateCamera();
  const video = $("locateCameraVideo");
  if (!state.locateCamera.stream || !video.videoWidth || !video.videoHeight) {
    throw new Error("摄像头画面尚未准备好");
  }
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (!blob) {
        reject(new Error("摄像头采样失败"));
        return;
      }
      resolve(new File([blob], `locate_camera_${Date.now()}.jpg`, { type: "image/jpeg" }));
    }, "image/jpeg", 0.9);
  });
}

async function runLocateCameraOnce(button = null, options = {}) {
  if (state.locateAnythingInspectInFlight) {
    if (!options.quiet) toast("检测正在进行，请等待当前帧完成。");
    return null;
  }
  const file = await captureLocateCameraFrame();
  state.locateCamera.frameCount += 1;
  return runLocateInspectWithFile(file, button, { kind: "camera", quiet: options.quiet });
}

function locateCameraSampleDelayMs() {
  const input = $("locateCameraSampleSeconds");
  const value = Number.parseFloat(input?.value || "");
  const sampleSeconds = Math.min(2, Math.max(0.5, Number.isFinite(value) ? value : 1));
  if (input && input.value !== String(sampleSeconds)) input.value = String(sampleSeconds);
  return Math.round(sampleSeconds * 1000);
}

async function locateCameraLoop() {
  if (!state.locateCamera.detecting) return;
  if (state.locateAnythingInspectInFlight) {
    setTimeout(locateCameraLoop, locateCameraSampleDelayMs());
    return;
  }
  state.locateCamera.inFlight = true;
  try {
    await runLocateCameraOnce(null, { quiet: true });
  } catch (error) {
    renderLocateResult({ ok: false, overall_pass: false, error: error.message, items: [], latency_ms: 0 });
  } finally {
    state.locateCamera.inFlight = false;
    if (state.locateCamera.detecting) setTimeout(locateCameraLoop, locateCameraSampleDelayMs());
  }
}

async function startLocateCameraLoop(button) {
  if (state.locateAnythingInspectInFlight) return toast("检测正在进行，请等待当前帧完成。");
  if (!selectedLocateRules().length) return toast("请至少选择一个检测项。");
  setBusy(button, true);
  try {
    if (!state.locateCamera.stream) await startLocateCamera();
    if (!state.locateCamera.stream) return;
    state.locateCamera.detecting = true;
    $("startLocateCameraLoop")?.classList.add("hidden");
    $("stopLocateCameraLoop")?.classList.remove("hidden");
    locateCameraLoop();
  } finally {
    setBusy(button, false);
  }
}

function stopLocateCameraLoop() {
  state.locateCamera.detecting = false;
  $("startLocateCameraLoop")?.classList.remove("hidden");
  $("stopLocateCameraLoop")?.classList.add("hidden");
}

async function onLocateViewEntry() {
  await refreshLocateSources();
  await checkLocateStatus(null, { quiet: true });
  renderLocateCameraMenu();
}

function dataAnalysisStatusLabel(value) {
  return {
    same: "一致",
    different: "有差异",
    completed: "已定位",
    failed: "定位失败",
    unavailable: "服务不可用",
  }[value] || value || "未定位";
}

function dataAnalysisAiSummaryText(summary = {}) {
  const stateText = summary.passed ? "通过" : "不通过";
  const present = Number(summary.present_count || 0);
  const missing = Number(summary.missing_count || 0);
  const mismatch = Number(summary.count_mismatch_count || 0);
  return `${stateText} · 命中 ${present} · 缺失 ${missing}${mismatch ? ` · 数量 ${mismatch}` : ""}`;
}

function dataAnalysisLocateSummaryText(record = {}) {
  const latest = record.latest_locateanything_run || {};
  if (!record.locateanything_run_count) return "未定位";
  if (latest.status === "completed") {
    return `${latest.overall_pass ? "通过" : "不通过"} · ${Number(latest.box_count || 0)} 框 · ${latest.latency_ms || 0} ms`;
  }
  return latest.error || dataAnalysisStatusLabel(latest.status);
}

function latestDataAnalysisRun(record = {}) {
  const runs = Array.isArray(record.locateanything_runs) ? record.locateanything_runs.filter((item) => item && typeof item === "object") : [];
  if (runs.length) return runs[runs.length - 1];
  return record.latest_locateanything_run && typeof record.latest_locateanything_run === "object" ? record.latest_locateanything_run : {};
}

function dataAnalysisAiImageUrl(record = {}) {
  const result = record.ai_detection_result && typeof record.ai_detection_result === "object" ? record.ai_detection_result : {};
  return result.annotated_url || result.preview_url || result.output_url || record.image_url || record.source_image?.url || "";
}

function dataAnalysisLocateImageUrl(record = {}, latestRun = latestDataAnalysisRun(record)) {
  const listLatest = record.latest_locateanything_run && typeof record.latest_locateanything_run === "object" ? record.latest_locateanything_run : {};
  return latestRun.overlay_url || latestRun.preview_url || listLatest.overlay_url || "";
}

function dataAnalysisComparisonText(summary = {}) {
  const parts = [dataAnalysisStatusLabel(summary.status)];
  const differenceCount = Number(summary.difference_count);
  if (Number.isFinite(differenceCount) && summary.status) parts.push(`差异 ${differenceCount}`);
  return parts.join(" · ");
}

function dataAnalysisRunSummaryText(run = {}) {
  if (!run.run_id) return "未定位";
  if (run.status === "completed") {
    return `${run.overall_pass ? "通过" : "不通过"} · ${Number(run.box_count || 0)} 框 · ${Number(run.latency_ms || 0)} ms`;
  }
  return run.error || dataAnalysisStatusLabel(run.status);
}

function dataAnalysisLocatePlaceholder(run = {}) {
  if (!run.run_id) return "尚未运行 LocateAnything";
  if (run.status === "completed") return "本次定位未生成框选图";
  return run.error || dataAnalysisStatusLabel(run.status);
}

function renderDataAnalysisMetric(label, value, options = {}) {
  const className = options.className ? ` ${escapeAttr(options.className)}` : "";
  return `
    <div>
      <label>${escapeHtml(label)}</label>
      <strong class="${className.trim()}">${escapeHtml(value || "-")}</strong>
    </div>
  `;
}

function renderDataAnalysisImagePanel(title, url, placeholder, rows = [], token = "") {
  const media = url
    ? `<img src="${escapeAttr(cacheBustedUrl(url, token || uniqueClientToken(title)))}" alt="${escapeAttr(title)}" />`
    : `<div class="analysis-compare-empty">${escapeHtml(placeholder)}</div>`;
  const meta = rows
    .filter((row) => row && row.value !== undefined && row.value !== null && String(row.value).trim() !== "")
    .map((row) => `<li><span>${escapeHtml(row.label)}</span><strong>${escapeHtml(row.value)}</strong></li>`)
    .join("");
  return `
    <section class="analysis-compare-card">
      <div class="analysis-compare-card-head">
        <h3>${escapeHtml(title)}</h3>
        <span class="pill ${url ? "ok" : "neutral"}">${url ? "图像可用" : "无图像"}</span>
      </div>
      <div class="analysis-compare-frame">${media}</div>
      <ul class="analysis-compare-meta">${meta}</ul>
    </section>
  `;
}

function renderDataAnalysisDifferences(summary = {}) {
  const differences = Array.isArray(summary.differences) ? summary.differences : [];
  if (!differences.length) return "";
  return `
    <div class="data-analysis-diff-list">
      <strong>差异明细</strong>
      <div>
        ${differences
          .slice(0, 6)
          .map((item) => {
            const delta = Number(item.delta || 0);
            const deltaText = delta > 0 ? `+${delta}` : String(delta);
            return `
              <span>
                ${escapeHtml(item.label || item.accessory_id || "未命名")}
                <small>AI ${Number(item.ai_count || 0)} / LA ${Number(item.locateanything_count || 0)} / ${escapeHtml(deltaText)}</small>
              </span>
            `;
          })
          .join("")}
      </div>
    </div>
  `;
}

function dataAnalysisCompareClass(summary = {}) {
  if (summary.status === "same") return "ok";
  if (summary.status === "different") return "warn";
  if (summary.status) return "fail";
  return "neutral";
}

function dataAnalysisQueryPath() {
  const params = new URLSearchParams({ limit: "200" });
  if (state.dataAnalysis.selectedTaskId) params.set("task_id", state.dataAnalysis.selectedTaskId);
  return withAuthScope(`/api/data-analysis/records?${params.toString()}`);
}

async function refreshDataAnalysisRecords(options = {}) {
  if (!hasPermission("ai_detection")) return;
  state.dataAnalysis.loading = true;
  if (!options.quiet) renderDataAnalysisRecords();
  try {
    const result = await api(dataAnalysisQueryPath());
    state.dataAnalysis.records = result.records || [];
    state.dataAnalysis.tasks = result.tasks || [];
    state.dataAnalysis.batchLimit = Number(result.batch_limit || 25);
    const visibleIds = new Set(state.dataAnalysis.records.map((record) => record.record_id));
    state.dataAnalysis.selectedRecordIds = new Set([...state.dataAnalysis.selectedRecordIds].filter((id) => visibleIds.has(id)));
    renderDataAnalysisTaskFilter();
    renderDataAnalysisRecords();
  } catch (error) {
    toast(`读取数据分析失败：${error.message}`);
  } finally {
    state.dataAnalysis.loading = false;
    renderDataAnalysisRecords();
  }
}

function renderDataAnalysisTaskFilter() {
  const select = $("dataAnalysisTaskFilter");
  if (!select) return;
  const current = state.dataAnalysis.selectedTaskId || "";
  const options = [
    `<option value="">全部任务</option>`,
    ...state.dataAnalysis.tasks.map((task) => `<option value="${escapeAttr(task.id)}">${escapeHtml(task.name)} (${Number(task.count || 0)})</option>`),
  ].join("");
  select.innerHTML = options;
  select.value = state.dataAnalysis.tasks.some((task) => task.id === current) ? current : "";
  state.dataAnalysis.selectedTaskId = select.value;
}

function selectedDataAnalysisRecords() {
  const selected = state.dataAnalysis.selectedRecordIds;
  return state.dataAnalysis.records.filter((record) => selected.has(record.record_id));
}

function renderDataAnalysisRecords() {
  const list = $("dataAnalysisList");
  if (!list) return;
  const records = state.dataAnalysis.records || [];
  const selectedCount = selectedDataAnalysisRecords().length;
  const allVisibleSelected = Boolean(records.length) && records.every((record) => state.dataAnalysis.selectedRecordIds.has(record.record_id));
  if ($("dataAnalysisSelectedCount")) $("dataAnalysisSelectedCount").textContent = `${selectedCount} 已选`;
  if ($("dataAnalysisProgress")) $("dataAnalysisProgress").textContent = state.dataAnalysis.progressText || (state.dataAnalysis.running ? "定位中" : "");
  if ($("dataAnalysisSelectAll")) {
    $("dataAnalysisSelectAll").checked = allVisibleSelected;
    $("dataAnalysisSelectAll").indeterminate = selectedCount > 0 && !allVisibleSelected;
  }
  ["runDataAnalysisSelected", "runDataAnalysisVisible"].forEach((id) => {
    const button = $(id);
    if (!button) return;
    button.disabled = state.dataAnalysis.running || (id === "runDataAnalysisSelected" ? selectedCount === 0 : records.length === 0);
  });
  if (state.dataAnalysis.loading && !records.length) {
    list.innerHTML = `<tr><td colspan="8">正在读取数据分析记录...</td></tr>`;
    return;
  }
  if (!records.length) {
    list.innerHTML = `<tr><td colspan="8">暂无 AI 检测记录。完成一次 AI 检测后会自动出现在这里。</td></tr>`;
    return;
  }
  list.innerHTML = records
    .map((record) => {
      const task = record.task || {};
      const comparison = record.comparison_summary || {};
      const latest = record.latest_locateanything_run || {};
      const checked = state.dataAnalysis.selectedRecordIds.has(record.record_id) ? "checked" : "";
      const imageUrl = record.image_url || record.source_image?.url || latest.overlay_url || "";
      const compareStatus = comparison.status || latest.status || "";
      return `
        <tr data-analysis-record="${escapeAttr(record.record_id)}">
          <td class="select-cell"><input type="checkbox" data-analysis-select ${checked} aria-label="选择记录" /></td>
          <td>
            <button class="analysis-thumb" type="button" data-preview-url="${escapeAttr(imageUrl)}" ${imageUrl ? "" : "disabled"}>
              ${imageUrl ? `<img src="${escapeAttr(imageUrl)}?v=${escapeAttr(record.updated_at || record.created_at || "")}" alt="" />` : `<span>无图</span>`}
            </button>
          </td>
          <td>
            <strong>${escapeHtml(record.source_image?.filename || record.record_id)}</strong>
            <span>${escapeHtml(recordAuditText(record, { includeUpdated: true }))}</span>
          </td>
          <td>${escapeHtml(task.name || task.id || "AI 检测")}</td>
          <td>${escapeHtml(dataAnalysisAiSummaryText(record.ai_summary || {}))}</td>
          <td>${escapeHtml(dataAnalysisLocateSummaryText(record))}</td>
          <td><span class="status-dot ${dataAnalysisCompareClass(comparison)}">${escapeHtml(dataAnalysisStatusLabel(compareStatus))}</span></td>
          <td class="row-actions">
            <button class="mini-secondary" type="button" data-analysis-run>定位</button>
            <button class="mini-secondary" type="button" data-analysis-detail>详情</button>
          </td>
        </tr>
      `;
    })
    .join("");
  list.querySelectorAll("[data-analysis-select]").forEach((checkbox) => {
    checkbox.addEventListener("change", (event) => {
      const recordId = event.currentTarget.closest("[data-analysis-record]")?.dataset.analysisRecord || "";
      if (!recordId) return;
      if (event.currentTarget.checked) state.dataAnalysis.selectedRecordIds.add(recordId);
      else state.dataAnalysis.selectedRecordIds.delete(recordId);
      renderDataAnalysisRecords();
    });
  });
  list.querySelectorAll("[data-analysis-run]").forEach((button) => {
    button.addEventListener("click", () => runDataAnalysisLocate([button.closest("[data-analysis-record]")?.dataset.analysisRecord].filter(Boolean), button));
  });
  list.querySelectorAll("[data-analysis-detail]").forEach((button) => {
    button.addEventListener("click", () => openDataAnalysisDetail(button.closest("[data-analysis-record]")?.dataset.analysisRecord || ""));
  });
  bindImagePreviewTriggers(list);
}

async function runDataAnalysisLocate(recordIds, button = null) {
  const ids = [...new Set((recordIds || []).filter(Boolean))];
  if (!ids.length) return toast("请先选择记录。");
  if (ids.length > state.dataAnalysis.batchLimit) return toast(`一次最多处理 ${state.dataAnalysis.batchLimit} 条。`);
  state.dataAnalysis.running = true;
  setBusy(button, true);
  try {
    for (const [index, recordId] of ids.entries()) {
      state.dataAnalysis.progressText = `定位 ${index + 1}/${ids.length}`;
      renderDataAnalysisRecords();
      await api(`/api/data-analysis/records/${encodeURIComponent(recordId)}/locate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
    }
    state.dataAnalysis.progressText = "";
    await refreshDataAnalysisRecords({ quiet: true });
    toast(ids.length > 1 ? "批量定位完成。" : "定位完成。");
  } catch (error) {
    toast(`定位失败：${error.message}`);
  } finally {
    state.dataAnalysis.running = false;
    state.dataAnalysis.progressText = "";
    setBusy(button, false);
    renderDataAnalysisRecords();
  }
}

async function openDataAnalysisDetail(recordId) {
  if (!recordId) return;
  try {
    const result = await api(`/api/data-analysis/records/${encodeURIComponent(recordId)}`);
    const record = result.record || result;
    const latestRun = latestDataAnalysisRun(record);
    const comparison = record.comparison_summary || {};
    const aiSummary = record.ai_summary || {};
    const aiImageUrl = dataAnalysisAiImageUrl(record);
    const locateImageUrl = dataAnalysisLocateImageUrl(record, latestRun);
    const locateRows = [
      { label: "状态", value: dataAnalysisRunSummaryText(latestRun) },
      { label: "运行", value: latestRun.created_at ? formatRecordTime(latestRun.created_at) : "未运行" },
    ];
    if (isAdmin()) locateRows.push({ label: "诊断", value: latestRun.diagnostic_url || "-" });
    const filename = record.source_image?.filename || record.record_id || "数据分析记录";
    if ($("dataAnalysisDetailTitle")) $("dataAnalysisDetailTitle").textContent = filename;
    if ($("dataAnalysisDetailSummary")) {
      $("dataAnalysisDetailSummary").innerHTML = [
        renderDataAnalysisMetric("任务", record.task?.name || record.task?.id || "AI 检测"),
        renderDataAnalysisMetric("AI 检测", dataAnalysisAiSummaryText(aiSummary)),
        renderDataAnalysisMetric("LocateAnything", dataAnalysisRunSummaryText(latestRun)),
        renderDataAnalysisMetric("对比", dataAnalysisComparisonText(comparison), { className: `status-text ${dataAnalysisCompareClass(comparison)}` }),
      ].join("");
    }
    if ($("dataAnalysisDetailMedia")) {
      $("dataAnalysisDetailMedia").innerHTML = `
        <div class="analysis-compare-grid">
          ${renderDataAnalysisImagePanel(
            "AI 检测结果",
            aiImageUrl,
            "AI 检测图未保存",
            [
              { label: "状态", value: dataAnalysisAiSummaryText(aiSummary) },
              { label: "检测数量", value: Number(aiSummary.detection_count || 0) },
              { label: "请求", value: record.ai_detection_result?.request_id || "-" },
            ],
            record.updated_at || record.created_at || record.record_id,
          )}
          ${renderDataAnalysisImagePanel(
            "LocateAnything 框选图",
            locateImageUrl,
            dataAnalysisLocatePlaceholder(latestRun),
            locateRows,
            latestRun.run_id || record.updated_at || record.record_id,
          )}
        </div>
        ${renderDataAnalysisDifferences(comparison)}
      `;
    }
    if ($("dataAnalysisDetailRaw")) {
      $("dataAnalysisDetailRaw").innerHTML = isAdmin()
        ? `
          <details class="data-analysis-raw-detail">
            <summary>原始记录</summary>
            <pre id="dataAnalysisDetailJson" class="debug-pre"></pre>
          </details>
        `
        : "";
    }
    if (isAdmin() && $("dataAnalysisDetailJson")) $("dataAnalysisDetailJson").textContent = JSON.stringify(record, null, 2);
    $("dataAnalysisDetailModal")?.classList.add("visible");
    $("dataAnalysisDetailModal")?.setAttribute("aria-hidden", "false");
  } catch (error) {
    toast(`读取详情失败：${error.message}`);
  }
}

function closeDataAnalysisDetailModal() {
  $("dataAnalysisDetailModal")?.classList.remove("visible");
  $("dataAnalysisDetailModal")?.setAttribute("aria-hidden", "true");
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
    const files = item.source_file_count ?? item.source_files?.length ?? 0;
    const size = formatPhysicalSize(item.physical_size);
    row.innerHTML = `
      <div>
        <strong>${escapeHtml(zhLabel(item.name))}</strong>
        <span>${escapeHtml(recordAuditText(item))}</span>
        <span>${material} · 类别 ${item.class_id} · ${files} 个素材 · ${size} · ${STATUS_ZH[item.status] || item.status} · ${accessoryAiProfileText(item)}</span>
      </div>
      <button class="mini-secondary" data-view-accessory="${escapeAttr(item.id)}" type="button">查看</button>
      <button class="mini-danger" data-delete-accessory="${escapeAttr(item.id)}" type="button">删除</button>
    `;
    list.appendChild(row);
  }
  renderTrainingAccessories();
  renderAiAccessoryConfig();
  renderPipelineAddLibrary();
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
    button.addEventListener("click", () => openAccessoryDetail(button.dataset.viewAccessory, button));
  });
}

async function openAccessoryDetail(accessoryId, trigger = null) {
  setBusy(trigger, true);
  $("accessoryDetailTitle").textContent = "加载配件素材";
  $("accessoryDetailSummary").innerHTML = `<span>正在读取素材详情...</span>`;
  $("accessoryDetailGrid").innerHTML = `<div class="job-empty">正在加载素材预览...</div>`;
  $("accessoryDetailModal").classList.add("visible");
  $("accessoryDetailModal").setAttribute("aria-hidden", "false");
  try {
    const result = await api(`/api/accessories/${encodeURIComponent(accessoryId)}/detail`);
    const item = result.item || {};
    const gallery = result.gallery || [];
    state.accessoryDetailItem = item;
    renderAccessoryDetailFileQueue();
    $("accessoryDetailTitle").textContent = zhLabel(item.name || "配件素材");
    $("accessoryDetailSummary").innerHTML = `
      <strong>${escapeHtml(zhLabel(item.name || "配件"))} · ${item.material_type === "text" ? "文字类" : "物品类"}</strong>
      <span>${escapeHtml(recordAuditText(item, { includeUpdated: true }))}</span>
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
          <img src="${escapeAttr(asset.url)}" alt="${escapeHtml(assetLabel)}" loading="lazy" />
        </button>
        <figcaption>
          <strong>${escapeHtml(assetLabel)}</strong>
          <span>${escapeHtml(recordAuditText(asset, { owner: false }))}</span>
        </figcaption>
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
  } catch (error) {
    toast(`打开配件失败：${error.message}`);
  } finally {
    setBusy(trigger, false);
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
      if (!validateTextAccessoryFileBatch(state.accessoryDetailPendingFiles, item.source_file_count || item.source_files?.length || 0)) return;
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

function currentAiTask() {
  return state.aiTasks.find((item) => item.id === state.selectedAiTaskId) || null;
}

function selectedAiModelId() {
  const task = currentAiTask();
  if (!task?.id) return "";
  return task.model_id || `${AI_TASK_MODEL_PREFIX}${task.id}`;
}

function selectedAiModel() {
  const modelId = selectedAiModelId();
  return [...state.specializedModels, ...state.models].find((item) => item.id === modelId) || {
    id: modelId,
    label: "AI 检测",
    variant: "ai_detection",
    is_ai_detection: true,
  };
}

function currentAiTaskRequiredCounts() {
  return currentAiTask()?.required_accessory_counts || {};
}

function renderAiInspectStatus() {
  const badge = $("aiInspectStatus");
  const text = $("aiInspectStatusText");
  if (!badge) return;
  const config = state.aiConfig || {};
  const task = currentAiTask();
  badge.textContent = aiStatusText(config.status);
  badge.className = `pill ${config.status === "ready" ? "ok" : config.status === "missing_api_key" ? "neutral" : "fail"}`;
  const taskSuffix = task?.id ? `当前模型 ID：${selectedAiModelId()}` : "请先在训练流水线创建并选择 AI 检测任务。";
  if (text) {
    if (config.status === "ready") {
      text.textContent = `${config.model || "Gemini"} 已配置，AI 检测任务会直接调用当前 Provider。${taskSuffix}`;
    } else if (config.status === "missing_api_key") {
      text.textContent = `缺少 API Key；检测会显示结构化未就绪结果，不会静默通过。${taskSuffix}`;
    } else {
      text.textContent = `AI 检测未就绪；可在规则设置里配置 Gemini。${taskSuffix}`;
    }
    if ((task?.missing_accessory_ids || []).length) {
      text.textContent += ` 当前任务有 ${task.missing_accessory_ids.length} 个配件已不在配件库中。`;
    }
  }
}

function setAiTaskDraftFromTask(task) {
  state.aiTaskDraftCounts = {};
  const counts = task?.required_accessory_counts || {};
  for (const [itemId, count] of Object.entries(counts)) {
    state.aiTaskDraftCounts[itemId] = Math.max(1, Number(count || 1));
  }
}

function renderAiAccessoryConfig() {
  const wrap = $("aiAccessoryConfig");
  if (!wrap) return;
  const selectedCounts = currentAiTaskRequiredCounts();
  if (!state.accessories.length) {
    wrap.innerHTML = `<p class="hint">当前配件库为空，请先在配件管理中添加配件。</p>`;
    return;
  }
  if (!currentAiTask()) {
    wrap.innerHTML = `<p class="hint">AI 检测任务由训练流水线创建；当前还没有可用任务。</p>`;
    return;
  }
  wrap.innerHTML = state.accessories
    .map((item) => {
      const itemId = String(item.id || "");
      const checked = selectedCounts[itemId] !== undefined;
      const count = Math.max(1, Number(selectedCounts[itemId] || 1));
      const material = item.material_type === "text" ? "文本/说明书" : "物体";
      return `
        <label class="ai-accessory-row">
          <input type="checkbox" data-ai-accessory-id="${escapeAttr(itemId)}" ${checked ? "checked" : ""} disabled />
          <span class="ai-accessory-copy">
            <strong>${escapeHtml(item.name || item.label || itemId)}</strong>
            <small>${escapeHtml(material)} · ${escapeHtml(item.status || "active")}</small>
          </span>
          <input type="number" min="1" max="99" value="${count}" data-ai-accessory-count="${escapeAttr(itemId)}" disabled />
        </label>
      `;
    })
    .join("");
}

function renderAiTasks() {
  const options = state.aiTasks.length
    ? state.aiTasks.map((task) => ({
    value: task.id,
    label: task.name || task.accessory_names?.join(" + ") || task.id,
    meta: `${task.source === "pipeline" ? "流水线" : "已建档"} · ${task.accessory_count || task.selected_accessory_ids?.length || 0} 类配件`,
    }))
    : [{ value: "", label: "暂无流水线 AI 任务", meta: "请先在训练流水线创建", disabled: true }];
  if (state.selectedAiTaskId && !state.aiTasks.some((item) => item.id === state.selectedAiTaskId)) {
    state.selectedAiTaskId = "";
  }
  if (!state.selectedAiTaskId && state.aiTasks.length) {
    state.selectedAiTaskId = state.aiTasks[0].id;
  }
  const selected = renderCustomMenu("aiTaskMenu", options, state.selectedAiTaskId, (value) => {
    state.selectedAiTaskId = value;
    setAiTaskDraftFromTask(currentAiTask());
    renderAiTasks();
  });
  state.selectedAiTaskId = selected || state.selectedAiTaskId || "";
  const task = currentAiTask();
  if ($("aiTaskName")) $("aiTaskName").value = task?.name || "";
  if ($("deleteAiTask")) $("deleteAiTask").disabled = true;
  renderAiAccessoryConfig();
  renderAiInspectStatus();
}

function readAiTaskForm() {
  const accessories = [];
  document.querySelectorAll("[data-ai-accessory-id]").forEach((input) => {
    if (!input.checked) return;
    const itemId = input.dataset.aiAccessoryId;
    const countInput = document.querySelector(`[data-ai-accessory-count="${CSS.escape(itemId)}"]`);
    accessories.push({
      accessory_id: itemId,
      required_count: Math.max(1, Number(countInput?.value || 1)),
    });
  });
  return {
    name: $("aiTaskName")?.value.trim() || currentAiTask()?.name || "",
    accessories,
  };
}

async function refreshAiTasks(selectedId = state.selectedAiTaskId) {
  const result = await api(withAuthScope("/api/ai/tasks"));
  state.aiTasks = result.tasks || [];
  state.selectedAiTaskId = selectedId || result.selected_task_id || state.aiTasks[0]?.id || "";
  setAiTaskDraftFromTask(currentAiTask());
  renderAiTasks();
}

function startNewAiTask() {
  state.selectedAiTaskId = "__new__";
  state.aiTaskDraftCounts = {};
  if ($("aiTaskName")) $("aiTaskName").value = "";
  renderAiTasks();
  $("aiTaskName")?.focus();
}

async function saveCurrentAiTask(button) {
  const payload = readAiTaskForm();
  if (!payload.accessories.length) return toast("请至少选择一个配件。");
  const isUpdate = state.selectedAiTaskId && state.selectedAiTaskId !== "__new__";
  setBusy(button, true);
  try {
    const result = await api(isUpdate ? `/api/ai/tasks/${encodeURIComponent(state.selectedAiTaskId)}` : "/api/ai/tasks", {
      method: isUpdate ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.aiTasks = result.tasks || [];
    state.selectedAiTaskId = result.task?.id || result.selected_task_id || "";
    setAiTaskDraftFromTask(currentAiTask());
    renderAiTasks();
    await refreshStatusModels();
    toast("AI 检测任务已保存。");
  } catch (error) {
    toast(`保存 AI 任务失败：${error.message}`);
  } finally {
    setBusy(button, false);
  }
}

async function deleteCurrentAiTask(button) {
  const task = currentAiTask();
  if (!task) return toast("当前没有可删除的 AI 任务。");
  setBusy(button, true);
  try {
    const result = await api(`/api/ai/tasks/${encodeURIComponent(task.id)}`, { method: "DELETE" });
    state.aiTasks = result.tasks || [];
    state.selectedAiTaskId = result.selected_task_id || state.aiTasks[0]?.id || "";
    setAiTaskDraftFromTask(currentAiTask());
    renderAiTasks();
    await refreshStatusModels();
    toast("AI 检测任务已删除。");
  } catch (error) {
    toast(`删除 AI 任务失败：${error.message}`);
  } finally {
    setBusy(button, false);
  }
}

async function runAiImageDetection(button) {
  const file = $("aiImageFile").files[0];
  if (!file) return toast("请先选择一张图片。");
  const modelId = selectedAiModelId();
  if (!modelId) return toast("请先在训练流水线创建并选择 AI 检测任务。");
  setAiInspectInput("image", file);
  setBusy(button, true);
  startProgress("image", { ids: AI_PROGRESS_IDS, timerKey: "aiProgressTimer", valueKey: "aiProgressValue", getModel: selectedAiModel });
  try {
    const form = new FormData();
    form.append("file", file);
    form.append("model_id", modelId);
    const result = await api("/api/analyze/image", { method: "POST", body: form });
    renderImageResult(result, {
      ids: AI_RESULT_IDS,
      resultKey: "aiLastResult",
      requiredCounts: currentAiTaskRequiredCounts(),
      syncFullscreen: false,
    });
    if (state.fullscreenMode === "ai") syncInspectFullscreen("ai");
    finishProgress(true, { ids: AI_PROGRESS_IDS, timerKey: "aiProgressTimer", valueKey: "aiProgressValue" });
    refreshDataAnalysisRecords({ quiet: true }).catch(() => {});
    toast("AI 图片检测完成。");
  } catch (error) {
    finishProgress(false, { ids: AI_PROGRESS_IDS, timerKey: "aiProgressTimer", valueKey: "aiProgressValue" });
    toast(`AI 图片检测失败：${error.message}`);
  } finally {
    setBusy(button, false);
  }
}

async function runAiVideoDetection(button) {
  const file = $("aiVideoFile").files[0];
  if (!file) return toast("请先选择一个视频。");
  const modelId = selectedAiModelId();
  if (!modelId) return toast("请先在训练流水线创建并选择 AI 检测任务。");
  setAiInspectInput("video", file);
  setBusy(button, true);
  startProgress("video", { ids: AI_PROGRESS_IDS, timerKey: "aiProgressTimer", valueKey: "aiProgressValue", getModel: selectedAiModel });
  try {
    const form = new FormData();
    form.append("file", file);
    form.append("model_id", modelId);
    const result = await api("/api/analyze/video", { method: "POST", body: form });
    renderVideoResult(result, {
      ids: AI_RESULT_IDS,
      resultKey: "aiLastResult",
      requiredCounts: currentAiTaskRequiredCounts(),
      syncFullscreen: false,
    });
    if (state.fullscreenMode === "ai") syncInspectFullscreen("ai");
    finishProgress(true, { ids: AI_PROGRESS_IDS, timerKey: "aiProgressTimer", valueKey: "aiProgressValue" });
    refreshDataAnalysisRecords({ quiet: true }).catch(() => {});
    toast("AI 视频分析完成。");
  } catch (error) {
    finishProgress(false, { ids: AI_PROGRESS_IDS, timerKey: "aiProgressTimer", valueKey: "aiProgressValue" });
    toast(`AI 视频分析失败：${error.message}`);
  } finally {
    setBusy(button, false);
  }
}

async function refreshStatusModels() {
  const status = await api(withAuthScope("/api/status"));
  state.classes = status.classes;
  state.aiTasks = status.ai_detection_tasks || state.aiTasks;
  renderModels(status);
  return status;
}

function setInspectInput(kind, file = null) {
  if (state.inspectInput.url) URL.revokeObjectURL(state.inspectInput.url);
  state.inspectInput = { kind, url: file ? URL.createObjectURL(file) : "", fileName: file?.name || "" };
  syncInspectFullscreen();
}

function setAiInspectInput(kind, file = null) {
  if (state.aiInspectInput.url) URL.revokeObjectURL(state.aiInspectInput.url);
  state.aiInspectInput = { kind, url: file ? URL.createObjectURL(file) : "", fileName: file?.name || "" };
  if (state.fullscreenMode === "ai") syncInspectFullscreen("ai");
}

function fullscreenModeConfig(mode) {
  const normalizedMode = ["inspect", "ai", "locate"].includes(mode) ? mode : "inspect";
  if (normalizedMode === "ai") {
    return {
      mode: "ai",
      title: "AI 全屏检测",
      captureLabel: "拍照 AI 检测 · Enter",
      input: state.aiInspectInput,
      activeInputTab: document.querySelector(".mode-tab[data-ai-tab].active")?.dataset.aiTab || state.aiInspectInput.kind,
      cameraStream: state.aiCamera.stream,
      resultPreviewId: "aiPreviewImage",
      resultBadgeId: "aiResultBadge",
      decisionTextId: "aiDecisionText",
      detectionCountId: "aiDetectionCount",
      passRateId: "aiPassRate",
      tableId: "aiPartsTable",
    };
  }
  if (normalizedMode === "locate") {
    return {
      mode: "locate",
      title: "Locate Anything 全屏检测",
      captureLabel: "检测一帧 · Enter",
      input: state.locateAnythingInput,
      activeInputTab: state.locateAnythingInput.kind,
      cameraStream: state.locateCamera.stream,
      resultPreviewId: "locatePreviewImage",
      resultBadgeId: "locateOverallResult",
      decisionTextId: "locateResultStatus",
      detectionCountId: "locateBoxCount",
      passRateId: "locateLatencyText",
      tableId: "locateInspectionItems",
    };
  }
  return {
    mode: "inspect",
    title: "VantaLine 全屏检测",
    captureLabel: "拍照检测 · Enter",
    input: state.inspectInput,
    activeInputTab: document.querySelector(".mode-tab[data-tab].active")?.dataset.tab || state.inspectInput.kind,
    cameraStream: state.camera.stream,
    resultPreviewId: "previewImage",
    resultBadgeId: "resultBadge",
    decisionTextId: "decisionText",
    detectionCountId: "detectionCount",
    passRateId: "passRate",
    tableId: "partsTable",
  };
}

function syncInspectFullscreen(mode = state.fullscreenMode || "inspect") {
  const stage = $("inspectFullscreenStage");
  if (!stage) return;
  const config = fullscreenModeConfig(mode);
  state.fullscreenMode = config.mode;
  if ($("fullscreenTitle")) $("fullscreenTitle").textContent = config.title;
  if ($("fullscreenCaptureCamera")) $("fullscreenCaptureCamera").textContent = config.captureLabel;
  const inputImage = $("fullscreenInputImage");
  const inputVideo = $("fullscreenInputVideo");
  const inputEmpty = $("fullscreenInputEmpty");
  inputImage.style.display = "none";
  inputVideo.style.display = "none";
  inputVideo.pause?.();
  inputVideo.removeAttribute("src");
  inputVideo.srcObject = null;
  if (config.activeInputTab === "camera" && config.cameraStream) {
    inputVideo.srcObject = config.cameraStream;
    inputVideo.controls = false;
    inputVideo.style.display = "block";
    inputVideo.play?.();
    inputEmpty.style.display = "none";
  } else if (config.input.kind === "image" && config.input.url) {
    inputImage.src = config.input.url;
    inputImage.style.display = "block";
    inputEmpty.style.display = "none";
  } else if (config.input.kind === "video" && config.input.url) {
    inputVideo.src = config.input.url;
    inputVideo.controls = true;
    inputVideo.style.display = "block";
    inputEmpty.style.display = "none";
  } else {
    inputEmpty.style.display = "grid";
  }

  const preview = $(config.resultPreviewId);
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
  $("fullscreenDecision").textContent = $(config.resultBadgeId)?.textContent || "等待输入";
  $("fullscreenDecisionText").textContent = $(config.decisionTextId)?.textContent || "-";
  $("fullscreenDetectionCount").textContent = $(config.detectionCountId)?.textContent || "-";
  $("fullscreenPassRate").textContent = $(config.passRateId)?.textContent || "-";
  $("fullscreenPartsTable").innerHTML = $(config.tableId)?.innerHTML || "";
}

function runFullscreenCapture(button) {
  if (state.fullscreenMode === "ai") return runAiCameraDetection(button);
  if (state.fullscreenMode === "locate") return runLocateCameraOnce(button);
  return runCameraDetection(button);
}

async function openInspectFullscreen(mode = "inspect") {
  const stage = $("inspectFullscreenStage");
  syncInspectFullscreen(mode);
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
  const aiConfigRequest = hasPermission("ai_config") ? api("/api/ai/config") : Promise.resolve({});
  const locateConfigRequest = hasPermission("locate_config") ? api("/api/locateanything/config") : Promise.resolve({});
  const [status, config, aiConfig, locateConfig, aiTasks, accessories, trainingPlan] = await Promise.all([
    api(withAuthScope("/api/status")),
    api(withAuthScope("/api/config/summary")),
    aiConfigRequest,
    locateConfigRequest,
    api(withAuthScope("/api/ai/tasks")),
    api(withAuthScope("/api/accessories")),
    api(withAuthScope("/api/training/plan")),
  ]);
  state.config = config;
  state.aiConfig = aiConfig;
  state.classes = status.classes;
  $("serviceState").textContent = STATUS_ZH[status.service] || status.service;
  $("serviceState").className = `pill ${status.service === "running" ? "ok" : "fail"}`;
  $("modelState").textContent = status.model_exists ? "模型已加载" : "模型缺失";
  $("modelState").className = `pill ${status.model_exists ? "ok" : "fail"}`;
  if ($("homeServiceState")) {
    $("homeServiceState").textContent = $("serviceState").textContent;
    $("homeServiceState").className = $("serviceState").className;
  }
  if ($("homeModelState")) {
    $("homeModelState").textContent = $("modelState").textContent;
    $("homeModelState").className = $("modelState").className;
  }
  renderWindowsWorkerStatus(status.training_execution?.windows_worker || status.windows_worker || {});
  renderModels(status);
  renderAiConfig();
  renderAiInspectStatus();
  renderLocateConfig(locateConfig);
  await refreshLocateSources();
  renderRules();
  renderAccessories(accessories.items);
  state.aiTasks = aiTasks.tasks || status.ai_detection_tasks || [];
  state.selectedAiTaskId = aiTasks.selected_task_id || state.aiTasks[0]?.id || "";
  setAiTaskDraftFromTask(currentAiTask());
  renderAiTasks();
  // 标签参考接口在大量参考图时可能耗时十几秒,异步加载避免阻塞其余页面数据。
  refreshLabelSheetReferences().catch(() => {});
  refreshWindowsWorkerStatus().catch(() => {});
  renderTrainingPlan(trainingPlan);
  refreshDataAnalysisRecords({ quiet: true }).catch(() => {});
  refreshTrainingLibrary().catch(() => {});
  refreshImageJobs().catch(() => {});
  if (!state.imageJobPollTimer) state.imageJobPollTimer = setInterval(refreshImageJobs, 5000);
}

async function refreshImageJobs() {
  try {
    const result = await api(withAuthScope("/api/image-jobs"));
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

async function refreshTrainingLibrary(options = {}) {
  const refreshButton = options.manual ? $("refreshTrainingLibrary") : null;
  setBusy(refreshButton, true);
  try {
    const [result, status] = await Promise.all([
      api(withAuthScope("/api/training/resources")),
      api(withAuthScope("/api/status")),
    ]);
    state.trainingResources = result;
    renderTrainingLibrary(result);
    renderTrainingDatasetMenu();
    if ($("trainingResourceModal")?.classList.contains("visible") && state.trainingResourceDetail) {
      openTrainingResourceDetail(state.trainingResourceDetail.kind, state.trainingResourceDetail.id);
    }
    state.aiTasks = status.ai_detection_tasks || state.aiTasks;
    if (state.trainingResources) state.trainingResources.ai_detection_tasks = state.aiTasks;
    if (state.selectedAiTaskId && !state.aiTasks.some((item) => item.id === state.selectedAiTaskId)) {
      state.selectedAiTaskId = state.aiTasks[0]?.id || "";
    }
    renderAiTasks();
    renderModels(status);
  } catch (error) {
    toast(`刷新训练库失败：${error.message}`);
  } finally {
    setBusy(refreshButton, false);
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

function modelGroupAuditRecord(group) {
  const records = [group.task, ...(group.models || [])].filter(Boolean);
  return records.sort((a, b) => Number(b.created_at || 0) - Number(a.created_at || 0))[0] || {};
}

const MODEL_LIBRARY_TYPE_OPTIONS = [
  { value: "all", label: "全部类型", meta: "模型与任务" },
  { value: "trained", label: "训练模型", meta: "所有训练产物" },
  { value: "yolo_ocr", label: "YOLO + OCR", meta: "说明书分类" },
  { value: "yolo", label: "YOLO", meta: "目标检测" },
  { value: "ai_detection", label: "AI 检测任务", meta: "无训练模型" },
  { value: "other", label: "其他类型", meta: "历史模型" },
];

function aiDetectionLibraryTasks(resources) {
  const tasks = resources?.ai_detection_tasks || state.aiTasks || [];
  return tasks
    .filter((task) => task?.id)
    .sort((a, b) => Number(b.updated_at || b.created_at || 0) - Number(a.updated_at || a.created_at || 0));
}

function modelLibraryTypeForGroup(group) {
  const variants = new Set(group.models.map((model) => String(model.variant || "").toLowerCase()).filter(Boolean));
  if (variants.has("yolo_ocr")) return "yolo_ocr";
  if (variants.has("yolo")) return "yolo";
  return "other";
}

function modelLibraryFilterOptions(modelGroups, aiTasks) {
  const present = new Set(["all"]);
  if (modelGroups.length) present.add("trained");
  modelGroups.forEach((group) => present.add(modelLibraryTypeForGroup(group)));
  if (aiTasks.length) present.add("ai_detection");
  return MODEL_LIBRARY_TYPE_OPTIONS.filter((item) => present.has(item.value));
}

function renderModelLibraryTypeFilter(modelGroups, aiTasks) {
  const menu = $("modelLibraryTypeMenu");
  if (!menu) return;
  const options = modelLibraryFilterOptions(modelGroups, aiTasks);
  if (!options.some((item) => item.value === state.modelLibraryTaskTypeFilter)) {
    state.modelLibraryTaskTypeFilter = "all";
  }
  state.modelLibraryTaskTypeFilter = renderCustomMenu(
    "modelLibraryTypeMenu",
    options,
    state.modelLibraryTaskTypeFilter,
    (value) => {
      state.modelLibraryTaskTypeFilter = value || "all";
      renderTrainingLibrary(state.trainingResources);
    },
  ) || "all";
}

function modelGroupMatchesLibraryFilter(group) {
  const filter = state.modelLibraryTaskTypeFilter || "all";
  if (filter === "all") return true;
  if (filter === "trained") return true;
  return modelLibraryTypeForGroup(group) === filter;
}

function aiTaskMatchesLibraryFilter() {
  const filter = state.modelLibraryTaskTypeFilter || "all";
  return filter === "all" || filter === "ai_detection";
}

function aiTaskAccessoryText(task) {
  const labels = task.accessory_labels || {};
  const counts = task.required_accessory_counts || {};
  const ids = task.selected_accessory_ids || Object.keys(counts);
  const names = ids.map((itemId, index) => {
    const label = labels[itemId] || (task.accessory_names || [])[index] || itemId;
    const count = Math.max(1, Number(counts[itemId] || 1));
    return `${label}${count > 1 ? `×${count}` : ""}`;
  });
  return names.length ? names.join("、") : "配件信息缺失";
}

function renderTrainingLibrary(resources) {
  const datasets = resources?.datasets || [];
  const models = resources?.models || [];
  const tasks = resources?.training_tasks || resources?.tasks || [];
  const modelGroups = modelRunGroups(models, tasks);
  const aiTasks = aiDetectionLibraryTasks(resources);
  renderModelLibraryTypeFilter(modelGroups, aiTasks);
  const datasetList = $("datasetLibraryList");
  const modelList = $("modelLibraryList");
  if (datasetList) {
    datasetList.innerHTML = datasets.length ? "" : `<div class="job-empty">暂无样本库</div>`;
    for (const dataset of datasets) {
      const accessoryNames = (dataset.selected_accessory_ids || [])
        .map((accessoryId) => {
          const accessory = (state.accessories || []).find((item) => String(item.id) === String(accessoryId));
          return accessory ? zhLabel(accessory.name) : "";
        })
        .filter(Boolean);
      const row = document.createElement("article");
      row.className = "resource-card";
      row.innerHTML = `
        <div>
          <strong>${escapeHtml(dataset.display_name || dataset.id)}</strong>
          <span class="record-meta">${escapeHtml(recordAuditText(dataset))}</span>
          <span>${dataset.sample_count || 0} 个样本 · ${dataset.missing_files ? "文件缺失" : "已归档"}${accessoryNames.length ? ` · ${escapeHtml(accessoryNames.join("、"))}` : ""}</span>
          ${dataset.note ? `<span>${escapeHtml(dataset.note)}</span>` : ""}
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
    const visibleModelGroups = modelGroups.filter(modelGroupMatchesLibraryFilter);
    const visibleAiTasks = aiTaskMatchesLibraryFilter() ? aiTasks : [];
    modelList.innerHTML = visibleModelGroups.length || visibleAiTasks.length ? "" : `<div class="job-empty">当前类型暂无模型资源</div>`;
    for (const group of visibleModelGroups) {
      const task = group.task || {};
      const taskModels = group.models;
      const dataset = task.dataset;
      const missingCount = taskModels.filter((item) => !item.exists).length;
      const auditRecord = modelGroupAuditRecord(group);
      const row = document.createElement("article");
      row.className = "resource-card";
      row.innerHTML = `
        <div>
          <strong>${escapeHtml(modelRunLabel(group))}</strong>
          <span class="record-meta">${escapeHtml(recordAuditText(auditRecord))}</span>
          <span>${task.status ? STATUS_ZH[task.status] || task.status : "历史模型"} · ${task.sample_count || 0} 个样本</span>
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
    for (const task of visibleAiTasks) {
      const row = document.createElement("article");
      row.className = "resource-card ai-library-card";
      row.innerHTML = `
        <div>
          <strong>${escapeHtml(task.name || "AI 检测任务")}</strong>
          <span class="record-meta">${escapeHtml(recordAuditText(task, { includeUpdated: true }))}</span>
          <span>AI 检测任务 · ${task.accessory_count || task.selected_accessory_ids?.length || 0} 类配件</span>
          <span>配件：${escapeHtml(aiTaskAccessoryText(task))}</span>
          <span>模型 ID：${escapeHtml(task.model_id || `${AI_TASK_MODEL_PREFIX}${task.id}`)}</span>
        </div>
        <div class="resource-actions">
          <button type="button" data-open-ai-library-task="${escapeAttr(task.id)}">查看</button>
          <button type="button" class="danger-action compact-danger" data-delete-ai-library-task="${escapeAttr(task.id)}">删除</button>
        </div>
      `;
      row.querySelector("div").addEventListener("click", () => openTrainingResourceDetail("aiTask", task.id));
      modelList.appendChild(row);
    }
  }
  bindTrainingLibraryActions();
  setTrainingLibraryTab(state.trainingLibraryTab || "datasets");
  renderTrainingDatasetMenu();
}

function setTrainingLibraryTab(tab) {
  const active = tab === "models" ? "models" : "datasets";
  state.trainingLibraryTab = active;
  document.querySelectorAll("[data-training-library-tab]").forEach((button) => {
    const selected = button.dataset.trainingLibraryTab === active;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-selected", selected ? "true" : "false");
  });
  document.querySelectorAll("[data-training-library-pane]").forEach((pane) => {
    pane.classList.toggle("active", pane.dataset.trainingLibraryPane === active);
  });
}

function bindTrainingLibraryTabs() {
  document.querySelectorAll("[data-training-library-tab]").forEach((button) => {
    button.addEventListener("click", () => setTrainingLibraryTab(button.dataset.trainingLibraryTab || "datasets"));
  });
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
  document.querySelectorAll("[data-open-ai-library-task]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      openTrainingResourceDetail("aiTask", button.dataset.openAiLibraryTask);
    });
  });
  document.querySelectorAll("[data-delete-ai-library-task]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.stopPropagation();
      const taskId = button.dataset.deleteAiLibraryTask || "";
      if (!window.confirm(`确认删除 AI 检测任务 ${taskId}？`)) return;
      const result = await api(`/api/ai/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE" });
      state.aiTasks = result.tasks || [];
      state.selectedAiTaskId = result.selected_task_id || state.aiTasks[0]?.id || "";
      if (state.trainingResourceDetail?.kind === "aiTask" && state.trainingResourceDetail.id === taskId) {
        closeTrainingResourceModal();
      }
      await refreshTrainingLibrary();
      renderAiTasks();
      toast("AI 检测任务已删除。");
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

async function openTrainingResourceDetail(kind, id) {
  state.trainingResourceDetail = { kind, id };
  const title = $("trainingResourceTitle");
  const body = $("trainingResourceBody");
  $("trainingResourceModal").classList.add("visible");
  $("trainingResourceModal").setAttribute("aria-hidden", "false");
  if (kind === "dataset") {
    let dataset = (state.trainingResources?.datasets || []).find((item) => item.id === id);
    if (!dataset) return toast("样本库不存在。");
    title.textContent = dataset.display_name || dataset.id;
    if (!dataset.samples_loaded && !dataset.missing_files) {
      body.innerHTML = `<div class="job-empty">正在加载样本缩略图...</div>`;
      try {
        const detail = await api(`/api/training/resources/datasets/${encodeURIComponent(id)}/detail`);
        dataset = detail.dataset || dataset;
        const datasets = state.trainingResources?.datasets || [];
        const index = datasets.findIndex((item) => item.id === id);
        if (index >= 0) datasets[index] = dataset;
      } catch (error) {
        body.innerHTML = `<div class="job-empty">样本详情加载失败：${escapeHtml(error.message)}</div>`;
        return;
      }
    }
    const samples = dataset.samples || [];
    title.textContent = dataset.display_name || dataset.id;
    body.innerHTML = `
      <div class="summary-grid resource-summary">
        <div><label>样本数量</label><strong>${samples.length || dataset.sample_count || 0}</strong></div>
        <div><label>Dataset ID</label><strong>${escapeHtml(dataset.id)}</strong></div>
        <div><label>配件</label><strong>${escapeHtml((dataset.selected_accessory_ids || []).join(", ") || "-")}</strong></div>
        <div><label>创建记录</label><strong>${escapeHtml(recordAuditText(dataset))}</strong></div>
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
                <span>${escapeHtml(recordAuditText(sample, { owner: false }))}</span>
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
  } else if (kind === "aiTask") {
    const task = aiDetectionLibraryTasks(state.trainingResources).find((item) => item.id === id);
    if (!task) return toast("AI 检测任务不存在。");
    const counts = task.required_accessory_counts || {};
    const labels = task.accessory_labels || {};
    const ids = task.selected_accessory_ids || Object.keys(counts);
    title.textContent = task.name || "AI 检测任务";
    body.innerHTML = `
      <div class="summary-grid resource-summary">
        <div><label>任务类型</label><strong>AI 检测</strong></div>
        <div><label>配件数量</label><strong>${task.accessory_count || ids.length || 0}</strong></div>
        <div><label>来源</label><strong>${escapeHtml(task.source || "ai_detection_workbench")}</strong></div>
        <div><label>状态</label><strong>${(task.missing_accessory_ids || []).length ? "配件缺失" : "可用"}</strong></div>
      </div>
      <div class="resource-detail-list">
        <p><strong>Task ID</strong><span>${escapeHtml(task.id)}</span></p>
        <p><strong>创建记录</strong><span>${escapeHtml(recordAuditText(task, { includeUpdated: true }))}</span></p>
        <p><strong>Model ID</strong><span>${escapeHtml(task.model_id || `${AI_TASK_MODEL_PREFIX}${task.id}`)}</span></p>
        <p><strong>配件</strong><span>${escapeHtml(aiTaskAccessoryText(task))}</span></p>
        ${(task.missing_accessory_ids || []).length ? `<p><strong>缺失配件</strong><span>${escapeHtml(task.missing_accessory_ids.join(", "))}</span></p>` : ""}
        ${ids.map((itemId, index) => `
          <p>
            <strong>${escapeHtml(labels[itemId] || (task.accessory_names || [])[index] || itemId)}</strong>
            <span>Accessory ID: ${escapeHtml(itemId)} · 数量 ${Math.max(1, Number(counts[itemId] || 1))}</span>
          </p>
        `).join("")}
      </div>
    `;
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
        <div><label>创建记录</label><strong>${escapeHtml(recordAuditText(modelGroupAuditRecord(group || { task, models }), { includeUpdated: true }))}</strong></div>
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
    const openKind = group.open_kind || summary.open_kind || "candidate";
    const detail = group.jobs.map((job) => {
      const estimate = job.estimated_minutes ? ` · 预计 ${job.estimated_minutes} 分钟` : "";
      const sampleInfo = job.action === "generate_background_set"
        ? ` · ${job.generated_image_count || 0} 张背景`
        : job.sample_count ? ` · ${job.sample_count} 个样本` : "";
      const epochInfo = job.action === "train_model" ? ` · Epoch ${job.current_epoch || 0}/${job.total_epochs || job.epochs || "-"}` : "";
      return `${userJobLabel(job.label || job.pose_family)} · ${STATUS_ZH[job.status] || job.status}${sampleInfo}${epochInfo}${estimate}`;
    }).join("；");
    const activeJobs = group.jobs.filter((job) => isActiveImageJobStatus(job.status));
    const retryJobs = group.jobs.filter((job) => !isTrainingTask && !isActiveImageJobStatus(job.status) && job.status !== "completed");
    const row = document.createElement("div");
    row.className = "job-item";
    row.innerHTML = `
      <span>
        <strong>${escapeHtml(zhLabel(group.candidate_name || "Accessory"))}</strong>
        <em>${escapeHtml(statusText)} · ${isBackgroundTask ? `${summary.generated_image_count || 0} 张背景` : isTrainingTask ? `${summary.sample_count || 0} 个样本` : `${group.jobs.length} 张图`}</em>
        <em>${escapeHtml(recordAuditText(summary, { includeUpdated: true }))}</em>
        <small>${escapeHtml(detail)}</small>
      </span>
      <progress value="${summary.progress || 0}" max="100">${summary.progress || 0}%</progress>
      <div class="job-actions">
        ${isTrainingTask ? `<button type="button" data-view-training-task="${escapeAttr(summary.job_id)}" title="查看任务">详情</button>` : `<button type="button" data-open-job="${escapeAttr(group.candidate_id)}" data-open-kind="${escapeAttr(openKind)}">打开</button>`}
        ${retryJobs.map((job) => `<button type="button" data-retry-job="${escapeAttr(job.job_id || job.task_id)}" title="重试 ${escapeAttr(userJobLabel(job.label || job.pose_family || "生成任务"))}">重试</button>`).join("")}
        ${!isTrainingTask && activeJobs.length ? `<button type="button" data-stop-candidate="${escapeAttr(group.candidate_id)}">停止</button>` : ""}
        ${isTrainingTask ? `<button type="button" class="danger-action compact-danger" data-delete-training-task="${escapeAttr(summary.job_id)}" title="删除任务">删除</button>` : `<button type="button" class="danger-action compact-danger" data-delete-candidate="${escapeAttr(group.candidate_id)}">删除</button>`}
      </div>
    `;
    row.querySelector("span").addEventListener("click", () => {
      if (isTrainingTask) openTrainingTaskDetail(summary.job_id);
      else openImageJobCandidate(group.candidate_id, null, openKind);
    });
    list.appendChild(row);
  }
  bindImageJobActions();
}

async function openImageJobCandidate(candidateId, trigger = null, openKind = "candidate") {
  if (openKind === "accessory") {
    await openAccessoryDetail(candidateId, trigger);
    return;
  }
  setBusy(trigger, true);
  try {
    const result = await api(`/api/accessories/candidates/${encodeURIComponent(candidateId)}`);
    openAccessoryReview(result.candidate);
    await refreshImageJobs();
    updateOpenAccessoryCandidateFromJobs();
  } catch (error) {
    if (String(candidateId || "").startsWith("acc_")) {
      await openAccessoryDetail(candidateId, trigger);
    } else {
      toast(`打开任务失败：${error.message}`);
    }
  } finally {
    setBusy(trigger, false);
  }
}

async function openTrainingTaskDetail(jobId, trigger = null) {
  setBusy(trigger, true);
  try {
    await refreshTrainingLibrary();
    openTrainingResourceDetail("task", jobId);
  } catch (error) {
    toast(`打开任务失败：${error.message}`);
  } finally {
    setBusy(trigger, false);
  }
}

function bindImageJobActions() {
  document.querySelectorAll("[data-open-job]").forEach((button) => {
    button.addEventListener("click", () => openImageJobCandidate(button.dataset.openJob, button, button.dataset.openKind || "candidate"));
  });
  document.querySelectorAll("[data-view-training-task]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      openTrainingTaskDetail(button.dataset.viewTrainingTask, button);
    });
  });
  document.querySelectorAll("[data-delete-training-task]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.stopPropagation();
      if (!window.confirm(`确认删除任务 ${button.dataset.deleteTrainingTask}？`)) return;
      setBusy(button, true);
      try {
        await api(`/api/training/tasks/${encodeURIComponent(button.dataset.deleteTrainingTask)}`, { method: "DELETE" });
        await refreshImageJobs();
        toast("任务已删除。");
      } finally {
        setBusy(button, false);
      }
    });
  });
  document.querySelectorAll("[data-stop-candidate]").forEach((button) => {
    button.addEventListener("click", async () => {
      setBusy(button, true);
      try {
        await api(`/api/image-job-candidates/${encodeURIComponent(button.dataset.stopCandidate)}/stop`, { method: "POST" });
        await refreshImageJobs();
        toast("任务已停止。");
      } finally {
        setBusy(button, false);
      }
    });
  });
  document.querySelectorAll("[data-delete-candidate]").forEach((button) => {
    button.addEventListener("click", async () => {
      setBusy(button, true);
      try {
        await api(`/api/image-job-candidates/${encodeURIComponent(button.dataset.deleteCandidate)}`, { method: "DELETE" });
        await refreshImageJobs();
        toast("任务已删除。");
      } finally {
        setBusy(button, false);
      }
    });
  });
  document.querySelectorAll("[data-retry-job]").forEach((button) => {
    button.addEventListener("click", async () => {
      setBusy(button, true);
      try {
        await api(`/api/image-jobs/${encodeURIComponent(button.dataset.retryJob)}/retry`, { method: "POST" });
        await refreshImageJobs();
        toast("任务已重新排队。");
      } finally {
        setBusy(button, false);
      }
    });
  });
  document.querySelectorAll("[data-stop-job]").forEach((button) => {
    button.addEventListener("click", async () => {
      setBusy(button, true);
      try {
        await api(`/api/image-jobs/${encodeURIComponent(button.dataset.stopJob)}/stop`, { method: "POST" });
        await refreshImageJobs();
        toast("任务已停止。");
      } finally {
        setBusy(button, false);
      }
    });
  });
  document.querySelectorAll("[data-delete-job]").forEach((button) => {
    button.addEventListener("click", async () => {
      setBusy(button, true);
      try {
        await api(`/api/image-jobs/${encodeURIComponent(button.dataset.deleteJob)}`, { method: "DELETE" });
        await refreshImageJobs();
        toast("任务已删除。");
      } finally {
        setBusy(button, false);
      }
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
        job_store: job.job_store || "candidate",
        open_kind: job.open_kind || "candidate",
        jobs: [],
        created_at: job.created_at || 0,
      });
    }
    const group = groups.get(candidateId);
    group.jobs.push(job);
    group.created_at = Math.max(group.created_at || 0, job.created_at || 0);
    if (job.open_kind === "accessory" || job.job_store === "config") {
      group.open_kind = "accessory";
      group.job_store = "config";
    }
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

function fileLooksLikeImage(file) {
  return file.type.startsWith("image/") || /\.(png|jpe?g|webp|bmp)$/i.test(file.name || "");
}

function validateTextAccessoryFileBatch(files, existingCount = 0) {
  const list = Array.from(files || []);
  if (!list.every(fileLooksLikeImage)) {
    toast("文字类配件只能上传图片，不能上传视频或其它文件。");
    return false;
  }
  if (existingCount + list.length > TEXT_ACCESSORY_MAX_IMAGES) {
    toast(`文字类配件最多上传 ${TEXT_ACCESSORY_MAX_IMAGES} 张图片。`);
    return false;
  }
  return true;
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
        <em>${escapeHtml(recordAuditText(item))}</em>
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
  ["dataAnalysisDetailModal", closeDataAnalysisDetailModal],
  ["locateDiagnosticModal", closeLocateDiagnosticModal],
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
      const scope = tab.closest(".view") || document;
      scope.querySelectorAll(".mode-tab[data-tab]").forEach((x) => x.classList.remove("active"));
      scope.querySelectorAll(".tabpane").forEach((x) => x.classList.remove("active"));
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

function bindAiTabs() {
  document.querySelectorAll(".mode-tab[data-ai-tab]").forEach((tab) => {
    tab.addEventListener("click", () => {
      if (tab.classList.contains("active")) return;
      const nextPane = $(`ai${tab.dataset.aiTab[0].toUpperCase()}${tab.dataset.aiTab.slice(1)}Tab`);
      if (!nextPane) return;
      document.querySelectorAll(".mode-tab[data-ai-tab]").forEach((x) => x.classList.remove("active"));
      document.querySelectorAll("[data-ai-pane]").forEach((x) => x.classList.remove("active"));
      tab.classList.add("active");
      nextPane.classList.add("active");
      if (tab.dataset.aiTab === "camera") {
        setAiInspectInput("camera");
        startAiCamera();
      } else {
        stopAiCameraStream();
      }
    });
  });
}

function bindLabelSheetTabs() {
  document.querySelectorAll(".mode-tab[data-label-tab]").forEach((tab) => {
    tab.addEventListener("click", () => {
      if (tab.classList.contains("active")) return;
      const nextPane = $(`labelSheet${tab.dataset.labelTab[0].toUpperCase()}${tab.dataset.labelTab.slice(1)}Tab`);
      if (!nextPane) return;
      document.querySelectorAll(".mode-tab[data-label-tab]").forEach((x) => x.classList.remove("active"));
      document.querySelectorAll("[data-label-pane]").forEach((x) => x.classList.remove("active"));
      tab.classList.add("active");
      nextPane.classList.add("active");
      if (tab.dataset.labelTab === "camera") {
        setLabelSheetInput("camera");
        startLabelSheetCamera();
      } else {
        stopLabelSheetCameraStream();
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
      if (item.dataset.view !== "aiInspect") stopAiCameraStream();
      if (item.dataset.view !== "labelSheet") stopLabelSheetCameraStream();
      if (item.dataset.view !== "locateAnything") stopLocateCameraStream();
      if (item.dataset.view === "locateAnything") onLocateViewEntry();
      if (item.dataset.view === "dataAnalysis") refreshDataAnalysisRecords({ quiet: true });
    });
  });
  document.querySelectorAll("[data-go]").forEach((trigger) => {
    trigger.addEventListener("click", () => {
      const target = document.querySelector(`.nav-item[data-view="${trigger.dataset.go}"]`);
      target?.click();
    });
  });
}

function bindActions() {
  bindModalDismissal();
  bindAiTabs();
  bindLabelSheetTabs();
  bindTrainingLibraryTabs();
  $("accessoryMaterialType").addEventListener("change", renderAccessoryProcess);
  $("paperPreset").addEventListener("change", updatePaperDimensionLock);
  $("openAccessoryPicker").addEventListener("click", () => {
    $("accessoryPicker").classList.toggle("visible");
  });
  $("closePreviewModal").addEventListener("click", closePreviewModal);
  $("cancelPreviewModal").addEventListener("click", closePreviewModal);
  $("closeImageViewer").addEventListener("click", closeImageViewer);
  $("openAiDebug")?.addEventListener("click", () => openAiDebugModal());
  $("openAiInspectDebug")?.addEventListener("click", () => openAiDebugModal(state.aiLastResult));
  $("closeAiDebug")?.addEventListener("click", closeAiDebugModal);
  $("closeDataAnalysisDetail")?.addEventListener("click", closeDataAnalysisDetailModal);
  $("openLocateDiagnostic")?.addEventListener("click", openLocateDiagnosticModal);
  $("closeLocateDiagnostic")?.addEventListener("click", closeLocateDiagnosticModal);
  $("refreshDataAnalysis")?.addEventListener("click", () => refreshDataAnalysisRecords());
  $("dataAnalysisTaskFilter")?.addEventListener("change", (event) => {
    state.dataAnalysis.selectedTaskId = event.currentTarget.value;
    state.dataAnalysis.selectedRecordIds.clear();
    refreshDataAnalysisRecords();
  });
  $("dataAnalysisSelectAll")?.addEventListener("change", (event) => {
    const checked = event.currentTarget.checked;
    state.dataAnalysis.records.forEach((record) => {
      if (checked) state.dataAnalysis.selectedRecordIds.add(record.record_id);
      else state.dataAnalysis.selectedRecordIds.delete(record.record_id);
    });
    renderDataAnalysisRecords();
  });
  $("runDataAnalysisSelected")?.addEventListener("click", (event) => runDataAnalysisLocate(selectedDataAnalysisRecords().map((record) => record.record_id), event.currentTarget));
  $("runDataAnalysisVisible")?.addEventListener("click", (event) => runDataAnalysisLocate(state.dataAnalysis.records.map((record) => record.record_id), event.currentTarget));
  $("toggleInspectFullscreen").addEventListener("click", () => openInspectFullscreen("inspect"));
  $("toggleAiFullscreen")?.addEventListener("click", () => openInspectFullscreen("ai"));
  $("toggleLocateFullscreen")?.addEventListener("click", () => openInspectFullscreen("locate"));
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
      const fromPipeline = state.accessoryCandidate?.pipeline_context === "pipeline";
      const result = await api(`/api/accessories/confirm/${encodeURIComponent(state.accessoryCandidate.id)}`, { method: "POST" });
      finishTaskProgress("imageWorker", true);
      renderAccessories(result.items);
      if (fromPipeline) applyPipelineAccessoryPayload(result.pipeline);
      closeAccessoryReview();
      $("accessoryName").value = "";
      clearAccessoryFileQueue();
      $("objectLengthMm").value = "";
      $("objectWidthMm").value = "";
      $("objectHeightMm").value = "";
      $("objectAlphaPolicy").value = "";
      if (fromPipeline) resetPipelineAccessoryForm();
      await refreshImageJobs();
      await refreshPipeline();
      toast(fromPipeline ? "配件已确认并加入当前流水线。" : "配件已确认添加。");
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
  $("refreshTrainingLibrary")?.addEventListener("click", () => refreshTrainingLibrary({ manual: true }));
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
  $("aiImageFile")?.addEventListener("change", () => {
    const file = $("aiImageFile").files[0];
    if (file) setAiInspectInput("image", file);
  });
  $("aiVideoFile")?.addEventListener("change", () => {
    const file = $("aiVideoFile").files[0];
    if (file) setAiInspectInput("video", file);
  });
  $("labelSheetImageFile")?.addEventListener("change", () => {
    const file = $("labelSheetImageFile").files[0];
    if (file) setLabelSheetInput("image", file);
  });
  $("locateImageFile")?.addEventListener("change", () => {
    const file = $("locateImageFile").files[0];
    if (file) setLocateInput("image", file);
  });
  $("runAiImage")?.addEventListener("click", () => runAiImageDetection($("runAiImage")));
  $("runAiVideo")?.addEventListener("click", () => runAiVideoDetection($("runAiVideo")));
  $("addLabelReference")?.addEventListener("click", () => addLabelSheetReference($("addLabelReference")));
  $("refreshLabelReferences")?.addEventListener("click", async () => {
    const button = $("refreshLabelReferences");
    setBusy(button, true);
    try {
      await refreshLabelSheetReferences();
      toast("标签参考已刷新。");
    } catch (error) {
      toast(`刷新标签参考失败：${error.message}`);
    } finally {
      setBusy(button, false);
    }
  });
  $("runLabelSheetMatch")?.addEventListener("click", () => runLabelSheetMatchWithFile($("labelSheetImageFile").files[0], $("runLabelSheetMatch")));
  $("startLocateRuntime")?.addEventListener("click", () => startLocateRuntime($("startLocateRuntime")));
  $("saveLocateConfig")?.addEventListener("click", () => saveLocateConfig($("saveLocateConfig")));
  $("checkLocateStatus")?.addEventListener("click", () => checkLocateStatus($("checkLocateStatus")));
  $("runLocateImage")?.addEventListener("click", () => runLocateImage($("runLocateImage")));
  $("addLocateRecipeItem")?.addEventListener("click", () => {
    state.locateRecipePickerOpen = !state.locateRecipePickerOpen;
    if (state.locateRecipePickerOpen) state.locateRecipeExpanded = true;
    renderLocateSources();
    $("locateRecipeSearch")?.focus();
  });
  $("toggleLocateRecipeDetails")?.addEventListener("click", () => {
    setLocateRecipeExpanded(!state.locateRecipeExpanded);
    renderLocateSources();
  });
  $("locateRecipeSearch")?.addEventListener("input", (event) => {
    state.locateRecipeQuery = event.currentTarget.value;
    renderLocateRecipePicker();
  });
  $("refreshLocateCameras")?.addEventListener("click", async () => {
    const button = $("refreshLocateCameras");
    setBusy(button, true);
    try {
      if (!state.locateCamera.stream) {
        await startLocateCamera();
      } else {
        await refreshLocateCameraDevices();
      }
    } finally {
      setBusy(button, false);
    }
  });
  $("captureLocateFrame")?.addEventListener("click", () => runLocateCameraOnce($("captureLocateFrame")));
  $("startLocateCameraLoop")?.addEventListener("click", () => startLocateCameraLoop($("startLocateCameraLoop")));
  $("stopLocateCameraLoop")?.addEventListener("click", stopLocateCameraLoop);
  $("refreshAiCameras")?.addEventListener("click", async () => {
    const button = $("refreshAiCameras");
    setBusy(button, true);
    try {
      if (!state.aiCamera.stream) {
        await startAiCamera();
      } else {
        const devices = await refreshAiCameraDevices();
        setAiCameraStatus(devices.length ? `检测到 ${devices.length} 个摄像头。` : "未检测到摄像头。", !devices.length);
      }
    } finally {
      setBusy(button, false);
    }
  });
  $("captureAiCamera")?.addEventListener("click", () => runAiCameraDetection($("captureAiCamera")));
  $("refreshLabelSheetCameras")?.addEventListener("click", async () => {
    const button = $("refreshLabelSheetCameras");
    setBusy(button, true);
    try {
      if (!state.labelSheetCamera.stream) {
        await startLabelSheetCamera();
      } else {
        const devices = await refreshLabelSheetCameraDevices();
        setLabelSheetCameraStatus(devices.length ? `检测到 ${devices.length} 个摄像头。` : "未检测到摄像头。", !devices.length);
      }
    } finally {
      setBusy(button, false);
    }
  });
  $("captureLabelSheetCamera")?.addEventListener("click", () => runLabelSheetCameraMatch($("captureLabelSheetCamera")));

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
      if (result.model?.is_ai_detection) refreshDataAnalysisRecords({ quiet: true }).catch(() => {});
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
      if (result.ai || result.frames?.some((frame) => frame.model?.is_ai_detection)) refreshDataAnalysisRecords({ quiet: true }).catch(() => {});
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
  $("fullscreenCaptureCamera").addEventListener("click", () => runFullscreenCapture($("fullscreenCaptureCamera")));

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
      if (materialType === "text" && !validateTextAccessoryFileBatch(pendingFiles)) return;
      const uploadFiles = materialType === "text" ? await prepareTextAccessoryFiles(pendingFiles) : pendingFiles;
      for (const file of uploadFiles) form.append("files", file);
      const result = await api("/api/accessories", { method: "POST", body: form });
      renderAccessories(result.items || [result.item].filter(Boolean));
      $("accessoryName").value = "";
      clearAccessoryFileQueue();
      $("objectLengthMm").value = "";
      $("objectWidthMm").value = "";
      $("objectHeightMm").value = "";
      $("objectAlphaPolicy").value = "";
      await refreshTrainingPlan();
      toast("配件已添加。");
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
  renderAiCameraMenu();
  renderLabelSheetCameraMenu();
  renderLocateCameraMenu();
  showTrainingFlowTab("samples");
}

bindViews();
bindTabs();
bindActions();
bindAuth();
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
window.addEventListener("beforeunload", () => {
  stopCameraStream();
  stopAiCameraStream();
  stopLabelSheetCameraStream();
  stopLocateCameraStream();
});

function hasCookieConsent() {
  return document.cookie
    .split(";")
    .map((item) => item.trim())
    .some((item) => item === "vantaline_cookie_consent=accepted");
}

function acceptCookieConsent() {
  document.cookie = "vantaline_cookie_consent=accepted; Max-Age=31536000; Path=/; SameSite=Lax";
  $("cookieConsent")?.setAttribute("hidden", "");
}

function initCookieConsent() {
  const banner = $("cookieConsent");
  if (!banner) return;
  if (hasCookieConsent()) {
    banner.setAttribute("hidden", "");
  } else {
    banner.removeAttribute("hidden");
  }
  $("acceptCookies")?.addEventListener("click", acceptCookieConsent);
}

initCookieConsent();
renderAccessoryProcess();
renderAccessoryFileQueue();
initAuth().catch((error) => showAuthLogin(`启动失败：${error.message}`));

// ============================================================
// 训练流水线看板(Agent 编排)
// ============================================================

const PIPELINE_ROUTE_META = {
  yolo: { label: "YOLO 训练", cls: "route-yolo" },
  ai: { label: "AI 检测", cls: "route-ai" },
  locate: { label: "Locate Anything", cls: "route-locate" },
  archive_only: { label: "仅建档", cls: "route-archive" },
};

const PIPELINE_METHOD_META = {
  yolo_ocr: { label: "YOLO+OCR", usesTraining: true },
  yolo: { label: "YOLO", usesTraining: true },
  ai: { label: "AI 检测", usesTraining: false },
  locate: { label: "Locate Anything", usesTraining: false },
};

const PIPELINE_STAGE_LANES = {
  draft: "pipelineDraftList",
  samples: "pipelineSamplesList",
  training: "pipelineTrainingList",
};

const PIPELINE_NEXT_STAGE = { draft: "samples", samples: "training", training: "library" };
const AGENT_BASE_URL_PRESETS = [
  { label: "Cursor", value: "https://api.cursor.com" },
  { label: "OpenAI", value: "https://api.openai.com/v1" },
  { label: "OpenRouter", value: "https://openrouter.ai/api/v1" },
  { label: "Gemini OpenAI 兼容", value: "https://generativelanguage.googleapis.com/v1beta/openai" },
];

const AGENT_PROVIDER_META = {
  openai_compatible: {
    label: "OpenAI 兼容",
    base_placeholder: "https://api.openai.com/v1",
    model_placeholder: "例如 gpt-4o-mini",
    hint: "当前会按 OpenAI 兼容接口测试 /chat/completions；OpenAI、OpenRouter、Gemini OpenAI 兼容入口都走这里。",
  },
  cursor: {
    label: "Cursor",
    base_placeholder: "https://api.cursor.com",
    model_placeholder: "auto 或 Cursor 模型 ID",
    hint: "检测到 Cursor API；测试连接会调用 /v1/models，不会调用 /chat/completions。",
  },
};

const PIPELINE_STATUS_ZH = {
  ready: "待开始",
  running: "执行中",
  completed: "已完成",
  failed: "失败",
  stopped: "已停止",
};

state.pipeline = { tasks: [], agent: null, accessories: [], pendingCandidates: [] };
state.pipelineParamsTarget = null;
state.pipelineDetailTaskId = "";
state.pipelinePollTimer = null;
state.pipelineAccessoryPendingFiles = [];
state.pipelineAccessoryPendingFileUrls = new Map();

function pipelineModalOpen(id) {
  $(id)?.classList.add("visible");
  $(id)?.setAttribute("aria-hidden", "false");
}

function pipelineModalClose(id) {
  $(id)?.classList.remove("visible");
  $(id)?.setAttribute("aria-hidden", "true");
}

async function refreshPipeline() {
  try {
    if (!state.accessories?.length) {
      // 首次渲染可能早于 loadInitial 完成,补拉配件列表。
      const accessories = await api(withAuthScope("/api/accessories"));
      renderAccessories(accessories.items);
    }
    const result = await api(withAuthScope("/api/pipeline/tasks"));
    state.pipeline.tasks = result.items || [];
    state.pipeline.agent = result.agent || null;
    state.pipeline.accessories = result.accessories || [];
    state.pipeline.pendingCandidates = result.pending_candidates || [];
    renderPipeline();
  } catch {
    // 轮询失败保持安静,下一轮重试。
  }
}

function renderPipeline() {
  renderPipelineAgentPill();
  renderPipelineAccessories();
  renderPipelineTasks();
}

function applyPipelineAccessoryPayload(payload) {
  if (!payload) return false;
  state.pipeline.accessories = payload.accessories || [];
  state.pipeline.pendingCandidates = payload.pending_candidates || [];
  renderPipelineAccessories();
  renderPipelineAddLibrary();
  return true;
}

function renderPipelineAgentPill() {
  const pill = $("pipelineAgentMode");
  if (!pill) return;
  const agent = state.pipeline.agent;
  const isAgent = agent?.mode === "agent";
  pill.textContent = isAgent ? "Agent 推荐" : "规则推荐";
  pill.className = `pill ${isAgent ? "ok" : "neutral"}`;
}

function normalizePipelineMethod(value) {
  const method = String(value || "").trim().toLowerCase();
  if (["ai_detection", "ai_inspect", "gemini"].includes(method)) return "ai";
  if (["locate_anything", "locateanything", "open_vocab"].includes(method)) return "locate";
  return PIPELINE_METHOD_META[method] ? method : "yolo_ocr";
}

function pipelineTaskMethod(task) {
  const params = task?.params || {};
  return normalizePipelineMethod(task?.detection_method || params.train_mode || params.route);
}

function pipelineMethodMeta(method) {
  return PIPELINE_METHOD_META[normalizePipelineMethod(method)] || PIPELINE_METHOD_META.yolo_ocr;
}

function pipelineTaskById(taskId) {
  return (state.pipeline.tasks || []).find((item) => item.id === taskId) || null;
}

function pipelineTaskUsesTraining(task) {
  if (task?.uses_training_flow !== undefined) return task.uses_training_flow !== false;
  return Boolean(pipelineMethodMeta(pipelineTaskMethod(task)).usesTraining);
}

function pipelineAssignedAccessoryIds() {
  const ids = new Set();
  for (const task of state.pipeline.tasks || []) {
    if (task.stage === "library") continue;
    for (const itemId of task.accessory_ids || []) ids.add(String(itemId));
  }
  return ids;
}

function pipelineTaskAccessoryCount(task, accessoryId) {
  const counts = task?.accessory_counts || {};
  return Math.max(1, Math.min(99, Number(counts[accessoryId] || 1)));
}

function pipelineTaskTypePill(task) {
  const method = pipelineTaskMethod(task);
  const methodMeta = pipelineMethodMeta(method);
  const hasAccessories = Boolean((task.accessory_ids || []).length);
  const ready = method === "ai" && hasAccessories;
  const text = method === "ai"
    ? `AI Type · ${ready ? "Ready" : "待配件"}`
    : `Type · ${methodMeta.label}`;
  return `<span class="pipeline-type-pill ${ready ? "ready" : ""}">${escapeHtml(text)}</span>`;
}

function normalizeAgentBaseUrl(value) {
  return String(value || "").trim().replace(/\/+$/, "");
}

function agentProviderFromBaseUrl(baseUrl) {
  try {
    const url = new URL(normalizeAgentBaseUrl(baseUrl));
    return url.hostname.toLowerCase() === "api.cursor.com" ? "cursor" : "openai_compatible";
  } catch {
    return "openai_compatible";
  }
}

function syncAgentBaseUrlPreset() {
  const preset = $("agentBaseUrlPreset");
  if (!preset) return;
  const current = normalizeAgentBaseUrl($("agentBaseUrl")?.value);
  const match = AGENT_BASE_URL_PRESETS.find((item) => item.value === current);
  preset.value = match?.value || "";
}

function currentAgentBaseUrl() {
  const presetValue = $("agentBaseUrlPreset")?.value || "";
  return normalizeAgentBaseUrl(presetValue || $("agentBaseUrl")?.value || "");
}

function syncAgentEndpointUi(options = {}) {
  const baseUrlInput = $("agentBaseUrl");
  const modelInput = $("agentModel");
  const presetValue = $("agentBaseUrlPreset")?.value || "";
  if (baseUrlInput) {
    if (presetValue) {
      baseUrlInput.value = presetValue;
      baseUrlInput.disabled = true;
    } else {
      baseUrlInput.disabled = false;
    }
  }
  const provider = agentProviderFromBaseUrl(currentAgentBaseUrl());
  const meta = AGENT_PROVIDER_META[provider] || AGENT_PROVIDER_META.openai_compatible;
  if (baseUrlInput) baseUrlInput.placeholder = meta.base_placeholder;
  if (modelInput) {
    modelInput.placeholder = meta.model_placeholder;
    if (options.applyModelDefault && provider === "cursor" && !modelInput.value.trim()) {
      modelInput.value = "auto";
    }
  }
  syncAgentBaseUrlPreset();
  if ($("agentProviderHint")) $("agentProviderHint").textContent = `${meta.label}: ${meta.hint}`;
}

function normalizeAgentModelOptions(options) {
  const seen = new Set();
  const result = [];
  for (const item of Array.isArray(options) ? options : []) {
    const id = String(item?.id || item?.value || item || "").trim();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    result.push({ id, label: String(item?.label || item?.name || id).trim() || id });
  }
  return result;
}

function renderAgentModelOptions(config = {}) {
  const options = normalizeAgentModelOptions(config.model_options || []);
  const select = $("agentModel");
  if (select) {
    const current = String(config.model || select.value || "").trim();
    select.innerHTML = "";
    if (options.length) {
      for (const option of options) {
        const node = document.createElement("option");
        node.value = option.id;
        node.textContent = option.id;
        node.title = option.label;
        select.appendChild(node);
      }
      const selected = options.some((option) => option.id === current) ? current : options[0].id;
      select.value = selected;
      select.disabled = false;
    } else {
      const node = document.createElement("option");
      node.value = "";
      node.textContent = "先测试连接生成模型列表";
      select.appendChild(node);
      select.value = "";
      select.disabled = true;
    }
  }
  const hint = $("agentModelHint");
  if (hint) {
    hint.textContent = options.length
      ? `已获取 ${options.length} 个可用模型，点击 Model 可选择。`
      : "测试连接后自动生成可用模型列表。";
  }
}

function applyAgentBaseUrlPreset(value) {
  if (value && $("agentBaseUrl")) {
    $("agentBaseUrl").value = value;
  }
  syncAgentEndpointUi({ applyModelDefault: true });
  renderAgentModelOptions({ model_options: [] });
}

function agentConnectionLabel(config) {
  if (!config?.configured) return "未配置";
  const providerLabel = config.provider_label || AGENT_PROVIDER_META[config.provider]?.label || "Agent";
  if (config.connection_status === "connected") return `${providerLabel} 已连接`;
  if (config.connection_status === "failed") return "测试失败";
  return "已配置，未测试";
}

function agentConnectionClass(config) {
  if (config?.configured && config.connection_status === "connected") return "ok";
  if (config?.configured && config.connection_status === "failed") return "fail";
  return "neutral";
}

function renderPipelineAccessories() {
  const list = $("pipelineAccessoryList");
  if (!list) return;
  list.innerHTML = "";
  const candidates = state.pipeline.pendingCandidates || [];
  for (const candidate of candidates) {
    const failed = candidate.status === "failed";
    const ready = candidate.status === "ready";
    const running = candidate.status === "running";
    const dotClass = failed ? "failed" : ready ? "ready" : "pending";
    const rawProgress = Number(candidate.progress);
    const progressValue = Math.max(2, Math.min(100, Number.isFinite(rawProgress) ? rawProgress : 0));
    const showProgress = Number.isFinite(rawProgress) && (ready || failed || running || progressValue > 2);
    const card = document.createElement("article");
    card.className = `pipeline-card accessory-card ${ready ? "ready candidate-ready" : "pending"}${failed ? " failed" : ""}`;
    card.innerHTML = `
      <div class="pipeline-card-head">
        <strong>${escapeHtml(zhLabel(candidate.name || "新配件"))}</strong>
        <span class="pipeline-state-dot ${dotClass}" title="${escapeAttr(candidate.status_text || "待确认")}"></span>
      </div>
      <p class="pipeline-card-meta">${escapeHtml(candidate.status_text || STATUS_ZH[candidate.status] || candidate.status || "待确认")} · ${escapeHtml(recordAuditText(candidate))}</p>
      ${showProgress ? `<div class="pipeline-progress"><div class="pipeline-progress-bar" style="width:${progressValue}%"></div></div>` : ""}
      <div class="pipeline-card-actions">
        <button type="button" class="mini-secondary" data-pipeline-open-candidate="${escapeAttr(candidate.id || "")}">${ready ? "确认" : "查看"}</button>
      </div>
    `;
    list.appendChild(card);
  }
  const assignedAccessoryIds = pipelineAssignedAccessoryIds();
  const visibleAccessories = (state.pipeline.accessories || []).filter((item) => !assignedAccessoryIds.has(String(item.id)));
  for (const item of visibleAccessories) {
    const ready = pipelineAccessoryReady(item);
    const card = document.createElement("article");
    card.className = `pipeline-card accessory-card ${ready ? "ready" : "pending"}`;
    if (ready) {
      card.draggable = true;
      card.addEventListener("dragstart", (event) => {
        event.dataTransfer.setData("text/plain", `acc:${item.id}`);
        event.dataTransfer.effectAllowed = "copyMove";
        card.classList.add("dragging");
      });
      card.addEventListener("dragend", () => card.classList.remove("dragging"));
    }
    card.innerHTML = `
      <div class="pipeline-card-head">
        <strong>${escapeHtml(zhLabel(item.name))}</strong>
        <span class="pipeline-state-dot ${ready ? "ready" : "pending"}" title="${ready ? "可使用" : "等待中"}"></span>
      </div>
      <p class="pipeline-card-meta">${(item.source_files || []).length} 份素材 · ${ready ? "已上传" : "等待中"} · ${escapeHtml(recordAuditText(item))}</p>
      <div class="pipeline-card-actions">
        <button type="button" class="mini-secondary" data-view-accessory="${escapeAttr(item.id)}">查看</button>
        <button type="button" class="danger-action compact-danger" data-pipeline-remove-accessory="${escapeAttr(item.id)}">移除</button>
      </div>
    `;
    list.appendChild(card);
  }
  if (!list.children.length) {
    list.innerHTML = assignedAccessoryIds.size
      ? `<div class="lane-empty">当前配件都已分配到任务。</div>`
      : `<div class="lane-empty">当前流水线还没有配件。</div>`;
  }
  list.querySelectorAll("[data-pipeline-open-candidate]").forEach((button) => {
    button.addEventListener("click", () => openImageJobCandidate(button.dataset.pipelineOpenCandidate));
  });
  list.querySelectorAll("[data-view-accessory]").forEach((button) => {
    button.addEventListener("click", () => openAccessoryDetail(button.dataset.viewAccessory));
  });
  list.querySelectorAll("[data-pipeline-remove-accessory]").forEach((button) => {
    button.addEventListener("click", () => removePipelineAccessory(button.dataset.pipelineRemoveAccessory, button));
  });
}

function pipelineAccessoryReady(item) {
  const status = String(item?.status || "active").trim().toLowerCase();
  return !["queued", "running", "pending", "candidate_review", "building", "generating", "failed", "error"].includes(status);
}

function pipelineAccessoryById(accessoryId) {
  return (state.pipeline.accessories || []).find((item) => item.id === accessoryId);
}

async function removePipelineAccessory(accessoryId, button = null) {
  if (!accessoryId) return;
  if (button) setBusy(button, true);
  try {
    const result = await api(`/api/pipeline/accessories/${encodeURIComponent(accessoryId)}`, { method: "DELETE" });
    applyPipelineAccessoryPayload(result);
    toast("已从当前流水线移除,配件库仍保留。");
  } catch (error) {
    toast(`移除失败:${error.message}`);
  } finally {
    if (button) setBusy(button, false);
  }
}

function renderPipelineAddLibrary() {
  const list = $("pipelineLibraryAccessoryList");
  if (!list) return;
  const currentIds = new Set((state.pipeline.accessories || []).map((item) => item.id));
  const items = state.accessories || [];
  list.innerHTML = "";
  if (!items.length) {
    list.innerHTML = `<div class="lane-empty">配件库暂无可用配件。</div>`;
    return;
  }
  for (const item of items) {
    const row = document.createElement("div");
    const inFlow = currentIds.has(item.id);
    row.className = "pipeline-library-accessory-row";
    row.innerHTML = `
      <div>
        <strong>${escapeHtml(zhLabel(item.name))}</strong>
        <span>${escapeHtml(item.material_type === "text" ? "文字类" : "物品类")} · ${escapeHtml(STATUS_ZH[item.status] || item.status || "active")}</span>
        <span>${escapeHtml(recordAuditText(item))}</span>
      </div>
      <button type="button" class="mini-secondary" data-pipeline-add-existing="${escapeAttr(item.id)}" ${inFlow ? "disabled" : ""}>${inFlow ? "已加入" : "加入"}</button>
    `;
    list.appendChild(row);
  }
  list.querySelectorAll("[data-pipeline-add-existing]").forEach((button) => {
    button.addEventListener("click", () => addExistingPipelineAccessory(button.dataset.pipelineAddExisting, button));
  });
}

async function openPipelineAccessoryModal() {
  try {
    const accessories = await api(withAuthScope("/api/accessories"));
    renderAccessories(accessories.items);
  } catch {
    // 保留现有列表,弹窗仍可用于新建配件。
  }
  updatePipelineMaterialFields();
  renderPipelineAccessoryFileQueue();
  renderPipelineAddLibrary();
  pipelineModalOpen("pipelineAccessoryModal");
}

function closePipelineAccessoryModal() {
  pipelineModalClose("pipelineAccessoryModal");
}

async function addExistingPipelineAccessory(accessoryId, button) {
  if (!accessoryId) return;
  setBusy(button, true);
  try {
    const result = await api(`/api/pipeline/accessories/${encodeURIComponent(accessoryId)}`, { method: "POST" });
    applyPipelineAccessoryPayload(result);
    toast("配件已加入当前流水线。");
  } catch (error) {
    toast(`加入失败:${error.message}`);
  } finally {
    setBusy(button, false);
  }
}

function clearPipelineAccessoryFileQueue() {
  for (const url of state.pipelineAccessoryPendingFileUrls.values()) URL.revokeObjectURL(url);
  state.pipelineAccessoryPendingFileUrls.clear();
  state.pipelineAccessoryPendingFiles = [];
  if ($("pipelineAccessoryFiles")) $("pipelineAccessoryFiles").value = "";
  renderPipelineAccessoryFileQueue();
}

function addPipelineAccessoryPendingFiles(fileList) {
  const existing = new Set(state.pipelineAccessoryPendingFiles.map(accessoryFileKey));
  for (const file of Array.from(fileList || [])) {
    const key = accessoryFileKey(file);
    if (existing.has(key)) continue;
    state.pipelineAccessoryPendingFiles.push(file);
    existing.add(key);
  }
  if ($("pipelineAccessoryFiles")) $("pipelineAccessoryFiles").value = "";
  renderPipelineAccessoryFileQueue();
}

function removePipelineAccessoryPendingFile(index) {
  const file = state.pipelineAccessoryPendingFiles[Number(index)];
  if (!file) return;
  const key = accessoryFileKey(file);
  const url = state.pipelineAccessoryPendingFileUrls.get(key);
  if (url) URL.revokeObjectURL(url);
  state.pipelineAccessoryPendingFileUrls.delete(key);
  state.pipelineAccessoryPendingFiles.splice(Number(index), 1);
  renderPipelineAccessoryFileQueue();
}

function renderPipelineAccessoryFileQueue() {
  const queue = $("pipelineAccessoryFileQueue");
  if (!queue) return;
  if (!state.pipelineAccessoryPendingFiles.length) {
    queue.innerHTML = `<div class="upload-thumb-empty">还没有添加素材</div>`;
    return;
  }
  queue.innerHTML = "";
  const title = document.createElement("div");
  title.className = "upload-thumb-summary";
  title.textContent = `待上传素材 ${state.pipelineAccessoryPendingFiles.length} 个`;
  queue.appendChild(title);
  const grid = document.createElement("div");
  grid.className = "upload-thumb-grid";
  for (const [index, file] of state.pipelineAccessoryPendingFiles.entries()) {
    const key = accessoryFileKey(file);
    if (!state.pipelineAccessoryPendingFileUrls.has(key) && file.type.startsWith("image/")) {
      state.pipelineAccessoryPendingFileUrls.set(key, URL.createObjectURL(file));
    }
    const url = state.pipelineAccessoryPendingFileUrls.get(key);
    const kind = file.type.startsWith("video/") ? "视频" : file.type.startsWith("image/") ? "图片" : "文件";
    const card = document.createElement("div");
    card.className = "upload-thumb-card";
    card.innerHTML = `
      <button type="button" class="upload-thumb-remove" data-remove-pipeline-file="${index}" aria-label="移除素材">×</button>
      ${url ? `<img src="${url}" alt="${escapeHtml(file.name)}" />` : `<div class="upload-thumb-file">${kind}</div>`}
      <span title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</span>
      <em>${kind}</em>
    `;
    grid.appendChild(card);
  }
  queue.appendChild(grid);
  queue.querySelectorAll("[data-remove-pipeline-file]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      removePipelineAccessoryPendingFile(button.dataset.removePipelineFile);
    });
  });
}

function updatePipelineMaterialFields() {
  const materialType = $("pipelineAccessoryMaterialType")?.value || "object";
  $("pipelineObjectFields")?.classList.toggle("hidden", materialType !== "object");
  $("pipelineTextFields")?.classList.toggle("hidden", materialType !== "text");
}

function resetPipelineAccessoryForm() {
  if ($("pipelineAccessoryName")) $("pipelineAccessoryName").value = "";
  if ($("pipelineObjectAlphaPolicy")) $("pipelineObjectAlphaPolicy").value = "";
  for (const id of ["pipelineObjectLengthMm", "pipelineObjectWidthMm", "pipelineObjectHeightMm", "pipelinePaperWidthMm", "pipelinePaperHeightMm"]) {
    if ($(id)) $(id).value = "";
  }
  clearPipelineAccessoryFileQueue();
}

async function startPipelineAccessoryAdd(button) {
  const name = $("pipelineAccessoryName")?.value.trim() || "";
  if (!name) return toast("请输入配件名称。");
  const materialType = $("pipelineAccessoryMaterialType")?.value || "object";
  const pendingFiles = state.pipelineAccessoryPendingFiles;
  if (!pendingFiles.length) return toast("请先添加至少一张照片或一段视频。");
  const form = new FormData();
  form.append("name", name);
  form.append("material_type", materialType);
  form.append("training_role", materialType === "text" ? "detect_then_ocr" : "detect_shape");
  form.append("pipeline_context", "pipeline");
  if (materialType === "text") {
    form.append("paper_preset", $("pipelinePaperPreset")?.value || "A4");
    form.append("paper_width_mm", $("pipelinePaperWidthMm")?.value || "");
    form.append("paper_height_mm", $("pipelinePaperHeightMm")?.value || "");
  } else {
    const alphaPolicy = $("pipelineObjectAlphaPolicy")?.value || "";
    if (!alphaPolicy) return toast("请先选择物品透明或不透明。");
    form.append("material_alpha_policy", alphaPolicy);
    form.append("object_length_mm", $("pipelineObjectLengthMm")?.value || "");
    form.append("object_width_mm", $("pipelineObjectWidthMm")?.value || "");
    form.append("object_height_mm", $("pipelineObjectHeightMm")?.value || "");
  }
  setBusy(button, true);
  try {
    if (materialType === "text" && !validateTextAccessoryFileBatch(pendingFiles)) return;
    const uploadFiles = materialType === "text" ? await prepareTextAccessoryFiles(pendingFiles) : pendingFiles;
    for (const file of uploadFiles) form.append("files", file);
    const result = await api("/api/accessories", { method: "POST", body: form });
    closePipelineAccessoryModal();
    resetPipelineAccessoryForm();
    if (result.items) renderAccessories(result.items);
    if (result.pipeline) {
      applyPipelineAccessoryPayload(result.pipeline);
    } else if (result.item?.id) {
      const pipeline = await api(`/api/pipeline/accessories/${encodeURIComponent(result.item.id)}`, { method: "POST" });
      applyPipelineAccessoryPayload(pipeline);
    }
    await refreshPipeline();
    toast("配件已添加到当前流水线，可直接拖入任务。");
  } catch (error) {
    toast(`添加失败:${error.message}`);
  } finally {
    setBusy(button, false);
  }
}

async function setAccessoryRoute(accessoryId, route, select) {
  if (select) select.disabled = true;
  try {
    const result = await api(`/api/accessories/${encodeURIComponent(accessoryId)}/route`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ route, apply: true }),
    });
    for (const collection of [state.accessories || [], state.pipeline.accessories || []]) {
      const target = collection.find((item) => item.id === accessoryId);
      if (target) target.detection_route = route;
    }
    if (route === "ai") {
      if (result.profile_status === "ready") {
        toast("已切换为 AI 检测:画像已就绪,并加入 Dashboard 快捷 AI 检测任务。");
      } else {
        toast(`已切换为 AI 检测,但画像生成失败:${result.profile_error || "未知原因"}`);
      }
      await loadAiTasksQuietly();
    } else if (route === "locate") {
      toast("已切换为开放定位:该配件会出现在开放定位工作台的检测项里。");
    } else if (route === "archive_only") {
      toast("已切换为仅建档:配件保留档案,不参与训练或检测。");
    } else {
      toast("已切换为 YOLO 训练路线。");
    }
    renderPipelineAccessories();
  } catch (error) {
    toast(`切换检测路线失败:${error.message}`);
    renderPipelineAccessories();
  } finally {
    if (select) select.disabled = false;
  }
}

async function loadAiTasksQuietly() {
  try {
    const aiTasks = await api(withAuthScope("/api/ai/tasks"));
    state.aiTasks = aiTasks.tasks || [];
    state.selectedAiTaskId = aiTasks.selected_task_id || state.aiTasks[0]?.id || "";
    renderAiTasks();
  } catch {
    // AI 任务刷新失败不影响主流程。
  }
}

function pipelineParamsSummary(task) {
  const method = pipelineTaskMethod(task);
  if (!pipelineMethodMeta(method).usesTraining) {
    return method === "ai" ? "AI 检测工作台" : "Locate Anything 工作台";
  }
  const params = task.params || {};
  const parts = [];
  if (params.sample_count) parts.push(`${params.sample_count} 样本`);
  if (params.epochs) parts.push(`${params.epochs} epoch`);
  if (params.image_size) parts.push(`${params.image_size}px`);
  if (params.train_mode) parts.push(params.train_mode === "yolo_ocr" ? "YOLO+OCR" : "YOLO");
  return parts.length ? parts.join(" · ") : "待 Agent 推荐";
}

function pipelineTaskAccessoryRows(task) {
  if (Array.isArray(task?.accessories) && task.accessories.length) return task.accessories;
  return (task?.accessory_ids || []).map((itemId) => {
    const accessory = [...(state.pipeline.accessories || []), ...(state.accessories || [])].find((item) => String(item.id) === String(itemId));
    return {
      id: itemId,
      name: accessory?.name || itemId,
      material_type: accessory?.material_type || "",
      count: pipelineTaskAccessoryCount(task, itemId),
    };
  });
}

function renderPipelineTaskDetail() {
  const task = pipelineTaskById(state.pipelineDetailTaskId);
  const title = $("pipelineTaskDetailTitle");
  const meta = $("pipelineTaskDetailMeta");
  const list = $("pipelineTaskAccessoryDetailList");
  if (!title || !meta || !list) return;
  if (!task) {
    title.textContent = "任务详情";
    meta.innerHTML = `<div class="lane-empty">任务不存在或已删除。</div>`;
    list.innerHTML = "";
    return;
  }
  const method = pipelineTaskMethod(task);
  const methodMeta = pipelineMethodMeta(method);
  const canEditCounts = task.stage === "draft";
  title.textContent = task.name || "任务详情";
  meta.innerHTML = `
    <span>${escapeHtml(methodMeta.label)}</span>
    <strong class="${method === "ai" && (task.accessory_ids || []).length ? "ready" : ""}">${method === "ai" && (task.accessory_ids || []).length ? "Type Ready" : PIPELINE_STATUS_ZH[task.status] || task.status || "待开始"}</strong>
    <span>${escapeHtml(task.stage || "draft")}</span>
    <span>${escapeHtml(recordAuditText(task, { includeUpdated: true }))}</span>
  `;
  const rows = pipelineTaskAccessoryRows(task);
  if (!rows.length) {
    list.innerHTML = `<div class="lane-empty">还没有选择配件。把左侧配件拖入这个任务后，可在这里调整数量。</div>`;
    return;
  }
  list.innerHTML = rows
    .map((item) => {
      const count = pipelineTaskAccessoryCount(task, item.id);
      const kind = item.material_type === "text" ? "文本/说明书" : item.material_type === "object" ? "物体" : "配件";
      return `
        <div class="pipeline-task-accessory-row">
          <div>
            <strong>${escapeHtml(zhLabel(item.name || item.id))}</strong>
            <span>${escapeHtml(kind)}</span>
          </div>
          <div class="pipeline-quantity-control">
            <button type="button" data-pipeline-count="${escapeAttr(item.id)}" data-count-delta="-1" ${!canEditCounts || count <= 1 ? "disabled" : ""} aria-label="减少数量">−</button>
            <strong>${count}</strong>
            <button type="button" data-pipeline-count="${escapeAttr(item.id)}" data-count-delta="1" ${!canEditCounts || count >= 99 ? "disabled" : ""} aria-label="增加数量">+</button>
          </div>
        </div>
      `;
    })
    .join("");
  list.querySelectorAll("[data-pipeline-count]").forEach((button) => {
    button.addEventListener("click", () => updatePipelineTaskAccessoryCount(task.id, button.dataset.pipelineCount, Number(button.dataset.countDelta || 0), button));
  });
}

function openPipelineTaskDetail(taskId) {
  state.pipelineDetailTaskId = taskId || "";
  renderPipelineTaskDetail();
  pipelineModalOpen("pipelineTaskDetailModal");
}

async function updatePipelineTaskAccessoryCount(taskId, accessoryId, delta, button = null) {
  const task = pipelineTaskById(taskId);
  if (!task || !accessoryId || !delta) return;
  const counts = { ...(task.accessory_counts || {}) };
  counts[accessoryId] = Math.max(1, Math.min(99, pipelineTaskAccessoryCount(task, accessoryId) + delta));
  if (button) setBusy(button, true);
  try {
    const updated = await api(`/api/pipeline/tasks/${encodeURIComponent(taskId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ accessory_counts: counts }),
    });
    const index = state.pipeline.tasks.findIndex((item) => item.id === taskId);
    if (index >= 0) state.pipeline.tasks[index] = updated;
    renderPipeline();
    state.pipelineDetailTaskId = taskId;
    renderPipelineTaskDetail();
  } catch (error) {
    toast(`调整数量失败:${error.message}`);
  } finally {
    if (button) setBusy(button, false);
  }
}

function pipelineTaskDraggable(task) {
  if (task.stage === "draft") return task.status !== "running";
  if (task.stage === "samples" || task.stage === "training") return task.status === "completed";
  return false;
}

function renderPipelineTasks() {
  for (const laneId of Object.values(PIPELINE_STAGE_LANES)) {
    const lane = $(laneId);
    if (lane) lane.innerHTML = "";
  }
  const libraryZone = $("pipelineLibraryZone");
  if (libraryZone) libraryZone.querySelectorAll(".pipeline-library-chip").forEach((chip) => chip.remove());
  for (const task of state.pipeline.tasks) {
    if (task.stage === "library") {
      continue;
    }
    const lane = $(PIPELINE_STAGE_LANES[task.stage] || "pipelineDraftList");
    if (!lane) continue;
    const card = document.createElement("article");
    card.className = `pipeline-card task-card status-${task.status || "ready"}`;
    const draggable = pipelineTaskDraggable(task);
    if (draggable) {
      card.draggable = true;
      card.addEventListener("dragstart", (event) => {
        event.dataTransfer.setData("text/plain", `task:${task.id}`);
        event.dataTransfer.effectAllowed = "move";
        card.classList.add("dragging");
      });
      card.addEventListener("dragend", () => card.classList.remove("dragging"));
    }
    const progress = task.stage === "samples" || task.stage === "training"
      ? `<div class="pipeline-progress"><div class="pipeline-progress-bar" style="width:${Math.max(2, Math.min(100, Number(task.progress || 0)))}%"></div></div>`
      : "";
    const epochInfo = task.stage === "training" && task.total_epochs
      ? ` · Epoch ${task.current_epoch || 0}/${task.total_epochs}`
      : "";
    const method = pipelineTaskMethod(task);
    const methodMeta = pipelineMethodMeta(method);
    const usesTraining = pipelineTaskUsesTraining(task);
    const methodLabel = methodMeta.label;
    const accessorySummary = pipelineTaskAccessoryRows(task)
      .map((item) => `${zhLabel(item.name || item.id)}×${pipelineTaskAccessoryCount(task, item.id)}`)
      .join("、");
    const advanceLabel = task.stage === "draft"
      ? usesTraining
        ? "生成样本"
        : method === "ai"
          ? "创建 AI 任务"
          : "启用定位任务"
      : task.stage === "samples"
        ? "开始训练"
        : "入库使用";
    const canAdvance = task.stage === "draft" ? task.status !== "running" : task.status === "completed";
    const paramsChip = usesTraining
      ? `<button type="button" class="pipeline-params-chip" data-pipeline-params="${escapeAttr(task.id)}" title="${escapeAttr(task.agent_reason || "")}">${escapeHtml(pipelineParamsSummary(task))}</button>`
      : `<button type="button" class="pipeline-params-chip" disabled title="${escapeAttr(method === "ai" ? "AI 检测任务会由流水线创建" : "Locate Anything 任务会由流水线创建")}">${escapeHtml(pipelineParamsSummary(task))}</button>`;
    card.innerHTML = `
      <div class="pipeline-card-head">
        <strong>${escapeHtml(task.name)}</strong>
        <div class="pipeline-card-badges">
          ${pipelineTaskTypePill(task)}
          <span class="pill ${task.status === "completed" ? "ok" : task.status === "failed" ? "fail" : "neutral"}">${PIPELINE_STATUS_ZH[task.status] || task.status}</span>
        </div>
      </div>
      <p class="pipeline-card-meta">${escapeHtml(`${methodLabel} · ${accessorySummary || (task.accessory_names || []).join("、") || "未选择配件"}`)}${epochInfo}</p>
      <p class="pipeline-card-meta">${escapeHtml(recordAuditText(task, { includeUpdated: true }))}</p>
      ${progress}
      ${task.last_error ? `<p class="pipeline-card-error">${escapeHtml(task.last_error)}</p>` : ""}
      ${paramsChip}
      <div class="pipeline-card-actions">
        <button type="button" class="mini-secondary" data-pipeline-detail="${escapeAttr(task.id)}">详情</button>
        ${canAdvance ? `<button type="button" class="mini-secondary" data-pipeline-advance="${escapeAttr(task.id)}">${advanceLabel}</button>` : ""}
        <label class="pipeline-auto-mini" title="阶段完成后自动进入下一步">
          <input type="checkbox" data-pipeline-auto="${escapeAttr(task.id)}" ${task.auto_advance ? "checked" : ""} />
          <span>自动</span>
        </label>
        <button type="button" class="danger-action compact-danger" data-pipeline-delete="${escapeAttr(task.id)}">删除</button>
      </div>
    `;
    lane.appendChild(card);
    card.addEventListener("dragover", (event) => {
      // dragover 阶段读不到拖拽内容,先放行,drop 时再校验类型。
      if (task.stage !== "draft") return;
      if (event.dataTransfer.types.includes("text/plain")) {
        event.preventDefault();
        card.classList.add("drop-target");
      }
    });
    card.addEventListener("dragleave", () => card.classList.remove("drop-target"));
    card.addEventListener("drop", async (event) => {
      card.classList.remove("drop-target");
      const payload = event.dataTransfer.getData("text/plain");
      if (task.stage === "draft" && payload.startsWith("acc:")) {
        event.preventDefault();
        event.stopPropagation();
        const accessoryId = payload.slice(4);
        if ((task.accessory_ids || []).includes(accessoryId)) return;
        try {
          await api(`/api/pipeline/tasks/${encodeURIComponent(task.id)}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ accessory_ids: [...(task.accessory_ids || []), accessoryId] }),
          });
          toast("配件已加入任务。");
          await refreshPipeline();
          state.pipelineDetailTaskId = task.id;
          if ($("pipelineTaskDetailModal")?.classList.contains("visible")) renderPipelineTaskDetail();
        } catch (error) {
          toast(`加入配件失败:${error.message}`);
        }
      }
    });
  }
  for (const [stage, laneId] of Object.entries(PIPELINE_STAGE_LANES)) {
    const lane = $(laneId);
    if (lane && !lane.children.length) {
      const empty = document.createElement("div");
      empty.className = "lane-empty";
      empty.textContent = stage === "draft" ? "新建任务或拖入配件开始。" : stage === "samples" ? "把待开始的任务拖到这里生成样本。" : "样本完成后拖到这里开始训练。";
      lane.appendChild(empty);
    }
  }
  document.querySelectorAll("[data-pipeline-advance]").forEach((button) => {
    button.addEventListener("click", () => advancePipelineTaskById(button.dataset.pipelineAdvance, button));
  });
  document.querySelectorAll("[data-pipeline-detail]").forEach((button) => {
    button.addEventListener("click", () => openPipelineTaskDetail(button.dataset.pipelineDetail));
  });
  document.querySelectorAll("[data-pipeline-params]").forEach((button) => {
    button.addEventListener("click", () => openPipelineParamsModal(button.dataset.pipelineParams));
  });
  document.querySelectorAll("[data-pipeline-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await api(`/api/pipeline/tasks/${encodeURIComponent(button.dataset.pipelineDelete)}`, { method: "DELETE" });
        toast("流水线任务已删除。");
        refreshPipeline();
      } catch (error) {
        toast(`删除失败:${error.message}`);
      }
    });
  });
  document.querySelectorAll("[data-pipeline-auto]").forEach((input) => {
    input.addEventListener("change", async () => {
      try {
        await api(`/api/pipeline/tasks/${encodeURIComponent(input.dataset.pipelineAuto)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ auto_advance: input.checked }),
        });
        toast(input.checked ? "已开启自动推进。" : "已关闭自动推进。");
      } catch (error) {
        toast(`设置失败:${error.message}`);
        input.checked = !input.checked;
      }
    });
  });
}

async function advancePipelineTaskById(taskId, button) {
  const task = state.pipeline.tasks.find((item) => item.id === taskId);
  if (!task) return;
  if (task.stage === "draft" && !(task.accessory_ids || []).length) {
    toast("先拖入至少一个配件。");
    return;
  }
  const method = pipelineTaskMethod(task);
  const usesTraining = pipelineTaskUsesTraining(task);
  // 进入下一阶段前若还没有确认过参数,先弹出参数确认。
  const stageKey = task.stage === "draft" ? "samples" : "training";
  const params = task.params || {};
  const missing = stageKey === "samples" ? !params.sample_count : !params.epochs;
  if (usesTraining && missing && task.stage !== "training") {
    openPipelineParamsModal(taskId, { advanceAfter: true });
    return;
  }
  if (button) setBusy(button, true);
  try {
    await api(`/api/pipeline/tasks/${encodeURIComponent(taskId)}/advance`, { method: "POST" });
    toast(
      !usesTraining && task.stage === "draft"
        ? method === "ai"
          ? "AI 检测任务已创建，可在 AI 检测工作台使用。"
          : "Locate Anything 任务已入库，可在开放定位工作台使用。"
        : task.stage === "training"
          ? "模型已入库,可在工作台切换使用。"
          : "已进入下一阶段。",
    );
    refreshPipeline();
    if (task.stage === "training") refreshTrainingLibrary();
    if (method === "ai") loadAiTasksQuietly();
    if (method === "locate") refreshLocateSources();
  } catch (error) {
    toast(`推进失败:${error.message}`);
  } finally {
    if (button) setBusy(button, false);
  }
}

async function openPipelineParamsModal(taskId, options = {}) {
  const task = state.pipeline.tasks.find((item) => item.id === taskId);
  if (!task) return;
  if (!pipelineTaskUsesTraining(task)) {
    toast("AI 检测与 Locate Anything 任务不需要训练参数。");
    return;
  }
  const stageKey = task.stage === "draft" ? "samples" : "training";
  state.pipelineParamsTarget = { taskId, stageKey, advanceAfter: Boolean(options.advanceAfter) };
  const modal = $("pipelineParamsModal");
  modal.querySelectorAll("[data-param-field]").forEach((field) => {
    const name = field.dataset.paramField;
    const forSamples = name === "sample_count";
    const forTraining = name === "epochs" || name === "image_size";
    field.classList.toggle("hidden", (stageKey === "samples" && forTraining) || (stageKey === "training" && forSamples));
  });
  $("pipelineParamsTitle").textContent = stageKey === "samples" ? `生成样本参数 · ${task.name}` : `训练参数 · ${task.name}`;
  $("pipelineParamsReason").textContent = "正在获取推荐参数…";
  pipelineModalOpen("pipelineParamsModal");
  let params = { ...(task.params || {}) };
  let reason = task.agent_reason || "";
  let source = task.agent_source || "";
  const needRecommend = stageKey === "samples" ? !params.sample_count : !params.epochs;
  if (needRecommend) {
    try {
      const recommendation = await api("/api/agent/recommend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          stage: stageKey,
          accessory_ids: task.accessory_ids || [],
          sample_count: params.sample_count || null,
        }),
      });
      params = { ...recommendation.params, ...params };
      reason = recommendation.reason || reason;
      source = recommendation.source || source;
    } catch (error) {
      reason = `获取推荐失败,使用默认值:${error.message}`;
    }
  }
  if ($("pipelineParamSampleCount")) $("pipelineParamSampleCount").value = params.sample_count || 400;
  if ($("pipelineParamEpochs")) $("pipelineParamEpochs").value = params.epochs || 40;
  if ($("pipelineParamImageSize")) $("pipelineParamImageSize").value = String(params.image_size || 640);
  if ($("pipelineParamTrainMode")) $("pipelineParamTrainMode").value = params.train_mode || "yolo_ocr";
  const sourceLabel = source === "agent" ? "Agent 推荐" : "规则推荐";
  $("pipelineParamsReason").textContent = reason ? `${sourceLabel}:${reason}` : `${sourceLabel}:可直接接受或修改后保存。`;
}

function collectPipelineParams() {
  const target = state.pipelineParamsTarget;
  if (!target) return {};
  if (target.stageKey === "samples") {
    return {
      sample_count: Number($("pipelineParamSampleCount").value) || 400,
      train_mode: $("pipelineParamTrainMode").value,
    };
  }
  return {
    epochs: Number($("pipelineParamEpochs").value) || 40,
    image_size: Number($("pipelineParamImageSize").value) || 640,
    train_mode: $("pipelineParamTrainMode").value,
  };
}

async function savePipelineParams(advance) {
  const target = state.pipelineParamsTarget;
  if (!target) return;
  try {
    await api(`/api/pipeline/tasks/${encodeURIComponent(target.taskId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ params: collectPipelineParams() }),
    });
    pipelineModalClose("pipelineParamsModal");
    if (advance || target.advanceAfter) {
      await api(`/api/pipeline/tasks/${encodeURIComponent(target.taskId)}/advance`, { method: "POST" });
      toast("参数已确认,任务开始执行。");
    } else {
      toast("参数已保存。");
    }
    refreshPipeline();
  } catch (error) {
    toast(`保存参数失败:${error.message}`);
  }
}

function openPipelineTaskModal() {
  if ($("pipelineTaskDetectionMethod")) $("pipelineTaskDetectionMethod").value = "yolo_ocr";
  $("pipelineTaskName").value = "";
  pipelineModalOpen("pipelineTaskModal");
}

async function confirmPipelineTaskCreate() {
  try {
    await api("/api/pipeline/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: $("pipelineTaskName").value.trim(),
        detection_method: $("pipelineTaskDetectionMethod")?.value || "yolo_ocr",
      }),
    });
    pipelineModalClose("pipelineTaskModal");
    toast("任务已创建,拖入配件后即可确认参数。");
    refreshPipeline();
  } catch (error) {
    toast(`创建任务失败:${error.message}`);
  }
}

function bindPipelineLaneDrops() {
  document.querySelectorAll("[data-drop-stage]").forEach((zone) => {
    zone.addEventListener("dragover", (event) => {
      event.preventDefault();
      zone.classList.add("drop-target");
    });
    zone.addEventListener("dragleave", () => zone.classList.remove("drop-target"));
    zone.addEventListener("drop", async (event) => {
      event.preventDefault();
      zone.classList.remove("drop-target");
      const payload = event.dataTransfer.getData("text/plain");
      const targetStage = zone.dataset.dropStage;
      if (payload.startsWith("acc:")) {
        if (targetStage === "draft") toast("先新建任务,再把配件拖到任务卡片上。");
        else toast("配件需要先在第 2 栏组成任务。");
        return;
      }
      if (!payload.startsWith("task:")) return;
      const taskId = payload.slice(5);
      const task = state.pipeline.tasks.find((item) => item.id === taskId);
      if (!task) return;
      if (PIPELINE_NEXT_STAGE[task.stage] !== targetStage) {
        toast("只能拖入下一个阶段。");
        return;
      }
      await advancePipelineTaskById(taskId);
    });
  });
}

function bindPipelineSidebarDropTarget() {
  const target = document.querySelector('.nav-item[data-view="accessories"]');
  if (!target) return;
  target.addEventListener("dragover", (event) => {
    if (!event.dataTransfer.types.includes("text/plain")) return;
    event.preventDefault();
    target.classList.add("sidebar-drop-target");
    event.dataTransfer.dropEffect = "move";
  });
  target.addEventListener("dragleave", () => target.classList.remove("sidebar-drop-target"));
  target.addEventListener("drop", async (event) => {
    const payload = event.dataTransfer.getData("text/plain");
    target.classList.remove("sidebar-drop-target");
    if (!payload.startsWith("acc:")) return;
    event.preventDefault();
    event.stopPropagation();
    await removePipelineAccessory(payload.slice(4));
  });
}

async function refreshAgentConfigPanel() {
  if (!hasPermission("agent_config")) return;
  try {
    const config = await api("/api/agent/config");
    state.pipeline.agent = config;
    if ($("agentBaseUrl")) $("agentBaseUrl").value = config.base_url || "";
    if ($("agentModel")) $("agentModel").value = config.model || "";
    if ($("agentApiKey")) $("agentApiKey").placeholder = config.has_api_key ? `已保存:${config.api_key_masked}` : "保存后只显示掩码";
    if ($("agentTimeout")) $("agentTimeout").value = config.timeout_seconds || 45;
    if ($("agentAutoAdvanceDefault")) $("agentAutoAdvanceDefault").checked = Boolean(config.auto_advance_default);
    syncAgentBaseUrlPreset();
    syncAgentEndpointUi();
    renderAgentModelOptions(config);
    const pill = $("agentConfigStatus");
    if (pill) {
      pill.textContent = agentConnectionLabel(config);
      pill.className = `pill ${agentConnectionClass(config)}`;
      pill.title = config.connection_message || "";
    }
    renderPipelineAgentPill();
  } catch {
    // 设置面板刷新失败保持安静。
  }
}

function currentAgentConfigPayload() {
  const payload = {
    base_url: currentAgentBaseUrl(),
    model: $("agentModel").value.trim(),
    timeout_seconds: Number($("agentTimeout").value) || 45,
    auto_advance_default: $("agentAutoAdvanceDefault").checked,
  };
  const key = $("agentApiKey").value.trim();
  if (key) payload.api_key = key;
  return payload;
}

async function postAgentConfigFromPanel() {
  const result = await api("/api/agent/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(currentAgentConfigPayload()),
  });
  $("agentApiKey").value = "";
  state.pipeline.agent = result;
  if ($("agentBaseUrl")) $("agentBaseUrl").value = result.base_url || $("agentBaseUrl").value.trim();
  if ($("agentModel")) $("agentModel").value = result.model || "";
  if ($("agentTimeout")) $("agentTimeout").value = result.timeout_seconds || 45;
  if ($("agentAutoAdvanceDefault")) $("agentAutoAdvanceDefault").checked = Boolean(result.auto_advance_default);
  if ($("agentApiKey")) $("agentApiKey").placeholder = result.has_api_key ? `已保存:${result.api_key_masked}` : "保存后只显示掩码";
  syncAgentBaseUrlPreset();
  syncAgentEndpointUi();
  renderAgentModelOptions(result);
  return result;
}

async function saveAgentConfigFromPanel(button) {
  setBusy(button, true);
  try {
    await postAgentConfigFromPanel();
    toast("Agent 设置已保存。");
    refreshAgentConfigPanel();
  } catch (error) {
    toast(`保存失败:${error.message}`);
  } finally {
    setBusy(button, false);
  }
}

async function testAgentConfigFromPanel(button) {
  setBusy(button, true);
  try {
    await postAgentConfigFromPanel();
    const result = await api("/api/agent/config/test", { method: "POST" });
    toast(result.message || (result.ok ? "连接成功。" : "连接失败。"));
    state.pipeline.agent = result;
    if ($("agentModel")) $("agentModel").value = result.model || $("agentModel").value;
    renderAgentModelOptions(result);
    const pill = $("agentConfigStatus");
    if (pill) {
      pill.textContent = agentConnectionLabel(result);
      pill.className = `pill ${agentConnectionClass(result)}`;
      pill.title = result.connection_message || "";
    }
    renderPipelineAgentPill();
  } catch (error) {
    toast(`测试失败:${error.message}`);
  } finally {
    setBusy(button, false);
  }
}

function startPipelinePolling() {
  if (!state.auth.user || state.pipelinePollTimer) return;
  state.pipelinePollTimer = setInterval(refreshPipeline, 6000);
  refreshPipeline();
  refreshAgentConfigPanel();
}

function bindPipeline() {
  $("openTrainingWizard")?.addEventListener("click", () => pipelineModalOpen("trainingWizardModal"));
  $("closeTrainingWizard")?.addEventListener("click", () => pipelineModalClose("trainingWizardModal"));
  $("openJobHistory")?.addEventListener("click", () => pipelineModalOpen("jobHistoryModal"));
  $("closeJobHistory")?.addEventListener("click", () => pipelineModalClose("jobHistoryModal"));
  $("pipelineAddAccessory")?.addEventListener("click", openPipelineAccessoryModal);
  $("closePipelineAccessoryModal")?.addEventListener("click", closePipelineAccessoryModal);
  $("pipelineAccessoryMaterialType")?.addEventListener("change", updatePipelineMaterialFields);
  $("pipelineAccessoryFiles")?.addEventListener("change", () => addPipelineAccessoryPendingFiles($("pipelineAccessoryFiles").files));
  $("pipelineStartAccessoryAdd")?.addEventListener("click", (event) => startPipelineAccessoryAdd(event.currentTarget));
  $("pipelineCreateTask")?.addEventListener("click", () => openPipelineTaskModal());
  $("closePipelineTaskModal")?.addEventListener("click", () => pipelineModalClose("pipelineTaskModal"));
  $("cancelPipelineTaskModal")?.addEventListener("click", () => pipelineModalClose("pipelineTaskModal"));
  $("confirmPipelineTask")?.addEventListener("click", confirmPipelineTaskCreate);
  $("closePipelineTaskDetailModal")?.addEventListener("click", () => pipelineModalClose("pipelineTaskDetailModal"));
  $("donePipelineTaskDetailModal")?.addEventListener("click", () => pipelineModalClose("pipelineTaskDetailModal"));
  $("closePipelineParamsModal")?.addEventListener("click", () => pipelineModalClose("pipelineParamsModal"));
  $("savePipelineParams")?.addEventListener("click", () => savePipelineParams(false));
  $("acceptPipelineParams")?.addEventListener("click", () => savePipelineParams(true));
  $("saveAgentConfig")?.addEventListener("click", (event) => saveAgentConfigFromPanel(event.currentTarget));
  $("testAgentConfig")?.addEventListener("click", (event) => testAgentConfigFromPanel(event.currentTarget));
  $("agentBaseUrlPreset")?.addEventListener("change", (event) => applyAgentBaseUrlPreset(event.currentTarget.value));
  $("agentBaseUrl")?.addEventListener("input", () => {
    syncAgentEndpointUi();
    renderAgentModelOptions({ model_options: [] });
  });
  for (const id of ["trainingWizardModal", "jobHistoryModal", "pipelineTaskModal", "pipelineTaskDetailModal", "pipelineAccessoryModal", "pipelineParamsModal"]) {
    MODAL_CLOSE_HANDLERS.push([id, () => pipelineModalClose(id)]);
    $(id)?.addEventListener("click", (event) => {
      if (event.target === $(id)) pipelineModalClose(id);
    });
  }
  document.querySelector('.nav-item[data-view="pipeline"]')?.addEventListener("click", refreshPipeline);
  bindPipelineLaneDrops();
  bindPipelineSidebarDropTarget();
  startPipelinePolling();
}

bindPipeline();
