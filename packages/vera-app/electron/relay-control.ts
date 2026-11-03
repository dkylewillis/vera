import type { ProSession } from '../src/shared/pro.js';
import type { RelayDirectory } from './relay-client.js';

export interface RelayControlOptions {
  relayUrl: string;
  readSession: () => ProSession | null;
  refreshSession: (session: ProSession) => Promise<ProSession>;
  fetchImpl?: typeof fetch;
}

export class RelayControlError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
  }
}

/** First-party calls that choose which computer answers cloud agents. */
export class RelayControl {
  constructor(private readonly options: RelayControlOptions) {}

  devices(): Promise<RelayDirectory> {
    return this.send('/devices', 'GET');
  }

  setRouting(mode: 'auto' | 'pinned', deviceId?: string): Promise<RelayDirectory> {
    const body: { mode: 'auto' | 'pinned'; device_id?: string } = { mode };
    if (deviceId) body.device_id = deviceId;
    return this.send('/routing', 'PUT', body);
  }

  rename(id: string, name: string): Promise<RelayDirectory> {
    return this.send(`/devices/${encodeURIComponent(id)}`, 'PATCH', { name });
  }

  forget(id: string): Promise<RelayDirectory> {
    return this.send(`/devices/${encodeURIComponent(id)}`, 'DELETE');
  }

  private async send(path: string, method: string, body?: unknown, attempt = 0): Promise<RelayDirectory> {
    const base = httpOrigin(this.options.relayUrl);
    if (!base) throw new RelayControlError(0, 'This build has no relay URL.');
    const session = this.options.readSession();
    if (!session?.access_token) throw new RelayControlError(401, 'Sign in to VERA Pro before managing computers.');
    const response = await (this.options.fetchImpl ?? fetch)(`${base}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${session.access_token}`,
        Accept: 'application/json',
        ...(body === undefined ? {} : { 'content-type': 'application/json' }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (response.status === 401 && attempt === 0) {
      await response.text().catch(() => undefined);
      const next = await this.options.refreshSession(session);
      return this.sendWith(base, path, method, body, next.access_token);
    }
    return readDirectory(response);
  }

  private async sendWith(base: string, path: string, method: string, body: unknown, token: string): Promise<RelayDirectory> {
    const response = await (this.options.fetchImpl ?? fetch)(`${base}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/json',
        ...(body === undefined ? {} : { 'content-type': 'application/json' }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    return readDirectory(response);
  }
}

export function httpOrigin(relayUrl: string): string {
  if (!relayUrl) return '';
  const url = new URL(relayUrl);
  if (url.protocol === 'wss:') url.protocol = 'https:';
  else if (url.protocol === 'ws:') url.protocol = 'http:';
  url.pathname = '';
  url.search = '';
  url.hash = '';
  return url.origin;
}

async function readDirectory(response: Response): Promise<RelayDirectory> {
  const text = await response.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text) as unknown;
    } catch {
      parsed = null;
    }
  }
  if (!response.ok) {
    const message = errorMessage(parsed) || `The relay returned ${response.status}.`;
    throw new RelayControlError(response.status, message);
  }
  if (!parsed || typeof parsed !== 'object') throw new RelayControlError(response.status, 'The relay returned an unreadable computer list.');
  return parsed as RelayDirectory;
}

function errorMessage(value: unknown): string {
  if (!value || typeof value !== 'object') return '';
  const error = (value as { error?: { message?: unknown } }).error;
  return typeof error?.message === 'string' ? error.message : '';
}
