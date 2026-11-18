import { describe, expect, it } from 'vitest';
import { environmentErrors, environmentPipelinesLabel, pluginLoadErrors, pluginPipelinesLabel } from './PluginsSection';

describe('separate Python environment', () => {
  it('names the pipelines the environment runs', () => {
    expect(environmentPipelinesLabel([])).toBe('It has no pipelines beyond the ones VERA already includes.');
    expect(environmentPipelinesLabel(['docling'])).toBe('Runs the docling pipeline.');
    expect(environmentPipelinesLabel(['a', 'b', 'c'])).toBe('Runs the a, b and c pipelines.');
  });

  it('picks the environment errors out of the load errors', () => {
    const errors = [
      "Failed to load ingest pipeline plugin 'plans': ImportError('fitz')",
      'Separate Python environment C:\\envs\\docling: C:\\envs\\docling does not exist.',
    ];
    expect(environmentErrors(errors)).toEqual([errors[1]]);
    expect(environmentErrors([errors[0]])).toEqual([]);
  });
});

describe('pluginPipelinesLabel', () => {
  it('names the pipelines a plugin adds', () => {
    expect(pluginPipelinesLabel({ pipelines: [] })).toBe('Adds no ingest pipelines.');
    expect(pluginPipelinesLabel({ pipelines: ['plans'] })).toBe('Adds the plans pipeline.');
    expect(pluginPipelinesLabel({ pipelines: ['a', 'b', 'c'] })).toBe('Adds the a, b and c pipelines.');
  });
});

describe('pluginLoadErrors', () => {
  it('keeps only errors that name one of the plugin pipelines', () => {
    const errors = [
      "Failed to load ingest pipeline plugin 'plans': ImportError('fitz')",
      "Failed to load ingest pipeline plugin 'other': ImportError('x')",
    ];
    expect(pluginLoadErrors({ pipelines: ['plans'] }, errors)).toEqual([errors[0]]);
    expect(pluginLoadErrors({ pipelines: ['plan'] }, errors)).toEqual([]);
  });
});
