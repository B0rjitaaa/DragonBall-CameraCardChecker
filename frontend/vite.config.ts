import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// En desarrollo (`npm run dev`) se hace proxy al backend expuesto en :8000.
const backend = process.env.VITE_BACKEND_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": backend,
      "/media": backend,
    },
  },
});
