/**
 * PDF.js 6 loads JBIG2, JPEG2000, and CCITT decoders from `wasmUrl`.
 * The desktop viewer serves that directory on this privileged scheme because
 * the renderer origin is `file:` when packaged and `vera-source:` is not a
 * URL the worker can fetch itself.
 */
export const PDFJS_WASM_URL = 'vera-pdfjs://wasm/';

const WASM_FILE = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;

/** Filename addressed by a `vera-pdfjs://wasm/<file>` request, or null. */
export function pdfjsWasmFilename(requestUrl: string): string | null {
  let parsed: URL;
  try {
    parsed = new URL(requestUrl);
  } catch {
    return null;
  }
  const expected = new URL(PDFJS_WASM_URL);
  if (parsed.protocol !== expected.protocol || parsed.hostname !== expected.hostname) {
    return null;
  }
  let name: string;
  try {
    name = decodeURIComponent(parsed.pathname.replace(/^\/+/, ''));
  } catch {
    return null;
  }
  if (!WASM_FILE.test(name)) return null;
  return name;
}
