import { describe, expect, it } from 'vitest';

import { plansheetRulesToUpdate } from './library-model-settings.js';

const config = {
  vlm_model: 'google/gemini-3-flash-preview',
  vlm_fallback_model: 'qwen/qwen2.5-vl-72b-instruct',
};

describe('plansheetRulesToUpdate', () => {
  it('updates plansheet rules that do not already have these settings', () => {
    expect(plansheetRulesToUpdate([
      { folder: '', parser: 'plansheet', pipeline_options: {} },
      { folder: 'Specs', parser: 'pymupdf', pipeline_options: {} },
      { folder: 'Old', parser: 'plansheet', pipeline_options: { ...config } },
    ], config)).toEqual([
      { folder: '', pipeline_options: config },
    ]);
  });

  it('leaves a library alone when plansheet settings are empty', () => {
    expect(plansheetRulesToUpdate(
      [{ folder: '', parser: 'plansheet', pipeline_options: {} }],
      {},
    )).toEqual([]);
  });
});
