import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// En desarrollo, /api va a la API local (python run.py). En producción la API sirve la web compilada.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: process.env.NEUROLAB_API ?? 'http://127.0.0.1:8000', changeOrigin: true } },
  },
});
