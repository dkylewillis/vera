import { useRef, type Dispatch, type SetStateAction } from 'react';
import { mergePipelineFieldValues } from '../components/PipelineConfigForm';
import type { SideView } from '../components/AppShell';
import { DEFAULT_ACTION_TIMEOUT_MS, type SidecarCall } from './useSidecarCall';
import type { BackgroundTask, BackgroundTaskAction } from '../lib/backgroundTasks';
import {
  awaitConversionRequest,
  buildBatchConvertPayload,
  conversionFailedMessage,
  conversionMissingTargetMessage,
  conversionProgressTaskUpdate,
  type ConversionProgressMode,
  type ConvertMode,
} from '../lib/conversion';
import { convertDefaultsFromSelection, fileName, isPathInsideFolder, siblingPdfPath, type ExplorerSelection } from '../lib/formatting';
import {
  findSiblingPdfPath,
  reconvertExportGate,
  reconvertInspectFailedMessage,
  reconvertMissingSourceMessage,
  reconvertPipelineOptionsFromInspect,
  reconvertPrefillFromInspect,
  resolveReconvertPdf,
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

export function createConversionController(getHost: () => ConversionHost) {
  const conversionRequestIdRef = { current: null as string | null };
  const conversionProgressCleanupRef = { current: null as { requestId: string; off: () => void } | null };
  const conversionCanceledRef = { current: false };
  const conversionInterruptRef = { current: null as 'stop' | 'skip' | null };
  const conversionPhaseRef = { current: null as string | null };
  const reconvertInFlightRef = { current: false };
  const reconvertDefaultsRef = { current: null as { overwrite: boolean; storeOriginal: boolean } | null };

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
    if (paths?.length) {
      host.setSelectedPdfs(paths);
      host.setExplorerSelection({ kind: 'file', path: paths[paths.length - 1], type: 'pdf' });
    }
    host.setReconvertNotice(null);
    host.setConvertMode('selected');
    host.setSideView('convert');
    host.setSidebarCollapsed(false);
  }

  function openConvertFolder(folderPath: string) {
    const host = getHost();
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
    const folder = host.folders.find((item) => item.path === folderPath);
    const listedPdf = findSiblingPdfPath(entry.path, folder?.entries ?? []);
    snapshotConvertDefaultsForReconvert();
    host.setReconvertBusy(true);
    host.setConversionError(null);
    host.setBatchOverwrite(true);
    host.setConvertMode('selected');
    host.setSideView('convert');
    host.setSidebarCollapsed(false);
    host.setReconvertNotice(`Preparing to reconvert “${fileName(entry.path)}”…`);
    if (listedPdf) {
      host.setSelectedPdfs([listedPdf]);
      host.setExplorerSelection({ kind: 'file', path: listedPdf, type: 'pdf' });
    }
    const reconvertCall = { scope: 'reconvert', timeoutMs: DEFAULT_ACTION_TIMEOUT_MS };
    let prepared = false;
    try {
      const sibling = siblingPdfPath(entry.path);
      const siblingExists = Boolean(listedPdf) || (sibling ? await window.vera.pathExists(sibling) : false);
      const resolution = resolveReconvertPdf(entry.path, {
        entries: folder?.entries ?? [],
        siblingExists,
      });
      const inspectResult = await host.call<InspectResult>(
        { action: SIDECAR_ACTIONS.inspect, path: entry.path },
        'Preparing reconvert',
        undefined,
        reconvertCall,
      );
      const prefill = reconvertPrefillFromInspect(inspectResult);

      let pdfPath: string | null = listedPdf;
      let restoredFromArchive = false;
      if (resolution.status === 'ready') {
        pdfPath = resolution.pdfPath;
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
              : reconvertMissingSourceMessage(entry.path),
          );
          return;
        }
        const exported = await host.call<ExportResult>(
          { action: SIDECAR_ACTIONS.export, path: entry.path, output: resolution.pdfPath },
          'Restoring embedded PDF',
          undefined,
          reconvertCall,
        );
        if (exported?.output) {
          pdfPath = exported.output;
          restoredFromArchive = true;
          void host.refreshFolder(folderPath, { showBusy: false }).catch((error) => {
            console.error('Unable to refresh folder after restoring source PDF', error);
          });
        } else {
          host.setReconvertNotice(null);
          host.setConversionError(reconvertMissingSourceMessage(entry.path));
          return;
        }
      } else {
        host.setReconvertNotice(null);
        host.setConversionError(reconvertMissingSourceMessage(entry.path));
        return;
      }

      if (!pdfPath) {
        host.setReconvertNotice(null);
        host.setConversionError(reconvertMissingSourceMessage(entry.path));
        return;
      }

      if (prefill.embeddingModel) host.setEmbeddingModel(prefill.embeddingModel);
      const nextPipeline = prefill.ingestPipeline || host.ingestPipeline;
      const nextDescriptor = host.ingestPipelineDescriptors.find(
        (item) => item.spec === nextPipeline || item.provider === nextPipeline,
      ) ?? null;
      const inspectOptions = reconvertPipelineOptionsFromInspect(inspectResult);
      const mergedOptions = mergePipelineFieldValues(nextDescriptor, {
        ...host.ingestPipelineConfigs[nextPipeline],
        ...inspectOptions,
      });
      if (prefill.ingestPipeline) host.setIngestPipeline(prefill.ingestPipeline);
      host.setIngestPipelineConfigs((prev) => ({ ...prev, [nextPipeline]: mergedOptions }));
      host.setPipelineOptions(mergedOptions);
      if (prefill.hasEmbeddedSource || restoredFromArchive) {
        host.setStoreOriginal(true);
      }

      host.setSelectedPdfs([pdfPath]);
      host.setExplorerSelection({ kind: 'file', path: pdfPath, type: 'pdf' });
      host.setReconvertNotice(
        restoredFromArchive
          ? 'Restored the embedded PDF beside this archive. Overwrite is on so Convert will replace the existing .vera. Choose a different pipeline or embedding if you want, then convert. Update the library index afterward if this folder is indexed.'
          : 'Overwrite is on so Convert will replace the existing .vera. The pipeline and embedding below start from this archive — change them if you want, then convert. Update the library index afterward if this folder is indexed.',
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
    host.setExplorerSelection({ kind: 'file', path: paths[paths.length - 1], type: 'pdf' });
    host.setConvertMode('selected');
    host.setBatchConvertResult(null);
  }

  async function chooseBatchDirectory() {
    const host = getHost();
    const chosen = await window.vera.pickFolder();
    if (chosen) {
      host.setBatchDirectory(chosen);
      host.setBatchConvertResult(null);
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

  async function batchConvertPdfs(options: { paths?: string[] } = {}) {
    const host = getHost();
    const selectedPaths = (options.paths ?? []).map((entry) => entry.trim()).filter(Boolean);
    const directory = host.batchDirectory.trim();
    if (!selectedPaths.length && !directory) {
      host.setConversionError(conversionMissingTargetMessage(host.convertMode));
      return;
    }
    conversionCanceledRef.current = false;
    conversionInterruptRef.current = null;
    conversionPhaseRef.current = null;
    host.setConversionError(null);
    host.setBatchConvertResult(null);
    host.setReconvertNotice(null);
    const preflight = await host.call<{
      ok: boolean;
      detail?: string;
      missing_credential_env?: string;
    }>(
      { action: SIDECAR_ACTIONS.preflightEmbedder, model: host.embeddingModel },
      'Checking embedder',
    );
    if (!preflight) return;
    if (!preflight.ok) {
      const missing = preflight.missing_credential_env?.trim();
      host.setConversionError(
        missing
          ? `Embedding provider is not ready. Set ${missing} under File > Settings → Embeddings, then convert again.`
          : (preflight.detail || 'Embedding provider is not ready.'),
      );
      return;
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
    const refreshRoot = selectedPaths[0] || directory;
    const offProgress = window.vera.onAnswerEvent((event) => {
      if (event.id !== conversionRequestId || event.event !== 'conversion_progress') return;
      applyConversionProgress(conversionRequestId, event, 'batch');
    });
    conversionProgressCleanupRef.current = { requestId: conversionRequestId, off: offProgress };
    try {
      const response = await awaitConversionRequest(
        window.vera.request<BatchConvertResult>(
          buildBatchConvertPayload({
            selectedPaths,
            directory,
            batchRecursive: host.batchRecursive,
            batchOverwrite: host.batchOverwrite,
            embeddingModel: host.embeddingModel,
            ingestPipeline: host.ingestPipeline,
            storeOriginal: host.storeOriginal,
            pipelineOptions: host.pipelineOptions,
            embedderOptions: host.embedderOptions,
          }),
          conversionRequestId,
        ),
        () => settleConversionRequest(conversionRequestId),
      );
      if (conversionRequestWasSuperseded(conversionRequestId)) return;
      if (response.cancelled || response.error?.includes('cancelled')) {
        refreshFoldersAfterConversion(refreshRoot);
        host.setConversionError(null);
        return;
      }
      if (!response.ok || !response.result) {
        throw new Error(response.error || conversionFailedMessage(selectedPaths.length > 0));
      }
      const result = response.result;
      host.setBatchConvertResult(result);
      refreshFoldersAfterConversion(result.directory || refreshRoot);
      if (selectedPaths.length) {
        host.setSelectedPdfs([]);
      }
    } catch (error) {
      if (conversionRequestWasSuperseded(conversionRequestId)) return;
      const message = error instanceof Error
        ? error.message
        : conversionFailedMessage(selectedPaths.length > 0);
      if (conversionCanceledRef.current || message.toLowerCase().includes('cancelled')) {
        refreshFoldersAfterConversion(refreshRoot);
        host.setConversionError(null);
        return;
      }
      host.setConversionError(message);
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
    stopConversion,
    skipCurrentConversion,
    batchConvertPdfs,
  };
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
