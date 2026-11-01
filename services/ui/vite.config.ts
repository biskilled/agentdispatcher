import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

export default defineConfig(({ mode }) => {
  const env = { ...loadEnv(mode, process.cwd(), ""), ...process.env };
  return {
    root: fileURLToPath(new URL(".", import.meta.url)),
    publicDir: fileURLToPath(new URL("../../third_party", import.meta.url)),
    plugins: [react()],
    server: {
      host: env.UI_HOST || "127.0.0.1",
      port: Number(env.UI_PORT || 5173),
      strictPort: true,
      proxy: env.BACKEND_URL
        ? { "/api": env.BACKEND_URL, "/health": env.BACKEND_URL }
        : undefined,
    },
    build: { outDir: "../../dist/ui", emptyOutDir: true },
  };
});
