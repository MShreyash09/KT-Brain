import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// /api is the FastAPI backend: defaults to deployed Render instance, or local if KT_API is set
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: process.env.KT_API ?? "https://kt-brain.onrender.com",
        changeOrigin: true,
      },
    },
  },
  preview: {
    proxy: {
      "/api": {
        target: process.env.KT_API ?? "https://kt-brain.onrender.com",
        changeOrigin: true,
      },
    },
  },
});
