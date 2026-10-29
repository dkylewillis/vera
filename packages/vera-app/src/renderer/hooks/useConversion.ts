import { useRef, type Dispatch, type SetStateAction } from 'react';
import { mergePipelineFieldValues } from '../components/PipelineConfigForm';
import type { SideView } from '../components/AppShell';
import { DEFAULT_ACTION_TIMEOUT_MS, type SidecarCall } from './useSidecarCall';
import type { BackgroundTask, BackgroundTaskAction } from '../lib/backgroundTasks';
import {
  awaitConversionRequest,
  buildBatchConvertPayload,
  buildSingleConvertPayload,
  conversionFailedMessage,
  conversionMissingTargetMessage,
  conversionProgressTaskUpdate,
  singleConvertAsBatchResult,
  type ConversionProgressMode,
  type ConvertMode,
} from '../lib/conversion';
import { convertDefaultsFromSelection, fileName, isPathInsideFolder, siblingSourcePath, type ExplorerSelection } from '../lib/formatting';
import { explorerEntryType } from '../lib/explorer';
import { pipelineAcceptsPdf } from '../lib/convertPresets';
import {
  findSiblingSourcePath,
  reconvertConvertOutput,
  reconvertExportGate,
  reconvertInspectFailedMessage,
  reconvertMissingSourceMessage,
  reconvertPipelineOptionsFromInspect,
  reconvertPrefillFromInspect,
  resolveReconvertSource,
  type ReconvertTarget,
} from '../lib/reconvert';
import { SIDECAR_ACTIONS } from '../../shared/protocol';
import type {
  BatchConvertResult,
  ExportResult,
  FolderEntry,
  InspectResult,
  PipelineDescriptor,
  PipelineOptions,
  StreamEvent,
  WorkspaceFolderResult,
} from '../types';

export type ConversionHost = {
  convertMode: ConvertMode;
  selectedPdfs: string[];
  batchDirectory: string;
  batchRecursive: boolean;
  batchOverwrite: boolean;
  storeOriginal: boolean;
  embeddingModel: string;
  ingestPipeline: string;
  pipelineOptions: PipelineOptions;
  embedderOptions: PipelineOptions;
  explorerSelection: ExplorerSelection | null;
  activeLibraryPath: string;
  conversionInProgress: boolean;
  folders: WorkspaceFolderResult[];
  libraryPaths: string[];
  ingestPipelineDescriptors: PipelineDescriptor[];
  ingestPipelineConfigs: Record<string, PipelineOptions>;
  call: SidecarCall;
  dispatchBackgroundTask: Dispatch<BackgroundTaskAction>;
  refreshFolder: (folderPath: string, options?: { showBusy?: boolean }) => Promise<void>;
  setBatchDirectory: Dispatch<SetStateAction<string>>;
  setBatchOverwrite: Dispatch<SetStateAction<boolean>>;
  setStoreOriginal: Dispatch<SetStateAction<boolean>>;
  setConvertMode: Dispatch<SetStateAction<ConvertMode>>;
  setSideView: Dispatch<SetStateAction<SideView>>;
  setSidebarCollapsed: Dispatch<SetStateAction<boolean>>;
  setReconvertNotice: Dispatch<SetStateAction<string | null>>;
  setReconvertBusy: Dispatch<SetStateAction<boolean>>;
  setConversionError: Dispatch<SetStateAction<string | null>>;
  setBatchConvertResult: Dispatch<SetStateAction<BatchConvertResult | null>>;
  setSelectedPdfs: Dispatch<SetStateAction<string[]>>;
  setExplorerSelection: Dispatch<SetStateAction<ExplorerSelection | null>>;
  setEmbeddingModel: Dispatch<SetStateAction<string>>;
  setIngestPipeline: Dispatch<SetStateAction<string>>;
  setIngestPipelineConfigs: Dispatch<SetStateAction<Record<string, PipelineOptions>>>;
  setPipelineOptions: Dispatch<SetStateAction<PipelineOptions>>;
};

