import { describe, expect, it } from 'vitest';
import {
  BUNDLED_PIPELINE_PROVIDER,
  conversionRuntimeOwner,
  isBundledPipeline,
  mergePipelineDescriptors,
  normalizeExternalPython,
  parsePipelineProvider,
  pluginHostCompatibilityError,
  pluginHostSpawnCommand,
  processOwnerFor,
  shouldRouteToExternal,
} from './ingest-runtime.js';
import type { PipelineDescriptor } from '../src/shared/contracts.js';

const pymupdf: PipelineDescriptor = {
  provider: 'pymupdf',
  variant: '',
  spec: 'pymupdf',
  label: 'pymupdf',
  description: '',
  installed: true,
  capabilities: {},
  fields: [],
  source: 'bundled',
};

const docling: PipelineDescriptor = {
  provider: 'docling',
  variant: 'hybrid',
  spec: 'docling',
  label: 'docling',
  description: '',
  installed: true,
  capabilities: {},
  fields: [],
  source: 'external',
};

describe('ingest-runtime', () => {
  it('parses provider names from pipeline specs', () => {
    expect(parsePipelineProvider('')).toBe(BUNDLED_PIPELINE_PROVIDER);
    expect(parsePipelineProvider('docling:hybrid')).toBe('docling');
    expect(isBundledPipeline('pymupdf')).toBe(true);
    expect(isBundledPipeline('docling')).toBe(false);
  });

  it('keeps bundled providers when merging duplicates', () => {
    const duplicate: PipelineDescriptor = { ...pymupdf, source: 'external', label: 'external pymupdf' };
    const merged = mergePipelineDescriptors([pymupdf], [duplicate, docling]);
    expect(merged.map((item) => item.provider)).toEqual(['pymupdf', 'docling']);
    expect(merged[0]?.source).toBe('bundled');
    expect(merged[1]?.source).toBe('external');
  });

  it('routes unknown providers to the external worker', () => {
    expect(shouldRouteToExternal('pymupdf', ['pymupdf'])).toBe(false);
    expect(shouldRouteToExternal('docling', ['pymupdf'])).toBe(true);
    expect(shouldRouteToExternal('docling:hybrid', ['pymupdf'])).toBe(true);
  });

  it('rejects incompatible plugin hosts', () => {
    expect(pluginHostCompatibilityError({
      protocol: 1,
      plugin_api: 1,
      vera_ingest_version: '0.3.0',
    })).toBeNull();
    expect(pluginHostCompatibilityError({
      protocol: 2,
      plugin_api: 1,
      vera_ingest_version: '0.3.0',
    })).toMatch(/protocol/);
    expect(pluginHostCompatibilityError({
      protocol: 1,
      plugin_api: 1,
      vera_ingest_version: '0.2.5',
    })).toMatch(/not compatible/);
  });

  it('normalizes external Python settings and disables empty interpreters', () => {
    expect(normalizeExternalPython(null)).toEqual({ enabled: false, executable: '' });
    expect(normalizeExternalPython({
      enabled: true,
      executable: '  C:\\venvs\\plugins\\Scripts\\python.exe  ',
      artifacts_path: '  D:\\models  ',
      validated_at: 42,
    })).toEqual({
      enabled: true,
      executable: 'C:\\venvs\\plugins\\Scripts\\python.exe',
      artifacts_path: 'D:\\models',
      validated_at: 42,
    });
    expect(normalizeExternalPython({ enabled: true, executable: '   ' }).enabled).toBe(false);
  });

  it('builds plugin host spawn arguments for Windows interpreter paths', () => {
    const command = pluginHostSpawnCommand({
      pythonPath: 'C:\\Users\\me\\venv\\Scripts\\python.exe',
      pluginHostRoot: 'C:\\Program Files\\VERA\\resources\\python\\plugin-host',
      artifactsPath: 'D:\\docling-cache',
      extraEnv: {
        PATH: 'C:\\Windows',
        PYTHONPATH: 'C:\\should-not-leak',
        DOCLING_ARTIFACTS_PATH: 'C:\\old-cache',
        HF_TOKEN: 'hf_test',
      },
    });
    expect(command.executable).toBe('C:\\Users\\me\\venv\\Scripts\\python.exe');
    expect(command.args).toEqual(['-m', 'vera_plugin_host']);
    expect(command.env.PYTHONPATH).toBe('C:\\Program Files\\VERA\\resources\\python\\plugin-host');
    expect(command.env.PYTHONUNBUFFERED).toBe('1');
    expect(command.env.PYTHONNOUSERSITE).toBe('1');
    expect(command.env.DOCLING_ARTIFACTS_PATH).toBe('D:\\docling-cache');
    expect(command.env.HF_TOKEN).toBe('hf_test');
  });

  it('routes convert requests by provider and keeps cancel ownership', () => {
    expect(conversionRuntimeOwner('search', 'docling', ['pymupdf'], true)).toBe('core');
    expect(conversionRuntimeOwner('convert', 'pymupdf', ['pymupdf'], true)).toBe('core');
    expect(conversionRuntimeOwner('convert', 'docling', ['pymupdf'], true)).toBe('external');
    expect(conversionRuntimeOwner('batch_convert', 'docling', ['pymupdf'], false)).toBe('core');
    const owners = new Map<string, 'core' | 'external'>([['req-ext', 'external'], ['req-core', 'core']]);
    expect(processOwnerFor('req-ext', owners)).toBe('external');
    expect(processOwnerFor('req-core', owners)).toBe('core');
    expect(processOwnerFor('missing', owners)).toBe('core');
  });
});
