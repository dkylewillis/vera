import { describe, expect, it } from 'vitest';

import { DESKTOP_DEFAULT_EMBEDDING_MODEL } from './desktop-defaults.js';
import {
  PRO_KEY_SECRET,
  PRO_OPENROUTER_BASE_URL,
  PRO_PRESET_KEY,
  parseVeraAuthCallback,
  proFirst,
  providerCredentialKey,
  includedUsagePercent,
  onDemandLabel,
  usagePercent,
  veraProLimitMessage,
  veraAuthCallbackFromArgs,
  withProProvider,
} from './pro.js';
import type { AppSettings } from './contracts.js';

describe('proFirst', () => {
  it('moves VERA Pro to the top and keeps the rest in order', () => {
    const providers = [
      { id: 'openai', preset_key: 'openai' },
      { id: 'ollama', preset_key: 'ollama' },
      { id: 'pro', preset_key: PRO_PRESET_KEY },
      { id: 'custom' },
    ];
    expect(proFirst(providers).map((profile) => profile.id)).toEqual(['pro', 'openai', 'ollama', 'custom']);
    expect(providers[0].id).toBe('openai');
  });
});

describe('desktop embedding default', () => {
  it('is the local MiniLM model', () => {
    expect(DESKTOP_DEFAULT_EMBEDDING_MODEL).toBe('sentence-transformers:all-MiniLM-L6-v2');
  });
});

describe('VERA Pro credential separation', () => {
  it('stores the Pro key apart from a personal OpenRouter key at the same base URL', () => {
    const personal = providerCredentialKey({
      preset_key: 'openrouter',
      base_url: PRO_OPENROUTER_BASE_URL,
    });
    const pro = providerCredentialKey({
      preset_key: PRO_PRESET_KEY,
      base_url: `${PRO_OPENROUTER_BASE_URL}/`,
    });
    expect(personal).toBe('https://openrouter.ai/api/v1');
    expect(pro).toBe(PRO_KEY_SECRET);
    expect(pro).not.toBe(personal);
  });

  it('activates a stable Pro provider without dropping other providers', () => {
    const settings: AppSettings = {
      providers: [{
        id: 'prov_own',
        preset_key: 'openrouter',
        label: 'OpenRouter',
        provider: 'openai_compatible',
        base_url: PRO_OPENROUTER_BASE_URL,
        api_key_env: 'OPENROUTER_API_KEY',
        auth_type: 'api_key',
        temperature: 0.2,
        models: ['openai/gpt-4.1-mini'],
      }],
      active_provider_id: 'prov_own',
      active_model: 'openai/gpt-4.1-mini',
      active_mode_id: '',
      embedding_model: 'hashing',
      ingest_pipeline: 'pymupdf',
      ingest_pipeline_configs: {},
    };
    const next = withProProvider(settings);
    expect(next.providers).toHaveLength(2);
    expect(next.providers[0]?.id).toBe('prov_own');
    expect(next.active_provider_id).toBe('prov_vera_pro');
    expect(next.active_model).toBe('google/gemini-3.5-flash');
    expect(next.embedding_model).toBe('hashing');
    const again = withProProvider(next);
    expect(again.providers.filter((profile) => profile.preset_key === PRO_PRESET_KEY)).toHaveLength(1);
  });
});

describe('Pro usage display', () => {
  it('reports a percentage and hides the dollar cap', () => {
    expect(usagePercent(1.5, 6)).toBe(25);
    expect(usagePercent(0, 6)).toBe(0);
    expect(usagePercent(9, 6)).toBe(100);
    expect(usagePercent(null, 6)).toBe(0);
    expect(usagePercent(1, null)).toBeNull();
    expect(usagePercent(1, 0)).toBeNull();
  });

  it('shows included usage as a percentage and on-demand usage in dollars', () => {
    const account = {
      includedPercent: 52,
      usageUsd: 99,
      limitUsd: 6,
      onDemandEnabled: true,
      onDemandUsedUsd: 3.4,
      onDemandLimitUsd: 10,
    };
    expect(includedUsagePercent(account)).toBe(52);
    expect(onDemandLabel(account)).toBe('$3.40 of $10.00');
    expect(onDemandLabel({ ...account, onDemandEnabled: false })).toBe('Off');
    expect(includedUsagePercent({ ...account, includedPercent: null })).toBe(100);
  });

  it('explains a VERA Pro key limit and leaves other providers alone', () => {
    const error = 'LLM provider request failed (HTTP 402): Key limit exceeded';
    expect(veraProLimitMessage(error, { onDemandEnabled: false, siteUrl: 'https://veradoc.si' }, 'vera_pro'))
      .toBe('Included usage is used up. Turn on on-demand usage at https://veradoc.si/account.html');
    expect(veraProLimitMessage(error, { onDemandEnabled: true, siteUrl: 'https://veradoc.si/' }, 'vera_pro'))
      .toBe('On-demand limit reached. Raise your limit at https://veradoc.si/account.html');
    expect(veraProLimitMessage(error, null, 'openrouter')).toBeNull();
  });
});

describe('vera:// auth callback', () => {
  it('parses a protocol callback and ignores archive paths', () => {
    expect(parseVeraAuthCallback('vera://auth/callback?code=abc&state=xyz')).toEqual({
      code: 'abc',
      state: 'xyz',
    });
    expect(parseVeraAuthCallback('"vera://auth/callback?code=abc&state=xyz"')).toEqual({
      code: 'abc',
      state: 'xyz',
    });
    expect(parseVeraAuthCallback('vera://auth/callback?code=abc')).toBeNull();
    expect(parseVeraAuthCallback('C:\\Docs\\manual.vera')).toBeNull();
    expect(veraAuthCallbackFromArgs([
      'C:\\Program Files\\VERA\\VERA.exe',
      'vera://auth/callback?code=one&state=two',
    ])).toEqual({ code: 'one', state: 'two' });
  });
});