export type ConversionController = ReturnType<typeof createConversionController>;

/**
 * Reconverting a Markdown archive (or an older settings file) can leave a
 * non-PDF pipeline selected; PDF runs then fall back to an installed PDF
 * pipeline and that pipeline's saved options, which may differ in schema.
 */
export function pipelineForRun(
  host: Pick<ConversionHost, 'ingestPipeline' | 'pipelineOptions' | 'ingestPipelineDescriptors' | 'ingestPipelineConfigs'>,
  includesPdfs: boolean,
): { ingestPipeline: string; pipelineOptions: PipelineOptions } {
  const current = { ingestPipeline: host.ingestPipeline, pipelineOptions: host.pipelineOptions };
  if (!includesPdfs) return current;
  const selected = host.ingestPipelineDescriptors.find(
    (item) => item.spec === host.ingestPipeline || item.provider === host.ingestPipeline,
  );
  if (!selected || pipelineAcceptsPdf(selected)) return current;
  const fallback = host.ingestPipelineDescriptors.find((item) => item.installed && pipelineAcceptsPdf(item));
  if (!fallback) return current;
  return {
    ingestPipeline: fallback.spec,
    pipelineOptions: mergePipelineFieldValues(fallback, host.ingestPipelineConfigs[fallback.spec]),
  };
}

