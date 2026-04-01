import { describe, expect, it } from "vitest";
import { MobileNotificationService } from "@/plugins/capacitor";

describe("Capacitor Mobile Features", () => {
  it("should expose mobile notification service", () => {
    expect(MobileNotificationService).toBeDefined();
  });

  it("should report non-native environment in web tests", () => {
    expect(MobileNotificationService.isNative()).toBe(false);
  });
});
