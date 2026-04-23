import { defineConfig } from 'astro/config';

export default defineConfig({
  // Static site (no server-side rendering needed)
  output: 'static',
  
  // Configure dev server to listen on all interfaces
  server: {
    port: 3000,
    host: '0.0.0.0'  // Listen on all interfaces, not just localhost
  },
  
  // Allow CORS for Flask backend
  vite: {
    server: {
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:5000',
          changeOrigin: true
        }
      }
    }
  }
});
