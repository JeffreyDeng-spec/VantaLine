import { type ReactNode, useId, useRef, useState } from "react";
import { getFile, rememberFile } from "../features/agent/files";
import { useAgentActions } from "../features/agent/useAgentActions";

export function fileMatchesAccept(file: File, accept = "") {
  if (!accept.trim()) return true;
  const fileName = file.name.toLowerCase();
  const mime = file.type.toLowerCase();
  return accept.split(",").map((part) => part.trim().toLowerCase()).filter(Boolean).some((rule) => {
    if (rule.startsWith(".")) return fileName.endsWith(rule);
    if (rule.endsWith("/*")) {
      const family = rule.slice(0, -1);
      if (mime.startsWith(family)) return true;
      if (family === "image/") return /\.(png|jpe?g|webp|gif|bmp|tiff?)$/i.test(fileName);
      if (family === "video/") return /\.(mp4|mov|m4v|avi|webm|mkv)$/i.test(fileName);
      return false;
    }
    return mime === rule;
  });
}

export function FileDropZone({
  accept,
  multiple = false,
  disabled = false,
  className = "dropzone",
  ariaLabel = "上传文件",
  onFiles,
  children
}: {
  accept?: string;
  multiple?: boolean;
  disabled?: boolean;
  className?: string;
  ariaLabel?: string;
  onFiles: (files: File[]) => void;
  children: ReactNode;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const toolId = useId().replace(/[^a-zA-Z0-9]/g, "").toLowerCase();
  const [requested, setRequested] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [rejection, setRejection] = useState("");

  const selectFiles = (incoming: File[]) => {
    if (disabled) return;
    const accepted = incoming.filter((file) => fileMatchesAccept(file, accept));
    const rejected = incoming.filter((file) => !fileMatchesAccept(file, accept));
    setRejection(rejected.length ? `不支持：${rejected.map((file) => file.name).join("、")}` : "");
    if (accepted.length) {
      const selected = multiple ? accepted : accepted.slice(0, 1);
      selected.forEach(rememberFile);
      onFiles(selected);
      setRequested(false);
    }
    else if (incoming.length) onFiles([]);
  };

  useAgentActions([{ name: `select_files_${toolId}`, domain: "core", description: `Select already-authorized files for ${ariaLabel}. With no file_ids, request native file selection. Accepted types: ${accept || "any"}.`, readOnly: false,
    inputSchema: {type:"object",properties:{file_ids:{type:"array",items:{type:"string"},maxItems:multiple ? 50 : 1}},additionalProperties:false},
    available: () => disabled ? "This upload surface is disabled." : null,
    execute: input => {
      if (!Array.isArray(input.file_ids) || !input.file_ids.length) { setRequested(true); return {status:"requires_user_input",data:{label:ariaLabel,accept,multiple},next_action:`select_files_${toolId}`}; }
      const chosen = input.file_ids.map(id => getFile(String(id)));
      if (chosen.some(file => !fileMatchesAccept(file, accept))) throw new Error("Selected file type is not accepted here.");
      selectFiles(chosen);
      return {selected: input.file_ids};
    }
  }]);

  return <div
    className={`${className} file-drop-target ${dragging ? "dragging" : ""} ${disabled ? "disabled" : ""}`}
    data-file-drop-zone="true"
    role="button"
    tabIndex={disabled ? -1 : 0}
    aria-label={ariaLabel}
    aria-disabled={disabled}
    onClick={() => { if (!disabled) inputRef.current?.click(); }}
    onKeyDown={(event) => {
      if (disabled || (event.key !== "Enter" && event.key !== " ")) return;
      event.preventDefault(); inputRef.current?.click();
    }}
    onDragEnter={(event) => { event.preventDefault(); if (!disabled) setDragging(true); }}
    onDragOver={(event) => { event.preventDefault(); if (!disabled) { event.dataTransfer.dropEffect = "copy"; setDragging(true); } }}
    onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false); }}
    onDrop={(event) => { event.preventDefault(); setDragging(false); selectFiles(Array.from(event.dataTransfer.files || [])); }}
  >
    <input
      ref={inputRef}
      className="visually-hidden-file"
      type="file"
      accept={accept}
      multiple={multiple}
      disabled={disabled}
      tabIndex={-1}
      onClick={(event) => event.stopPropagation()}
      onChange={(event) => { selectFiles(Array.from(event.currentTarget.files || [])); event.currentTarget.value = ""; }}
    />
    {children}
    {requested ? <small role="status">Agent 请求为“{ariaLabel}”选择文件；选择后可继续操作。</small> : null}
    {rejection ? <small className="file-drop-rejection" role="alert">{rejection}</small> : null}
  </div>;
}
