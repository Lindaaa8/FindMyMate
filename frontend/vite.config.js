import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import crypto from 'node:crypto';

// Fallback polyfill for older Node.js versions
if (!crypto.hash) {
  crypto.hash = (algorithm, data, outputEncoding = 'hex') =>
    crypto.createHash(algorithm).update(data).digest(outputEncoding);
}

// In dev, Vite serves the UI on :5173 and proxies API + uploaded photos to Flask on :5000.
// Flask routes already start with /api, so the path is forwarded unchanged (no rewrite).
const API = process.env.VITE_API_URL || 'http://127.0.0.1:5000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: API, changeOrigin: true },
      '/uploads': { target: API, changeOrigin: true },
    },
  },
  build: { outDir: 'dist', emptyOutDir: true },
});
