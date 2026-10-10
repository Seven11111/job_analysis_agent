import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#12233f",
        mist: "#f5f9fc",
        brand: "#1688d8",
        mint: "#dff6f0",
      },
    },
  },
  plugins: [],
} satisfies Config;
