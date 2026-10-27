import {
  AlertTriangle,
  FilePlus,
  FileText,
  Folder,
  FolderPlus,
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
  DEFAULT_EMBEDDING_MODEL,
  EMBEDDING_MODEL_PRESETS,
  embeddingModelLabel,
  embeddingModelsMatch,
  embeddingProviderFromSpec,
  embeddingSelectValue,
  pipelineInstallHint,
  pipelineSelectOptions,
  presetOptionAvailable,
} from '../lib/convertPresets';
import { fileName } from '../lib/formatting';
import type {
  BatchConvertResult,
  EmbedderDescriptor,
  PipelineDescriptor,
  PipelineOptions,
} from '../types';

const MAX_LISTED_FILES = 6;

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
  libraryModel,
  busy,
  convertLocked,
  conversionInProgress,
  modelsPreparing,
  reconvertBusy,
  reconvertNotice,
  conversionStatus,
  conversionError,
  batchConvertResult,
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
  /** Model already used by the library the target belongs to. */
  libraryModel: { library: string; model: string } | null;
  busy: boolean;
  convertLocked: boolean;
  conversionInProgress: boolean;
  modelsPreparing?: boolean;
  reconvertBusy: boolean;
  reconvertNotice: string | null;
  conversionStatus: string | null;
  conversionError: string | null;
  batchConvertResult: BatchConvertResult | null;
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
  const showPipelineSelect = pipelineOptionsForSelect.length > 1;
  const isCustomModel = embeddingSelectValue(embeddingModel) === CUSTOM_EMBEDDING_VALUE;
  const modelMismatch = Boolean(
    libraryModel && embeddingModel.trim() && !embeddingModelsMatch(libraryModel.model, embeddingModel),
  );
  // A non-default model is otherwise hidden inside the collapsed Advanced section.
  const customizedModel = !embeddingModelsMatch(embeddingModel, DEFAULT_EMBEDDING_MODEL);
  const hasTarget = convertMode === 'selected' ? selectedPdfs.length > 0 : Boolean(batchDirectory.trim());
  const listedFiles = selectedPdfs.slice(0, MAX_LISTED_FILES);
  const unlistedFiles = selectedPdfs.length - listedFiles.length;

  const convertLabel = conversionInProgress
    ? 'Converting…'
    : modelsPreparing
      ? 'Downloading models…'
      : reconvertBusy
        ? 'Preparing…'
        : convertMode === 'batch'
          ? 'Convert folder'
          : selectedPdfs.length
            ? `Convert ${selectedPdfs.length} file${selectedPdfs.length === 1 ? '' : 's'}`
            : 'Convert';

  return (
    <div className="convertView">
      <section className="convertTarget" aria-label="What to convert">
        <span className="fieldLabel">What to convert</span>
        {convertMode === 'batch' && batchDirectory.trim() ? (
          <div className="convertTargetItem" title={batchDirectory}>
            <Folder size={14} aria-hidden="true" />
            <span className="convertTargetName">
              {fileName(batchDirectory) || batchDirectory}
              <span className="convertTargetHint">{batchRecursive ? ' and subfolders' : ''}</span>
            </span>
            <button
              type="button"
              className="ghostIcon tiny visible"
              onClick={() => onBatchDirectoryChange('')}
              disabled={convertLocked}
              title="Clear folder"
              aria-label="Clear folder"
            >
              <X size={12} />
            </button>
          </div>
        ) : convertMode === 'selected' && selectedPdfs.length > 0 ? (
          <ul className="convertTargetList">
            {listedFiles.map((filePath) => (
              <li key={filePath} className="convertTargetItem" title={filePath}>
                <FileText size={14} aria-hidden="true" />
                <span className="convertTargetName">{fileName(filePath)}</span>
                <button
                  type="button"
                  className="ghostIcon tiny visible"
                  onClick={() => onToggleSelectedPdf(filePath)}
                  disabled={convertLocked}
                  title="Remove from selection"
                  aria-label={`Remove ${filePath}`}
                >
                  <X size={12} />
                </button>
              </li>
            ))}
            {unlistedFiles > 0 ? (
              <li className="convertTargetMore">
                and {unlistedFiles} more ·{' '}
                <button type="button" className="sideLink" onClick={() => onSelectedPdfsChange([])} disabled={convertLocked}>
                  Clear
                </button>
              </li>
            ) : null}
          </ul>
        ) : (
          <p className="sideMuted">
            Choose files or a folder, or right-click in Explorer and choose Convert to start right away.
          </p>
        )}
        <div className="convertTargetActions">
          <button type="button" className="secondaryAction" onClick={() => void onChoosePdfs()} disabled={busy || convertLocked}>
            <FilePlus size={15} />
            Add files…
          </button>
          <button type="button" className="secondaryAction" onClick={() => void onChooseDirectory()} disabled={busy || convertLocked}>
            <FolderPlus size={15} />
            Choose folder…
          </button>
        </div>
      </section>

      {modelMismatch && libraryModel ? (
        <div className="convertWarning" role="note">
          <AlertTriangle size={14} aria-hidden="true" />
          <span>
            {fileName(libraryModel.library)} uses {embeddingModelLabel(libraryModel.model)}, but this conversion uses {embeddingModelLabel(embeddingModel)}. Mixing models leaves some documents out of semantic search.{' '}
            <button
              type="button"
              className="sideLink"
              disabled={convertLocked}
              onClick={() => void onSaveEmbeddingModel(libraryModel.model)}
            >
              Use {embeddingModelLabel(libraryModel.model)}
            </button>
          </span>
        </div>
      ) : null}

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
          disabled={!hasTarget || busy || convertLocked || Boolean(modelsPreparing)}
        >
          <RefreshCw size={16} className={convertLocked || modelsPreparing ? 'spinning' : undefined} />
          {convertLabel}
        </button>
        {conversionInProgress ? (
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
        {conversionInProgress || modelsPreparing ? (
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
      {batchConvertResult ? <ConvertResult result={batchConvertResult} /> : null}

      <details className="convertAdvanced">
        <summary>
          Advanced
          {customizedModel ? <span className="convertAdvancedHint"> · {embeddingModelLabel(embeddingModel) || 'custom model'}</span> : null}
        </summary>
        <label className="miniCheck">
          <input type="checkbox" checked={batchOverwrite} onChange={(event) => onBatchOverwriteChange(event.target.checked)} />
          <span>Replace existing .vera files</span>
        </label>
        {convertMode === 'batch' ? (
          <label className="miniCheck">
            <input type="checkbox" checked={batchRecursive} onChange={(event) => onBatchRecursiveChange(event.target.checked)} />
            <span>Include subfolders</span>
          </label>
        ) : null}
        <label
          className="miniCheck"
          title="Makes each .vera self-contained, so you can share it or preview it without the source file."
        >
          <input type="checkbox" checked={storeOriginal} onChange={(event) => onStoreOriginalChange(event.target.checked)} />
          <span>Include a copy of the original file</span>
        </label>
        <p className="sideMuted">Each .vera is saved next to its source with the same name. Files that are already converted are skipped unless you replace them.</p>
        <label className="field">
          <span>Search model</span>
          <select
            value={embeddingSelectValue(embeddingModel)}
            onChange={(event) => {
              const next = event.target.value;
              if (next === CUSTOM_EMBEDDING_VALUE) {
                if (!isCustomModel) onEmbeddingModelChange('');
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
              .filter((item) => {
                const covered = new Set(
                  EMBEDDING_MODEL_PRESETS.map((preset) => preset.requiresProvider || embeddingProviderFromSpec(preset.value)),
                );
                return !covered.has(item.provider);
              })
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
        {isCustomModel ? (
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
              <option value="sentence-transformers:all-MiniLM-L6-v2" />
              {embeddingDescriptors.map((item) => (
                <option
                  key={item.provider}
                  value={item.default_model_id ? `${item.provider}:${item.default_model_id}` : `${item.provider}:`}
                />
              ))}
            </datalist>
          </label>
        ) : null}
        {activeEmbedderProvider === 'openai' ? (
          <p className="sideMuted">Needs an OpenAI API key (File &gt; Settings → Embeddings) and bills per conversion. Others need their own key to search these archives semantically.</p>
        ) : !embeddingProviders.includes('sentence-transformers') && activeEmbedderProvider === 'sentence-transformers' ? (
          <p className="sideMuted">MiniLM is not available in this sidecar. Run <code>uv sync --extra app</code> and restart the app, or choose another model.</p>
        ) : null}
        {showPipelineSelect ? (
          <>
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
            {!activePipelineDescriptor?.installed ? (
              <p className="sideMuted">{pipelineInstallHint(ingestPipeline, ingestPipelineDescriptors) || 'Choose an ingest pipeline.'}</p>
            ) : null}
          </>
        ) : null}
        <PipelineConfigForm
          descriptor={activePipelineDescriptor}
          values={pipelineOptions}
          disabled={convertLocked}
          onChange={(next) => { void onSavePipelineOptions(next); }}
        />
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
        <button
          type="button"
          className="sideLink"
          onClick={() => { void window.vera.openConvertLog(); }}
        >
          Open convert log
        </button>
      </details>
    </div>
  );
}

function ConvertResult({ result }: { result: BatchConvertResult }) {
  const upToDate = result.skipped;
  const problems = result.failed + result.malformed;
  const parts = [
    upToDate ? `${upToDate} already up to date` : '',
    result.user_skipped ? `${result.user_skipped} skipped by you` : '',
    result.failed ? `${result.failed} failed` : '',
    result.malformed ? `${result.malformed} damaged .vera file${result.malformed === 1 ? '' : 's'}` : '',
  ].filter(Boolean);
  const details = [
    ...result.errors.map((entry) => ({ key: entry.input, text: `${fileName(entry.input)}: ${entry.error}`, title: entry.error, error: true })),
    ...result.malformed_existing.map((entry) => ({ key: entry.output, text: `${fileName(entry.output)}: ${entry.issues.join('; ')}`, title: entry.issues.join('; '), error: true })),
    ...(result.skipped_by_user || []).map((filePath) => ({ key: filePath, text: `${fileName(filePath)}: skipped`, title: filePath, error: false })),
  ];
  return (
    <div className={problems ? 'batchConvertReport hasProblems' : 'batchConvertReport'} role="status">
      <strong>
        {result.converted === 0 && problems === 0 && upToDate > 0
          ? 'Everything is already converted'
          : `${result.converted} converted`}
      </strong>
      {parts.length ? <span>{parts.join(' · ')}</span> : null}
      {details.length ? (
        <details>
          <summary>Show details</summary>
          {details.map((entry) => (
            <span className={entry.error ? 'batchConvertError' : 'batchConvertSkipped'} key={entry.key} title={entry.title}>
              {entry.text}
            </span>
          ))}
        </details>
      ) : null}
    </div>
  );
}
