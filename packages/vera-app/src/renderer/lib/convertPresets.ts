/** Convert-view presets for source-run testing of embedding and ingest plugins. */

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

export const INGEST_PIPELINE_PRESETS: ConvertPresetOption[] = [
  {
    value: 'pymupdf',
    label: 'pymupdf — built-in (default)',
  },
  {
    value: 'docling',
    label: 'docling — HybridChunker',
    requiresProvider: 'docling',
  },
];

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

export function mergePipelineOptions(installed: string[]): ConvertPresetOption[] {
  const known = new Set(INGEST_PIPELINE_PRESETS.map((preset) => preset.value));
  const extras = installed
    .filter((name) => !known.has(name))
    .map((name) => ({ value: name, label: name }));
  return [...INGEST_PIPELINE_PRESETS, ...extras];
}
