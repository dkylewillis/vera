import { PDFJS_WASM_URL } from '../../shared/pdfjs';

/**
 * `pdfjsLib.getDocument` source for the desktop viewer.
 *
 * `enableScripting` must stay false: PDF.js 6.0.x defaulted it on, which is
 * CVE-2026-16633 (arbitrary JS from a malicious PDF in the hosting page).
 *
 * `wasmUrl` must stay set. PDF.js 6 decodes JBIG2, JPEG2000, and CCITT through
 * that directory; without it those images are dropped and scanned sheets
 * render blank. `useWorkerFetch` stays false so the renderer, which can read
 * `vera-source:` and `vera-pdfjs:`, loads the PDF and the wasm bytes.
 */
export function pdfDocumentSource(url: string) {
  return {
    url,
    wasmUrl: PDFJS_WASM_URL,
    useWorkerFetch: false,
    enableScripting: false,
  };
}
