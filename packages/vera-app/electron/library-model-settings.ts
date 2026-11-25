export type LibraryPipelineRule = {
  folder?: string;
  parser?: string;
  pipeline_options?: Record<string, unknown>;
};

function stableOptions(value: Record<string, unknown>): string {
  return JSON.stringify(Object.keys(value).sort().map((key) => [key, value[key]]));
}

/** Plansheet rules whose stored options differ from the Convert settings. */
export function plansheetRulesToUpdate(
  rules: LibraryPipelineRule[],
  config: Record<string, unknown> | null | undefined,
): Array<{ folder: string; pipeline_options: Record<string, unknown> }> {
  if (!config || !Object.keys(config).length) return [];
  const wanted = stableOptions(config);
  const updates: Array<{ folder: string; pipeline_options: Record<string, unknown> }> = [];
  for (const rule of rules) {
    if ((rule.parser || '').trim() !== 'plansheet') continue;
    const current = rule.pipeline_options && typeof rule.pipeline_options === 'object' && !Array.isArray(rule.pipeline_options)
      ? rule.pipeline_options
      : {};
    if (stableOptions(current) === wanted) continue;
    updates.push({
      folder: (rule.folder || '').replace(/\\/g, '/'),
      pipeline_options: config,
    });
  }
  return updates;
}
