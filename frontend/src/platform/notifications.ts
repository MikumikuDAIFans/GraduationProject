export function isTauriEnvironment() {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}


export async function sendPlatformNotification(title: string, body: string) {
  if (isTauriEnvironment()) {
    const plugin = await import("@tauri-apps/plugin-notification");
    await plugin.sendNotification({ title, body });
    return;
  }

  try {
    const core = await import("@capacitor/core");
    if (core.Capacitor.isNativePlatform()) {
      const localNotifications = await import("@capacitor/local-notifications");
      await localNotifications.LocalNotifications.schedule({
        notifications: [
          {
            id: Date.now(),
            title,
            body,
            schedule: { at: new Date(Date.now() + 1000) },
          },
        ],
      });
      return;
    }
  } catch {
    // fall through to browser notifications
  }

  if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "granted") {
    new Notification(title, { body });
  }
}
