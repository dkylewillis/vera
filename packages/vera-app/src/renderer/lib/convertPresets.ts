/** Convert-view presets for embedding models and optional pipeline install hints. */

import type { EmbedderDescriptor, PipelineDescriptor } from '../../shared/contracts';

export type ConvertPresetOption = {
  value: string;
  label: string;
  /** When false, the option is shown but disabled until the sidecar reports it. */
  requiresProvider?: string;
  source?: 'bundled' | 'external';
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
    label: 'Advanced layout (slower)',
    hint: 'Docling is bundled in the desktop app. For CLI use, install it with `pip install "vera-cli[docling]>=0.3.0"` or `uv sync --extra docling`.',
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

export function embeddingProviderFromSpec(model: string): string {
  const raw = model.trim();
  if (!raw || raw === 'hashing' || /^vera-hashing-\d+$/.test(raw)) return 'hashing';
  if (raw === 'all-MiniLM-L6-v2' || raw.startsWith('sentence-transformers')) {
    return 'sentence-transformers';
  }
  if (raw.includes(':')) return raw.split(':', 1)[0]?.trim().toLowerCase() || raw.toLowerCase();
  return raw.toLowerCase();
}

export function embeddingSelectOptions(
  descriptors: EmbedderDescriptor[],
): ConvertPresetOption[] {
  const installed = descriptors.map((descriptor) => ({
    value: descriptor.default_model_id
      ? `${descriptor.provider}:${descriptor.default_model_id}`
      : descriptor.provider,
    label: descriptor.label || descriptor.provider,
    source: descriptor.source,
    requiresProvider: descriptor.provider,
  }));
  const known = new Set(descriptors.map((item) => item.provider));
  const presets = EMBEDDING_MODEL_PRESETS.filter((preset) => {
    const provider = preset.requiresProvider || embeddingProviderFromSpec(preset.value);
    return !known.has(provider) || preset.value === 'hashing';
  });
  const extra = installed.filter((option) => {
    const provider = option.requiresProvider || embeddingProviderFromSpec(option.value);
    return provider !== 'hashing' && provider !== 'sentence-transformers';
  });
  return [...presets, ...extra];
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
  const ready = descriptors.filter((descriptor) => descriptor.installed);
  const installed = ready.map((descriptor) => ({
    value: descriptor.spec,
    label: descriptor.label || descriptor.spec,
    source: descriptor.source,
  }));
  const known = new Set([
    ...installed.map((option) => option.value),
    ...ready.map((item) => item.provider),
  ]);
  const missingHints = Object.entries(PIPELINE_INSTALL_HINTS)
    .filter(([provider]) => !known.has(provider) && !ready.some((item) => item.provider === provider))
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
