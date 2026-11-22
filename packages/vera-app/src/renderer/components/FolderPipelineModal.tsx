import { useEffect, useState } from 'react';
import { Library, X } from 'lucide-react';
import {
  DEFAULT_PDF_PIPELINE,
  librarySetupPipelineRules,
  normalizeLibraryRuleFolder,
  type PdfPipelineChoice,
  type SetupFolderDraft,
} from '../lib/libraryPipelines';

/** Choice value meaning "no rule here; use the parent folder's pipeline". */
const INHERIT = '';

type DraftRow = SetupFolderDraft & { id: number };

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
  /** Replaces the default note under the choices. */
  note?: string;
  /**
   * New-library setup. The list stays collapsed until the user opens it, and
   * its rules are saved with the library choice before the first sync.
   */
  collectFolderRules?: boolean;
  /** Library root, used to turn a picked folder into a relative rule. */
  rootPath?: string;
};

let nextRowId = 1;

function differentPipeline(selected: string, choices: PdfPipelineChoice[]): string {
  return choices.find((choice) => choice.spec !== selected)?.spec
    ?? choices[0]?.spec
    ?? DEFAULT_PDF_PIPELINE;
}

export function FolderPipelineModal({
  prompt,
  busy = false,
  onSave,
  onCancel,
  onBrowseFolder,
}: {
  prompt: FolderPipelinePrompt | null;
  busy?: boolean;
  /** `null` means follow the parent folder, or pymupdf when setting up a library. */
  onSave: (parser: string | null, folderRules?: SetupFolderDraft[]) => void;
  onCancel: () => void;
  /** Opens a folder picker. Used only while collecting folder rules. */
  onBrowseFolder?: () => Promise<string | null>;
}) {
  const [selected, setSelected] = useState(prompt?.selected ?? INHERIT);
  const [showRules, setShowRules] = useState(false);
  const [rows, setRows] = useState<DraftRow[]>([]);
  const [ruleError, setRuleError] = useState<string | null>(null);
  useEffect(() => {
    setSelected(prompt?.selected ?? INHERIT);
    setShowRules(false);
    setRows([]);
    setRuleError(null);
  }, [prompt]);
  if (!prompt) return null;
  const dialog = prompt;
  const options: (PdfPipelineChoice | null)[] = dialog.inheritLabel !== undefined
    ? [null, ...dialog.choices]
    : dialog.choices;

  function addRow() {
    setRows((current) => [
      ...current,
      { id: nextRowId++, folder: '', parser: differentPipeline(selected, dialog.choices) },
    ]);
    setShowRules(true);
    setRuleError(null);
  }

  async function browseRow(id: number) {
    if (!onBrowseFolder) return;
    const picked = await onBrowseFolder();
    if (!picked) return;
    const normalized = normalizeLibraryRuleFolder(dialog.rootPath ?? '', picked);
    if ('error' in normalized) {
      setRuleError(normalized.error);
      setShowRules(true);
      return;
    }
    if (!normalized.folder) {
      setRuleError('The whole library uses the choice above.');
      setShowRules(true);
      return;
    }
    setRows((current) => current.map((row) => (row.id === id ? { ...row, folder: normalized.folder } : row)));
    setRuleError(null);
  }

  function save() {
    if (!dialog.collectFolderRules) {
      onSave(selected === INHERIT ? null : selected);
      return;
    }
    const libraryParser = selected && selected !== DEFAULT_PDF_PIPELINE ? selected : null;
    const built = librarySetupPipelineRules(dialog.rootPath ?? '', rows);
    if (built.error) {
      setRuleError(built.error);
      setShowRules(true);
      return;
    }
    onSave(libraryParser, built.rules);
  }

  return (
    <div className="modalBackdrop" onClick={busy ? undefined : onCancel}>
      <div className="modal folderPipelineModal" role="dialog" aria-modal="true" aria-labelledby="folder-pipeline-title" onClick={(event) => event.stopPropagation()}>
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
          {prompt.collectFolderRules ? (
            <div className="folderPipelineExtras">
              <button
                type="button"
                className="folderPipelineExtrasToggle"
                aria-expanded={showRules}
                disabled={busy}
                onClick={() => setShowRules((open) => !open)}
              >
                {showRules ? '▾' : '▸'} Different folders use a different pipeline
              </button>
              {showRules ? (
                <div className="folderPipelineRuleList">
                  <p className="folderPipelineSubtitle">
                    Folders you leave out keep the choice above. A pattern such as Projects/*/Plans matches each project&apos;s Plans folder. * matches one folder name.
                  </p>
                  {rows.map((row) => (
                    <div className="folderPipelineRule" key={row.id}>
                      <input
                        type="text"
                        value={row.folder}
                        disabled={busy}
                        placeholder="Projects/*/Plans"
                        aria-label="Folder or pattern"
                        onChange={(event) => {
                          const folder = event.target.value;
                          setRows((current) => current.map((item) => (item.id === row.id ? { ...item, folder } : item)));
                          setRuleError(null);
                        }}
                      />
                      <select
                        value={row.parser}
                        disabled={busy}
                        aria-label="Pipeline for this folder"
                        onChange={(event) => {
                          const parser = event.target.value;
                          setRows((current) => current.map((item) => (item.id === row.id ? { ...item, parser } : item)));
                        }}
                      >
                        {prompt.choices.map((choice) => (
                          <option key={choice.spec} value={choice.spec}>{choice.label}</option>
                        ))}
                      </select>
                      <button type="button" className="secondaryAction compactAction" disabled={busy || !onBrowseFolder} onClick={() => { void browseRow(row.id); }}>
                        Browse
                      </button>
                      <button
                        type="button"
                        className="secondaryAction compactAction"
                        disabled={busy}
                        onClick={() => setRows((current) => current.filter((item) => item.id !== row.id))}
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                  <button type="button" className="secondaryAction compactAction" disabled={busy} onClick={addRow}>
                    Add folder
                  </button>
                  {ruleError ? <p className="folderPipelineError">{ruleError}</p> : null}
                </div>
              ) : null}
            </div>
          ) : null}
          <p className="folderPipelineSubtitle">
            {prompt.note ?? 'Only PDFs whose pipeline changes are reconverted. Subfolders follow this choice unless they set their own.'}
          </p>
        </div>
        <footer className="modalFooter">
          <span className="modalMessage" />
          <div className="modalFooterActions">
            <button className="secondaryAction" disabled={busy} onClick={onCancel}>{prompt.cancelLabel ?? 'Cancel'}</button>
            <button
              className="primaryAction"
              disabled={busy}
              onClick={save}
            >
              {prompt.saveLabel}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
