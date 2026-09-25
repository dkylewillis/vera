import { EventEmitter } from 'node:events';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BridgeManager, findTunnelClientOnPath } from './bridge-manager.js';

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

  afterEach(() => {
    children.length = 0;
    vi.useRealTimers();
  });

  function createManager(overrides: Partial<ConstructorParameters<typeof BridgeManager>[0]> = {}) {
    const userDataDir = mkdtempSync(join(tmpdir(), 'vera-bridge-'));
    const tunnelClient = join(userDataDir, 'tunnel-client.exe');
    writeFileSync(tunnelClient, 'fake');
    let credential = 'sk-test';
    let spawnedArgs: string[] = [];
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
      readHealthUrl: () => 'http://127.0.0.1:40123/',
      spawnImpl: ((_exe, args, _opts) => {
        spawnedArgs = [...args];
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
      spawnedArgs: () => spawnedArgs,
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
    expect(await duplicate).toMatchObject({ state: 'connected' });
  });

  it('reports the resolved tunnel client to the setup wizard', () => {
    const { manager } = createManager();
    const status = manager.getStatus();
    expect(status.clientDetected).toBe(true);
    expect(status.tunnelClientPath).toMatch(/tunnel-client\.exe$/u);
    expect(status.libraryValid).toBe(true);
    expect(status.tunnelIdValid).toBe(true);
  });

  it('explains when tunnel-client still needs to be selected', () => {
    const { manager, userDataDir } = createManager({ resolveTunnelClientPath: () => null });
    const status = manager.updateConfig({ libraryPath: userDataDir, tunnelId: 'tunnel_test' });
    expect(status.state).toBe('needs_setup');
    expect(status.clientDetected).toBe(false);
    expect(status.message).toMatch(/Select tunnel-client/i);
  });

  it('uses tunnel-client’s dynamically assigned loopback health URL', async () => {
    const checked: string[] = [];
    const { manager } = createManager({
      fetchReady: async (url) => {
        checked.push(url);
        return url === 'http://127.0.0.1:40123/readyz';
      },
    });
    const status = await manager.start();
    expect(status.state).toBe('connected');
    expect(checked).toEqual(['http://127.0.0.1:40123/readyz']);
  });

  it('starts tunnel-client with a dynamic health URL file and current flag names', async () => {
    const { manager, userDataDir, spawnedArgs } = createManager();
    await manager.start();
    expect(spawnedArgs()).toEqual(expect.arrayContaining([
      '--control-plane.tunnel-id',
      'tunnel_test',
      '--mcp.command',
      'vera-sidecar mcp-bridge',
      '--health.listen-addr',
      '127.0.0.1:0',
      '--health.url-file',
      join(userDataDir, 'bridge', 'health-url.txt'),
    ]));
  });

  it('uses Windows-safe forward slashes in the embedded MCP command', async () => {
    const { manager, spawnedArgs } = createManager({
      resolveMcpCommand: () => ({
        executable: 'C:\\Program Files\\VERA\\vera-sidecar.exe',
        args: ['mcp-bridge'],
      }),
    });
    await manager.start();
    const args = spawnedArgs();
    expect(args[args.indexOf('--mcp.command') + 1]).toBe(
      '"C:/Program Files/VERA/vera-sidecar.exe" mcp-bridge',
    );
  });

  it('redacts credentials before persisting tunnel diagnostics', async () => {
    const messages: Array<{ stream: string; chunk: string }> = [];
    const { manager } = createManager({
      logDiagnostic: (stream, chunk) => messages.push({ stream, chunk }),
    });
    await manager.start();
    children[0]?.stderr.emit('data', Buffer.from('CONTROL_PLANE_API_KEY=sk-test Bearer sk-live-secret'));
    expect(messages).toEqual([{ stream: 'stderr', chunk: 'CONTROL_PLANE_API_KEY=[REDACTED] Bearer [REDACTED]' }]);
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

  it('restarts after a tunnel-client exit during an active session', async () => {
    const { manager } = createManager();
    await manager.start();
    children[0]?.emit('exit', 1, null);
    await new Promise((resolve) => setTimeout(resolve, 550));
    expect(children).toHaveLength(2);
    expect((await manager.start()).state).toBe('connected');
  });

  it('fails clearly without encryption', async () => {
    const { manager } = createManager({ encryptionAvailable: () => false });
    const status = await manager.start();
    expect(status.state).toBe('error');
    expect(status.message).toMatch(/Secure credential storage/i);
  });

  it('never fetches a health URL that is not http loopback with an explicit port', async () => {
    const checked: string[] = [];
    const rejected = [
      'http://example.com:8080/',
      'https://127.0.0.1:40123/',
      'http://localhost:40123/',
      'http://127.0.0.1/',
      'http://127.0.0.1:40123/readyz',
    ];
    for (const value of rejected) {
      const { manager } = createManager({
        readHealthUrl: () => value,
        fetchReady: async (url) => {
          checked.push(url);
          return true;
        },
        startupTimeoutMs: 50,
        readyPollMs: 15,
      });
      const status = await manager.start();
      expect(status.state).toBe('error');
      expect(status.lastError || status.message).toMatch(/timed out/i);
    }
    expect(checked).toEqual([]);
  });

  it('accepts IPv6 loopback health URLs', async () => {
    const checked: string[] = [];
    const { manager } = createManager({
      readHealthUrl: () => 'http://[::1]:40123/',
      fetchReady: async (url) => {
        checked.push(url);
        return url.endsWith('/readyz');
      },
    });
    const status = await manager.start();
    expect(status.state).toBe('connected');
    expect(checked[0]).toMatch(/http:\/\/\[::1\]:40123\/readyz$/u);
  });
});

describe('findTunnelClientOnPath', () => {
  it('prefers VERA_TUNNEL_CLIENT when that file exists', () => {
    const dir = mkdtempSync(join(tmpdir(), 'vera-tunnel-'));
    const client = join(dir, 'custom-client');
    writeFileSync(client, 'fake');
    expect(findTunnelClientOnPath({
      VERA_TUNNEL_CLIENT: client,
      PATH: '',
    })).toBe(client);
  });

  it('discovers tunnel-client on PATH and otherwise returns null', () => {
    const dir = mkdtempSync(join(tmpdir(), 'vera-tunnel-path-'));
    const name = process.platform === 'win32' ? 'tunnel-client.exe' : 'tunnel-client';
    const client = join(dir, name);
    writeFileSync(client, 'fake');
    expect(findTunnelClientOnPath({ PATH: dir, VERA_TUNNEL_CLIENT: '' })).toBe(client);
    expect(findTunnelClientOnPath({ PATH: '', VERA_TUNNEL_CLIENT: '' })).toBeNull();
    expect(findTunnelClientOnPath({
      PATH: '',
      VERA_TUNNEL_CLIENT: join(dir, 'missing-client'),
    })).toBeNull();
  });
});
