import { cpSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';

const appRoot = path.dirname(fileURLToPath(import.meta.url));

/** Ship pdfjs-dist/wasm beside the packaged renderer for `vera-pdfjs://wasm/`. */
function copyPdfjsWasm(): Plugin {
  return {
    name: 'copy-pdfjs-wasm',
    apply: 'build',
    closeBundle() {
      cpSync(
        path.join(appRoot, 'node_modules', 'pdfjs-dist', 'wasm'),
        path.join(appRoot, 'dist', 'pdfjs', 'wasm'),
        { recursive: true },
      );
    },
  };
}

export default defineConfig({
  // The packaged renderer is opened from a file:// URL, so asset URLs must be
  // relative to index.html rather than rooted at the filesystem.
  base: './',
  plugins: [react(), copyPdfjsWasm()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
