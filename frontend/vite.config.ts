import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const srsProxyTarget = process.env.SRS_WEBRTC_PROXY_TARGET || "http://srs:1985";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/srs-api": {
        target: srsProxyTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/srs-api/, "")
      }
    }
  }
});
