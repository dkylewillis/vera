import { SIDECAR_ACTIONS } from '../../shared/protocol';
import { useEffect, useRef, useState } from 'react';
import { Download, Loader2 } from 'lucide-react';
import type { OcrLanguageStatus, OcrLanguagesDownloadResult, OcrLanguagesListResult } from '../types';

function formatSize(bytes: number | undefined): string {
  if (!bytes) return '';
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

let requestCounter = 0;
function nextRequestId(prefix: string): string {
  requestCounter += 1;
  return `${prefix}-${Date.now()}-${requestCounter}`;
}

/**
 * Shows bundled/cached/downloadable status for the codes in `language` (a
 * '+'-joined Tesseract language spec, e.g. "eng" or "eng+fra") and lets the
 * user pre-fetch missing ones with progress, independent of running a
 * conversion. Renders nothing while the pipeline isn't Tesseract-based.
 */
export function OcrLanguagePackManager({
  language,
  disabled = false,
}: {
  language: string;
  disabled?: boolean;
}) {
  const [statuses, setStatuses] = useState<OcrLanguageStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloadingCode, setDownloadingCode] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ downloaded: number; total: number } | null>(null);
  const requestIdRef = useRef<string | null>(null);

  const normalized = language.trim();

  useEffect(() => {
    if (!normalized) {
      setStatuses(null);
      return;
    }
    let cancelled = false;
    void window.vera
      .request<OcrLanguagesListResult>({ action: SIDECAR_ACTIONS.ocrLanguagesList, language: normalized })
      .then((response) => {
        if (cancelled) return;
        if (response.ok && response.result) {
          setStatuses(response.result.languages);
          setError(null);
        } else {
          setError(response.error || 'Unable to check OCR language status');
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Unable to check OCR language status');
      });
    return () => {
      cancelled = true;
    };
  }, [normalized]);

  async function downloadLanguage(code: string) {
    const requestId = nextRequestId('ocr-download');
    requestIdRef.current = requestId;
    setDownloadingCode(code);
    setProgress(null);
    setError(null);
    const offProgress = window.vera.onAnswerEvent((event) => {
      if (event.id !== requestId || event.event !== 'ocr_download_progress') return;
      setProgress({ downloaded: event.downloaded ?? 0, total: event.total ?? 0 });
    });
    try {
      const response = await window.vera.request<OcrLanguagesDownloadResult>(
        { action: SIDECAR_ACTIONS.ocrLanguagesDownload, language: code },
        requestId,
      );
      if (!response.ok) {
        throw new Error(response.error || `Unable to download OCR language data for ${code}`);
      }
      const refreshed = await window.vera.request<OcrLanguagesListResult>({
        action: SIDECAR_ACTIONS.ocrLanguagesList,
        language: normalized,
      });
      if (refreshed.ok && refreshed.result) setStatuses(refreshed.result.languages);
    } catch (err) {
      setError(err instanceof Error ? err.message : `Unable to download OCR language data for ${code}`);
    } finally {
      offProgress();
      requestIdRef.current = null;
      setDownloadingCode(null);
      setProgress(null);
    }
  }

  if (!normalized || !statuses || statuses.every((entry) => entry.bundled)) {
    return null;
  }

  return (
    <div className="ocrLanguagePacks">
      {statuses.map((entry) => {
        if (entry.bundled || entry.cached) {
          return (
            <p className="sideMuted" key={entry.code}>
              {entry.name} ({entry.code}): {entry.bundled ? 'bundled with VERA' : 'downloaded and cached'}.
            </p>
          );
        }
        const isDownloading = downloadingCode === entry.code;
        return (
          <div className="ocrLanguagePackRow" key={entry.code}>
            <p className="sideMuted">
              {entry.name} ({entry.code}) is not available yet
              {entry.downloadable ? ` (${formatSize(entry.size_bytes)})` : ''}.
              {!entry.downloadable
                ? ' Install a Tesseract .traineddata file manually and set TESSDATA_PREFIX.'
                : ''}
            </p>
            {entry.downloadable ? (
              <button
                className="secondaryAction compactAction"
                disabled={disabled || isDownloading}
                onClick={() => void downloadLanguage(entry.code)}
              >
                {isDownloading ? <Loader2 size={14} className="spinning" /> : <Download size={14} />}
                {isDownloading
                  ? progress && progress.total
                    ? `Downloading… ${Math.min(100, Math.round((progress.downloaded / progress.total) * 100))}%`
                    : 'Downloading…'
                  : `Download ${entry.name}`}
              </button>
            ) : null}
          </div>
        );
      })}
      {error ? <p className="sideMuted" role="alert">{error}</p> : null}
    </div>
  );
}
