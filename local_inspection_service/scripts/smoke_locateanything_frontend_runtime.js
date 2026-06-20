#!/usr/bin/env node
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..", "..");
const APP_JS = path.join(ROOT, "local_inspection_service", "static", "app.js");

class ClassListStub {
  constructor(element) {
    this.element = element;
    this.values = new Set();
  }

  add(...names) {
    for (const name of names) this.values.add(name);
    this.sync();
  }

  remove(...names) {
    for (const name of names) this.values.delete(name);
    this.sync();
  }

  contains(name) {
    return this.values.has(name);
  }

  toggle(name, force) {
    const enabled = force === undefined ? !this.values.has(name) : Boolean(force);
    if (enabled) this.values.add(name);
    else this.values.delete(name);
    this.sync();
    return enabled;
  }

  sync() {
    this.element._className = Array.from(this.values).join(" ");
  }
}

class ElementStub {
  constructor(tagName = "div", id = "") {
    this.tagName = tagName.toUpperCase();
    this.id = id;
    this.dataset = {};
    this.style = {};
    this.children = [];
    this.attributes = {};
    this.files = [];
    this.value = "";
    this.disabled = false;
    this.textContent = "";
    this._innerHTML = "";
    this._className = "";
    this.classList = new ClassListStub(this);
  }

  get className() {
    return this._className;
  }

  set className(value) {
    this._className = String(value || "");
    this.classList.values = new Set(this._className.split(/\s+/).filter(Boolean));
  }

  get innerHTML() {
    return this._innerHTML;
  }

  set innerHTML(value) {
    this._innerHTML = String(value ?? "");
    this.children = [];
  }

  addEventListener() {}
  removeEventListener() {}
  focus() {}
  click() {}
  play() {
    return Promise.resolve();
  }

  appendChild(child) {
    this.children.push(child);
    child.parentElement = this;
    return child;
  }

