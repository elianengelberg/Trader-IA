import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API serves the built output from the same origin, so production needs no proxy and
// no CORS. `npm run dev` proxies to a locally running API instead, which keeps the
// development and production request paths identical (`/api/...` in both).
export default defineConfig({
  plugins: [react()],
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 900 },
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        // SSE must not be buffered by the dev proxy or the dashboard looks frozen.
        configure: (proxy) => {
          proxy.on("proxyRes", (proxyRes) => {
            if (proxyRes.headers["content-type"]?.includes("text/event-stream")) {
              proxyRes.headers["cache-control"] = "no-cache";
            }
          });
        },
      },
    },
  },
});
