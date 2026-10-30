import type { RelayCloudStatus } from '../src/shared/contracts.js';
import type { ProSession } from '../src/shared/pro.js';
import { sessionNeedsRefresh, type ProCloudConfig } from './pro-account.js';
import { openRelaySocket, type RelayConnectError, type RelaySocket } from './relay-socket.js';

export type { RelayCloudStatus };
export type RelayState = RelayCloudStatus['state'];

export interface RelayClientOptions {
  getConfig: () => ProCloudConfig;
  localMcpUrl: () => string;
  readLocalToken: () => string;
  readSession: () => ProSession | null;
  refreshSession: (session: ProSession) => Promise<ProSession>;
  isPro: () => Promise<boolean>;
  openSocket?: (url: string, token: string) => Promise<RelaySocket>;
  fetchImpl?: typeof fetch;
  log?: (line: string) => void;
  now?: () => number;
  onStatus?: (status: RelayCloudStatus) => void;
}

interface ReqFrame {
  type: 'req';
  id: string;
  method: string;
  headers: Record<string, string>;
  body: string;
}

const REQUEST_HEADERS = ['content-type', 'accept', 'mcp-session-id', 'mcp-protocol-version', 'last-event-id'];
const RESPONSE_HEADERS = ['content-type', 'mcp-session-id', 'mcp-protocol-version', 'cache-control'];

/** Outbound bridge from one desktop to the VERA relay. */
export class RelayClient {
  private state: RelayState = 'off';
  private message = 'Cloud agents are off.';
  private socket: RelaySocket | null = null;
  private stopped = true;
  private looping = false;
  private attempt = 0;
  private generation = 0;
  private readonly inflight = new Map<string, AbortController>();

  constructor(private readonly options: RelayClientOptions) {}

  getStatus(): RelayCloudStatus {
    return {
      state: this.state,
      message: this.message,
      connectorUrl: connectorUrl(this.options.getConfig().relayUrl),
    };
  }

  start(): void {
    this.stopped = false;
    if (this.looping) return;
    this.looping = true;
    void this.loop();
  }

  stop(message = 'Cloud agents are off.'): void {
    this.stopped = true;
    this.generation += 1;
    this.attempt = 0;
    this.closeSocket(1000);
    this.abortAll();
    this.looping = false;
    this.setState('off', message);
  }

  markNotPro(): void {
    this.stop('VERA Pro is required for cloud agents.');
    this.setState('not_pro', 'VERA Pro is required for cloud agents.');
  }

  private async loop(): Promise<void> {
    while (!this.stopped) {
      const generation = this.generation;
      const config = this.options.getConfig();
      if (!config.relayUrl) {
        this.setState('error', 'This build has no relay URL.');
        this.looping = false;
        return;
      }
      let pro = false;
      try {
        pro = await this.options.isPro();
      } catch (error) {
        this.setState('error', error instanceof Error ? error.message : 'Unable to check VERA Pro.');
        await this.backoff(generation);
        continue;
      }
      if (!pro) {
        this.markNotPro();
        return;
      }
      this.setState('connecting', 'Connecting to the VERA relay…');
      try {
        const session = await this.freshSession(false);
        if (!session) throw new Error('Sign in to VERA Pro before allowing cloud agents.');
        const socket = await (this.options.openSocket ?? openRelaySocket)(socketUrl(config.relayUrl), session.access_token);
        if (this.stopped || generation !== this.generation) {
          socket.close(1000, 'stopped');
          return;
        }
        this.socket = socket;
        this.attempt = 0;
        this.looping = false;
        socket.onMessage((data) => { void this.onFrame(data); });
        socket.onClose((code) => { void this.onSocketClose(code, generation); });
        this.setState('connected', 'Cloud agents can reach this computer.');
        return;
      } catch (error) {
        const status = (error as RelayConnectError).status;
        if (status === 401) {
          try {
            await this.freshSession(true);
          } catch (refreshError) {
            this.setState('error', refreshError instanceof Error ? refreshError.message : 'Unable to refresh VERA Pro sign-in.');
          }
        } else if (status === 403) {
          this.markNotPro();
          return;
        } else {
          this.setState('error', error instanceof Error ? error.message : 'Unable to reach the VERA relay.');
        }
        await this.backoff(generation);
      }
    }
    this.looping = false;
  }

  private async onSocketClose(code: number, generation: number): Promise<void> {
    if (this.stopped || generation !== this.generation) return;
    this.socket = null;
    this.abortAll();
    if (this.looping) return;
    if (code === 4001) {
      try {
        await this.freshSession(true);
      } catch (error) {
        this.setState('error', error instanceof Error ? error.message : 'Unable to refresh VERA Pro sign-in.');
      }
    } else {
      await this.backoff(generation);
    }
    if (this.stopped || generation !== this.generation || this.looping) return;
    this.looping = true;
    void this.loop();
  }

