import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1B1B18",
        parchment: "#F3EEE0",
        emerald: {
          DEFAULT: "#123326",
          deep: "#0C241B",
          soft: "#1F4A38",
        },
        gold: {
          DEFAULT: "#B8923D",
          light: "#D8B968",
          muted: "#8A6C2C",
        },
        rani: {
          DEFAULT: "#A63A56",
          deep: "#7E2740",
        },
      },
      fontFamily: {
        display: [
          "Iowan Old Style",
          "Palatino Linotype",
          "URW Palladio L",
          "Georgia",
          "ui-serif",
          "serif",
        ],
        body: [
          "ui-sans-serif",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
      backgroundImage: {
        "thread-line":
          "repeating-linear-gradient(90deg, var(--tw-gradient-stops))",
      },
    },
  },
  plugins: [],
};

export default config;
