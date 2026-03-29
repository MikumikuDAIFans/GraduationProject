import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{vue,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#111827",
        "ink-2": "#374151",
        "ink-3": "#6b7280",
        surface: "#ffffff",
        "surface-2": "#f9fafb",
        "surface-3": "#f3f4f6",
        border: "#e5e7eb",
        "border-2": "#d1d5db",
        accent: {
          DEFAULT: "#4f46e5",
          hover: "#4338ca",
          light: "#eef2ff",
          muted: "#818cf8",
        },
        positive: {
          DEFAULT: "#059669",
          light: "#ecfdf5",
          hover: "#047857",
        },
        warn: {
          DEFAULT: "#d97706",
          light: "#fffbeb",
        },
        danger: {
          DEFAULT: "#dc2626",
          light: "#fef2f2",
          hover: "#b91c1c",
        },
      },
      boxShadow: {
        card: "0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04)",
        "card-md": "0 4px 12px rgba(0,0,0,0.08), 0 1px 3px rgba(0,0,0,0.04)",
        panel: "0 0 0 1px #e5e7eb, 0 4px 12px rgba(0,0,0,0.06)",
      },
      fontFamily: {
        display: ["Inter", "system-ui", "sans-serif"],
        body: ["Inter", "system-ui", "sans-serif"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      backgroundImage: {
        "app-bg": "linear-gradient(180deg, #f9fafb 0%, #ffffff 100%)",
      },
    },
  },
  plugins: [],
} satisfies Config;
