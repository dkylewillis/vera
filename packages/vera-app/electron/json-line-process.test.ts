import { EventEmitter } from 'node:events';
import { afterEach, describe, expect, it, vi } from 'vitest';

const spawn = vi.hoisted(() => vi.fn());
vi.mock('node:child_process', () => ({ spawn }));

import { JsonLineProcess } from './json-line-process.js';

function fakeChild() {
  const child = new EventEmitter() as unknown as EventEmitter & {
    stdout: EventEmitter;
    stderr: EventEmitter;
    stdin: { write: ReturnType<typeof vi.fn>; writable: boolean; destroyed: boolean };
    kill: ReturnType<typeof vi.fn>;
  };
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  child.stdin = {
    write: vi.fn((_data: string, cb?: (error?: Error | null) => void) => cb?.(null)),
    writable: true,
    destroyed: false,
  };
  child.kill = vi.fn(() => {
    child.emit('exit', 1, null);
  });
  return child;
}

describe('JsonLineProcess', () => {
  afterEach(() => {
    spawn.mockReset();
  });

  it('spawns with shell disabled for Windows python paths', async () => {
    const child = fakeChild();
    spawn.mockReturnValue(child);
    const proc = new JsonLineProcess('plugin-host', () => ({
      executable: 'C:\\Users\\me\\venv\\Scripts\\python.exe',
      args: ['-m', 'vera_plugin_host'],
      cwd: 'C:\\Users\\me\\AppData\\Roaming\\VERA',
      env: { PYTHONPATH: 'C:\\Program Files\\VERA\\resources\\python\\plugin-host' },
    }));
    const pending = proc.request({ action: 'ping' });
    expect(spawn).toHaveBeenCalledWith(
      'C:\\Users\\me\\venv\\Scripts\\python.exe',
      ['-m', 'vera_plugin_host'],
      expect.objectContaining({
        shell: false,
        windowsHide: true,
        cwd: 'C:\\Users\\me\\AppData\\Roaming\\VERA',
      }),
    );
    child.stdout.emit('data', Buffer.from('{"id":"1","ok":true,"result":{"status":"ok"}}\n'));
    await expect(pending).resolves.toMatchObject({ ok: true });
  });

  it('rejects in-flight work on crash and respawns for the next request', async () => {
    const first = fakeChild();
    const second = fakeChild();
    spawn.mockReturnValueOnce(first).mockReturnValueOnce(second);
    const proc = new JsonLineProcess('plugin-host', () => ({
      executable: 'python',
      args: ['-m', 'vera_plugin_host'],
    }));
    const crashed = proc.request({ action: 'convert' }, undefined, 'req-1');
    first.emit('exit', 1, null);
    await expect(crashed).rejects.toThrow(/exited/);

    const recovered = proc.request({ action: 'ping' }, undefined, 'req-2');
    expect(spawn).toHaveBeenCalledTimes(2);
    second.stdout.emit('data', Buffer.from('{"id":"req-2","ok":true,"result":{"status":"ok"}}\n'));
    await expect(recovered).resolves.toMatchObject({ ok: true });
  });

  it('sends skip and cancel to the process that owns the request', async () => {
    const child = fakeChild();
    spawn.mockReturnValue(child);
    const proc = new JsonLineProcess('plugin-host', () => ({
      executable: 'python',
      args: ['-m', 'vera_plugin_host'],
    }));
    const convert = proc.request({ action: 'convert' }, undefined, 'job-1');
    const skip = proc.skipConversion('job-1');
    child.stdout.emit('data', Buffer.from('{"id":"1","ok":true,"result":{"skipped":true}}\n'));
    await expect(skip).resolves.toEqual({ skipped: true });
    expect(child.stdin.write).toHaveBeenCalledWith(
      expect.stringContaining('"action":"skip"'),
      expect.any(Function),
    );
    expect(child.stdin.write).toHaveBeenCalledWith(
      expect.stringContaining('"target_id":"job-1"'),
      expect.any(Function),
    );
    child.stdout.emit('data', Buffer.from('{"id":"job-1","ok":true,"result":{"output":"out.vera"}}\n'));
    await expect(convert).resolves.toMatchObject({ ok: true });
  });

  it('forceRestart kills in-flight work instead of waiting for idle', async () => {
    const child = fakeChild();
    spawn.mockReturnValue(child);
    const proc = new JsonLineProcess('plugin-host', () => ({
      executable: 'python',
      args: ['-m', 'vera_plugin_host'],
    }));
    const pending = proc.request({ action: 'ping' });
    proc.forceRestart();
    await expect(pending).rejects.toThrow(/restarted/);
    expect(child.kill).toHaveBeenCalled();
  });
});
