import { Library, X } from 'lucide-react';
import { fileName } from '../lib/formatting';
import type { NestedLibraryConflict } from '../lib/workspaceFolders';

export function NestedLibraryModal({
  conflict,
  onSearchFolder,
  onUseOuterLibrary,
  onAddAnyway,
  onDismiss,
}: {
  conflict: NestedLibraryConflict | null;
  onSearchFolder: (library: string, folderPath: string) => void;
  onUseOuterLibrary: (folderPath: string, innerLibraries: string[]) => void;
  onAddAnyway: (folderPath: string) => void;
  onDismiss: () => void;
}) {
  if (!conflict) return null;
  const name = fileName(conflict.path) || conflict.path;
  const innerNames = conflict.kind === 'contains'
    ? conflict.libraries.map((library) => `“${fileName(library) || library}”`).join(', ')
    : '';
  return (
    <div className="modalBackdrop" onClick={onDismiss}>
      <div
        className="modal nestedLibraryModal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="nested-library-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="modalHeader">
          <h2 id="nested-library-title">
            <Library size={18} />
            {conflict.kind === 'inside' ? 'This folder is already in a library' : 'This folder contains a library'}
          </h2>
          <button className="iconAction" onClick={onDismiss} title="Close"><X size={17} /></button>
        </header>
        <div className="libraryIndexModalBody">
          {conflict.kind === 'inside' ? (
            <>
              <p>
                “{name}” is part of the “{fileName(conflict.library) || conflict.library}” library. You can search
                just this folder there, without a second index to keep up to date.
              </p>
              <p className="sideMuted">
                Adding it as its own library shows these documents twice in Explorer and indexes them twice.
              </p>
            </>
          ) : (
            <>
              <p>
                “{name}” contains {conflict.libraries.length === 1 ? 'the library' : 'the libraries'} {innerNames}.
                Use “{name}” instead and {conflict.libraries.length === 1 ? 'that library is' : 'those libraries are'} shown
                inside it, where you can still search {conflict.libraries.length === 1 ? 'it' : 'each one'} on its own.
              </p>
              <p className="sideMuted">
                Keeping both shows those documents twice in Explorer and indexes them twice.
              </p>
            </>
          )}
        </div>
        <footer className="modalFooter">
          <span className="modalMessage" />
          <div className="modalFooterActions">
            <button className="secondaryAction" onClick={() => onAddAnyway(conflict.path)}>
              {conflict.kind === 'inside' ? 'Add as separate library' : 'Keep both'}
            </button>
            {conflict.kind === 'inside' ? (
              <button className="primaryAction" onClick={() => onSearchFolder(conflict.library, conflict.path)}>
                Search this folder
              </button>
            ) : (
              <button className="primaryAction" onClick={() => onUseOuterLibrary(conflict.path, conflict.libraries)}>
                Use “{name}”
              </button>
            )}
          </div>
        </footer>
      </div>
    </div>
  );
}
