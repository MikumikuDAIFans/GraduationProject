import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import "./style.css";
import { registerServiceWorker } from "@/platform/pwa";
import { setupTauriWindow } from "@/platform/tauri";

void setupTauriWindow();
void registerServiceWorker();

createApp(App).use(createPinia()).mount("#app");
