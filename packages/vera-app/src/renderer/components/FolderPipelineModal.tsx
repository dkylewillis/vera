import { useEffect, useState } from 'react';
import { Library, X } from 'lucide-react';
import type { PdfPipelineChoice } from '../lib/libraryPipelines';

/** Choice value meaning "no rule here; use the parent folder's pipeline". */
const INHERIT = '';

export type FolderPipelinePrompt = {
  title: string;
  /** Shown under the title, for example the folder path. */
  subtitle?: string;
  choices: PdfPipelineChoice[];
  /** Initially selected spec, or `''` to follow the parent. */
  selected: string;
  /** When set, offers an option to follow the parent folder, described by this text. */
  inheritLabel?: string;
  inheritTitle?: string;
  saveLabel: string;
  cancelLabel?: string;
};

export function FolderPipelineModal({
  prompt,
  busy = false,
  onSave,
  onCancel,
}: {
  prompt: FolderPipelinePrompt | null;
  busy?: boolean;
  /** `null` means follow the parent folder. */
  onSave: (parser: string | null) => void;
  onCancel: () => void;
}) {
  const [selected, setSelected] = useState(prompt?.selected ?? INHERIT);
  useEffect(() => {
    setSelected(prompt?.selected ?? INHERIT);
  }, [prompt]);
  if (!prompt) return null;
  const options: (PdfPipelineChoice | null)[] = prompt.inheritLabel !== undefined
    ? [null, ...prompt.choices]
    : prompt.choices;

  return (
    <div className="modalBackdrop" onClick={busy ? undefined : onCancel}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="folder-pipeline-title" onClick={(event) => event.stopPropagation()}>
        <header className="modalHeader">
          <h2 id="folder-pipeline-title"><Library size={18} /> {prompt.title}</h2>
          <button className="iconAction" onClick={onCancel} title="Close"><X size={17} /></button>
        </header>
        <div className="libraryIndexModalBody">
          {prompt.subtitle ? <p className="folderPipelineSubtitle">{prompt.subtitle}</p> : null}
          <div className="folderPipelineChoices" role="radiogroup" aria-labelledby="folder-pipeline-title">
            {options.map((choice) => {
              const value = choice?.spec ?? INHERIT;
              return (
                <label key={value || 'inherit'} className={`folderPipelineChoice${selected === value ? ' selected' : ''}`}>
                  <input
                    type="radio"
                    name="folder-pipeline"
                    value={value}
                    checked={selected === value}
                    disabled={busy}
                    onChange={() => setSelected(value)}
                  />
                  <span>
                    <strong>{choice ? choice.label : prompt.inheritTitle ?? 'Same as parent folder'}</strong>
                    <small>{choice ? choice.description : prompt.inheritLabel}</small>
                    {choice?.alsoReads.length ? (
                      <small>Also converts {choice.alsoReads.join(', ')} files here.</small>
                    ) : null}
                  </span>
                </label>
              );
            })}
          </div>
          <p className="folderPipelineSubtitle">
            Only PDFs whose pipeline changes are reconverted. Subfolders follow this choice unless they set their own.
          </p>
        </div>
        <footer className="modalFooter">
          <span className="modalMessage" />
          <div className="modalFooterActions">
            <button className="secondaryAction" disabled={busy} onClick={onCancel}>{prompt.cancelLabel ?? 'Cancel'}</button>
            <button
              className="primaryAction"
              disabled={busy}
              onClick={() => onSave(selected === INHERIT ? null : selected)}
            >
              {prompt.saveLabel}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
