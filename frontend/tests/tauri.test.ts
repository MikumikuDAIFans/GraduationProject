import config from "../src-tauri/tauri.conf.json";
import { describe, expect, it } from "vitest";

describe("Tauri Desktop Features", () => {
  it("should expose tauri configuration files", () => {
    expect(config.productName).toBe("ma-ipaas-desktop");
  });
});
