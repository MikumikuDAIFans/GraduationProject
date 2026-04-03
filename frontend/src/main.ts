import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import "./style.css";
import { registerServiceWorker } from "@/platform/pwa";
import { setupTauriWindow } from "@/platform/tauri";
import { i18n } from "@/i18n";

void setupTauriWindow();
void registerServiceWorker();

const app = createApp(App);

// Global error handler to prevent unhandled errors from crashing the app
app.config.errorHandler = (err, instance, info) => {
  console.error("Global error caught:", err, info);
  // In production, you could send this to a monitoring service like Sentry
};

app.use(createPinia()).use(i18n).mount("#app");
