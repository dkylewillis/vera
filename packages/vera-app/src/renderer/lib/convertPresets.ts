/** Convert-view presets for embedding models and optional pipeline install hints. */

import type { EmbedderDescriptor, PipelineDescriptor } from '../../shared/contracts';
import { DESKTOP_DEFAULT_EMBEDDING_MODEL } from '../../shared/desktop-defaults';

export type ConvertPresetOption = {
  value: string;
  label: string;
  /** When false, the option is shown but disabled until the sidecar reports it. */
  requiresProvider?: string;
  source?: 'bundled' | 'external';
};

/** Desktop default for new installs; saved settings keep their own model. */
export const DEFAULT_EMBEDDING_MODEL = DESKTOP_DEFAULT_EMBEDDING_MODEL;

export const EMBEDDING_MODEL_PRESETS: ConvertPresetOption[] = [
  {
    value: DESKTOP_DEFAULT_EMBEDDING_MODEL,
    label: 'Standard — local semantic (MiniLM)',
    requiresProvider: 'sentence-transformers',
  },
  {
    value: 'hashing',
    label: 'Fast — offline lexical (hashing)',
  },
  {
    value: 'openai:text-embedding-3-small',
    label: 'OpenAI text-embedding-3-small (cloud)',
    requiresProvider: 'openai',
  },
  {
    value: 'openai:text-embedding-3-large',
    label: 'OpenAI text-embedding-3-large (cloud)',
    requiresProvider: 'openai',
  },
];

/** Short name for a model spec, e.g. in "This library uses MiniLM". */
export function embeddingModelLabel(model: string): string {
  const key = embeddingModelKey(model);
  if (key === 'hashing') return 'hashing';
  if (key === 'sentence-transformers:all-minilm-l6-v2') return 'MiniLM';
  return model.trim();
}

function embeddingModelKey(model: string): string {
  const provider = embeddingProviderFromSpec(model);
  if (provider === 'hashing') return 'hashing';
  const raw = model.trim();
  const id = raw.includes(':') ? raw.slice(raw.indexOf(':') + 1) : raw;
  return `${provider}:${id.replace(/^sentence-transformers\//i, '').toLowerCase()}`;
}

/** Archives store either the convert spec or the bare model id; compare both forms. */
export function embeddingModelsMatch(a: string, b: string): boolean {
  return embeddingModelKey(a) === embeddingModelKey(b);
}

/** Optional pipelines that should appear disabled with an install hint when missing. */
export const PIPELINE_INSTALL_HINTS: Record<string, { label: string; hint: string }> = {};

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
    return !known.has(provider)
      || preset.value === 'hashing'
      || provider === 'openai'
      || provider === 'sentence-transformers';
  });
  const extra = installed.filter((option) => {
    const provider = option.requiresProvider || embeddingProviderFromSpec(option.value);
    return provider !== 'hashing' && provider !== 'sentence-transformers' && provider !== 'openai';
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

/** Descriptors without `source_formats` predate the field and only handled PDFs. */
export function pipelineAcceptsPdf(descriptor: PipelineDescriptor): boolean {
  const formats = descriptor.capabilities?.source_formats;
  if (!formats?.length) return true;
  return formats.some((format) => format.replace(/^\./, '').toLowerCase() === 'pdf');
}

/**
 * The pipeline select only chooses how PDFs are converted; Markdown and other
 * formats are routed by file extension, so non-PDF pipelines are not listed.
 */
export function pipelineSelectOptions(
  descriptors: PipelineDescriptor[],
): ConvertPresetOption[] {
  const ready = descriptors.filter((descriptor) => descriptor.installed && pipelineAcceptsPdf(descriptor));
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
