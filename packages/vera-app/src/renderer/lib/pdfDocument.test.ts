import { describe, expect, it } from 'vitest';

import { pdfDocumentSource } from './pdfDocument';

describe('pdfDocumentSource', () => {
  it('disables PDF.js scripting so malicious PDFs cannot run page JS', () => {
    expect(pdfDocumentSource('vera-pdf://doc.pdf')).toEqual({
      url: 'vera-pdf://doc.pdf',
      useWorkerFetch: false,
      enableScripting: false,
    });
  });
});
