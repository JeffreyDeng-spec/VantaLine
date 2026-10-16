// Browser-local draft evidence. Values never enter storage or diagnostics.
type Editor = HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;
const drafts = new Map<Editor, string>();
let baselines = new WeakMap<Editor, string>();
let saveScope: Element | null = null;
export function clearEditorDrafts() { drafts.clear(); baselines = new WeakMap<Editor, string>(); saveScope = null; }
function value(node: Editor) { return node instanceof HTMLInputElement && ["checkbox", "radio"].includes(node.type) ? String(node.checked) : node.value; }
function editor(target: EventTarget | null): Editor | null {
  if (!(target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement)) return null;
  if (target.closest(".search-field, .library-search-box, [data-version-ignore-draft]") || target instanceof HTMLInputElement && ["search", "file", "range"].includes(target.type)) return null;
  return target.closest("form, [role=dialog], .field, .settings-field") ? target : null;
}
export function hasEditorDrafts() {
  for (const [node, changed] of drafts) {
    if (!node.isConnected || value(node) !== changed) drafts.delete(node);
  }
  return drafts.size > 0;
}
export function installDraftTracking() {
  const focus = (event: Event) => { const node = editor(event.target); if (node && !drafts.has(node)) baselines.set(node, value(node)); };
  const input = (event: Event) => {
    const node = editor(event.target); if (!node) return;
    const initial = baselines.get(node) ?? (node instanceof HTMLSelectElement ? [...node.options].find(o => o.defaultSelected)?.value || "" : node.defaultValue);
    if (value(node) === initial) drafts.delete(node); else drafts.set(node, value(node));
  };
  const saving = (event: Event) => {
    const node = event.target instanceof Element ? event.target : null;
    const button = node?.closest("button");
    if (event.type === "submit" || button && (button.type === "submit" || /保存|确认|创建/.test(button.textContent || ""))) {
      saveScope = node?.closest("form, [role=dialog], .panel") || null;
    } else saveScope = null;
  };
  document.addEventListener("focusin", focus, true);
  document.addEventListener("input", input, true);
  document.addEventListener("change", input, true);
  document.addEventListener("click", saving, true);
  document.addEventListener("submit", saving, true);
  return () => {
    document.removeEventListener("focusin", focus, true);
    document.removeEventListener("input", input, true);
    document.removeEventListener("change", input, true);
    document.removeEventListener("click", saving, true);
    document.removeEventListener("submit", saving, true);
    drafts.clear(); saveScope = null;
  };
}
export function savedEditorsAcknowledgement() {
  const scope = saveScope; saveScope = null;
  const snapshot = [...drafts].filter(([node]) => scope?.contains(node));
  return () => { for (const [node, changed] of snapshot) if (value(node) === changed) { drafts.delete(node); baselines.set(node, changed); } };
}
