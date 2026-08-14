import type {
  ExternalPythonConfig,
  PipelineDescriptor,
  PythonEnvironmentProbe,
} from '../src/shared/contracts.js';
import {
  COMPATIBLE_INGEST_MAJOR,
  COMPATIBLE_INGEST_MINOR,
  PLUGIN_API_VERSION,
  PLUGIN_HOST_PROTOCOL,
  SIDECAR_ACTIONS,
} from '../src/shared/protocol.js';

export const BUNDLED_PIPELINE_PROVIDER = 'pymupdf';
/** Cold Docling/Torch imports often exceed 40s; keep the launch probe above that. */
export const PLUGIN_HOST_VALIDATE_TIMEOUT_MS = 120_000;

export function parsePipelineProvider(spec: string | undefined | null): string {
  const raw = (spec || '').trim().toLowerCase();
  if (!raw) return BUNDLED_PIPELINE_PROVIDER;
  const provider = raw.split(':', 1)[0]?.trim();
  return provider || BUNDLED_PIPELINE_PROVIDER;
}

export function isBundledPipeline(spec: string | undefined | null): boolean {
  return parsePipelineProvider(spec) === BUNDLED_PIPELINE_PROVIDER;
}

export function normalizePipelineDescriptor(
  raw: unknown,
  source: 'bundled' | 'external',
): PipelineDescriptor | null {
  if (!raw || typeof raw !== 'object') return null;
  const item = raw as Record<string, unknown>;
  const provider = typeof item.provider === 'string' ? item.provider.trim().toLowerCase() : '';
  const spec = typeof item.spec === 'string' && item.spec.trim()
    ? item.spec.trim()
    : provider;
  if (!provider && !spec) return null;
  const notes = Array.isArray(item.notes)
    ? item.notes.filter((value): value is string => typeof value === 'string')
    : [];
  const fields = Array.isArray(item.fields)
    ? item.fields.filter((value) => value && typeof value === 'object') as PipelineDescriptor['fields']
    : [];
  return {
    provider: provider || parsePipelineProvider(spec),
    variant: typeof item.variant === 'string' ? item.variant : '',
    spec: spec || provider,
    label: typeof item.label === 'string' ? item.label : spec || provider,
    description: typeof item.description === 'string' ? item.description : '',
    installed: item.installed !== false,
    capabilities: item.capabilities && typeof item.capabilities === 'object'
      ? item.capabilities as PipelineDescriptor['capabilities']
      : {},
    fields,
    notes,
    source,
  };
}

export function mergePipelineDescriptors(
  bundled: PipelineDescriptor[],
  external: PipelineDescriptor[],
): PipelineDescriptor[] {
  const merged: PipelineDescriptor[] = [];
  const seen = new Set<string>();
  for (const descriptor of bundled) {
    const key = descriptor.provider || parsePipelineProvider(descriptor.spec);
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push({ ...descriptor, source: 'bundled' });
  }
  for (const descriptor of external) {
    const key = descriptor.provider || parsePipelineProvider(descriptor.spec);
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push({ ...descriptor, source: 'external' });
  }
  return merged;
}

export function shouldRouteToExternal(
  parser: string | undefined | null,
  bundledProviders: Iterable<string>,
): boolean {
  const provider = parsePipelineProvider(parser);
  const bundled = new Set(
    [...bundledProviders].map((item) => item.trim().toLowerCase()).filter(Boolean),
  );
  if (bundled.size === 0) {
    return !isBundledPipeline(provider);
  }
  return !bundled.has(provider);
}

export function parseVersionParts(version: string | undefined | null): { major: number; minor: number } | null {
  if (!version) return null;
  const match = version.trim().match(/^(\d+)\.(\d+)/);
  if (!match) return null;
  return { major: Number(match[1]), minor: Number(match[2]) };
}

export function pluginHostCompatibilityError(probe: {
  protocol?: number;
  plugin_api?: number;
  vera_ingest_version?: string;
}): string | null {
  if (probe.protocol !== PLUGIN_HOST_PROTOCOL) {
    return `Incompatible plugin host protocol ${probe.protocol ?? '(missing)'}; expected ${PLUGIN_HOST_PROTOCOL}.`;
  }
  if (probe.plugin_api !== PLUGIN_API_VERSION) {
    return `Incompatible ingest plugin API ${probe.plugin_api ?? '(missing)'}; expected ${PLUGIN_API_VERSION}.`;
  }
  const parts = parseVersionParts(probe.vera_ingest_version);
  if (!parts) {
    return 'The selected Python environment did not report a vera-ingest version.';
  }
  if (parts.major !== COMPATIBLE_INGEST_MAJOR || parts.minor !== COMPATIBLE_INGEST_MINOR) {
    return (
      `vera-ingest ${probe.vera_ingest_version} is not compatible with this app ` +
      `(requires ${COMPATIBLE_INGEST_MAJOR}.${COMPATIBLE_INGEST_MINOR}.x).`
    );
  }
  return null;
}

