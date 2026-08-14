import type { PipelineDescriptor } from '../../shared/contracts';

export type ConvertPresetOption = {
  value: string;
  label: string;
  requiresProvider?: string;
  source?: 'bundled' | 'external';
};

export const PIPELINE_INSTALL_HINTS: Record<string, { label: string; hint: string }> = {
  docling: {
    label: 'docling — HybridChunker',
    hint: 'Install it in the configured Python environment with `python -m pip install vera-ingest-docling`, or clone the plugin and run `python -m pip install -e <folder>`, then Validate / Refresh.',
  },
};

export function parsePipelineProvider(spec: string): string {
  const raw = spec.trim().toLowerCase();
  if (!raw) return 'pymupdf';
  return raw.split(':', 1)[0] || 'pymupdf';
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
    source: descriptor.source,
  }));
  const known = new Set([
    ...installed.map((option) => option.value),
    ...descriptors.map((item) => item.provider),
  ]);
  const missingHints = Object.entries(PIPELINE_INSTALL_HINTS)
    .filter(([provider]) => !known.has(provider))
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
  const descriptor = descriptors.find(
    (item) => item.spec === pipeline || item.provider === parsePipelineProvider(pipeline),
  );
  if (descriptor?.installed) {
    return descriptor.description || null;
  }
  const hint = PIPELINE_INSTALL_HINTS[parsePipelineProvider(pipeline)];
  return hint?.hint ?? null;
}
