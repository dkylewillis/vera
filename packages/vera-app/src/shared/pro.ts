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
  agentAccessStatus: string;
  hasProKey: boolean;
  usageUsd: number | null;
  limitUsd: number | null;
  remainingUsd: number | null;
  /** Included usage for the open period, 0 to 100. Null when usage has not loaded. */
  includedPercent: number | null;
  onDemandEnabled: boolean;
  onDemandUsedUsd: number | null;
  onDemandLimitUsd: number | null;
  error?: string;
}

/** Share of the monthly allowance already used, from 0 to 100. Dollar amounts stay off the screen. */
export function usagePercent(usageUsd: number | null, limitUsd: number | null): number | null {
  if (limitUsd === null || !Number.isFinite(limitUsd) || limitUsd <= 0) return null;
  const used = usageUsd !== null && Number.isFinite(usageUsd) ? Math.max(0, usageUsd) : 0;
  return Math.min(100, Math.round((used / limitUsd) * 100));
}

export function subscriptionActive(status: string): boolean {
  return status === 'active' || status === 'trialing';
}

/** Included percentage from the server, or from the older usage and limit fields. */
export function includedUsagePercent(account: Pick<ProAccount, 'includedPercent' | 'usageUsd' | 'limitUsd'>): number | null {
  if (account.includedPercent !== null && Number.isFinite(account.includedPercent)) {
    return Math.min(100, Math.max(0, Math.round(account.includedPercent)));
  }
  return usagePercent(account.usageUsd, account.limitUsd);
}

function usd(value: number | null): string {
  const amount = value !== null && Number.isFinite(value) ? value : 0;
  return `$${amount.toFixed(2)}`;
}

/** "Off", or dollars used out of the limit the customer set. */
export function onDemandLabel(account: Pick<ProAccount, 'onDemandEnabled' | 'onDemandUsedUsd' | 'onDemandLimitUsd'>): string {
  if (!account.onDemandEnabled) return 'Off';
  return `${usd(account.onDemandUsedUsd)} of ${usd(account.onDemandLimitUsd)}`;
}

/** Replaces a VERA Pro key-limit failure. Other providers keep the provider's own message. */
export function veraProLimitMessage(error: string, account: Pick<ProAccount, 'onDemandEnabled' | 'siteUrl'> | null, providerKey: unknown): string | null {
  if (providerKey !== PRO_PRESET_KEY) return null;
  if (!error.includes('HTTP 402')) return null;
  const site = (account?.siteUrl || 'https://veradoc.si').replace(/\/+$/, '');
  const page = `${site}/account.html`;
  if (account?.onDemandEnabled) return `On-demand limit reached. Raise your limit at ${page}`;
  return `Included usage is used up. Turn on on-demand usage at ${page}`;
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

/** VERA Pro first, then the other providers in their saved order. */
export function proFirst<T extends { preset_key?: string }>(providers: readonly T[]): T[] {
  return [
    ...providers.filter((profile) => isProPreset(profile.preset_key)),
    ...providers.filter((profile) => !isProPreset(profile.preset_key)),
  ];
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

/** Ensure the VERA Pro provider exists and is the default chat provider. */
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
