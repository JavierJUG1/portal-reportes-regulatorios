import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// En desarrollo, /api se envía al backend FastAPI (puerto 8000).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: false },
    },
  },
  // Rutas relativas: el mismo compilado sirve en la raíz o en una subruta (BASE_PATH del backend, vía <base href>).
  base: "./",
  build: { outDir: "dist", sourcemap: false },
});
