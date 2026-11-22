import { describe, expect, it } from 'vitest';

import { pdfjsWasmFilename } from './pdfjs';

describe('pdfjsWasmFilename', () => {
  it('accepts a single wasm or script name', () => {
    expect(pdfjsWasmFilename('vera-pdfjs://wasm/jbig2.wasm')).toBe('jbig2.wasm');
    expect(pdfjsWasmFilename('vera-pdfjs://wasm/openjpeg_nowasm_fallback.js')).toBe(
      'openjpeg_nowasm_fallback.js',
    );
  });

  it('rejects other hosts and path traversal', () => {
    expect(pdfjsWasmFilename('vera-pdfjs://cache/jbig2.wasm')).toBeNull();
    expect(pdfjsWasmFilename('vera-source://wasm/jbig2.wasm')).toBeNull();
    // The URL parser collapses `..` before the filename check. The result is
    // still one name inside the wasm directory, which the handler 404s unless
    // that file is actually there.
    expect(pdfjsWasmFilename('vera-pdfjs://wasm/../secret.wasm')).toBe('secret.wasm');
    expect(pdfjsWasmFilename('vera-pdfjs://wasm/nested/jbig2.wasm')).toBeNull();
    expect(pdfjsWasmFilename('vera-pdfjs://wasm/%2E%2E%2Fsecret.wasm')).toBeNull();
    expect(pdfjsWasmFilename('vera-pdfjs://wasm/jbig2.wasm%2F..%2Fsecret')).toBeNull();
    expect(pdfjsWasmFilename('not a url')).toBeNull();
  });
});
