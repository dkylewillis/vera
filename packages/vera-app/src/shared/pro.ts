import type { AppSettings, ProviderProfile } from './contracts.js';

/** Preset id for the subscription provider. Stored separately from a personal OpenRouter key. */
export const PRO_PRESET_KEY = 'vera_pro';

/** Reserved slot in the encrypted credential file. Not a provider base URL. */
export const PRO_KEY_SECRET = '__vera_pro_openrouter_key__';

export const PRO_SESSION_SECRET = '__vera_pro_session__';

export const PRO_PKCE_SECRET = '__vera_pro_pkce__';

export const PRO_OPENROUTER_BASE_URL = 'https://openrouter.ai/api/v1';

/** Affordable models enabled when VERA Pro is activated. OpenRouter has no per-key model allowlist. */
export const PRO_DEFAULT_MODELS = [
  'google/gemini-3.5-flash',
  'openai/gpt-5.4-mini',
  'openai/gpt-4.1-mini',
] as const;

export const PRO_PROVIDER_ID = 'prov_vera_pro';

export interface ProSession {
  access_token: string;
  refresh_token: string;
  expires_at: number;
  email: string;
  user_id: string;
}

export interface ProAccount {
  configured: boolean;
  siteUrl: string;
  signedIn: boolean;
  email: string;
  subscriptionStatus: string;
  hasProKey: boolean;
  usageUsd: number | null;
  limitUsd: number | null;
  remainingUsd: number | null;
  error?: string;
}

export interface ProActionResult {
  ok: boolean;
  error?: string;
  account?: ProAccount;
  settings?: AppSettings;
}

export interface VeraAuthCallback {
  code: string;
  state: string;
}

/**
 * Credential slot for a provider. VERA Pro does not use the OpenRouter base URL,
 * so it cannot overwrite a key the user saved for their own OpenRouter account.
 */
export function providerCredentialKey(profile: { preset_key?: string; base_url?: string }): string {
  if (profile.preset_key === PRO_PRESET_KEY) return PRO_KEY_SECRET;
  return (profile.base_url || '').trim().replace(/\/+$/, '').toLowerCase();
}

export function isProPreset(presetKey: string | undefined): boolean {
  return presetKey === PRO_PRESET_KEY;
}

/** Parse `vera://auth/callback?code=&state=` from a protocol launch argument. */
export function parseVeraAuthCallback(raw: string): VeraAuthCallback | null {
  const trimmed = raw.trim().replace(/^"(.*)"$/, '$1');
  if (!trimmed.toLowerCase().startsWith('vera://')) return null;
  let url: URL;
  try {
    url = new URL(trimmed);
  } catch {
    return null;
  }
  const host = url.hostname.toLowerCase();
  const path = url.pathname.replace(/\/+$/, '').toLowerCase();
  if (host !== 'auth' || path !== '/callback') return null;
  const code = url.searchParams.get('code')?.trim() || '';
  const state = url.searchParams.get('state')?.trim() || '';
  if (!code || !state) return null;
  return { code, state };
}

export function veraAuthCallbackFromArgs(args: readonly string[]): VeraAuthCallback | null {
  for (const arg of args) {
    const parsed = parseVeraAuthCallback(arg);
    if (parsed) return parsed;
  }
  return null;
}

export function proProviderProfile(existingId?: string): ProviderProfile {
  const models = [...PRO_DEFAULT_MODELS];
  return {
    id: existingId || PRO_PROVIDER_ID,
    preset_key: PRO_PRESET_KEY,
    label: 'VERA Pro',
    provider: 'openai_compatible',
    base_url: PRO_OPENROUTER_BASE_URL,
    api_key_env: '',
    auth_type: 'api_key',
    temperature: 0.2,
    models,
    available_models: models,
    models_refreshed_at: Date.now(),
  };
}

/** Ensure the VERA Pro provider exists and is the active Ask provider. */
export function withProProvider(settings: AppSettings): AppSettings {
  const existing = settings.providers.find((profile) => profile.preset_key === PRO_PRESET_KEY);
  const profile = proProviderProfile(existing?.id);
  if (existing?.model_options) profile.model_options = existing.model_options;
  const providers = existing
    ? settings.providers.map((entry) => (entry.preset_key === PRO_PRESET_KEY ? profile : entry))
    : [...settings.providers, profile];
  return {
    ...settings,
    providers,
    active_provider_id: profile.id,
    active_model: PRO_DEFAULT_MODELS[0],
  };
}
