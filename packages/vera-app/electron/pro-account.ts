import { createHash, randomBytes } from 'node:crypto';

import type { ProAccount, ProSession } from '../src/shared/pro.js';

export interface ProCloudConfig {
  siteUrl: string;
  supabaseUrl: string;
  supabaseAnonKey: string;
  relayUrl: string;
}

export interface StoredPkce {
  verifier: string;
  state: string;
}

export function proCloudConfigFromEnv(env: NodeJS.ProcessEnv): ProCloudConfig {
  return normalizeProCloud({
    siteUrl: env.VERA_PRO_SITE_URL || '',
    supabaseUrl: env.VERA_PRO_SUPABASE_URL || '',
    supabaseAnonKey: env.VERA_PRO_SUPABASE_ANON_KEY || '',
    relayUrl: env.VERA_PRO_RELAY_URL || '',
  });
}

export function proCloudConfigFromFile(raw: unknown): ProCloudConfig {
  const value = raw && typeof raw === 'object' ? raw as Record<string, unknown> : {};
  return normalizeProCloud({
    siteUrl: typeof value.siteUrl === 'string' ? value.siteUrl : '',
    supabaseUrl: typeof value.supabaseUrl === 'string' ? value.supabaseUrl : '',
    supabaseAnonKey: typeof value.supabaseAnonKey === 'string' ? value.supabaseAnonKey : '',
    relayUrl: typeof value.relayUrl === 'string' ? value.relayUrl : '',
  });
}

/** Environment values override a packaged pro-cloud.json when both are set. */
export function mergeProCloudConfig(fileConfig: ProCloudConfig, envConfig: ProCloudConfig): ProCloudConfig {
  return normalizeProCloud({
    siteUrl: envConfig.siteUrl || fileConfig.siteUrl,
    supabaseUrl: envConfig.supabaseUrl || fileConfig.supabaseUrl,
    supabaseAnonKey: envConfig.supabaseAnonKey || fileConfig.supabaseAnonKey,
    relayUrl: envConfig.relayUrl || fileConfig.relayUrl,
  });
}

export function proCloudConfigured(config: ProCloudConfig): boolean {
  return Boolean(config.siteUrl && config.supabaseUrl && config.supabaseAnonKey);
}

export function proSignInUrl(config: ProCloudConfig, challenge: string, state: string): string {
  const url = new URL(`${config.siteUrl}/login.html`);
  url.searchParams.set('code_challenge', challenge);
  url.searchParams.set('state', state);
  return url.toString();
}

export function proPageUrl(config: ProCloudConfig, page: 'pricing' | 'account'): string {
  return `${config.siteUrl}/${page}.html`;
}

export function createPkcePair(): { verifier: string; challenge: string; state: string } {
  const verifier = randomBytes(32).toString('base64url');
  const challenge = createHash('sha256').update(verifier).digest('base64url');
  const state = randomBytes(16).toString('base64url');
  return { verifier, challenge, state };
}

export function emptyProAccount(config: ProCloudConfig, extras: Partial<ProAccount> = {}): ProAccount {
  return {
    configured: proCloudConfigured(config),
    siteUrl: config.siteUrl,
    signedIn: false,
    email: '',
    subscriptionStatus: '',
    hasProKey: false,
    usageUsd: null,
    limitUsd: null,
    remainingUsd: null,
    ...extras,
  };
}

export function parseStoredSession(raw: string): ProSession | null {
  try {
    const parsed = JSON.parse(raw) as Partial<ProSession>;
    if (!parsed || typeof parsed.access_token !== 'string' || typeof parsed.refresh_token !== 'string') {
      return null;
    }
    if (typeof parsed.expires_at !== 'number' || typeof parsed.user_id !== 'string') return null;
    return {
      access_token: parsed.access_token,
      refresh_token: parsed.refresh_token,
      expires_at: parsed.expires_at,
      email: typeof parsed.email === 'string' ? parsed.email : '',
      user_id: parsed.user_id,
    };
  } catch {
    return null;
  }
}

export function parseStoredPkce(raw: string): StoredPkce | null {
  try {
    const parsed = JSON.parse(raw) as Partial<StoredPkce>;
    if (!parsed || typeof parsed.verifier !== 'string' || typeof parsed.state !== 'string') return null;
    if (!parsed.verifier || !parsed.state) return null;
    return { verifier: parsed.verifier, state: parsed.state };
  } catch {
    return null;
  }
}

export function sessionNeedsRefresh(session: ProSession, nowMs: number): boolean {
  return session.expires_at - nowMs < 60_000;
}

function normalizeProCloud(config: ProCloudConfig): ProCloudConfig {
  return {
    siteUrl: config.siteUrl.trim().replace(/\/+$/, ''),
    supabaseUrl: config.supabaseUrl.trim().replace(/\/+$/, ''),
    supabaseAnonKey: config.supabaseAnonKey.trim(),
    relayUrl: config.relayUrl.trim().replace(/\/+$/, ''),
  };
}

