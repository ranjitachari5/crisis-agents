/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    fontFamily: {
      sans: ["ui-sans-serif", "system-ui", "sans-serif"],
    },
    extend: {
      colors: {
        bg: "#0B0B0C",
        surface: "#111113",
        "surface-2": "#17171A",
        border: "#26262B",
        text: "#F4F4F5",
        muted: "#8B8B94",
        accent: "#E5484D",
        "accent-dim": "rgba(229, 72, 77, 0.15)",
        ok: "#4ADE80",
      },
      fontSize: {
        11: ["11px", { lineHeight: "16px", letterSpacing: "0.08em" }],
        12: ["12px", { lineHeight: "16px" }],
        13: ["13px", { lineHeight: "18px" }],
        14: ["14px", { lineHeight: "20px" }],
        16: ["16px", { lineHeight: "24px" }],
        20: ["20px", { lineHeight: "28px" }],
        28: ["28px", { lineHeight: "32px" }],
      },
      borderRadius: {
        panel: "6px",
        control: "4px",
      },
      spacing: {
        4.5: "18px",
      },
    },
  },
  plugins: [],
};
