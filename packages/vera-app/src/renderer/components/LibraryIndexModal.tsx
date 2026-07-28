import { AlertTriangle, Database, X } from 'lucide-react';
import type { LibraryIndexBuildReport, LibraryIndexStatus } from '../types';

export type IndexPrompt = { path: string; status: LibraryIndexStatus };

export function LibraryIndexModal({
  prompt,
  report,
  recursive,
  excludes,
  onRecursiveChange,
  onExcludesChange,
  onConfirm,
  onDismiss,
}: {
  prompt: IndexPrompt | null;
  report: LibraryIndexBuildReport | null;
  recursive: boolean;
  excludes: string;
  onRecursiveChange: (value: boolean) => void;
  onExcludesChange: (value: string) => void;
  onConfirm: () => void;
  onDismiss: () => void;
}) {
  if (!prompt && !report) return null;
  const isUpdate = Boolean(prompt?.status.exists);
  return (
    <div className="modalBackdrop" onClick={onDismiss}>
      <div className="modal libraryIndexModal" onClick={(event) => event.stopPropagation()}>
        <header className="modalHeader">
          <h2><Database size={18} />{report ? 'Library index ready' : isUpdate ? 'Update library index?' : 'Build library index?'}</h2>
          <button className="iconAction" onClick={onDismiss} title="Close"><X size={17} /></button>
        </header>
        <div className="libraryIndexModalBody">
          {report ? (
            <>
              <p>Indexed <strong>{report.indexed}</strong> of {report.discovered} archives with {report.chunks.toLocaleString()} searchable chunks.</p>
              {report.skipped ? (
                <div className="indexReportWarning">
                  <AlertTriangle size={16} />
                  <span>{report.skipped} archive{report.skipped === 1 ? ' was' : 's were'} skipped.</span>
                </div>
              ) : null}
              {[...report.invalid, ...report.incompatible].map((entry) => (
                <div className="indexSkippedFile" key={`${entry.file}:${entry.reason}`}>
                  <strong>{entry.file}</strong><span>{entry.reason}</span>
                </div>
              ))}
            </>
          ) : (
            <>
              <p>
                {isUpdate
                  ? 'This library changed after its index was built. Update it for fast whole-library search.'
                  : 'Build a local index for fast whole-library search. You can still search recursively without one.'}
              </p>
              {prompt?.status.reasons.length ? (
                <div className="indexReasons">{prompt.status.reasons.map((reason) => <span key={reason}>{reason}</span>)}</div>
              ) : null}
              {!isUpdate ? (
                <>
                  <label className="miniCheck">
                    <input type="checkbox" checked={recursive} onChange={(event) => onRecursiveChange(event.target.checked)} />
                    <span>Include nested folders (Recursive)</span>
                  </label>
                  <label className="field">
                    <span>Exclusions (one folder, file, or glob pattern per line)</span>
                    <textarea rows={4} value={excludes} onChange={(event) => onExcludesChange(event.target.value)} placeholder={'archive\n**/drafts/**'} />
                  </label>
                </>
              ) : (
                <p className="sideMuted">Saved settings: {prompt?.status.recursive ? 'recursive' : 'top-level only'}{prompt?.status.excludes?.length ? `; ${prompt.status.excludes.length} exclusion(s)` : ''}.</p>
              )}
            </>
          )}
        </div>
        <footer className="modalFooter">
          <span className="modalMessage">{report?.skipped ? 'Skipped archives are listed above.' : ''}</span>
          <div className="modalFooterActions">
            {!report ? <button className="secondaryAction" onClick={onDismiss}>Search anyway</button> : null}
            <button className="primaryAction" onClick={report ? onDismiss : onConfirm}>
              {report ? 'Done' : isUpdate ? 'Update index' : 'Build index'}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
