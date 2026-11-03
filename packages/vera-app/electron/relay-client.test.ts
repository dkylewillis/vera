import { describe, expect, it, vi } from 'vitest';
import type { ProSession } from '../src/shared/pro.js';
import { RelayClient, retryDelay } from './relay-client.js';
import { HEADER_DEVICE_ID, HEADER_PROTOCOL, PING } from './relay-protocol.js';
import type { RelaySocket } from './relay-socket.js';

class FakeSocket implements RelaySocket {
  sent: string[] = [];
  private messageHandler: ((data: string) => void) | null = null;
  private closeHandler: ((code: number) => void) | null = null;
  opened = false;

  send(data: string): void {
    this.sent.push(data);
  }

  close(code = 1000): void {
    this.closeHandler?.(code);
  }

  onMessage(handler: (data: string) => void): void {
    this.messageHandler = handler;
  }

  onClose(handler: (code: number) => void): void {
    this.closeHandler = handler;
  }

  onOpen(handler: () => void): void {
    this.opened = true;
    handler();
  }

  receive(data: string): void {
    this.messageHandler?.(data);
  }

  disconnect(code: number): void {
    this.closeHandler?.(code);
  }
}

function session(): ProSession {
  return {
    access_token: 'pro-access',
    refresh_token: 'pro-refresh',
    expires_at: Date.now() + 60 * 60 * 1000,
    email: 'a@example.com',
    user_id: 'user-1',
  };
}

function client(options: {
  pro?: boolean;
  session?: ProSession | null;
  socket?: FakeSocket;
  sockets?: FakeSocket[];
  fetchImpl?: typeof fetch;
  heartbeatIntervalMs?: number;
  pongTimeoutMs?: number;
  now?: () => number;
  device?: { id: string; name: string };
}) {
  const socket = options.socket ?? new FakeSocket();
  const queue = options.sockets ?? [socket];
  const refreshed: ProSession[] = [];
  const opened: { token: string; headers: Record<string, string> }[] = [];
  const regenerated: string[] = [];
  let device = options.device ?? { id: '11111111-1111-4111-8111-111111111111', name: 'Work PC' };
  let current = options.session === undefined ? session() : options.session;
  const relay = new RelayClient({
    getConfig: () => ({
      siteUrl: 'https://pro.example',
      supabaseUrl: 'https://project.supabase.co',
      supabaseAnonKey: 'anon',
      relayUrl: 'https://relay.example',
    }),
    localMcpUrl: () => 'http://127.0.0.1:47821/mcp',
    readLocalToken: () => 'local-token',
    readSession: () => current,
    refreshSession: async (existing) => {
      const next = { ...existing, access_token: 'refreshed-access', expires_at: Date.now() + 60 * 60 * 1000 };
      current = next;
      refreshed.push(next);
      return next;
    },
    isPro: async () => options.pro !== false,
    getDevice: () => device,
    regenerateDevice: () => {
      device = { ...device, id: '22222222-2222-4222-8222-222222222222' };
      regenerated.push(device.id);
      return device;
    },
    appVersion: '0.3.2',
    openSocket: async (_url, token, headers) => {
      opened.push({ token, headers });
      const next = queue.shift();
      if (!next) throw new Error('no socket');
      return next;
    },
    fetchImpl: options.fetchImpl,
    heartbeatIntervalMs: options.heartbeatIntervalMs,
    pongTimeoutMs: options.pongTimeoutMs,
    now: options.now,
  });
  return { relay, socket, refreshed, opened, regenerated };
}

