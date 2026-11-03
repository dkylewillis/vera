import { describe, expect, it, vi } from 'vitest';
import type { ProSession } from '../src/shared/pro.js';
import { RelayControl, RelayControlError } from './relay-control.js';

function session(token: string): ProSession {
  return {
    access_token: token,
    refresh_token: 'refresh',
    expires_at: Date.now() + 60_000,
    email: 'a@example.com',
    user_id: 'user-1',
  };
}

describe('RelayControl', () => {
  it('refreshes the session once after a 401 and then reads the computer list', async () => {
    const calls: { url: string; token: string; method: string }[] = [];
    const fetchImpl = vi.fn(async (url: string, init?: RequestInit) => {
      const token = String((init?.headers as Record<string, string>).Authorization || '');
      calls.push({ url, token, method: init?.method || 'GET' });
      if (token.endsWith('stale')) return new Response('{}', { status: 401 });
      return new Response(JSON.stringify({
        routing: { mode: 'auto' },
        current: 'device-1',
        devices: [],
      }), { status: 200 });
    });
    let current = session('stale');
    const control = new RelayControl({
      relayUrl: 'https://relay.example',
      readSession: () => current,
      refreshSession: async () => {
        current = session('fresh');
        return current;
      },
      fetchImpl: fetchImpl as typeof fetch,
    });
    const directory = await control.devices();
    expect(directory.routing).toEqual({ mode: 'auto' });
    expect(calls.map((call) => call.token)).toEqual(['Bearer stale', 'Bearer fresh']);
    expect(calls[0]?.url).toBe('https://relay.example/devices');
  });

  it('sends a pin and surfaces the relay error message', async () => {
    const fetchImpl = vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === 'PUT') {
        expect(JSON.parse(String(init.body))).toEqual({ mode: 'pinned', device_id: 'device-1' });
        return new Response(JSON.stringify({
          jsonrpc: '2.0',
          id: null,
          error: { code: -32000, message: 'That computer is not registered.' },
        }), { status: 404 });
      }
      return new Response('{}', { status: 500 });
    });
    const control = new RelayControl({
      relayUrl: 'wss://relay.example/ignored',
      readSession: () => session('fresh'),
      refreshSession: async (existing) => existing,
      fetchImpl: fetchImpl as typeof fetch,
    });
    await expect(control.setRouting('pinned', 'device-1')).rejects.toBeInstanceOf(RelayControlError);
    await expect(control.setRouting('pinned', 'device-1')).rejects.toThrow('That computer is not registered.');
  });
});