export function probeFromPing(
  executable: string,
  result: Record<string, unknown> | undefined,
  pipelines: PipelineDescriptor[] = [],
): PythonEnvironmentProbe {
  const protocol = typeof result?.protocol === 'number' ? result.protocol : undefined;
  const pluginApi = typeof result?.plugin_api === 'number' ? result.plugin_api : undefined;
  const pythonVersion = typeof result?.python === 'string' ? result.python : undefined;
  const veraIngestVersion = typeof result?.vera_ingest_version === 'string'
    ? result.vera_ingest_version
    : undefined;
  const loadErrors = Array.isArray(result?.load_errors)
    ? result.load_errors.filter((value): value is string => typeof value === 'string')
    : [];
  const compatibility = pluginHostCompatibilityError({
    protocol,
    plugin_api: pluginApi,
    vera_ingest_version: veraIngestVersion,
  });
  return {
    ok: !compatibility,
    executable,
    python_version: pythonVersion,
    vera_ingest_version: veraIngestVersion,
    protocol,
    plugin_api: pluginApi,
    pipelines,
    load_errors: loadErrors,
    error: compatibility || undefined,
  };
}

export function fallbackBundledDescriptors(): PipelineDescriptor[] {
  return [
    {
      provider: BUNDLED_PIPELINE_PROVIDER,
      variant: '',
      spec: BUNDLED_PIPELINE_PROVIDER,
      label: 'pymupdf — default PDF pipeline',
      description: 'Bundled PyMuPDF parser with selective Tesseract OCR.',
      installed: true,
      capabilities: {},
      fields: [],
      notes: [],
      source: 'bundled',
    },
  ];
}

export function normalizeExternalPython(raw: unknown): ExternalPythonConfig {
  if (!raw || typeof raw !== 'object') {
    return { enabled: false, executable: '' };
  }
  const value = raw as Record<string, unknown>;
  const executable = typeof value.executable === 'string' ? value.executable.trim() : '';
  const artifacts = typeof value.artifacts_path === 'string' ? value.artifacts_path.trim() : '';
  return {
    enabled: Boolean(value.enabled) && Boolean(executable),
    executable,
    artifacts_path: artifacts || undefined,
    validated_at: typeof value.validated_at === 'number' ? value.validated_at : undefined,
  };
}

export function conversionRuntimeOwner(
  action: string,
  parser: string | undefined,
  bundledProviders: Iterable<string>,
  externalReady: boolean,
): 'core' | 'external' {
  if (!externalReady) return 'core';
  if (action !== SIDECAR_ACTIONS.convert && action !== SIDECAR_ACTIONS.batchConvert) {
    return 'core';
  }
  return shouldRouteToExternal(parser, bundledProviders) ? 'external' : 'core';
}

export function processOwnerFor(
  requestId: string | undefined,
  owners: ReadonlyMap<string, 'core' | 'external'>,
): 'core' | 'external' {
  if (requestId && owners.get(requestId) === 'external') return 'external';
  return 'core';
}

export function pluginHostSpawnCommand(options: {
  pythonPath: string;
  pluginHostRoot: string;
  artifactsPath?: string;
  extraEnv?: NodeJS.ProcessEnv;
}): { executable: string; args: string[]; env: NodeJS.ProcessEnv } {
  const env: NodeJS.ProcessEnv = { ...(options.extraEnv || {}) };
  env.PYTHONPATH = options.pluginHostRoot;
  env.PYTHONUNBUFFERED = '1';
  env.PYTHONNOUSERSITE = '1';
  const artifacts = options.artifactsPath?.trim();
  if (artifacts) {
    env.DOCLING_ARTIFACTS_PATH = artifacts;
  } else {
    delete env.DOCLING_ARTIFACTS_PATH;
  }
  return {
    executable: options.pythonPath,
    args: ['-m', 'vera_plugin_host'],
    env,
  };
}
