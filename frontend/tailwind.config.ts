import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        serif: ['"Source Serif 4"', "Georgia", "serif"],
        sans: ['"Inter"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "monospace"],
      },
      maxWidth: {
        content: "640px",
      },
      colors: {
        ink: "#1a1a1a",
        "ink-light": "#6b7280",
        "ink-faint": "#9ca3af",
        surface: "#fafaf9",
        "surface-hover": "#f5f5f4",
        accent: "#2563eb",
        "accent-hover": "#1d4ed8",
      },
    },
  },
  plugins: [],
};
export default config;
