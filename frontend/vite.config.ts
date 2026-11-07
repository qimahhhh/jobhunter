import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// GitHub Pages 项目页地址是 https://<user>.github.io/jobhunter/，
// 所以生产构建的资源前缀用 /jobhunter/；本地 dev 仍从根路径 / 提供服务。
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: mode === "production" ? "/jobhunter/" : "/",
  server: { port: 5173, open: false },
}));