export function createConversionController(getHost: () => ConversionHost) {
  const conversionRequestIdRef = { current: null as string | null };
  const conversionProgressCleanupRef = { current: null as { requestId: string; off: () => void } | null };
  const conversionCanceledRef = { current: false };
  const conversionInterruptRef = { current: null as 'stop' | 'skip' | null };
  const conversionPhaseRef = { current: null as string | null };
  const reconvertInFlightRef = { current: false };
  const reconvertDefaultsRef = { current: null as { overwrite: boolean; storeOriginal: boolean } | null };
  const reconvertTargetRef = { current: null as ReconvertTarget | null };

  function applyConvertDefaultsFromSelection(selection?: ExplorerSelection | null) {
    const host = getHost();
    const defaults = convertDefaultsFromSelection(
      selection !== undefined ? selection : host.explorerSelection,
      host.activeLibraryPath,
    );
    if (!defaults?.batchDirectory) return;
    host.setBatchDirectory(defaults.batchDirectory);
  }

  function snapshotConvertDefaultsForReconvert() {
    if (reconvertDefaultsRef.current) return;
    const host = getHost();
    reconvertDefaultsRef.current = { overwrite: host.batchOverwrite, storeOriginal: host.storeOriginal };
  }

  function restoreConvertDefaultsAfterReconvert() {
    const snapshot = reconvertDefaultsRef.current;
    if (!snapshot) return;
    const host = getHost();
    host.setBatchOverwrite(snapshot.overwrite);
    host.setStoreOriginal(snapshot.storeOriginal);
    reconvertDefaultsRef.current = null;
  }

  function openConvertSelected(paths?: string[]) {
    const host = getHost();
    reconvertTargetRef.current = null;
    if (paths?.length) {
      host.setSelectedPdfs(paths);
      host.setExplorerSelection({ kind: 'file', path: paths[paths.length - 1], type: sourceSelectionType(paths[paths.length - 1]) });
    }
    host.setReconvertNotice(null);
    host.setConvertMode('selected');
    host.setSideView('convert');
    host.setSidebarCollapsed(false);
  }

  function openConvertFolder(folderPath: string) {
    const host = getHost();
    reconvertTargetRef.current = null;
    host.setReconvertNotice(null);
    host.setConversionError(null);
    host.setBatchDirectory(folderPath);
    host.setConvertMode('batch');
    host.setExplorerSelection({ kind: 'folder', path: folderPath });
    host.setSideView('convert');
    host.setSidebarCollapsed(false);
  }

  async function openReconvert(entry: FolderEntry, folderPath: string) {
    const host = getHost();
    if (host.conversionInProgress || reconvertInFlightRef.current) return;
    reconvertInFlightRef.current = true;
    reconvertTargetRef.current = null;
    const folder = host.folders.find((item) => item.path === folderPath);
    snapshotConvertDefaultsForReconvert();
    host.setReconvertBusy(true);
    host.setConversionError(null);
    host.setBatchOverwrite(true);
    host.setConvertMode('selected');
    host.setSideView('convert');
    host.setSidebarCollapsed(false);
    host.setReconvertNotice(`Preparing to reconvert “${fileName(entry.path)}”…`);
    const reconvertCall = { scope: 'reconvert', timeoutMs: DEFAULT_ACTION_TIMEOUT_MS };
    let prepared = false;
    try {
      const inspectResult = await host.call<InspectResult>(
        { action: SIDECAR_ACTIONS.inspect, path: entry.path },
        'Preparing reconvert',
        undefined,
        reconvertCall,
      );
      const prefill = reconvertPrefillFromInspect(inspectResult);
      const sourceFileName = inspectResult?.source_file_name?.trim() || null;
      const listedSource = findSiblingSourcePath(
        entry.path,
        folder?.entries ?? [],
        sourceFileName,
      );
      const sibling = siblingSourcePath(entry.path, sourceFileName);
      const siblingExists = Boolean(listedSource) || (sibling ? await window.vera.pathExists(sibling) : false);
      const resolution = resolveReconvertSource(entry.path, {
        entries: folder?.entries ?? [],
        siblingExists,
        sourceFileName,
      });

      let sourcePath: string | null = listedSource;
      let restoredFromArchive = false;
      if (resolution.status === 'ready') {
        sourcePath = resolution.sourcePath;
      } else if (resolution.status === 'export') {
        const gate = reconvertExportGate({
          inspectOk: inspectResult !== null,
          hasEmbeddedSource: prefill.hasEmbeddedSource,
        });
        if (!gate.allow) {
          host.setReconvertNotice(null);
          host.setConversionError(
            gate.reason === 'inspect-failed'
              ? reconvertInspectFailedMessage()
              : reconvertMissingSourceMessage(entry.path, sourceFileName),
          );
          return;
        }
        const exported = await host.call<ExportResult>(
          { action: SIDECAR_ACTIONS.export, path: entry.path, output: resolution.sourcePath },
          'Restoring embedded source',
          undefined,
          reconvertCall,
        );
        if (exported?.output) {
          sourcePath = exported.output;
          restoredFromArchive = true;
          void host.refreshFolder(folderPath, { showBusy: false }).catch((error) => {
            console.error('Unable to refresh folder after restoring source file', error);
          });
        } else {
          host.setReconvertNotice(null);
          host.setConversionError(reconvertMissingSourceMessage(entry.path, sourceFileName));
          return;
        }
      } else {
        host.setReconvertNotice(null);
        host.setConversionError(reconvertMissingSourceMessage(entry.path, sourceFileName));
        return;
      }

      if (!sourcePath) {
        host.setReconvertNotice(null);
        host.setConversionError(reconvertMissingSourceMessage(entry.path, sourceFileName));
        return;
      }

      if (prefill.embeddingModel) host.setEmbeddingModel(prefill.embeddingModel);
      const requestedPipeline = prefill.ingestPipeline || host.ingestPipeline;
      const nextDescriptor = host.ingestPipelineDescriptors.find(
        (item) => item.spec === requestedPipeline || item.provider === requestedPipeline,
      ) ?? null;
      const nextPipeline = nextDescriptor?.spec || host.ingestPipeline;
      const inspectOptions = reconvertPipelineOptionsFromInspect(inspectResult);
      const mergedOptions = mergePipelineFieldValues(nextDescriptor, {
        ...host.ingestPipelineConfigs[nextPipeline],
        ...inspectOptions,
      });
      if (prefill.ingestPipeline && nextDescriptor) host.setIngestPipeline(nextPipeline);
      host.setIngestPipelineConfigs((prev) => ({ ...prev, [nextPipeline]: mergedOptions }));
      host.setPipelineOptions(mergedOptions);
      if (prefill.hasEmbeddedSource || restoredFromArchive) {
        host.setStoreOriginal(true);
      }

      host.setSelectedPdfs([sourcePath]);
      host.setExplorerSelection({ kind: 'file', path: sourcePath, type: sourceSelectionType(sourcePath) });
      reconvertTargetRef.current = { sourcePath, archivePath: entry.path };
      host.setReconvertNotice(
        restoredFromArchive
          ? 'Restored the embedded source beside this archive. Overwrite is on so Convert will replace this archive, even if its name differs from the source file. Choose a different pipeline or embedding if you want, then convert. Update the library index afterward if this folder is indexed.'
          : 'Overwrite is on so Convert will replace this archive, even if its name differs from the source file. The pipeline and embedding below start from this archive — change them if you want, then convert. Update the library index afterward if this folder is indexed.',
      );
      prepared = true;
    } catch (error) {
      host.setReconvertNotice(null);
      host.setConversionError(error instanceof Error ? error.message : reconvertMissingSourceMessage(entry.path));
    } finally {
      reconvertInFlightRef.current = false;
      host.setReconvertBusy(false);
      if (!prepared) restoreConvertDefaultsAfterReconvert();
    }
  }

  function toggleSelectedPdf(pdfPathValue: string) {
    getHost().setSelectedPdfs((prev) => {
      if (prev.includes(pdfPathValue)) {
        return prev.filter((entry) => entry !== pdfPathValue);
      }
      return [...prev, pdfPathValue];
    });
  }

  async function choosePdfs() {
    const host = getHost();
    const paths = (await window.vera.pickPdf()).map((entry) => entry.trim()).filter(Boolean);
    if (!paths.length) return;
    host.setSelectedPdfs((prev) => {
      const merged = [...prev];
      for (const filePath of paths) {
        if (!merged.includes(filePath)) merged.push(filePath);
      }
      return merged;
    });
    host.setExplorerSelection({ kind: 'file', path: paths[paths.length - 1], type: sourceSelectionType(paths[paths.length - 1]) });
    host.setConvertMode('selected');
    host.setBatchConvertResult(null);
  }

  async function chooseBatchDirectory() {
    const host = getHost();
    const chosen = await window.vera.pickFolder();
    if (chosen) {
      host.setBatchDirectory(chosen);
      host.setConvertMode('batch');
      host.setExplorerSelection({ kind: 'folder', path: chosen });
      host.setBatchConvertResult(null);
    }
  }

  /**
   * The embedding model the library containing `targetPath` already uses, read
   * from one of its archives (nearest to the target first). Mixing models in a
   * library leaves the minority out of semantic search.
   */
  async function libraryEmbeddingModel(targetPath: string): Promise<{ library: string; model: string } | null> {
    const host = getHost();
    const target = targetPath.trim();
    if (!target) return null;
    const library = host.folders.find((folder) => (
      host.libraryPaths.includes(folder.path) && isPathInsideFolder(target, folder.path)
    ));
    if (!library) return null;
    const archives = library.entries.filter((entry) => entry.type === 'vera');
    const targetDir = explorerEntryType(target) ? target.replace(/[/\\][^/\\]+$/, '') : target;
    const sample = archives.find((entry) => isPathInsideFolder(entry.path, targetDir)) ?? archives[0];
    if (!sample) return null;
    const response = await window.vera.request<InspectResult>({ action: SIDECAR_ACTIONS.inspect, path: sample.path });
    const result = response.ok ? response.result : null;
    const model = result?.default_embedding_model?.trim()
      || result?.embedding_model?.trim()
      || result?.embedding_models?.[0]?.trim();
    return model ? { library: library.path, model } : null;
  }

  /**
   * Explorer's Convert: start immediately with saved defaults, skipping
   * archives that are already up to date. Opens the Convert view only when
   * something needs attention.
   */
  async function quickConvert(target: { paths?: string[]; directory?: string }) {
    const host = getHost();
    if (host.conversionInProgress || reconvertInFlightRef.current) return;
    reconvertTargetRef.current = null;
    const paths = (target.paths ?? []).filter(Boolean);
    const directory = target.directory?.trim() || '';
    if (!paths.length && !directory) return;
    let libraryModel: Awaited<ReturnType<typeof libraryEmbeddingModel>> = null;
    try {
      libraryModel = await libraryEmbeddingModel(paths[0] || directory);
    } catch {
      libraryModel = null;
    }
    if (paths.length) {
      host.setSelectedPdfs(paths);
      host.setConvertMode('selected');
    } else {
      host.setBatchDirectory(directory);
      host.setConvertMode('batch');
    }
    const outcome = await batchConvertPdfs({
      paths,
      directory,
      overwrite: false,
      recursive: true,
      embeddingModel: libraryModel?.model ?? host.embeddingModel,
    });
    if (outcome !== 'ok') {
      host.setSideView('convert');
      host.setSidebarCollapsed(false);
    }
  }

  function updateConversionTask(
    update: Partial<Omit<BackgroundTask, 'id' | 'kind'>>,
    requestId = conversionRequestIdRef.current,
  ) {
    if (!requestId) return;
    getHost().dispatchBackgroundTask({ type: 'update', id: requestId, update });
  }

  function stopConversion() {
    const host = getHost();
    const requestId = conversionRequestIdRef.current;
    if (!host.conversionInProgress || !requestId) return;
    conversionCanceledRef.current = true;
    conversionInterruptRef.current = 'stop';
    updateConversionTask({ message: 'Stopping…' }, requestId);
    void window.vera.cancelAnswer(requestId).then((result) => {
      if (result && 'cancelled' in result && !result.cancelled) {
        conversionCanceledRef.current = false;
        conversionInterruptRef.current = null;
        updateConversionTask({ message: 'Converting…' }, requestId);
        host.setConversionError('Unable to stop conversion (request was not found). Restart the app if this persists.');
      } else if (result && 'cancelled' in result && result.cancelled) {
        clearConversionUi(requestId);
      }
    }).catch((error) => {
      conversionCanceledRef.current = false;
      conversionInterruptRef.current = null;
      updateConversionTask({ message: 'Converting…' }, requestId);
      host.setConversionError(error instanceof Error ? error.message : 'Unable to stop conversion');
    });
  }

  function skipCurrentConversion() {
    const host = getHost();
    const requestId = conversionRequestIdRef.current;
    if (!host.conversionInProgress || !requestId || (host.convertMode !== 'batch' && host.convertMode !== 'selected')) return;
    if (conversionInterruptRef.current === 'stop') return;
    conversionInterruptRef.current = 'skip';
    updateConversionTask({ message: 'Skipping…' }, requestId);
    void window.vera.skipConversion(requestId).then((result) => {
      if (!result.skipped) {
        conversionInterruptRef.current = null;
        updateConversionTask({ message: 'Converting…' }, requestId);
        host.setConversionError('Unable to skip file (request was not found). Restart the app if this persists.');
      }
    }).catch((error) => {
      conversionInterruptRef.current = null;
      updateConversionTask({ message: 'Converting…' }, requestId);
      host.setConversionError(error instanceof Error ? error.message : 'Unable to skip file');
    });
  }

  function applyConversionProgress(requestId: string, event: StreamEvent, mode: ConversionProgressMode) {
    if (conversionInterruptRef.current === 'stop') return;
    if (conversionInterruptRef.current === 'skip') {
      conversionInterruptRef.current = null;
    }
    if (event.phase) conversionPhaseRef.current = event.phase;
    updateConversionTask(conversionProgressTaskUpdate(event, mode), requestId);
  }

  async function refreshFoldersForPath(target: string) {
    const host = getHost();
    await Promise.all(
      host.folders
        .filter((folder) => isPathInsideFolder(target, folder.path))
        .map((folder) => host.refreshFolder(folder.path, { showBusy: false })),
    );
  }

  function refreshFoldersAfterConversion(target: string) {
    void refreshFoldersForPath(target).catch((error) => {
      console.error('Unable to refresh folders after conversion', error);
    });
  }

  function clearConversionUi(requestId: string) {
    if (conversionProgressCleanupRef.current?.requestId === requestId) {
      conversionProgressCleanupRef.current.off();
      conversionProgressCleanupRef.current = null;
    }
    if (conversionRequestIdRef.current !== requestId) return;
    conversionRequestIdRef.current = null;
    getHost().dispatchBackgroundTask({ type: 'finish', id: requestId });
    conversionInterruptRef.current = null;
    conversionPhaseRef.current = null;
  }

  function settleConversionRequest(requestId: string) {
    clearConversionUi(requestId);
  }

  function conversionRequestWasSuperseded(requestId: string) {
    const activeRequestId = conversionRequestIdRef.current;
    return activeRequestId !== null && activeRequestId !== requestId;
  }

  /**
   * Run a conversion. Options override the Convert view's directory, overwrite,
   * nested-folder, and embedding settings for this run only. Resolves `ok`
   * when every file converted or was already up to date (or the user stopped
   * it), and `attention` when the Convert view has an error or failures to show.
   */
  async function batchConvertPdfs(options: {
    paths?: string[];
    directory?: string;
    overwrite?: boolean;
    recursive?: boolean;
    embeddingModel?: string;
  } = {}): Promise<'ok' | 'attention'> {
    const host = getHost();
    const selectedPaths = (options.paths ?? []).map((entry) => entry.trim()).filter(Boolean);
    const directory = (options.directory ?? host.batchDirectory).trim();
    const embeddingModel = options.embeddingModel?.trim() || host.embeddingModel;
    if (!selectedPaths.length && !directory) {
      host.setConversionError(conversionMissingTargetMessage(host.convertMode));
      return 'attention';
    }
    conversionCanceledRef.current = false;
    conversionInterruptRef.current = null;
    conversionPhaseRef.current = null;
    host.setConversionError(null);
    host.setBatchConvertResult(null);
    host.setReconvertNotice(null);
    const reconvertOutput = reconvertConvertOutput(reconvertTargetRef.current, selectedPaths);
    const preflight = await host.call<{
      ok: boolean;
      detail?: string;
      missing_credential_env?: string;
    }>(
      { action: SIDECAR_ACTIONS.preflightEmbedder, model: embeddingModel },
      'Checking embedder',
    );
    if (!preflight) return 'attention';
    if (!preflight.ok) {
      const missing = preflight.missing_credential_env?.trim();
      host.setConversionError(
        missing
          ? `Embedding provider is not ready. Set ${missing} under File > Settings → Embeddings, then convert again.`
          : (preflight.detail || 'Embedding provider is not ready.'),
      );
      return 'attention';
    }
    const conversionRequestId = crypto.randomUUID();
    conversionRequestIdRef.current = conversionRequestId;
    host.dispatchBackgroundTask({
      type: 'start',
      task: {
        id: conversionRequestId,
        kind: 'conversion',
        label: 'Conversion',
        message: 'Starting…',
      },
    });
    const refreshRoot = reconvertOutput || selectedPaths[0] || directory;
    const progressMode: ConversionProgressMode = reconvertOutput ? 'single' : 'batch';
    const offProgress = window.vera.onAnswerEvent((event) => {
      if (event.id !== conversionRequestId || event.event !== 'conversion_progress') return;
      applyConversionProgress(conversionRequestId, event, progressMode);
    });
    conversionProgressCleanupRef.current = { requestId: conversionRequestId, off: offProgress };
    const pipeline = pipelineForRun(
      host,
      !selectedPaths.length || selectedPaths.some((entry) => entry.toLowerCase().endsWith('.pdf')),
    );
    const convertFields = {
      embeddingModel,
      ingestPipeline: pipeline.ingestPipeline,
      storeOriginal: host.storeOriginal,
      pipelineOptions: pipeline.pipelineOptions,
      embedderOptions: host.embedderOptions,
    };
    try {
      const response = reconvertOutput
        ? await awaitConversionRequest(
          window.vera.request<{ output: string }>(
            buildSingleConvertPayload({
              inputPath: selectedPaths[0],
              outputPath: reconvertOutput,
              ...convertFields,
            }),
            conversionRequestId,
          ),
          () => settleConversionRequest(conversionRequestId),
        )
        : await awaitConversionRequest(
          window.vera.request<BatchConvertResult>(
            buildBatchConvertPayload({
              selectedPaths,
              directory,
              batchRecursive: options.recursive ?? host.batchRecursive,
              batchOverwrite: options.overwrite ?? host.batchOverwrite,
              ...convertFields,
            }),
            conversionRequestId,
          ),
          () => settleConversionRequest(conversionRequestId),
        );
      if (conversionRequestWasSuperseded(conversionRequestId)) return 'ok';
      if (response.cancelled || response.error?.includes('cancelled')) {
        refreshFoldersAfterConversion(refreshRoot);
        host.setConversionError(null);
        return 'ok';
      }
      if (!response.ok || !response.result) {
        throw new Error(response.error || conversionFailedMessage(selectedPaths.length > 0));
      }
      const convertedOutput = reconvertOutput
        ? (response.result as { output?: string }).output || reconvertOutput
        : null;
      const result = convertedOutput
        ? singleConvertAsBatchResult({ outputPath: convertedOutput, overwrite: true })
        : response.result as BatchConvertResult;
      host.setBatchConvertResult(result);
      refreshFoldersAfterConversion(result.directory || refreshRoot);
      if (convertedOutput) reconvertTargetRef.current = null;
      if (selectedPaths.length) {
        host.setSelectedPdfs([]);
      }
      return result.failed > 0 || result.malformed > 0 ? 'attention' : 'ok';
    } catch (error) {
      if (conversionRequestWasSuperseded(conversionRequestId)) return 'ok';
      const message = error instanceof Error
        ? error.message
        : conversionFailedMessage(selectedPaths.length > 0);
      if (conversionCanceledRef.current || message.toLowerCase().includes('cancelled')) {
        refreshFoldersAfterConversion(refreshRoot);
        host.setConversionError(null);
        return 'ok';
      }
      host.setConversionError(message);
      return 'attention';
    } finally {
      settleConversionRequest(conversionRequestId);
      if (conversionRequestIdRef.current === null) {
        conversionCanceledRef.current = false;
        conversionInterruptRef.current = null;
      }
      restoreConvertDefaultsAfterReconvert();
    }
  }

  return {
    applyConvertDefaultsFromSelection,
    restoreConvertDefaultsAfterReconvert,
    openConvertSelected,
    openConvertFolder,
    openReconvert,
    toggleSelectedPdf,
    choosePdfs,
    chooseBatchDirectory,
    libraryEmbeddingModel,
    quickConvert,
    stopConversion,
    skipCurrentConversion,
    batchConvertPdfs,
  };
}

function sourceSelectionType(path: string): 'pdf' | 'md' {
  return explorerEntryType(path) === 'md' ? 'md' : 'pdf';
}

export function useConversion(host: ConversionHost): ConversionController {
  const hostRef = useRef(host);
  hostRef.current = host;
  const controllerRef = useRef<ConversionController | null>(null);
  if (!controllerRef.current) {
    controllerRef.current = createConversionController(() => hostRef.current);
  }
  return controllerRef.current;
}