describe('RelayClient', () => {
  it('does not connect without an active subscription', async () => {
    const { relay, socket } = client({ pro: false });
    relay.start();
    await vi.waitFor(() => expect(relay.getStatus().state).toBe('not_pro'));
    expect(socket.opened).toBe(false);
    expect(relay.getStatus().connectorUrl).toBe('https://relay.example/mcp');
  });

  it('forwards a request to the local service and streams the response', async () => {
    const encoder = new TextEncoder();
    const fetchImpl = vi.fn(async (_url: string, init?: RequestInit) => {
      expect(init?.headers).toBeInstanceOf(Headers);
      expect((init?.headers as Headers).get('authorization')).toBe('Bearer local-token');
      expect(init?.method).toBe('POST');
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode('event: message\n'));
          controller.enqueue(encoder.encode('data: {"ok":true}\n\n'));
          controller.close();
        },
      });
      return new Response(stream, { status: 200, headers: { 'content-type': 'text/event-stream' } });
    });
    const { relay, socket } = client({ fetchImpl: fetchImpl as typeof fetch });
    relay.start();
    await vi.waitFor(() => expect(relay.getStatus().state).toBe('connected'));
    socket.receive(JSON.stringify({
      type: 'req',
      id: 'call-1',
      method: 'POST',
      headers: { accept: 'application/json, text/event-stream' },
      body: Buffer.from('{"method":"tools/list"}').toString('base64'),
    }));
    await vi.waitFor(() => expect(socket.sent.some((frame) => frame.includes('"type":"end"'))).toBe(true));
    const head = socket.sent.map((frame) => JSON.parse(frame) as { type: string; status?: number; data?: string }).find((frame) => frame.type === 'head');
    expect(head?.status).toBe(200);
    const chunks = socket.sent.map((frame) => JSON.parse(frame) as { type: string; data?: string }).filter((frame) => frame.type === 'chunk');
    const text = chunks.map((frame) => Buffer.from(frame.data || '', 'base64').toString('utf8')).join('');
    expect(text).toContain('{"ok":true}');
  });

  it('cancels the local fetch when the relay cancels', async () => {
    let signal: AbortSignal | undefined;
    const fetchImpl = vi.fn((_url: string, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
      signal = init?.signal ?? undefined;
      signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
    }));
    const { relay, socket } = client({ fetchImpl: fetchImpl as typeof fetch });
    relay.start();
    await vi.waitFor(() => expect(relay.getStatus().state).toBe('connected'));
    socket.receive(JSON.stringify({ type: 'req', id: 'call-2', method: 'GET', headers: {}, body: '' }));
    await vi.waitFor(() => expect(signal).toBeDefined());
    socket.receive(JSON.stringify({ type: 'cancel', id: 'call-2' }));
    await vi.waitFor(() => expect(signal?.aborted).toBe(true));
  });

  it('refreshes the Pro session after the relay closes the socket as expired', async () => {
    const first = new FakeSocket();
    const second = new FakeSocket();
    const { relay, refreshed, opened } = client({ sockets: [first, second] });
    relay.start();
    await vi.waitFor(() => expect(relay.getStatus().state).toBe('connected'));
    expect(opened.map((item) => item.token)).toEqual(['pro-access']);
    first.disconnect(4001);
    await vi.waitFor(() => expect(opened.map((item) => item.token)).toEqual(['pro-access', 'refreshed-access']));
    expect(refreshed).toHaveLength(1);
    expect(relay.getStatus().state).toBe('connected');
  });

  it('sends protocol 2 and the device identity on the handshake', async () => {
    const { relay, opened } = client({});
    relay.start();
    await vi.waitFor(() => expect(relay.getStatus().state).toBe('connected'));
    expect(opened[0]?.headers[HEADER_PROTOCOL]).toBe('2');
    expect(opened[0]?.headers[HEADER_DEVICE_ID]).toBe('11111111-1111-4111-8111-111111111111');
    expect(opened[0]?.headers['x-vera-device-name']).toBe('Work PC');
    expect(opened[0]?.headers['x-vera-app-version']).toBe('0.3.2');
    expect(opened[0]?.headers['x-vera-instance']).toMatch(/^[0-9a-f-]{36}$/i);
  });

  it('splits a large response into chunks of at most 32 KB', async () => {
    const payload = new Uint8Array(40 * 1024);
    for (let index = 0; index < payload.byteLength; index += 1) payload[index] = index % 251;
    const fetchImpl = vi.fn(async () => new Response(payload, { status: 200 }));
    const { relay, socket } = client({ fetchImpl: fetchImpl as typeof fetch });
    relay.start();
    await vi.waitFor(() => expect(relay.getStatus().state).toBe('connected'));
    socket.receive(JSON.stringify({ type: 'req', id: 'big', method: 'POST', headers: {}, body: '' }));
    await vi.waitFor(() => expect(socket.sent.some((frame) => frame.includes('"type":"end"'))).toBe(true));
    const chunks = socket.sent
      .map((frame) => JSON.parse(frame) as { type: string; data?: string })
      .filter((frame) => frame.type === 'chunk')
      .map((frame) => Buffer.from(frame.data || '', 'base64'));
    expect(chunks.length).toBeGreaterThan(1);
    for (const chunk of chunks) expect(chunk.byteLength).toBeLessThanOrEqual(32 * 1024);
    expect(Buffer.concat(chunks).equals(Buffer.from(payload))).toBe(true);
  });

  it('ends a stream that fails after the head without sending a second head', async () => {
    const encoder = new TextEncoder();
    const fetchImpl = vi.fn(async () => {
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode('partial'));
          controller.error(new Error('disk failed'));
        },
      });
      return new Response(stream, { status: 200, headers: { 'content-type': 'text/event-stream' } });
    });
    const { relay, socket } = client({ fetchImpl: fetchImpl as typeof fetch });
    relay.start();
    await vi.waitFor(() => expect(relay.getStatus().state).toBe('connected'));
    socket.receive(JSON.stringify({ type: 'req', id: 'mid', method: 'POST', headers: {}, body: '' }));
    await vi.waitFor(() => expect(socket.sent.filter((frame) => frame.includes('"type":"end"'))).toHaveLength(1));
    const frames = socket.sent.map((frame) => JSON.parse(frame) as { type: string; status?: number });
    const heads = frames.filter((frame) => frame.type === 'head');
    expect(heads).toHaveLength(1);
    expect(heads[0]?.status).toBe(200);
  });

  it('reconnects when a heartbeat is not answered', async () => {
    const first = new FakeSocket();
    const second = new FakeSocket();
    const { relay, opened } = client({ sockets: [first, second], heartbeatIntervalMs: 20, pongTimeoutMs: 20 });
    relay.start();
    await vi.waitFor(() => expect(relay.getStatus().state).toBe('connected'));
    await vi.waitFor(() => expect(first.sent).toContain(PING), { timeout: 1000 });
    await vi.waitFor(() => expect(opened).toHaveLength(2), { timeout: 4000 });
    expect(relay.getStatus().state).toBe('connected');
  });

  it('stands by when another computer is current and becomes active when pinned here', async () => {
    const { relay, socket } = client({});
    relay.start();
    await vi.waitFor(() => expect(relay.getStatus().state).toBe('connected'));
    const self = '11111111-1111-4111-8111-111111111111';
    socket.receive(JSON.stringify({
      type: 'devices',
      self,
      routing: { mode: 'auto' },
      current: 'laptop',
      devices: [
        { id: self, name: 'Work PC', online: true, lastSeen: 1, appVersion: '0.3.2' },
        { id: 'laptop', name: 'Laptop', online: true, lastSeen: 2, appVersion: '0.3.2' },
      ],
    }));
    expect(relay.getStatus().state).toBe('standby');
    expect(relay.getStatus().message).toBe('Connected. Cloud agents are using Laptop.');
    socket.receive(JSON.stringify({
      type: 'devices',
      self,
      routing: { mode: 'pinned', pinned: self },
      current: 'laptop',
      devices: [
        { id: self, name: 'Work PC', online: true, lastSeen: 1, appVersion: '0.3.2' },
        { id: 'laptop', name: 'Laptop', online: true, lastSeen: 2, appVersion: '0.3.2' },
      ],
    }));
    expect(relay.getStatus().state).toBe('connected');
    expect(relay.getStatus().routing).toEqual({ mode: 'pinned', pinned: self });
  });

  it('regenerates this computer once after a duplicate id and then stops', async () => {
    const first = new FakeSocket();
    const second = new FakeSocket();
    const third = new FakeSocket();
    let now = 1_000;
    const { relay, opened, regenerated } = client({ sockets: [first, second, third], now: () => now });
    relay.start();
    await vi.waitFor(() => expect(opened).toHaveLength(1));
    first.disconnect(4002);
    await vi.waitFor(() => expect(regenerated).toEqual(['22222222-2222-4222-8222-222222222222']));
    await vi.waitFor(() => expect(opened).toHaveLength(2));
    expect(opened[1]?.headers[HEADER_DEVICE_ID]).toBe('22222222-2222-4222-8222-222222222222');
    now += 1_000;
    second.disconnect(4002);
    await vi.waitFor(() => expect(relay.getStatus().state).toBe('error'));
    expect(relay.getStatus().message).toContain('could not tell this computer apart');
    expect(opened).toHaveLength(2);
  });

  it('does not reconnect after this computer is forgotten', async () => {
    const first = new FakeSocket();
    const second = new FakeSocket();
    const { relay, opened } = client({ sockets: [first, second] });
    relay.start();
    await vi.waitFor(() => expect(relay.getStatus().state).toBe('connected'));
    first.disconnect(4004);
    await vi.waitFor(() => expect(relay.getStatus().message).toContain('removed from cloud agents'));
    expect(relay.getStatus().state).toBe('off');
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(opened).toHaveLength(1);
  });

  it('does not reconnect while the computer is asleep', async () => {
    const first = new FakeSocket();
    const second = new FakeSocket();
    const { relay, opened } = client({ sockets: [first, second] });
    relay.start();
    await vi.waitFor(() => expect(relay.getStatus().state).toBe('connected'));
    relay.suspend();
    expect(relay.getStatus().state).toBe('standby');
    expect(relay.getStatus().message).toContain('asleep');
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(opened).toHaveLength(1);
    relay.reconnectNow();
    await vi.waitFor(() => expect(opened).toHaveLength(2));
    expect(relay.getStatus().state).toBe('connected');
  });

  it('jitters the reconnect delay by about a fifth', () => {
    expect(retryDelay(1, () => 0)).toBe(800);
    expect(retryDelay(1, () => 1)).toBe(1200);
  });
});
