import { EventEmitter } from 'node:events';
import { existsSync, mkdtempSync, mkdirSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AGENT_SERVICE_CLOUD_DISCLOSURE, AGENT_SERVICE_DISCLOSURE } from '../src/shared/agent-snippets.js';
import { ServiceManager } from './service-manager.js';

class FakeChild extends EventEmitter {
  killed = false;
  pid = 4242;
  stdout = new EventEmitter();
  stderr = new EventEmitter();

  kill(): boolean {
    this.killed = true;
    return true;
  }
}

describe('ServiceManager', () => {
  const children: FakeChild[] = [];

  afterEach(() => {
    children.length = 0;
  });

  function createManager(port = 47821) {
    const userDataDir = mkdtempSync(join(tmpdir(), 'vera-service-'));
    const library = join(userDataDir, 'library');
    mkdirSync(library);
    const other = join(userDataDir, 'other');
    mkdirSync(other);
    let token = '';
    const spawned: { args: string[]; env: NodeJS.ProcessEnv }[] = [];
    const manager = new ServiceManager({
      userDataDir,
      resolveCommand: () => ({
        executable: join(userDataDir, 'vera-sidecar.exe'),
        args: ['mcp-service'],
      }),
      readToken: () => token,
      writeToken: (value) => {
        token = value;
      },
      encryptionAvailable: () => true,
      findFreePort: async (preferred) => preferred,
      fetchHealth: async () => true,
      startupTimeoutMs: 500,
      readyPollMs: 10,
      maxRestartAttempts: 1,
      spawnImpl: ((_exe, args, opts) => {
        spawned.push({
          args: [...(args as string[])],
          env: { ...(opts as { env?: NodeJS.ProcessEnv }).env },
        });
        const child = new FakeChild();
        children.push(child);
        return child as unknown as ReturnType<typeof import('node:child_process').spawn>;
      }) as typeof import('node:child_process').spawn,
    });
    manager.updateConfig({ enabled: false, libraryRoots: [library], port });
    return { manager, userDataDir, library, other, spawned, token: () => token };
  }

  it('starts with the token in the environment and a multi-root policy', async () => {
    const { manager, userDataDir, library, spawned, token } = createManager();
    const status = await manager.start();
    expect(status.state).toBe('running');
    expect(status.token).toMatch(/^[a-f0-9]{64}$/);
    expect(token()).toBe(status.token);
    const args = spawned[0]?.args.join(' ') || '';
    expect(args).not.toContain(status.token);
    expect(spawned[0]?.env.VERA_SERVICE_TOKEN).toBe(status.token);
    const policy = JSON.parse(readFileSync(join(userDataDir, 'service', 'policy.json'), 'utf8')) as {
      library_roots: string[];
      disclosure: string;
    };
    expect(policy.library_roots).toEqual([library]);
    expect(policy.disclosure).toBe(AGENT_SERVICE_DISCLOSURE);
    expect(status.cloudEnabled).toBe(false);
    const connect = JSON.parse(readFileSync(join(userDataDir, 'service', 'connect.json'), 'utf8')) as {
      url: string;
      token: string;
    };
    expect(connect.url).toBe(status.url);
    expect(connect.token).toBe(status.token);
    expect(status.snippets.http).toContain(status.token);
    expect(status.snippets.stdio).toContain('mcp-connect');
    expect(status.snippets.note).toContain('model provider');
  });

  it('writes the cloud disclosure when cloud agents are allowed', async () => {
    const { manager, userDataDir } = createManager();
    manager.updateConfig({ cloudEnabled: true });
    await manager.start();
    const policy = JSON.parse(readFileSync(join(userDataDir, 'service', 'policy.json'), 'utf8')) as {
      disclosure: string;
    };
    expect(policy.disclosure).toBe(AGENT_SERVICE_CLOUD_DISCLOSURE);
    expect(manager.getStatus().cloudEnabled).toBe(true);
  });

  it('stops the process and removes the connect file', async () => {
    const { manager, userDataDir } = createManager();
    await manager.start();
    const stopped = await manager.stop('Agent access is off.');
    expect(stopped.state).toBe('disabled');
    expect(children[0]?.killed).toBe(true);
    expect(existsSync(join(userDataDir, 'service', 'connect.json'))).toBe(false);
    expect(existsSync(join(userDataDir, 'service', 'policy.json'))).toBe(false);
  });

  it('restarts when the shared libraries change', async () => {
    const { manager, other } = createManager();
    await manager.start();
    await manager.reconfigure({ libraryRoots: [other] });
    await vi.waitFor(() => {
      expect(children).toHaveLength(2);
      expect(manager.getStatus().state).toBe('running');
    });
    expect(children[0]?.killed).toBe(true);
    expect(manager.getStatus().libraryRoots).toEqual([other]);
  });

  it('reports when the bound port differs from the saved port', async () => {
    const custom = new ServiceManager({
      userDataDir: mkdtempSync(join(tmpdir(), 'vera-service-port-')),
      resolveCommand: () => ({ executable: 'vera-sidecar', args: ['mcp-service'] }),
      readToken: () => 'abc',
      writeToken: () => undefined,
      encryptionAvailable: () => true,
      findFreePort: async (preferred) => preferred + 2,
      fetchHealth: async () => true,
      startupTimeoutMs: 500,
      readyPollMs: 10,
      spawnImpl: (() => {
        const child = new FakeChild();
        children.push(child);
        return child as unknown as ReturnType<typeof import('node:child_process').spawn>;
      }) as typeof import('node:child_process').spawn,
    });
    const library = mkdtempSync(join(tmpdir(), 'vera-lib-'));
    custom.updateConfig({ libraryRoots: [library], port: 48000 });
    const status = await custom.start();
    expect(status.port).toBe(48002);
    expect(status.portChanged).toBe(true);
    expect(status.message).toContain('Update any saved snippets');
    await custom.stop();
  });
});
