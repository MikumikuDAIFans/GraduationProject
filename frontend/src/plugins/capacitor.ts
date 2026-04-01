import { Capacitor } from "@capacitor/core";
import { LocalNotifications } from "@capacitor/local-notifications";
import { PushNotifications } from "@capacitor/push-notifications";


export class MobileNotificationService {
  static isNative() {
    return Capacitor.isNativePlatform();
  }

  static async registerPushNotifications(): Promise<void> {
    if (!this.isNative()) {
      return;
    }

    await PushNotifications.requestPermissions();
    await PushNotifications.register();
  }

  static async scheduleLocalReminder(
    id: number,
    title: string,
    body: string,
    scheduledAt: Date,
  ): Promise<void> {
    if (!this.isNative()) {
      return;
    }

    await LocalNotifications.schedule({
      notifications: [
        {
          id,
          title,
          body,
          schedule: { at: scheduledAt },
        },
      ],
    });
  }
}
