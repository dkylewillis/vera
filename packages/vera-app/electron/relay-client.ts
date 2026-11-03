import { randomUUID } from 'node:crypto';
import type { RelayCloudStatus, RelayDevice, RelayRouting } from '../src/shared/contracts.js';
import type { ProSession } from '../src/shared/pro.js';
import { sessionNeedsRefresh, type ProCloudConfig } from './pro-account.js';
import {
  CHUNK_BYTES,
  CLOSE_DUPLICATE,
  CLOSE_EXPIRED,
  CLOSE_FORGOTTEN,
  HEADER_APP_VERSION,
  HEADER_DEVICE_ID,
  HEADER_DEVICE_NAME,
  HEADER_INSTANCE,
  HEADER_PROTOCOL,
  PING,
  PONG,
  RELAY_PROTOCOL,
} from './relay-protocol.js';
import { openRelaySocket, type RelayConnectError, type RelaySocket } from './relay-socket.js';

export type { RelayCloudStatus };
export type RelayState = RelayCloudStatus['state'];

export interface DeviceSnapshot {
  id: string;
  name: string;
}

export interface RelayDirectory {
  self?: string;
  routing?: { mode?: string; pinned?: string };
  current?: string | null;
  devices?: RelayDevice[];
}

export interface RelayClientOptions {
  getConfig: () => ProCloudConfig;
  localMcpUrl: () => string;
  readLocalToken: () => string;
  readSession: () => ProSession | null;
  refreshSession: (session: ProSession) => Promise<ProSession>;
  isPro: () => Promise<boolean>;
  getDevice: () => DeviceSnapshot;
  regenerateDevice: () => DeviceSnapshot;
  appVersion: string;
  openSocket?: (url: string, token: string, headers: Record<string, string>) => Promise<RelaySocket>;
  fetchImpl?: typeof fetch;
  log?: (line: string) => void;
  now?: () => number;
  onStatus?: (status: RelayCloudStatus) => void;
  heartbeatIntervalMs?: number;
  pongTimeoutMs?: number;
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
const DUPLICATE_MESSAGE = 'VERA could not tell this computer apart from another copy. Restart VERA.';
const FORGOTTEN_MESSAGE = 'This computer was removed from cloud agents.';
const ASLEEP_MESSAGE = 'This computer is asleep. Cloud agents will reconnect when it wakes.';

/** Outbound bridge from one desktop to the VERA relay. */
export class RelayClient {
  private state: RelayState = 'off';
  private message = 'Cloud agents are off.';
  private socket: RelaySocket | null = null;
  private stopped = true;
  private looping = false;
  private attempt = 0;
  private generation = 0;
  private readonly instance = randomUUID();
  private readonly inflight = new Map<string, AbortController>();
  private routing: RelayRouting = { mode: 'auto' };
  private current: string | null = null;
  private devices: RelayDevice[] = [];
  private heartbeat: ReturnType<typeof setInterval> | null = null;
  private pongTimer: ReturnType<typeof setTimeout> | null = null;
  private duplicateAt = 0;

  constructor(private readonly options: RelayClientOptions) {}

