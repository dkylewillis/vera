/** Shared IPC channel names and sidecar actions used by Electron and the renderer. */

export const IPC_CHANNELS = {
  request: 'vera:request',
  cancelAnswer: 'vera:cancelAnswer',
  cancelRequest: 'vera:cancelRequest',
  skipConversion: 'vera:skipConversion',
  getSettings: 'vera:getSettings',
  saveSettings: 'vera:saveSettings',
  pickPythonInterpreter: 'vera:pickPythonInterpreter',
  validatePythonEnvironment: 'vera:validatePythonEnvironment',
  refreshExternalPipelines: 'vera:refreshExternalPipelines',
} as const;

export const SIDECAR_ACTIONS = {
  ping: 'ping',
  convert: 'convert',
  batchConvert: 'batch_convert',
  listIngestPipelines: 'list_ingest_pipelines',
  describeIngestPipelines: 'describe_ingest_pipelines',
  cancel: 'cancel',
  skip: 'skip',
} as const;

export const PLUGIN_HOST_PROTOCOL = 1;
export const PLUGIN_API_VERSION = 1;
export const COMPATIBLE_INGEST_MAJOR = 0;
export const COMPATIBLE_INGEST_MINOR = 2;
