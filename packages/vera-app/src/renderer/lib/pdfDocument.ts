/**
 * `pdfjsLib.getDocument` source for the desktop viewer.
 *
 * `enableScripting` must stay false: PDF.js 6.0.x defaulted it on, which is
 * CVE-2026-16633 (arbitrary JS from a malicious PDF in the hosting page).
 */
export function pdfDocumentSource(url: string) {
  return {
    url,
    useWorkerFetch: false,
    enableScripting: false,
  };
}
