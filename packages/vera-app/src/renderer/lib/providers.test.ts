import { describe, expect, it } from 'vitest';
import { PRO_PRESET_KEY } from '../../shared/pro';
import { staleModelProviderIds } from '../components/ProviderManagers';
import { providerRowStatus, providerRows } from '../components/ProviderSettings';
import {
  canListModels,
  isModelListStale,
  listModelsLlm,
  MODEL_LIST_MAX_AGE_MS,
  withDiscoveredModels,
} from './providers';
import type { ProviderProfile } from '../types';

const NOW = 1_800_000_000_000;

function profile(overrides: Partial<ProviderProfile> = {}): ProviderProfile {
  return {
    id: 'p1',
    label: 'OpenAI',
    provider: 'openai_compatible',
    preset_key: 'openai',
    base_url: 'https://api.openai.com/v1',
    api_key_env: 'OPENAI_API_KEY',
    auth_type: 'api_key',
    has_api_key: true,
    models: [],
    temperature: 0.2,
    ...overrides,
  };
}

describe('model list freshness', () => {
  it('treats never-loaded and old lists as stale', () => {
    expect(isModelListStale(profile(), MODEL_LIST_MAX_AGE_MS, NOW)).toBe(true);
    expect(isModelListStale(profile({ models_refreshed_at: NOW - MODEL_LIST_MAX_AGE_MS - 1 }), MODEL_LIST_MAX_AGE_MS, NOW)).toBe(true);
    expect(isModelListStale(profile({ models_refreshed_at: NOW - 60_000 }), MODEL_LIST_MAX_AGE_MS, NOW)).toBe(false);
  });

  it('only lists models when the request can succeed', () => {
    expect(canListModels(profile())).toBe(true);
    expect(canListModels(profile({ has_api_key: false }))).toBe(false);
    expect(canListModels(profile({ has_api_key: false }), 'sk-typed')).toBe(true);
    expect(canListModels(profile({ base_url: ' ' }))).toBe(false);
    expect(canListModels(profile({ auth_type: 'none', has_api_key: false }))).toBe(true);
  });

  it('re-checks stale providers when the model list opens, skipping VERA Pro', () => {
    const ids = staleModelProviderIds([
      profile({ id: 'stale' }),
      profile({ id: 'fresh', models_refreshed_at: NOW - 1000 }),
      profile({ id: 'no-key', has_api_key: false }),
      profile({ id: 'pro', preset_key: PRO_PRESET_KEY }),
    ], NOW);
    expect(ids).toEqual(['stale']);
  });
});

describe('listModelsLlm', () => {
  it('passes the preset key so VERA Pro lists models with the Pro key', () => {
    expect(listModelsLlm(profile({ preset_key: PRO_PRESET_KEY }))).toMatchObject({ provider_key: PRO_PRESET_KEY });
    expect(listModelsLlm(profile({ preset_key: undefined }))).toMatchObject({ provider_key: '' });
  });

  it('includes a typed key only when one is given', () => {
    expect(listModelsLlm(profile())).not.toHaveProperty('api_key');
    expect(listModelsLlm(profile(), '  sk-new  ')).toMatchObject({ api_key: 'sk-new' });
  });
});

describe('withDiscoveredModels', () => {
  it('stores the curated list and enables catalog models the first time', () => {
    const next = withDiscoveredModels(profile(), ['gpt-4o-mini', 'whisper-1', 'gpt-4.1'], NOW);
    expect(next.available_models).toEqual(['gpt-4.1', 'gpt-4o-mini']);
    expect(next.models).toEqual(['gpt-4.1', 'gpt-4o-mini']);
    expect(next.models_refreshed_at).toBe(NOW);
  });

  it('keeps the models the user already chose', () => {
    const next = withDiscoveredModels(profile({ models: ['gpt-4o'] }), ['gpt-4o-mini', 'gpt-4o'], NOW);
    expect(next.models).toEqual(['gpt-4o']);
    expect(next.available_models).toEqual(['gpt-4o', 'gpt-4o-mini']);
  });

  it('enables every live model for local servers', () => {
    const local = profile({ preset_key: 'ollama', provider: 'ollama', auth_type: 'none', base_url: 'http://localhost:11434/v1' });
    expect(withDiscoveredModels(local, ['llama3.2', 'qwen3'], NOW).models).toEqual(['llama3.2', 'qwen3']);
  });
});

describe('provider rows', () => {
  it('lists hosted presets, then local presets, then custom endpoints', () => {
    const custom = profile({ id: 'c1', label: 'My vLLM', preset_key: undefined, base_url: 'http://gpu-box:8000/v1' });
    const rows = providerRows([custom]);
    expect(rows.map((row) => row.kind)).toEqual(['hosted', 'hosted', 'hosted', 'local', 'local', 'custom']);
    expect(rows[rows.length - 1].label).toBe('My vLLM');
  });

  it('describes what each row still needs', () => {
    const [pro, openai] = providerRows([profile({ has_api_key: false })]);
    expect(providerRowStatus(pro).label).toBe('Sign in to use');
    expect(providerRowStatus(openai).label).toBe('Needs key');
    const ready = providerRows([profile({ models: ['gpt-4o-mini'] })]).find((row) => row.preset?.key === 'openai');
    expect(ready && providerRowStatus(ready).label).toBe('Ready');
    const notSetUp = providerRows([]).find((row) => row.preset?.key === 'ollama');
    expect(notSetUp && providerRowStatus(notSetUp).label).toBe('Not set up');
  });
});
