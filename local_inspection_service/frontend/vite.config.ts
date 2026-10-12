import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => ({
  base: "/react-preview/",
  define: {
    __VANTALINE_RELEASE_IDENTITY__: JSON.stringify(`VANTALINE_RELEASE:${loadEnv(mode, ".", "VITE_").VITE_RELEASE_ID || "development"}:${loadEnv(mode, ".", "VITE_").VITE_GIT_COMMIT || "unknown"}`)
  },
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: false
  },
  server: {
    host: "0.0.0.0",
    port: 5173
  }
}));
