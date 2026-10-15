import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// /api is the FastAPI backend: cd backend && uv run uvicorn app:app
export default defineConfig({ plugins: [react()], server: { proxy: { "/api": "http://localhost:8000" } } });
