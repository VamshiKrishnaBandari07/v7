/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#efe6d8",
        card: "#fbf7f0",
        ink: "#241c16",
        moss: "#0e6b52",
        clay: "#b6401a",
        line: "#e3d5c4",
        lab: {
          bg: "#0b1220",
          panel: "#10182a",
          panel2: "#162033",
          line: "#2a3a52",
          text: "#e6eef8",
          muted: "#93a4bd",
          cyan: "#7fd3e8",
          violet: "#b7a6ff",
          amber: "#e2b15a",
          fail: "#e15b4c",
          ok: "#8fd0a8",
        },
      },
      fontFamily: {
        serif: ["var(--font-serif)", "Georgia", "serif"],
        sans: ["var(--font-sans)", "Segoe UI", "sans-serif"],
        mono: ["var(--font-mono)", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
