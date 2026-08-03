import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

/**
 * Base is relative ("./") because in production the shell loads this build
 * via `loadFile()` from the local filesystem (file://), not from an http
 * origin — absolute-rooted asset paths would 404 under file://.
 *
 * Dev server port (5173) matches `DEV_SERVER_URL` in
 * apps/shell/src/main/index.ts by convention; override both together via
 * JARVIS_RENDERER_DEV_URL if you ever need to change it.
 */
export default defineConfig({
  base: "./",
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    target: "esnext",
    rollupOptions: {
      output: {
        // Keep three.js/R3F in their own chunk — it's the heaviest
        // dependency and rarely changes relative to app code, so this
        // maximizes browser cache hits across renderer updates.
        manualChunks: {
          three: ["three", "@react-three/fiber", "@react-three/drei"],
        },
      },
    },
  },
});
