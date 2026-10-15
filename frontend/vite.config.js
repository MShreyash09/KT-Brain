import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// /api is the FastAPI backend: cd backend && uv run uvicorn app:app   (KT_API points it elsewhere)
export default defineConfig({ plugins: [react()], server: { proxy: { "/api": process.env.KT_API ?? "http://localhost:8000" } } });
