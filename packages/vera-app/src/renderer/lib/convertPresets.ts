/** Convert-view presets for embedding models and optional pipeline install hints. */

import type { PipelineDescriptor } from '../../shared/contracts';

export type ConvertPresetOption = {
  value: string;
  label: string;
  /** When false, the option is shown but disabled until the sidecar reports it. */
  requiresProvider?: string;
};

export const EMBEDDING_MODEL_PRESETS: ConvertPresetOption[] = [
  {
    value: 'hashing',
    label: 'hashing — offline lexical (default)',
  },
  {
    value: 'sentence-transformers:all-MiniLM-L6-v2',
    label: 'sentence-transformers:all-MiniLM-L6-v2',
    requiresProvider: 'sentence-transformers',
  },
];

/** Optional pipelines that should appear disabled with an install hint when missing. */
export const PIPELINE_INSTALL_HINTS: Record<string, { label: string; hint: string }> = {
  docling: {
    label: 'docling — HybridChunker',
    hint: 'From the repo root run `uv sync --extra docling` and restart the app.',
  },
};

export const CUSTOM_EMBEDDING_VALUE = '__custom__';

export function isKnownEmbeddingPreset(model: string): boolean {
  const normalized = model.trim();
  return EMBEDDING_MODEL_PRESETS.some((preset) => preset.value === normalized);
}

export function embeddingSelectValue(model: string): string {
  return isKnownEmbeddingPreset(model) ? model.trim() : CUSTOM_EMBEDDING_VALUE;
}

export function presetOptionAvailable(
  option: ConvertPresetOption,
  installed: string[],
): boolean {
  if (!option.requiresProvider) return true;
  return installed.includes(option.requiresProvider);
}

export function pipelineSelectOptions(
  descriptors: PipelineDescriptor[],
): ConvertPresetOption[] {
  const installed = descriptors.map((descriptor) => ({
    value: descriptor.spec,
    label: descriptor.label || descriptor.spec,
  }));
  const known = new Set(installed.map((option) => option.value));
  const missingHints = Object.entries(PIPELINE_INSTALL_HINTS)
    .filter(([provider]) => !known.has(provider) && !descriptors.some((item) => item.provider === provider))
    .map(([provider, meta]) => ({
      value: provider,
      label: meta.label,
      requiresProvider: provider,
    }));
  return [...installed, ...missingHints];
}

export function pipelineInstallHint(
  pipeline: string,
  descriptors: PipelineDescriptor[],
): string | null {
  const descriptor = descriptors.find((item) => item.spec === pipeline || item.provider === pipeline);
  if (descriptor?.installed) {
    return descriptor.description || null;
  }
  const hint = PIPELINE_INSTALL_HINTS[pipeline];
  return hint?.hint ?? null;
}
