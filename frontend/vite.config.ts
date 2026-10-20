import { execSync } from "node:child_process";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The commit a production build comes from, so the app can warn when the page is older than the code.
// The dev server reloads code as it changes, so it reports "dev" instead.
function buildSha(): string {
  if (process.env.WEBDATA_BUILD_SHA) return process.env.WEBDATA_BUILD_SHA;
  try {
    return execSync("git rev-parse HEAD", { stdio: ["ignore", "pipe", "ignore"] }).toString().trim();
  } catch {
    return "unknown";
  }
}

// In development the API runs on :8000 and Vite proxies /api to it, so cookies stay same-origin.
export default defineConfig(({ command }) => ({
  plugins: [react()],
  define: { __BUILD_SHA__: JSON.stringify(command === "build" ? buildSha() : "dev") },
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.VITE_API_TARGET ?? "http://localhost:8000", changeOrigin: false } },
  },
}));