  private async onFrame(raw: string): Promise<void> {
    let frame: { type?: string; id?: string; method?: string; headers?: Record<string, string>; body?: string };
    try {
      frame = JSON.parse(raw) as typeof frame;
    } catch {
      return;
    }
    if (frame.type === 'cancel' && frame.id) {
      this.inflight.get(frame.id)?.abort();
      this.inflight.delete(frame.id);
      return;
    }
    if (frame.type !== 'req' || !frame.id) return;
    await this.forward(frame as ReqFrame);
  }

  private async forward(frame: ReqFrame): Promise<void> {
    const controller = new AbortController();
    this.inflight.set(frame.id, controller);
    const started = (this.options.now ?? Date.now)();
    try {
      const headers = new Headers();
      for (const name of REQUEST_HEADERS) {
        const value = frame.headers?.[name];
        if (value) headers.set(name, value);
      }
      headers.set('authorization', `Bearer ${this.options.readLocalToken()}`);
      const bodyBytes = decodeBase64(frame.body || '');
      const response = await (this.options.fetchImpl ?? fetch)(this.options.localMcpUrl(), {
        method: frame.method || 'POST',
        headers,
        body: frame.method === 'GET' || bodyBytes.byteLength === 0 ? undefined : bodyBytes,
        signal: controller.signal,
      });
      this.send({
        type: 'head',
        id: frame.id,
        status: response.status,
        headers: responseHeaders(response),
      });
      const reader = response.body?.getReader();
      if (reader) {
        while (!controller.signal.aborted) {
          const next = await reader.read();
          if (next.done) break;
          if (next.value?.byteLength) this.send({ type: 'chunk', id: frame.id, data: encodeBase64(next.value) });
        }
      }
      this.send({ type: 'end', id: frame.id });
      this.options.log?.(`vera-relay method=${frame.method} status=${response.status} ms=${(this.options.now ?? Date.now)() - started}`);
    } catch (error) {
      if (controller.signal.aborted) return;
      const message = error instanceof Error ? error.message : 'Local VERA service did not answer.';
      this.send({
        type: 'head',
        id: frame.id,
        status: 502,
        headers: { 'content-type': 'application/json' },
      });
      this.send({
        type: 'chunk',
        id: frame.id,
        data: encodeBase64(new TextEncoder().encode(JSON.stringify({
          jsonrpc: '2.0',
          id: null,
          error: { code: -32000, message },
        }))),
      });
      this.send({ type: 'end', id: frame.id });
    } finally {
      this.inflight.delete(frame.id);
    }
  }

  private send(frame: unknown): void {
    this.socket?.send(JSON.stringify(frame));
  }

  private async freshSession(force: boolean): Promise<ProSession | null> {
    const session = this.options.readSession();
    if (!session) return null;
    const now = (this.options.now ?? Date.now)();
    if (!force && !sessionNeedsRefresh(session, now)) return session;
    return this.options.refreshSession(session);
  }

  private async backoff(generation: number): Promise<void> {
    this.attempt += 1;
    const delay = Math.min(60_000, 500 * 2 ** Math.min(this.attempt, 7));
    await new Promise((resolve) => setTimeout(resolve, delay));
    if (generation !== this.generation) return;
  }

  private closeSocket(code: number): void {
    const socket = this.socket;
    this.socket = null;
    socket?.close(code, 'stop');
  }

  private abortAll(): void {
    for (const controller of this.inflight.values()) controller.abort();
    this.inflight.clear();
  }

  private setState(state: RelayState, message: string): void {
    this.state = state;
    this.message = message;
    this.options.onStatus?.(this.getStatus());
  }
}

export function connectorUrl(relayUrl: string): string {
  if (!relayUrl) return '';
  const url = new URL(relayUrl);
  url.protocol = url.protocol === 'wss:' ? 'https:' : url.protocol === 'ws:' ? 'http:' : url.protocol;
  url.pathname = '/mcp';
  url.search = '';
  url.hash = '';
  return url.toString();
}

function socketUrl(relayUrl: string): string {
  const url = new URL(relayUrl);
  url.protocol = url.protocol === 'https:' ? 'wss:' : url.protocol === 'http:' ? 'ws:' : url.protocol;
  url.pathname = '/connect';
  url.search = '';
  url.hash = '';
  return url.toString();
}

function responseHeaders(response: Response): Record<string, string> {
  const headers: Record<string, string> = {};
  for (const name of RESPONSE_HEADERS) {
    const value = response.headers.get(name);
    if (value) headers[name] = value;
  }
  return headers;
}

function encodeBase64(bytes: Uint8Array): string {
  return Buffer.from(bytes).toString('base64');
}

function decodeBase64(value: string): Uint8Array {
  return new Uint8Array(Buffer.from(value, 'base64'));
}
