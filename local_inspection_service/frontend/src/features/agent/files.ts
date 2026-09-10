// Files are scoped to this signed-in page lifetime, never arbitrary server paths.
const files = new Map<string, File>();
const identities = new WeakMap<File, string>();
export function rememberFile(file: File) {
  const known = identities.get(file);
  if (known && files.has(known)) return known;
  if (files.size >= 100) files.delete(files.keys().next().value!);
  const id = crypto.randomUUID(); files.set(id, file); identities.set(file, id); return id;
}
export function getFile(id: string) {
  const file = files.get(id);
  if (!file) throw new Error("File handle expired. Select the file in this session.");
  return file;
}
export function listFiles() { return [...files].map(([id, file]) => ({ id, name: file.name, size: file.size, type: file.type })); }
export function clearFiles() { files.clear(); }
export function buildForm(input: { fields?: Record<string, unknown>; files?: Record<string, string[]> }) {
  const form = new FormData();
  for (const [key, value] of Object.entries(input.fields ?? {})) if (value !== undefined && value !== null) form.set(key, typeof value === "object" ? JSON.stringify(value) : String(value));
  for (const [key, ids] of Object.entries(input.files ?? {})) for (const id of ids) form.append(key, getFile(id));
  return form;
}
