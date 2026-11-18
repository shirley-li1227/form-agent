import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 统一同源：开发/预览由 vite 代理 /api，生产由 nginx 反代 /api 到网关
// 本机 3000 被其他项目占用，网关改用 3111（仅影响 dev/preview，生产走 nginx）
const proxy = {
  "/api": {
    target: "http://127.0.0.1:3111",
    changeOrigin: true,
  },
};

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    allowedHosts: true,
    proxy,
  },
  preview: {
    port: 4173,
    allowedHosts: true,
    proxy,
  },
});
