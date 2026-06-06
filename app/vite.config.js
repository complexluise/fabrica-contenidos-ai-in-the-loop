import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// Dev: proxy /api y /files al backend FastAPI (pipeline studio, puerto 8765).
// Build: sale a app/dist, que el backend sirve en el mismo origen (sin proxy).
export default defineConfig({
  plugins: [svelte()],
  build: { outDir: "dist", emptyOutDir: true },
  server: {
    proxy: {
      "/api": { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/files": { target: "http://127.0.0.1:8765", changeOrigin: true },
    },
  },
});