  getStatus(): RelayCloudStatus {
    return {
      state: this.state,
      message: this.message,
      connectorUrl: connectorUrl(this.options.getConfig().relayUrl),
      device: this.options.getDevice(),
      routing: this.routing,
      current: this.current,
      devices: this.devices,
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
    this.clearHeartbeat();
    this.closeSocket(1000);
    this.abortAll();
    this.looping = false;
    this.setState('off', message);
  }

  /** Close for system sleep without scheduling a reconnect. */
  suspend(): void {
    this.stopped = true;
    this.generation += 1;
    this.clearHeartbeat();
    this.closeSocket(1001, 'sleep');
    this.abortAll();
    this.looping = false;
    this.setState('standby', ASLEEP_MESSAGE);
  }

  /** Drop the backoff and connect now. Used after wake and after a routing change. */
  reconnectNow(): void {
    this.stopped = false;
    this.generation += 1;
    this.attempt = 0;
    this.clearHeartbeat();
    this.closeSocket(1000, 'reconnect');
    this.abortAll();
    if (this.looping) return;
    this.looping = true;
    void this.loop();
  }

  applyDirectory(directory: RelayDirectory): void {
    const mode = directory.routing?.mode === 'pinned' ? 'pinned' : 'auto';
    const pinned = typeof directory.routing?.pinned === 'string' ? directory.routing.pinned : undefined;
    this.routing = pinned ? { mode, pinned } : { mode };
    this.current = typeof directory.current === 'string' && directory.current ? directory.current : null;
    this.devices = Array.isArray(directory.devices) ? directory.devices.filter(isDevice) : [];
    if (this.stopped || this.state === 'off' || this.state === 'not_pro') {
      this.options.onStatus?.(this.getStatus());
      return;
    }
    const self = directory.self || this.options.getDevice().id;
    const active = mode === 'pinned' ? pinned === self : this.current === self;
    if (active) {
      this.setState('connected', 'Cloud agents can reach this computer.');
      return;
    }
    const targetId = mode === 'pinned' ? pinned : this.current;
    const name = this.devices.find((item) => item.id === targetId)?.name || 'another computer';
    this.setState('standby', `Connected. Cloud agents are using ${name}.`);
  }

  markNotPro(): void {
    this.stop('Agent Access is required for cloud agents.');
    this.setState('not_pro', 'Agent Access is required for cloud agents.');
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
        const device = this.options.getDevice();
        const socket = await (this.options.openSocket ?? openRelaySocket)(
          socketUrl(config.relayUrl),
          session.access_token,
          {
            [HEADER_PROTOCOL]: RELAY_PROTOCOL,
            [HEADER_DEVICE_ID]: device.id,
            [HEADER_DEVICE_NAME]: device.name,
            [HEADER_INSTANCE]: this.instance,
            [HEADER_APP_VERSION]: this.options.appVersion,
          },
        );
        if (this.stopped || generation !== this.generation) {
          socket.close(1000, 'stopped');
          return;
        }
        this.socket = socket;
        this.attempt = 0;
        this.looping = false;
        socket.onMessage((data) => { void this.onFrame(data); });
        socket.onClose((code) => { void this.onSocketClose(code, generation); });
        this.armHeartbeat();
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
    this.clearHeartbeat();
    this.abortAll();
    if (this.looping) return;
    if (code === CLOSE_FORGOTTEN) {
      this.stop(FORGOTTEN_MESSAGE);
      return;
    }
    if (code === CLOSE_DUPLICATE) {
      const now = (this.options.now ?? Date.now)();
      if (this.duplicateAt !== 0 && now - this.duplicateAt < 60_000) {
        this.stopped = true;
        this.generation += 1;
        this.looping = false;
        this.setState('error', DUPLICATE_MESSAGE);
        return;
      }
      this.duplicateAt = now;
      this.options.regenerateDevice();
      this.looping = true;
      void this.loop();
      return;
    }
    if (code === CLOSE_EXPIRED) {
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
    if (raw === PONG) {
      this.clearPongTimer();
      return;
    }
    let frame: {
      type?: string;
      id?: string;
      method?: string;
      headers?: Record<string, string>;
      body?: string;
    } & RelayDirectory;
    try {
      frame = JSON.parse(raw) as typeof frame;
    } catch {
      return;
    }
    if (frame.type === 'pong') {
      this.clearPongTimer();
      return;
    }
    if (frame.type === 'devices') {
      this.applyDirectory(frame);
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
    let headSent = false;
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
      headSent = true;
      const reader = response.body?.getReader();
      if (reader) {
        while (!controller.signal.aborted) {
          const next = await reader.read();
          if (next.done) break;
          if (next.value?.byteLength) this.sendChunks(frame.id, next.value);
        }
      }
      if (controller.signal.aborted) return;
      this.send({ type: 'end', id: frame.id });
      this.options.log?.(`vera-relay method=${frame.method} status=${response.status} ms=${(this.options.now ?? Date.now)() - started}`);
    } catch (error) {
      if (controller.signal.aborted) return;
      if (!headSent) {
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
      }
      this.send({ type: 'end', id: frame.id });
    } finally {
      this.inflight.delete(frame.id);
    }
  }

  private sendChunks(id: string, bytes: Uint8Array): void {
    for (let offset = 0; offset < bytes.byteLength; offset += CHUNK_BYTES) {
      this.send({ type: 'chunk', id, data: encodeBase64(bytes.subarray(offset, offset + CHUNK_BYTES)) });
    }
  }

  private send(frame: unknown): void {
    this.socket?.send(JSON.stringify(frame));
  }

  private armHeartbeat(): void {
    this.clearHeartbeat();
    const interval = this.options.heartbeatIntervalMs ?? 25_000;
    if (interval <= 0) return;
    const timer = setInterval(() => {
      if (!this.socket) return;
      this.socket.send(PING);
      this.clearPongTimer();
      const timeout = this.options.pongTimeoutMs ?? 10_000;
      this.pongTimer = setTimeout(() => {
        this.pongTimer = null;
        this.closeSocket(1001, 'heartbeat');
      }, timeout);
      this.pongTimer.unref?.();
    }, interval);
    timer.unref?.();
    this.heartbeat = timer;
  }

  private clearHeartbeat(): void {
    if (this.heartbeat) clearInterval(this.heartbeat);
    this.heartbeat = null;
    this.clearPongTimer();
  }

  private clearPongTimer(): void {
    if (this.pongTimer) clearTimeout(this.pongTimer);
    this.pongTimer = null;
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
    const delay = retryDelay(this.attempt);
    await new Promise((resolve) => setTimeout(resolve, delay));
    if (generation !== this.generation) return;
  }

  private closeSocket(code: number, reason = 'stop'): void {
    const socket = this.socket;
    this.socket = null;
    socket?.close(code, reason);
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

export function retryDelay(attempt: number, random: () => number = Math.random): number {
  const base = Math.min(60_000, 500 * 2 ** Math.min(attempt, 7));
  const jitter = 0.8 + random() * 0.4;
  return Math.round(base * jitter);
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

function isDevice(value: RelayDevice): boolean {
  return Boolean(value && typeof value.id === 'string' && typeof value.name === 'string');
}
