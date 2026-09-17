import { EventEmitter } from 'node:events';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BridgeManager } from './bridge-manager.js';

class FakeChild extends EventEmitter {
  killed = false;
  pid = 4242;
  stdout = new EventEmitter();
  stderr = new EventEmitter();

  kill(): boolean {
    this.killed = true;
    queueMicrotask(() => this.emit('exit', 0, null));
    return true;
  }
}

describe('BridgeManager', () => {
  const children: FakeChild[] = [];
  const spawnOptions: Array<{ stdio?: unknown }> = [];

  afterEach(() => {
    children.length = 0;
    spawnOptions.length = 0;
    vi.useRealTimers();
  });

  function createManager(overrides: Partial<ConstructorParameters<typeof BridgeManager>[0]> = {}) {
    const userDataDir = mkdtempSync(join(tmpdir(), 'vera-bridge-'));
    const tunnelClient = join(userDataDir, 'tunnel-client.exe');
    writeFileSync(tunnelClient, 'fake');
    let credential = 'sk-test';
    const manager = new BridgeManager({
      userDataDir,
      resolveMcpCommand: () => ({ executable: 'vera-sidecar', args: ['mcp-bridge'] }),
      resolveTunnelClientPath: () => tunnelClient,
      readTunnelCredential: () => credential,
      encryptionAvailable: () => true,
      startupTimeoutMs: 200,
      readyPollMs: 20,
      maxRestartAttempts: 1,
      fetchReady: async () => true,
      spawnImpl: ((_exe, _args, opts) => {
        spawnOptions.push(opts || {});
        const child = new FakeChild();
        children.push(child);
        return child as unknown as ReturnType<typeof import('node:child_process').spawn>;
      }) as typeof import('node:child_process').spawn,
      ...overrides,
      // Allow tests to clear credential after construction.
      ...(overrides.readTunnelCredential
        ? {}
        : {
            readTunnelCredential: () => credential,
          }),
    });
    manager.updateConfig({ libraryPath: userDataDir, tunnelId: 'tunnel_test' });
    return {
      manager,
      setCredential: (value: string) => {
        credential = value;
      },
      userDataDir,
    };
  }

  it('reports needs_setup when configuration is incomplete', () => {
    const { manager, setCredential } = createManager();
    setCredential('');
    const status = manager.updateConfig({ libraryPath: '', tunnelId: '' });
    expect(status.state).toBe('needs_setup');
  });

  it('starts once and reaches connected when ready', async () => {
    const { manager } = createManager();
    const first = manager.start();
    const duplicate = manager.start();
    const status = await first;
    expect(status.state).toBe('connected');
    expect(status.ready).toBe(true);
    expect(children).toHaveLength(1);
    expect(spawnOptions[0]?.stdio).toEqual(['ignore', 'pipe', 'pipe']);
    await duplicate;
    expect(children).toHaveLength(1);
    expect(await manager.start()).toMatchObject({ state: 'connected' });
    expect(children).toHaveLength(1);
  });

  it('times out when readiness never arrives', async () => {
    const { manager } = createManager({
      fetchReady: async () => false,
      startupTimeoutMs: 60,
      readyPollMs: 15,
    });
    const status = await manager.start();
    expect(status.state).toBe('error');
    expect(status.lastError || status.message).toMatch(/timed out/i);
  });

  it('stops during work and cleans up the child', async () => {
    const { manager } = createManager({
      fetchReady: async () => {
        await new Promise((resolve) => setTimeout(resolve, 30));
        return true;
      },
    });
    const starting = manager.start();
    const stopped = await manager.stop('Disconnected during work.');
    expect(stopped.state).toBe('disabled');
    expect(children[0]?.killed).toBe(true);
    const after = await starting;
    expect(['disabled', 'error', 'connected', 'starting']).toContain(after.state);
  });

  it('fails clearly without encryption', async () => {
    const { manager } = createManager({ encryptionAvailable: () => false });
    const status = await manager.start();
    expect(status.state).toBe('error');
    expect(status.message).toMatch(/Secure credential storage/i);
  });
});
