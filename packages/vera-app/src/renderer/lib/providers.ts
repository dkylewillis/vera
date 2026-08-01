import type { ProviderProfile } from '../types';

export type ProviderPreset = {
  key: string;
  label: string;
  description: string;
  kind: 'hosted' | 'local';
  catalog?: string[];
  value: Omit<ProviderProfile, 'id'>;
};

export const REASONING_EFFORTS = ['minimal', 'low', 'medium', 'high', 'xhigh', 'max'] as const;

export const PROVIDER_PRESETS: ProviderPreset[] = [
  {
    key: 'ollama',
    label: 'Ollama',
    description: 'Run models locally with Ollama.',
    kind: 'local',
    value: { label: 'Ollama', provider: 'ollama', models: [], base_url: 'http://localhost:11434/v1', api_key_env: '', auth_type: 'none', temperature: 0.2 },
  },
  {
    key: 'lmstudio',
    label: 'LM Studio',
    description: 'Use models served by LM Studio on this computer.',
    kind: 'local',
    value: { label: 'LM Studio', provider: 'lmstudio', models: [], base_url: 'http://localhost:1234/v1', api_key_env: '', auth_type: 'none', temperature: 0.2 },
  },
  {
    key: 'openai',
    label: 'OpenAI',
    description: 'GPT and reasoning models from OpenAI.',
    kind: 'hosted',
    catalog: [
      'gpt-5.6-sol',
      'gpt-5.6-terra',
      'gpt-5.6-luna',
      'gpt-5.6-sol-pro',
      'gpt-5.6-terra-pro',
      'gpt-5.6-luna-pro',
      'gpt-5.5',
      'gpt-5.4',
      'gpt-5.4-mini',
      'gpt-4.1',
      'gpt-4.1-mini',
      'gpt-4.1-nano',
      'gpt-4o',
      'gpt-4o-mini',
      'o3',
      'o3-mini',
      'o4-mini',
    ],
    value: {
      label: 'OpenAI',
      provider: 'openai_compatible',
      models: [],
      base_url: 'https://api.openai.com/v1',
      api_key_env: 'OPENAI_API_KEY',
      auth_type: 'api_key',
      temperature: 0.2,
    },
  },
  {
    key: 'openrouter',
    label: 'OpenRouter',
    description: 'One API for models from multiple providers.',
    kind: 'hosted',
    catalog: [
      'openai/gpt-5.6-sol',
      'openai/gpt-5.6-terra',
      'openai/gpt-5.6-luna',
      'openai/gpt-5.6-sol-pro',
      'anthropic/claude-fable-5',
      'anthropic/claude-opus-4.8',
      'google/gemini-3.1-pro-preview',
      'google/gemini-3.5-flash',
      'openai/gpt-5.5',
      'openai/gpt-5.4',
      'openai/gpt-5.4-mini',
      'deepseek/deepseek-v4-pro',
    ],
    value: {
      label: 'OpenRouter',
      provider: 'openai_compatible',
      models: [],
      base_url: 'https://openrouter.ai/api/v1',
      api_key_env: 'OPENROUTER_API_KEY',
      auth_type: 'api_key',
      temperature: 0.2,
    },
  },
];

export function reasoningEffortLabel(effort: string): string {
  return effort === 'xhigh' ? 'Extra High' : effort.charAt(0).toUpperCase() + effort.slice(1);
}

export function providerPresetFor(profile: ProviderProfile): ProviderPreset | null {
  if (profile.preset_key) {
    return PROVIDER_PRESETS.find((preset) => preset.key === profile.preset_key) ?? null;
  }
  const baseUrl = profile.base_url.trim().replace(/\/+$/, '').toLowerCase();
  return PROVIDER_PRESETS.find((preset) =>
    preset.value.label === profile.label
    && preset.value.base_url.replace(/\/+$/, '').toLowerCase() === baseUrl,
  ) ?? null;
}

export function withPresetModels(profile: ProviderProfile): ProviderProfile {
  const preset = providerPresetFor(profile);
  if (!preset) return profile;
  return {
    ...profile,
    preset_key: preset.key,
  };
}

export function filterDiscoveredModels(profile: ProviderProfile, discovered: string[]): string[] {
  const preset = providerPresetFor(profile);
  // OpenAI's /models list is noisy; keep a curated allowlist. OpenRouter and
  // local providers surface the full live catalog (searchable in the UI).
  if (preset?.key !== 'openai' || !preset.catalog?.length) return discovered;
  const liveIds = new Set(discovered.map((model) => model.toLowerCase()));
  return preset.catalog.filter((model) => liveIds.has(model.toLowerCase()));
}

/** Models to enable on first refresh when the profile has none selected yet. */
export function defaultEnabledModels(profile: ProviderProfile, discovered: string[]): string[] {
  const preset = providerPresetFor(profile);
  if (!preset?.catalog?.length) return discovered;
  const liveIds = new Set(discovered.map((model) => model.toLowerCase()));
  return preset.catalog.filter((model) => liveIds.has(model.toLowerCase()));
}

export function newProviderId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `prov_${crypto.randomUUID()}`;
  }
  return `prov_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
}

export function emptyProvider(): ProviderProfile {
  return {
    id: newProviderId(),
    label: 'New Provider',
    provider: 'openai_compatible',
    models: [],
    base_url: '',
    api_key_env: '',
    auth_type: 'api_key',
    temperature: 0.2,
  };
}

export function providerTypeLabel(provider: string): string {
  switch (provider) {
    case 'ollama':
      return 'Ollama';
    case 'lmstudio':
    case 'lm_studio':
      return 'LM Studio';
    case 'openai':
      return 'OpenAI';
    default:
      return 'OpenAI Compatible';
  }
}

export function providerDisplayName(profile: ProviderProfile): string {
  return profile.label.trim() || providerTypeLabel(profile.provider);
}