export function proSubscriptionActive(status: string): boolean {
  return status === 'active' || status === 'trialing';
}

function functionUrl(config: ProCloudConfig, name: string): string {
  return `${config.supabaseUrl}/functions/v1/${name}`;
}

function supabaseHeaders(config: ProCloudConfig, accessToken?: string): Record<string, string> {
  return {
    apikey: config.supabaseAnonKey,
    Authorization: `Bearer ${accessToken || config.supabaseAnonKey}`,
    'Content-Type': 'application/json',
  };
}

async function readError(response: Response): Promise<string> {
  const text = await response.text();
  if (!text) return `Request failed (${response.status})`;
  try {
    const parsed = JSON.parse(text) as { error?: unknown; message?: unknown; msg?: unknown };
    const message = parsed.error || parsed.message || parsed.msg;
    if (typeof message === 'string' && message.trim()) return message.trim();
  } catch {
    /* plain text */
  }
  return text.slice(0, 300);
}

function sessionFromAuthPayload(payload: Record<string, unknown>, previous?: ProSession): ProSession {
  const accessToken = typeof payload.access_token === 'string' ? payload.access_token : '';
  const refreshToken = typeof payload.refresh_token === 'string' ? payload.refresh_token : previous?.refresh_token || '';
  const expiresIn = typeof payload.expires_in === 'number' ? payload.expires_in : 3600;
  const user = payload.user && typeof payload.user === 'object' ? payload.user as Record<string, unknown> : {};
  const email = typeof user.email === 'string' ? user.email : previous?.email || '';
  const userId = typeof user.id === 'string' ? user.id : previous?.user_id || '';
  if (!accessToken || !refreshToken || !userId) {
    throw new Error('VERA Pro sign-in did not return a session.');
  }
  return {
    access_token: accessToken,
    refresh_token: refreshToken,
    expires_at: Date.now() + expiresIn * 1000,
    email,
    user_id: userId,
  };
}

export async function exchangeDesktopCode(
  config: ProCloudConfig,
  body: { code: string; code_verifier: string; state: string },
  fetchImpl: typeof fetch,
): Promise<ProSession> {
  const response = await fetchImpl(functionUrl(config, 'desktop-exchange'), {
    method: 'POST',
    headers: supabaseHeaders(config),
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await readError(response));
  return sessionFromAuthPayload(await response.json() as Record<string, unknown>);
}

export async function refreshProSession(
  config: ProCloudConfig,
  session: ProSession,
  fetchImpl: typeof fetch,
): Promise<ProSession> {
  const response = await fetchImpl(`${config.supabaseUrl}/auth/v1/token?grant_type=refresh_token`, {
    method: 'POST',
    headers: supabaseHeaders(config),
    body: JSON.stringify({ refresh_token: session.refresh_token }),
  });
  if (!response.ok) throw new Error(await readError(response));
  return sessionFromAuthPayload(await response.json() as Record<string, unknown>, session);
}

export async function claimProKey(
  config: ProCloudConfig,
  accessToken: string,
  fetchImpl: typeof fetch,
): Promise<{ apiKey: string; limitUsd: number | null }> {
  const response = await fetchImpl(functionUrl(config, 'pro-key'), {
    method: 'POST',
    headers: supabaseHeaders(config, accessToken),
    body: '{}',
  });
  if (!response.ok) throw new Error(await readError(response));
  const payload = await response.json() as { api_key?: unknown; limit_usd?: unknown; error?: unknown };
  if (typeof payload.api_key !== 'string' || !payload.api_key) {
    throw new Error(typeof payload.error === 'string' ? payload.error : 'VERA Pro did not return an API key.');
  }
  return {
    apiKey: payload.api_key,
    limitUsd: typeof payload.limit_usd === 'number' ? payload.limit_usd : null,
  };
}

export interface ProUsage {
  subscriptionStatus: string;
  usageUsd: number | null;
  limitUsd: number | null;
  remainingUsd: number | null;
}

export async function fetchProUsage(
  config: ProCloudConfig,
  accessToken: string,
  fetchImpl: typeof fetch,
): Promise<ProUsage> {
  const response = await fetchImpl(functionUrl(config, 'pro-usage'), {
    method: 'POST',
    headers: supabaseHeaders(config, accessToken),
    body: '{}',
  });
  if (!response.ok) throw new Error(await readError(response));
  const payload = await response.json() as Record<string, unknown>;
  return {
    subscriptionStatus: typeof payload.subscription_status === 'string' ? payload.subscription_status : '',
    usageUsd: typeof payload.usage_monthly === 'number' ? payload.usage_monthly : null,
    limitUsd: typeof payload.limit_usd === 'number' ? payload.limit_usd : null,
    remainingUsd: typeof payload.limit_remaining === 'number' ? payload.limit_remaining : null,
  };
}
