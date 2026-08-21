import {
  FileText,
  Folder,
  FolderOpen,
  RefreshCw,
  SkipForward,
  Square,
  X,
} from 'lucide-react';
import { EmbedderConfigForm } from './EmbedderConfigForm';
import { PipelineConfigForm } from './PipelineConfigForm';
import { OcrLanguagePackManager } from './OcrLanguagePackManager';
import {
  CUSTOM_EMBEDDING_VALUE,
  EMBEDDING_MODEL_PRESETS,
  embeddingProviderFromSpec,
  embeddingSelectValue,
  pipelineInstallHint,
  pipelineSelectOptions,
  presetOptionAvailable,
} from '../lib/convertPresets';
import { convertDefaultsFromSelection, type ExplorerSelection } from '../lib/formatting';
import type {
  BatchConvertResult,
  EmbedderDescriptor,
  PipelineDescriptor,
  PipelineOptions,
} from '../types';

export function ConvertPanel({
  convertMode,
  selectedPdfs,
  batchDirectory,
  batchRecursive,
  batchOverwrite,
  storeOriginal,
  embeddingModel,
  embeddingProviders,
  embeddingDescriptors,
  embedderOptions,
  ingestPipeline,
  ingestPipelineDescriptors,
  pipelineOptions,
  explorerSelection,
  activeLibraryPath,
  busy,
  convertLocked,
  conversionInProgress,
  modelsPreparing,
  reconvertBusy,
  reconvertNotice,
  conversionStatus,
  conversionError,
  batchConvertResult,
  onConvertModeChange,
  onSelectedPdfsChange,
  onBatchDirectoryChange,
  onBatchRecursiveChange,
  onBatchOverwriteChange,
  onStoreOriginalChange,
  onEmbeddingModelChange,
  onSaveEmbeddingModel,
  onSaveEmbedderOptions,
  onSaveIngestPipeline,
  onSavePipelineOptions,
  onChoosePdfs,
  onChooseDirectory,
  onToggleSelectedPdf,
  onConvert,
  onSkip,
  onStop,
}: {
  convertMode: 'batch' | 'selected';
  selectedPdfs: string[];
  batchDirectory: string;
  batchRecursive: boolean;
  batchOverwrite: boolean;
  storeOriginal: boolean;
  embeddingModel: string;
  embeddingProviders: string[];
  embeddingDescriptors: EmbedderDescriptor[];
  embedderOptions: PipelineOptions;
  ingestPipeline: string;
  ingestPipelineDescriptors: PipelineDescriptor[];
  pipelineOptions: PipelineOptions;
  explorerSelection: ExplorerSelection | null;
  activeLibraryPath: string;
  busy: boolean;
  convertLocked: boolean;
  conversionInProgress: boolean;
  modelsPreparing?: boolean;
  reconvertBusy: boolean;
  reconvertNotice: string | null;
  conversionStatus: string | null;
  conversionError: string | null;
  batchConvertResult: BatchConvertResult | null;
  onConvertModeChange: (mode: 'batch' | 'selected') => void;
  onSelectedPdfsChange: (paths: string[]) => void;
  onBatchDirectoryChange: (value: string) => void;
  onBatchRecursiveChange: (value: boolean) => void;
  onBatchOverwriteChange: (value: boolean) => void;
  onStoreOriginalChange: (value: boolean) => void;
  onEmbeddingModelChange: (value: string) => void;
  onSaveEmbeddingModel: (model: string) => void;
  onSaveEmbedderOptions: (next: PipelineOptions) => void;
  onSaveIngestPipeline: (pipeline: string) => void;
  onSavePipelineOptions: (next: PipelineOptions) => void;
  onChoosePdfs: () => void;
  onChooseDirectory: () => void;
  onToggleSelectedPdf: (pdfPath: string) => void;
  onConvert: () => void;
  onSkip: () => void;
  onStop: () => void;
}) {
  const activePipelineDescriptor = ingestPipelineDescriptors.find(
    (item) => item.spec === ingestPipeline || item.provider === ingestPipeline,
  ) ?? null;
  const activeEmbedderProvider = embeddingProviderFromSpec(embeddingModel);
  const activeEmbedderDescriptor = embeddingDescriptors.find(
    (item) => item.provider === activeEmbedderProvider,
  ) ?? null;
  const pipelineOptionsForSelect = pipelineSelectOptions(ingestPipelineDescriptors);
  const installedPipelineProviders = ingestPipelineDescriptors
    .filter((item) => item.installed)
    .map((item) => item.provider);

  return (
    <div className="convertView">
      <div className="convertModeToggle">
        <button
          className={convertMode === 'selected' ? 'active' : ''}
          onClick={() => onConvertModeChange('selected')}
        >
          {selectedPdfs.length > 0 ? `Individual PDFs (${selectedPdfs.length})` : 'Individual PDFs'}
        </button>
        <button
          className={convertMode === 'batch' ? 'active' : ''}
          onClick={() => {
            onConvertModeChange('batch');
            const defaults = convertDefaultsFromSelection(explorerSelection, activeLibraryPath);
            const directory = defaults?.batchDirectory
              || (selectedPdfs[0]
                ? selectedPdfs[0].replace(/[/\\][^/\\]+$/, '')
                : activeLibraryPath);
            if (directory) onBatchDirectoryChange(directory);
          }}
        >
          PDF Directory
        </button>
      </div>
      {convertMode === 'selected' ? (
        <>
          <div className="selectedPdfList">
            <span className="fieldLabel">{selectedPdfs.length} PDF{selectedPdfs.length === 1 ? '' : 's'} selected</span>
            {selectedPdfs.length > 0 ? (
              <ul>
                {selectedPdfs.map((filePath) => (
                  <li key={filePath} title={filePath}>
                    <span>{filePath.replace(/^.*[/\\]/, '')}</span>
                    <button
                      type="button"
                      className="ghostIcon tiny visible"
                      onClick={() => onToggleSelectedPdf(filePath)}
                      title="Remove from selection"
                      aria-label={`Remove ${filePath}`}
                    >
                      <X size={12} />
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="sideMuted">No PDFs selected yet.</p>
            )}
          </div>
          <button
            type="button"
            className="secondaryAction"
            onClick={() => void onChoosePdfs()}
            disabled={busy || convertLocked}
          >
            <FolderOpen size={16} />
            Choose PDFs
          </button>
          <button
            type="button"
            className="secondaryAction"
            onClick={() => onSelectedPdfsChange([])}
            disabled={!selectedPdfs.length || busy || convertLocked}
          >
            Clear selection
          </button>
          <label className="miniCheck">
            <input type="checkbox" checked={batchOverwrite} onChange={(event) => onBatchOverwriteChange(event.target.checked)} />
            <span>Overwrite existing .vera files</span>
          </label>
          <p className="sideMuted">Each archive is created beside its PDF with the same base filename. Choose files here, or select them in Explorer (click, Ctrl/Cmd+click, or Shift+click).</p>
        </>
      ) : null}
      {convertMode === 'batch' ? (
        <>
          <label className="field">
            <span>PDF directory</span>
            <div className="pathInput">
              <Folder size={16} />
              <input value={batchDirectory} onChange={(event) => onBatchDirectoryChange(event.target.value)} placeholder="C:\\proposals" />
            </div>
          </label>
          <button className="secondaryAction" onClick={onChooseDirectory} disabled={busy || convertLocked}><FolderOpen size={16} />Choose Directory</button>
          <label className="miniCheck">
            <input type="checkbox" checked={batchRecursive} onChange={(event) => onBatchRecursiveChange(event.target.checked)} />
            <span>Include PDFs in nested folders</span>
          </label>
          <label className="miniCheck">
            <input type="checkbox" checked={batchOverwrite} onChange={(event) => onBatchOverwriteChange(event.target.checked)} />
            <span>Overwrite existing .vera files</span>
          </label>
          <p className="sideMuted">Each archive is created beside its PDF with the same base filename. Existing archives are skipped unless overwrite is enabled.</p>
        </>
      ) : null}
      <label className="field">
        <span>Ingest pipeline</span>
        <select
          value={
            pipelineOptionsForSelect.some((option) => option.value === ingestPipeline)
              ? ingestPipeline
              : ingestPipeline || 'pymupdf'
          }
          onChange={(event) => void onSaveIngestPipeline(event.target.value)}
          disabled={convertLocked}
        >
          {pipelineOptionsForSelect.map((option) => {
            const available = presetOptionAvailable(option, installedPipelineProviders);
            return (
              <option key={option.value} value={option.value} disabled={!available}>
                {available ? option.label : `${option.label} (not installed)`}
              </option>
            );
          })}
          {!pipelineOptionsForSelect.some((option) => option.value === ingestPipeline)
            && ingestPipeline
            ? <option value={ingestPipeline}>{ingestPipeline}</option>
            : null}
        </select>
      </label>
      <p className="sideMuted">
        {activePipelineDescriptor?.installed
          ? (activePipelineDescriptor.description || 'Pipeline ready for conversion.')
          : (pipelineInstallHint(ingestPipeline, ingestPipelineDescriptors)
            || 'Choose an ingest pipeline.')}
        {' '}PyMuPDF is the default ingest pipeline. Optional layout-aware conversion remains a CLI extra (`vera-cli[docling]`), not part of the 0.3.0 desktop app.
      </p>
      <label className="field">
        <span>Embedding model</span>
        <select
          value={embeddingSelectValue(embeddingModel)}
          onChange={(event) => {
            const next = event.target.value;
            if (next === CUSTOM_EMBEDDING_VALUE) {
              if (embeddingSelectValue(embeddingModel) !== CUSTOM_EMBEDDING_VALUE) {
                onEmbeddingModelChange('');
              }
              return;
            }
            void onSaveEmbeddingModel(next);
          }}
          disabled={convertLocked}
        >
          {EMBEDDING_MODEL_PRESETS.map((option) => {
            const available = presetOptionAvailable(option, embeddingProviders);
            return (
              <option key={option.value} value={option.value} disabled={!available}>
                {available ? option.label : `${option.label} (not installed)`}
              </option>
            );
          })}
          {embeddingDescriptors
            .filter((item) => item.provider !== 'hashing' && item.provider !== 'sentence-transformers')
            .map((item) => {
              const spec = item.default_model_id
                ? `${item.provider}:${item.default_model_id}`
                : item.provider;
              return (
                <option key={item.provider} value={spec}>
                  {item.label || spec}
                </option>
              );
            })}
          <option value={CUSTOM_EMBEDDING_VALUE}>Custom provider:model-id…</option>
        </select>
      </label>
      {embeddingSelectValue(embeddingModel) === CUSTOM_EMBEDDING_VALUE ? (
        <label className="field">
          <span>Custom embedding spec</span>
          <input
            list="embedding-provider-specs"
            value={embeddingModel}
            onChange={(event) => onEmbeddingModelChange(event.target.value)}
            onBlur={() => void onSaveEmbeddingModel(embeddingModel)}
            placeholder="provider:model-id"
            disabled={convertLocked}
          />
          <datalist id="embedding-provider-specs">
            <option value="hashing" />
            <option value="hashing:vera-hashing-384" />
            <option value="sentence-transformers:all-MiniLM-L6-v2" />
            {embeddingDescriptors.map((item) => (
              <option
                key={item.provider}
                value={item.default_model_id ? `${item.provider}:${item.default_model_id}` : `${item.provider}:`}
              />
            ))}
            {embeddingProviders.map((provider) => (
              <option key={`name-${provider}`} value={`${provider}:`} />
            ))}
          </datalist>
        </label>
      ) : null}
      <p className="sideMuted">
        {embeddingProviders.includes('sentence-transformers')
          ? 'Local semantic (MiniLM) is bundled in the desktop app with weights in the installer, so first use does not download. Hashing stays the default. The conversion embedding model is independent of Chat.'
          : <>Sentence Transformers is not installed. From the repo root run <code>uv sync --extra ml</code> and restart the app. Hosted embedders ship in a later 0.3.1 release.</>}
        {' '}Custom specs are saved when the field loses focus.
      </p>
      <label className="miniCheck">
        <input type="checkbox" checked={storeOriginal} onChange={(event) => onStoreOriginalChange(event.target.checked)} />
        <span>Store original PDF</span>
      </label>
      <details className="convertAdvanced">
        <summary>Advanced pipeline options</summary>
        <p className="sideMuted">
          Controls advertised by the selected ingest pipeline descriptor
          {activePipelineDescriptor?.spec ? ` (${activePipelineDescriptor.spec})` : ''}.
          Defaults apply until you change them.
        </p>
        <PipelineConfigForm
          descriptor={activePipelineDescriptor}
          values={pipelineOptions}
          disabled={convertLocked}
          onChange={(next) => { void onSavePipelineOptions(next); }}
        />
        <p className="sideMuted">
          Controls advertised by the selected embedding provider
          {activeEmbedderDescriptor?.provider ? ` (${activeEmbedderDescriptor.provider})` : ''}.
        </p>
        <EmbedderConfigForm
          descriptor={activeEmbedderDescriptor}
          values={embedderOptions}
          disabled={convertLocked}
          onChange={(next) => { void onSaveEmbedderOptions(next); }}
        />
        {activePipelineDescriptor?.capabilities?.ocr_engine === 'tesseract' ? (
          <OcrLanguagePackManager
            language={String(pipelineOptions.ocr_language ?? 'eng')}
            disabled={convertLocked}
          />
        ) : null}
      </details>
      {reconvertNotice ? (
        <p className="sideMuted reconvertStatus" role="status">
          {reconvertBusy ? <RefreshCw size={12} className="spinning" aria-hidden="true" /> : null}
          <span>{reconvertNotice}</span>
        </p>
      ) : null}
      <div className="convertActions">
        <button
          className="sidePrimary"
          onClick={onConvert}
          disabled={convertMode === 'selected'
            ? selectedPdfs.length === 0 || busy || convertLocked || Boolean(modelsPreparing)
            : !batchDirectory.trim() || busy || convertLocked || Boolean(modelsPreparing)}
        >
          <RefreshCw size={16} className={convertLocked || modelsPreparing ? 'spinning' : undefined} />
          {conversionInProgress
            ? 'Converting…'
            : modelsPreparing
              ? 'Downloading models…'
              : reconvertBusy
              ? 'Preparing…'
              : convertMode === 'selected'
                ? `Convert (${selectedPdfs.length})`
                : 'Convert Directory'}
        </button>
        <button
          type="button"
          className="secondaryAction convertStop"
          onClick={() => { void window.vera.openConvertLog(); }}
          title="Open convert log"
          aria-label="Open convert log"
        >
          <FileText size={14} />
          Open log
        </button>
        {conversionInProgress && (convertMode === 'batch' || convertMode === 'selected') ? (
          <button
            type="button"
            className="secondaryAction convertStop"
            onClick={onSkip}
            disabled={conversionStatus === 'Stopping…'}
            title="Skip current file and continue"
            aria-label="Skip current file"
          >
            <SkipForward size={14} />
            Skip
          </button>
        ) : null}
        {conversionInProgress ? (
          <button
            type="button"
            className="secondaryAction convertStop"
            onClick={onStop}
            disabled={conversionStatus === 'Stopping…'}
            title="Stop conversion"
            aria-label="Stop conversion"
          >
            <Square size={12} fill="currentColor" />
            Stop
          </button>
        ) : modelsPreparing ? (
          <button
            type="button"
            className="secondaryAction convertStop"
            onClick={onStop}
            disabled={conversionStatus === 'Stopping…'}
            title="Stop conversion"
            aria-label="Stop conversion"
          >
            <Square size={12} fill="currentColor" />
            Stop
          </button>
        ) : null}
      </div>
      {conversionError ? <p className="sideMuted" role="alert">{conversionError}</p> : null}
      {(convertMode === 'batch' || convertMode === 'selected') && batchConvertResult ? (
        <div className="batchConvertReport">
          <strong>{batchConvertResult.converted} converted</strong>
          <span>
            {batchConvertResult.discovered} PDFs found · {batchConvertResult.skipped} skipped
            {batchConvertResult.user_skipped ? ` · ${batchConvertResult.user_skipped} user-skipped` : ''}
            {' · '}{batchConvertResult.malformed} malformed · {batchConvertResult.failed} failed
          </span>
          {batchConvertResult.malformed_existing.map((entry) => (
            <span className="batchConvertError" key={entry.output} title={entry.issues.join('; ')}>{entry.output}: {entry.issues.join('; ')}</span>
          ))}
          {(batchConvertResult.skipped_by_user || []).map((filePath) => (
            <span className="batchConvertSkipped" key={filePath} title="Skipped by user">{filePath}: skipped</span>
          ))}
          {batchConvertResult.errors.map((entry) => (
            <span className="batchConvertError" key={entry.input} title={entry.error}>{entry.input}: {entry.error}</span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
