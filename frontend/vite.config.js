import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// /api is the local FastAPI backend (cd backend && uv run uvicorn app:app), which reads the local FalkorDB.
// Production goes through vercel.json to Render, which reads FalkorDB Cloud. KT_API points dev at another backend.
const proxy = { "/api": { target: process.env.KT_API ?? "http://localhost:8000", changeOrigin: true } };
export default defineConfig({ plugins: [react()], server: { proxy }, preview: { proxy } });
