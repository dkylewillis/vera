import { useEffect, useState } from 'react';
import { Library, X } from 'lucide-react';
import { loadLibraryTrash, restoreLibraryEntry } from '../lib/managedLibrary';
import type { LibraryTrashEntry } from '../types';

export function AdoptLibraryModal({
  prompt,
  onAdopt,
  onSkip,
}: {
  prompt: { path: string; count: number } | null;
  onAdopt: () => void;
  onSkip: () => void;
}) {
  if (!prompt) return null;
  return (
    <div className="modalBackdrop" onClick={onSkip}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="adopt-library-title" onClick={(event) => event.stopPropagation()}>
        <header className="modalHeader">
          <h2 id="adopt-library-title"><Library size={18} /> Move existing archives into the library?</h2>
          <button className="iconAction" onClick={onSkip} title="Close"><X size={17} /></button>
        </header>
        <div className="libraryIndexModalBody">
          <p>
            {prompt.count === 1
              ? 'One .vera file sits next to its document and matches it.'
              : `${prompt.count} .vera files sit next to their documents and match them.`}
            {' '}VERA can move {prompt.count === 1 ? 'it' : 'them'} into the hidden library folder so this directory stays uncluttered.
          </p>
        </div>
        <footer className="modalFooter">
          <span className="modalMessage" />
          <div className="modalFooterActions">
            <button className="secondaryAction" onClick={onSkip}>Leave them</button>
            <button className="primaryAction" onClick={onAdopt}>Move into library</button>
          </div>
        </footer>
      </div>
    </div>
  );
}

export function LibraryTrashModal({
  folderPath,
  onClose,
  onRestored,
}: {
  folderPath: string | null;
  onClose: () => void;
  onRestored: () => void;
}) {
  const [entries, setEntries] = useState<LibraryTrashEntry[]>([]);
  const [message, setMessage] = useState('');
  useEffect(() => {
    if (!folderPath) return;
    let cancelled = false;
    void loadLibraryTrash(folderPath, (payload) => window.vera.request(payload)).then((next) => {
      if (!cancelled) setEntries(next);
    });
    return () => { cancelled = true; };
  }, [folderPath]);
  if (!folderPath) return null;
  return (
    <div className="modalBackdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="library-trash-title" onClick={(event) => event.stopPropagation()}>
        <header className="modalHeader">
          <h2 id="library-trash-title"><Library size={18} /> Library trash</h2>
          <button className="iconAction" onClick={onClose} title="Close"><X size={17} /></button>
        </header>
        <div className="libraryIndexModalBody">
          {entries.length === 0 ? <p>Nothing in library trash.</p> : (
            <ul>
              {entries.map((entry) => (
                <li key={entry.entry}>
                  {entry.source_path}
                  {' '}
                  <button
                    className="secondaryAction"
                    onClick={() => {
                      void restoreLibraryEntry(folderPath, entry.entry, (payload) => window.vera.request(payload)).then((ok) => {
                        setMessage(ok ? `Restored ${entry.source_path}` : 'Could not restore that document');
                        if (ok) {
                          setEntries((current) => current.filter((item) => item.entry !== entry.entry));
                          onRestored();
                        }
                      });
                    }}
                  >
                    Restore
                  </button>
                </li>
              ))}
            </ul>
          )}
          {message ? <p className="sideMuted">{message}</p> : null}
        </div>
        <footer className="modalFooter">
          <span className="modalMessage" />
          <div className="modalFooterActions">
            <button className="primaryAction" onClick={onClose}>Close</button>
          </div>
        </footer>
      </div>
    </div>
  );
}
