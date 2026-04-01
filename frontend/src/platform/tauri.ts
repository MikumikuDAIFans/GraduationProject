export async function setupTauriWindow() {
  if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) {
    return;
  }

  try {
    const notification = await import("@tauri-apps/plugin-notification");
    const granted = await notification.isPermissionGranted();
    if (!granted) {
      await notification.requestPermission();
    }
  } catch {
    // ignore optional native setup failures in web environments
  }
}
