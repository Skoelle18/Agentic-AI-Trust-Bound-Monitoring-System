import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0d1117",
        surface: "#161b22",
        border: "#30363d",
        text: "#e6edf3",
        muted: "#7d8590",
        green: "#3fb950",
        red: "#f85149",
        yellow: "#d29922",
        blue: "#58a6ff",
        purple: "#bc8cff"
      }
    }
  },
  plugins: []
} satisfies Config;