  replaceChildren(...children) {
    this.children = [];
    for (const child of children) this.appendChild(child);
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  removeAttribute(name) {
    delete this.attributes[name];
  }

  getAttribute(name) {
    return this.attributes[name] || "";
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }

  querySelectorAll(selector) {
    if (selector === "[data-locate-template]") {
      const matches = [...this._innerHTML.matchAll(/data-locate-template="(\d+)"/g)];
      return matches.map((match) => {
        const button = new ElementStub("button");
        button.dataset.locateTemplate = match[1];
        return button;
      });
    }
    return [];
  }

  closest() {
    return null;
  }
}

const elements = new Map();
const locateModeButtons = ["fast", "hybrid", "slow"].map((mode, index) => {
  const button = new ElementStub("button");
  button.dataset.locateMode = mode;
  if (index === 0) button.classList.add("active");
  return button;
});

function element(id) {
  if (!elements.has(id)) {
    const node = new ElementStub("div", id);
    if (id.endsWith("File") || id.endsWith("Files")) node.files = [];
    elements.set(id, node);
  }
  return elements.get(id);
}

function inputStub(props = {}) {
  return Object.assign(new ElementStub("input"), props);
}

const locateRuleRow = new ElementStub("div");
locateRuleRow.dataset.locateRule = "class:0";
locateRuleRow.dataset.locateLabel = "Bottle";
locateRuleRow.querySelector = (selector) => {
  if (selector === "[data-locate-enabled]") return inputStub({ checked: true });
  if (selector === "[data-locate-expected-present]") return inputStub({ checked: true });
  if (selector === "[data-locate-expected-count]") return inputStub({ value: "1" });
  if (selector === "[data-locate-prompt-override]") return inputStub({ value: "" });
  return null;
};

Object.assign(element("locateEndpointUrl"), { value: "http://127.0.0.1:8000/locate" });
Object.assign(element("locateMaxSide"), { value: "640" });
Object.assign(element("locateMaxTokens"), { value: "512" });
Object.assign(element("locateCameraSampleSeconds"), { value: "1" });
Object.assign(element("locatePrompt"), { value: "Locate all the instances that match the following description: glass bottle." });
Object.assign(element("locateImageFile"), { files: [{ name: "smoke.jpg", type: "image/jpeg" }] });

const documentStub = {
  body: element("body"),
  fullscreenElement: null,
  createElement: (tagName) => new ElementStub(tagName),
  getElementById: (id) => element(id),
  addEventListener() {},
  removeEventListener() {},
  querySelector(selector) {
    if (selector === "[data-locate-mode].active") {
      return locateModeButtons.find((button) => button.classList.contains("active")) || locateModeButtons[0];
    }
    return null;
  },
  querySelectorAll(selector) {
    if (selector === "[data-locate-mode]") return locateModeButtons;
    if (selector === "[data-locate-rule]") return [locateRuleRow];
    return [];
  },
  exitFullscreen() {
    this.fullscreenElement = null;
    return Promise.resolve();
  },
};

function response(payload) {
  return {
    ok: true,
    statusText: "OK",
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  };
}

let inspectInFlight = 0;
let maxConcurrentInspect = 0;

async function fetchStub(url) {
  const pathname = String(url).split("?")[0];
  if (pathname === "/api/status") {
    return response({
      service: "running",
      model_exists: true,
      classes: [],
      available_models: [],
      specialized_models: [],
      specialized_model_tasks: [],
      ai_detection_tasks: [],
      rule: { required_classes: [] },
    });
  }
  if (pathname === "/api/config") {
    return response({
      confidence_threshold: 0.5,
      required_classes: [],
      min_counts: {},
      accessories: [],
      video: {},
      training: { status: "idle", sample_count: 4000, mode: "yolo_ocr", image_size: 640 },
    });
  }
  if (pathname === "/api/ai/config") {
    return response({ status: "disabled", provider: "gemini", model: "", model_options: [] });
  }
  if (pathname === "/api/locateanything/config") {
    return response({
      enabled: false,
      configured: false,
      endpoint_url: "http://127.0.0.1:8000/locate",
      generation_mode: "fast",
      max_new_tokens: 512,
      max_side: 640,
    });
  }
  if (pathname === "/api/locateanything/accessories") {
    return response({
      items: [
        {
          id: "class:0",
          source: "class",
          label: "Bottle",
          display_label: "Bottle",
          material_type: "object",
          default_expected_present: true,
          default_expected_count: 1,
          default_selected: true,
        },
      ],
    });
  }
  if (pathname === "/api/locateanything/inspect") {
    inspectInFlight += 1;
    maxConcurrentInspect = Math.max(maxConcurrentInspect, inspectInFlight);
    await new Promise((resolve) => setTimeout(resolve, 25));
    inspectInFlight -= 1;
    return response({
      ok: true,
      configured: true,
      overall_pass: true,
      decision: "pass",
      latency_ms: 25,
      overlay_url: "/outputs/locateanything/concurrency_smoke.jpg",
      items: [
        {
          id: "class:0",
          label: "Bottle",
          status: "found",
          passed: true,
          expected_present: true,
          expected_count: 1,
          box_count: 1,
        },
      ],
    });
  }
  if (pathname === "/api/ai/tasks") return response({ tasks: [], selected_task_id: "" });
  if (pathname === "/api/accessories") return response({ items: [] });
  if (pathname === "/api/training/plan") {
    return response({
      training: { status: "idle", sample_count: 4000, mode: "yolo_ocr", image_size: 640, selected_accessory_ids: [] },
      background_sets: [],
    });
  }
  if (pathname === "/api/label-sheets/references") {
    return response({ references: [], doc_filter_stats: { kept_count: 0, filtered_count: 0 } });
  }
  if (pathname === "/api/training/resources") {
    return response({ datasets: [], models: [], training_tasks: [], tasks: [], backgrounds: [] });
  }
  if (pathname === "/api/image-jobs") return response({ items: [] });
  return response({});
}

const context = vm.createContext({
  console,
  document: documentStub,
  window: {
    addEventListener() {},
    removeEventListener() {},
    scrollTo() {},
    matchMedia: () => ({ matches: false }),
  },
  navigator: { mediaDevices: {} },
  fetch: fetchStub,
  FormData: class FormDataStub {
    append() {}
  },
  File: class FileStub {},
  URL: {
    createObjectURL: () => "blob:locateanything-smoke",
    revokeObjectURL() {},
  },
  Blob: class BlobStub {},
  setInterval: () => 1,
  clearInterval() {},
  setTimeout,
  clearTimeout,
});

async function main() {
  vm.runInContext(fs.readFileSync(APP_JS, "utf8"), context, { filename: APP_JS });
  await new Promise((resolve) => setTimeout(resolve, 20));
  const startupToast = element("toast").textContent;
  if (startupToast.startsWith("启动失败")) throw new Error(startupToast);

  vm.runInContext(
    `renderLocateConfig({
      enabled: true,
      configured: true,
      ok: true,
      endpoint_url: "http://127.0.0.1:8000/locate",
      generation_mode: "fast",
      max_side: 768,
      max_new_tokens: 1024,
      latency_ms: 123
    });`,
    context,
  );
  vm.runInContext(
    `renderLocateSources([{
      id: "class:0",
      source: "class",
      label: "Bottle",
      display_label: "Bottle",
      material_type: "object",
      default_expected_present: true,
      default_expected_count: 1,
      default_selected: true
    }]);`,
    context,
  );
  vm.runInContext(
    `renderLocateResult({
      ok: true,
      overall_pass: true,
      latency_ms: 123,
      overlay_url: "/outputs/locateanything/runtime_smoke.jpg",
      items: [{
        id: "class:0",
        label: "Bottle",
        status: "found",
        passed: true,
        expected_present: true,
        expected_count: 1,
        box_count: 1
      }]
    });`,
    context,
  );

  const generationMode = vm.runInContext("state.locateAnythingConfig.generation_mode", context);
  const resultPass = vm.runInContext("state.locateAnythingLastResult.overall_pass", context);
  const overallText = element("locateOverallResult").textContent;
  const diagnostics = element("locateDiagnosticText").textContent;
  if (generationMode !== "fast") throw new Error(`generation mode did not default to fast: ${generationMode}`);
  if (resultPass !== true || overallText !== "通过") throw new Error(`PASS result did not render: ${overallText}`);
  if (diagnostics.includes("raw_answer") || diagnostics.includes("<box>")) throw new Error("normal diagnostics exposed raw model output");
  if (!element("startLocateRuntime").classList.contains("hidden")) throw new Error("ready runtime did not hide start action");

  Object.assign(element("locateCameraSampleSeconds"), { value: "0.7" });
  if (vm.runInContext("locateCameraSampleDelayMs()", context) !== 700) {
    throw new Error("camera sample delay did not use configured interval");
  }
  Object.assign(element("locateCameraSampleSeconds"), { value: "0.1" });
  if (vm.runInContext("locateCameraSampleDelayMs()", context) !== 500) {
    throw new Error("camera sample delay did not clamp below 0.5s");
  }
  Object.assign(element("locateCameraSampleSeconds"), { value: "5" });
  if (vm.runInContext("locateCameraSampleDelayMs()", context) !== 2000) {
    throw new Error("camera sample delay did not clamp above 2s");
  }

  vm.runInContext(
    `renderLocateSources([
      {
        id: "class:0",
        source: "class",
        label: "Bottle",
        display_label: "Bottle",
        material_type: "object",
        visual_prompt: "transparent glass bottle with cap",
        default_expected_present: true,
        default_expected_count: 1,
        default_selected: true
      },
      {
        id: "class:1",
        source: "class",
        label: "Manual",
        display_label: "Manual",
        material_type: "text",
        visual_prompt: "flat printed instruction manual",
        default_expected_present: true,
        default_expected_count: 1,
        default_selected: false
      }
    ]);
    upsertLocateRule("class:1");
    updateLocateRule("class:1", { enabled: false, expected_count: 3, prompt_override: "custom manual prompt" });
    renderLocateSources(state.locateAnythingSources);`,
    context,
  );
  let selectedRules = vm.runInContext("selectedLocateRules()", context);
  if (selectedRules.some((rule) => rule.id === "class:1")) throw new Error("disabled recipe item was included in selected rules");
  vm.runInContext(`state.locateRecipePickerOpen = true; renderLocateRecipePicker();`, context);
  const pickerHtml = element("locateRecipePickerList")._innerHTML;
  const manualStart = pickerHtml.indexOf('data-locate-picker-item="class:1"');
  const manualEnd = manualStart >= 0 ? pickerHtml.indexOf("</label>", manualStart) : -1;
  const manualPickerRow = manualStart >= 0 && manualEnd >= 0 ? pickerHtml.slice(manualStart, manualEnd) : "";
  if (!manualPickerRow) throw new Error("disabled configured recipe item was missing from picker");
  if (manualPickerRow.includes("checked")) throw new Error("disabled configured recipe item rendered as checked in picker");
  if (!manualPickerRow.includes("已停用")) throw new Error("disabled configured recipe item did not show stopped status");
  vm.runInContext(`updateLocateRule("class:1", { enabled: true });`, context);
  selectedRules = vm.runInContext("selectedLocateRules()", context);
  const manualRule = selectedRules.find((rule) => rule.id === "class:1");
  if (!manualRule || manualRule.expected_count !== 3 || manualRule.prompt_override !== "custom manual prompt") {
    throw new Error("recipe state did not survive re-render");
  }
  vm.runInContext(`removeLocateRule("class:1");`, context);
  selectedRules = vm.runInContext("selectedLocateRules()", context);
  if (selectedRules.some((rule) => rule.id === "class:1")) throw new Error("removed recipe item still selected");
  if (element("locateAccessoryList")._innerHTML.length > 20000) throw new Error("recipe list rendered an unbounded source list");

  vm.runInContext(
    `renderLocateRuntimeStatus({
      configured: true,
      ok: false,
      status: "reachable",
      status_code: 405,
      message: "Endpoint is reachable, but readiness is not confirmed."
    });`,
    context,
  );
  if (element("locateStatusBadge").textContent !== "需试检确认") throw new Error("reachable-only status rendered as ready");
  if (element("startLocateRuntime").classList.contains("hidden")) throw new Error("unconfirmed runtime hid start action");
  vm.runInContext(`renderLocateRuntimeStatus({ configured: true, ok: true, status: "ready" });`, context);

  maxConcurrentInspect = 0;
  inspectInFlight = 0;
  await Promise.all([
    vm.runInContext("runLocateImage(null)", context),
    vm.runInContext("runLocateImage(null)", context),
  ]);
  if (maxConcurrentInspect !== 1) throw new Error(`expected max one concurrent inspect call, saw ${maxConcurrentInspect}`);
  const lockReleased = vm.runInContext("state.locateAnythingInspectInFlight", context);
  if (lockReleased !== false) throw new Error("inspect lock was not released");
  vm.runInContext("stopLocateCameraLoop()", context);
  if (!element("stopLocateCameraLoop").classList.contains("hidden")) throw new Error("stop action did not hide after stop");
  if (element("startLocateCameraLoop").classList.contains("hidden")) throw new Error("start loop action did not show after stop");

  console.log("locateanything frontend runtime smoke passed");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
