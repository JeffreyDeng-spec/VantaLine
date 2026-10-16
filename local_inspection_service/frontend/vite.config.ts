import { defineConfig, loadEnv, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

function publicModelBoundary(): Plugin {
  return {
    name: "public-model-boundary",
    generateBundle(_options, bundle) {
      const identity = /yolo|ultralytics|gemini|doubao|豆包|qwen|千问|codex|agnes|api\.cursor\.com|sam(?:[-_ ]?\d|\b)|paddleocr|paddlepaddle|dashscope|volcengine|runpod|generativelanguage|openai|anthropic|claude|gpt[-_ ]?(?:\d|image)|seedream|seededit|seedance|dall[-_ ]?e|imagen(?:[-_ ]?\d|\b)/i;
      for (const [name, item] of Object.entries(bundle)) {
        if (name.split("/").pop()?.startsWith("admin-")) continue;
        if (!/\.(?:js|html|css|json|map)$/.test(name)) continue;
        const body = item.type === "chunk" ? item.code : String(item.source);
        if (identity.test(body) || name.endsWith(".map")) this.error(`Public asset violates model privacy: ${name}`);
      }
    }
  };
}

export default defineConfig(({ mode }) => ({
  base: "/react-preview/",
  define: {
    __VANTALINE_RELEASE_IDENTITY__: JSON.stringify(`VANTALINE_RELEASE:${loadEnv(mode, ".", "VITE_").VITE_RELEASE_ID || "development"}:${loadEnv(mode, ".", "VITE_").VITE_GIT_COMMIT || "unknown"}`)
  },
  plugins: [react(), publicModelBoundary()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      output: {
        assetFileNames: (asset) => asset.names.some(name => name.startsWith("Admin")) ? "assets/admin-[hash][extname]" : "assets/[name]-[hash][extname]",
        chunkFileNames: (chunk) => chunk.name.startsWith("Admin") ? "assets/admin-[hash].js" : "assets/[name]-[hash].js"
      }
    }
  },
  server: {
    host: "0.0.0.0",
    port: 5173
  }
}));
