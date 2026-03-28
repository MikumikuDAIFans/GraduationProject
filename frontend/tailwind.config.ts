import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{vue,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1a1f2e",
        mist: "#f4efe6",
        surface: "#ffffff",
        "surface-2": "#f8fafc",
        accent: {
          DEFAULT: "#4f46e5",
          light: "#eef2ff",
          muted: "#818cf8",
        },
        positive: {
          DEFAULT: "#059669",
          light: "#ecfdf5",
        },
        warn: {
          DEFAULT: "#d97706",
          light: "#fffbeb",
        },
        danger: {
          DEFAULT: "#dc2626",
          light: "#fef2f2",
        },
        ember: "#d97706",
        teal: "#0f766e",
        plum: "#7c2d92",
        slateblue: "#355c7d",
      },
      boxShadow: {
        panel: "0 24px 80px rgba(17, 33, 45, 0.14)",
      },
      borderRadius: {
        "4xl": "2rem",
      },
      fontFamily: {
        display: ["Inter", "system-ui", "sans-serif"],
        body: ["Inter", "system-ui", "sans-serif"],
      },
      backgroundImage: {
        "hero-wash":
          "radial-gradient(ellipse at top left, rgba(79,70,229,0.07), transparent 40%), radial-gradient(ellipse at bottom right, rgba(5,150,105,0.06), transparent 40%), linear-gradient(160deg, #f0f4ff 0%, #f8fafc 50%, #f0fdf4 100%)",
      },
    },
  },
  plugins: [],
} satisfies Config;
