import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During development the frontend calls same-origin "/api/*" and Vite proxies
// those requests to the FastAPI service on :8000 — so no CORS setup is needed.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
