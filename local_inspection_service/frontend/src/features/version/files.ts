const uploaded = new WeakSet<File>();
export function markVersionFilesUploaded(files: File[]) { files.forEach(file => uploaded.add(file)); }
export function hasUnuploadedVersionFiles(files: File[]) { return files.some(file => !uploaded.has(file)); }
