export async function cameraPermissionRequired() {
  try {
    const permission = await navigator.permissions.query({name:"camera" as PermissionName});
    return permission.state !== "granted";
  } catch {
    // Browsers without a camera permission query must use their visible flow.
    return true;
  }
}
