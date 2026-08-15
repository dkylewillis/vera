/** IPC invoke and event channel names shared by Electron main and preload. */
export const IPC_CHANNELS = {
  showMenu: 'vera:showMenu',
  request: 'vera:request',
  cancelAnswer: 'vera:cancelAnswer',
  cancelRequest: 'vera:cancelRequest',
  skipConversion: 'vera:skipConversion',
  getSettings: 'vera:getSettings',
  saveSettings: 'vera:saveSettings',
  saveApiKey: 'vera:saveApiKey',
  clearApiKey: 'vera:clearApiKey',
  saveHfToken: 'vera:saveHfToken',
  clearHfToken: 'vera:clearHfToken',
  saveEnvSecret: 'vera:saveEnvSecret',
  clearEnvSecret: 'vera:clearEnvSecret',
  getSessions: 'vera:getSessions',
  saveSession: 'vera:saveSession',
  deleteSession: 'vera:deleteSession',
  listModes: 'vera:listModes',
  openModesFolder: 'vera:openModesFolder',
  pickArchive: 'vera:pickArchive',
  pickFolder: 'vera:pickFolder',
  listFolder: 'vera:listFolder',
  pathExists: 'vera:pathExists',
  showInFolder: 'vera:showInFolder',
  trashWorkspaceFile: 'vera:trashWorkspaceFile',
  setWatchedFolders: 'vera:setWatchedFolders',
  pickPdf: 'vera:pickPdf',
  saveAny: 'vera:saveAny',
  openTarget: 'vera:openTarget',
  openSettings: 'vera:openSettings',
  folderChanged: 'vera:folderChanged',
  answerEvent: 'vera:answerEvent',
  pickPythonInterpreter: 'vera:pickPythonInterpreter',
  validatePythonEnvironment: 'vera:validatePythonEnvironment',
  refreshExternalPipelines: 'vera:refreshExternalPipelines',
  pythonEnvironment: 'vera:pythonEnvironment',
} as const;

export type IpcChannel = (typeof IPC_CHANNELS)[keyof typeof IPC_CHANNELS];

/** Sidecar JSON-RPC action names. Keep in sync with vera_app.protocol. */
export const SIDECAR_ACTIONS = {
  ping: 'ping',
  inspect: 'inspect',
  validate: 'validate',
  indexStatus: 'index_status',
  indexBuild: 'index_build',
  indexUpdate: 'index_update',
  search: 'search',
  figureData: 'figure_data',
  answer: 'answer',
  convert: 'convert',
  batchConvert: 'batch_convert',
  export: 'export',
  source: 'source',
  page: 'page',
  listModels: 'list_models',
  listEmbeddingProviders: 'list_embedding_providers',
  describeEmbeddingProviders: 'describe_embedding_providers',
  listEmbeddingModels: 'list_embedding_models',
  preflightEmbedder: 'preflight_embedder',
  listIngestPipelines: 'list_ingest_pipelines',
  describeIngestPipelines: 'describe_ingest_pipelines',
  ocrLanguagesList: 'ocr_languages_list',
  ocrLanguagesDownload: 'ocr_languages_download',
  listModes: 'list_modes',
  configurePluginRuntime: 'configure_plugin_runtime',
  pluginRuntimeStatus: 'plugin_runtime_status',
  cancel: 'cancel',
  skip: 'skip',
} as const;

export type SidecarAction = (typeof SIDECAR_ACTIONS)[keyof typeof SIDECAR_ACTIONS];

/** Stream event names emitted by the sidecar. Keep in sync with vera_app.protocol. */
export const STREAM_EVENTS = [
  'search_start',
  'search_done',
  'llm_request',
  'llm_response',
  'tool_call',
  'answer_delta',
  'answer_reset',
  'conversion_progress',
  'index_progress',
  'inspection_progress',
  'ocr_download_progress',
] as const;

export type StreamEventName = (typeof STREAM_EVENTS)[number];

/** JSON-lines protocol spoken by the shipped `vera_plugin_host` worker. */
export const PLUGIN_HOST_PROTOCOL = 2;
/** `vera_ingest.pipeline.PLUGIN_API_VERSION` expected by this app. */
export const PLUGIN_API_VERSION = 1;
export const COMPATIBLE_INGEST_MAJOR = 0;
export const COMPATIBLE_INGEST_MINOR = 3;
