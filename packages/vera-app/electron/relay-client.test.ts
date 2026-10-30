import { describe, expect, it, vi } from 'vitest';
import type { ProSession } from '../src/shared/pro.js';
import { RelayClient } from './relay-client.js';
import type { RelaySocket } from './relay-socket.js';

class FakeSocket implements RelaySocket {
  sent: string[] = [];
  private messageHandler: ((data: string) => void) | null = null;
  private closeHandler: ((code: number) => void) | null = null;
  opened = false;

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    this.closeHandler?.(1000);
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
}) {
  const socket = options.socket ?? new FakeSocket();
  const queue = options.sockets ?? [socket];
  const refreshed: ProSession[] = [];
  const opened: string[] = [];
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
    openSocket: async (_url, token) => {
      opened.push(token);
      const next = queue.shift();
      if (!next) throw new Error('no socket');
      return next;
    },
    fetchImpl: options.fetchImpl,
  });
  return { relay, socket, refreshed, opened };
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
    expect(opened).toEqual(['pro-access']);
    first.disconnect(4001);
    await vi.waitFor(() => expect(opened).toEqual(['pro-access', 'refreshed-access']));
    expect(refreshed).toHaveLength(1);
    expect(relay.getStatus().state).toBe('connected');
  });
});
