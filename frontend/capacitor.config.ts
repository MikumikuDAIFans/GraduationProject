import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.maipaas.mobile",
  appName: "MA-IPAAS",
  webDir: "dist",
  server: {
    androidScheme: "https",
  },
  plugins: {
    PushNotifications: {
      presentationOptions: ["badge", "sound", "alert"],
    },
    StatusBar: {
      style: "dark",
      backgroundColor: "#ffffff",
    },
  },
};

export default config;
