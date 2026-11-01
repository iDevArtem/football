/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        tg: {
          bg: "var(--tg-theme-bg-color, #0f172a)",
          text: "var(--tg-theme-text-color, #f8fafc)",
          hint: "var(--tg-theme-hint-color, #94a3b8)",
          link: "var(--tg-theme-link-color, #38bdf8)",
          button: "var(--tg-theme-button-color, #10b981)",
          buttonText: "var(--tg-theme-button-text-color, #ffffff)",
          secondaryBg: "var(--tg-theme-secondary-bg-color, #1e293b)",
        },
      },
    },
  },
  plugins: [],
};
