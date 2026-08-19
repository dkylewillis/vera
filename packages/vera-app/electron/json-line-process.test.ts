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
      args: ['-m', 'vera_app.sidecar'],
      cwd: 'C:\\Users\\me\\AppData\\Roaming\\VERA',
      env: { PYTHONPATH: 'C:\\Program Files\\VERA\\resources\\python\\sidecar' },
    }));
    const pending = proc.request({ action: 'ping' });
    expect(spawn).toHaveBeenCalledWith(
      'C:\\Users\\me\\venv\\Scripts\\python.exe',
      ['-m', 'vera_app.sidecar'],
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
      args: ['-m', 'vera_app.sidecar'],
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
      args: ['-m', 'vera_app.sidecar'],
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
      args: ['-m', 'vera_app.sidecar'],
    }));
    const pending = proc.request({ action: 'ping' });
    proc.forceRestart();
    await expect(pending).rejects.toThrow(/restarted/);
    expect(child.kill).toHaveBeenCalled();
  });

  it('defers restart until in-flight work finishes', async () => {
    const child = fakeChild();
    spawn.mockReturnValue(child);
    const proc = new JsonLineProcess('plugin-host', () => ({
      executable: 'python',
      args: ['-m', 'vera_app.sidecar'],
    }));
    const pending = proc.request({ action: 'ping' }, undefined, 'req-1');
    proc.restart();
    expect(child.kill).not.toHaveBeenCalled();
    child.stdout.emit('data', Buffer.from('{"id":"req-1","ok":true,"result":{"status":"ok"}}\n'));
    await expect(pending).resolves.toMatchObject({ ok: true });
    expect(child.kill).toHaveBeenCalled();
  });

  it('cancelRequest returns false when the id is not pending', async () => {
    const proc = new JsonLineProcess('plugin-host', () => ({
      executable: 'python',
      args: ['-m', 'vera_app.sidecar'],
    }));
    await expect(proc.cancelRequest('missing')).resolves.toBe(false);
    expect(spawn).not.toHaveBeenCalled();
  });

  it('cancelRequest sends cancel and returns the sidecar cancelled flag', async () => {
    const child = fakeChild();
    spawn.mockReturnValue(child);
    const proc = new JsonLineProcess('plugin-host', () => ({
      executable: 'python',
      args: ['-m', 'vera_app.sidecar'],
    }));
    const pending = proc.request({ action: 'search' }, undefined, 'search-1');
    const cancelled = proc.cancelRequest('search-1');
    child.stdout.emit('data', Buffer.from('{"id":"1","ok":true,"result":{"cancelled":true}}\n'));
    await expect(cancelled).resolves.toBe(true);
    expect(child.stdin.write).toHaveBeenCalledWith(
      expect.stringContaining('"action":"cancel"'),
      expect.any(Function),
    );
    expect(child.stdin.write).toHaveBeenCalledWith(
      expect.stringContaining('"target_id":"search-1"'),
      expect.any(Function),
    );
    child.stdout.emit('data', Buffer.from('{"id":"search-1","ok":false,"cancelled":true}\n'));
    await expect(pending).resolves.toMatchObject({ ok: false, cancelled: true });
  });

  it('cancelRequest returns false when cancel cannot be written', async () => {
    const child = fakeChild();
    spawn.mockReturnValue(child);
    const proc = new JsonLineProcess('plugin-host', () => ({
      executable: 'python',
      args: ['-m', 'vera_app.sidecar'],
    }));
    const pending = proc.request({ action: 'search' }, undefined, 'search-1');
    child.stdin.writable = false;
    await expect(proc.cancelRequest('search-1')).resolves.toBe(false);
    child.stdout.emit('data', Buffer.from('{"id":"search-1","ok":true,"result":{}}\n'));
    await expect(pending).resolves.toMatchObject({ ok: true });
  });

  it('rejects when stdin is not writable', async () => {
    const child = fakeChild();
    child.stdin.writable = false;
    spawn.mockReturnValue(child);
    const proc = new JsonLineProcess('plugin-host', () => ({
      executable: 'python',
      args: ['-m', 'vera_app.sidecar'],
    }));
    await expect(proc.request({ action: 'ping' })).rejects.toThrow(/stdin is not writable/);
  });

  it('forwards event lines without resolving the request', async () => {
    const child = fakeChild();
    spawn.mockReturnValue(child);
    const proc = new JsonLineProcess('plugin-host', () => ({
      executable: 'python',
      args: ['-m', 'vera_app.sidecar'],
    }));
    const onEvent = vi.fn();
    const pending = proc.request({ action: 'answer' }, onEvent, 'ans-1');
    child.stdout.emit('data', Buffer.from('{"id":"ans-1","event":"answer_delta","text":"Hi"}\n'));
    expect(onEvent).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'ans-1', event: 'answer_delta', text: 'Hi' }),
    );
    child.stdout.emit('data', Buffer.from('{"id":"ans-1","ok":true,"result":{"answer":"Hi"}}\n'));
    await expect(pending).resolves.toMatchObject({ ok: true, result: { answer: 'Hi' } });
  });

  it('ignores invalid stdout lines and still completes the request', async () => {
    const child = fakeChild();
    spawn.mockReturnValue(child);
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    const proc = new JsonLineProcess('plugin-host', () => ({
      executable: 'python',
      args: ['-m', 'vera_app.sidecar'],
    }));
    const pending = proc.request({ action: 'ping' }, undefined, 'req-1');
    child.stdout.emit('data', Buffer.from('not-json\n{"id":"req-1","ok":true,"result":{}}\n'));
    await expect(pending).resolves.toMatchObject({ ok: true });
    expect(error).toHaveBeenCalled();
    error.mockRestore();
  });
});
