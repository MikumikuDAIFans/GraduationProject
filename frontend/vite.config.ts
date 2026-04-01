import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [vue()],
  build: {
    target: "es2020",
    cssCodeSplit: true,
    chunkSizeWarningLimit: 650,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules")) {
            if (id.includes("@fullcalendar")) return "calendar";
            if (id.includes("vue") || id.includes("pinia")) return "framework";
            if (id.includes("marked")) return "markdown";
            return "vendor";
          }
          return undefined;
        },
      },
    },
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    host: "127.0.0.1",
    port: 8888,
    strictPort: true,
  },
});
