import { afterEach, describe, expect, it, vi } from 'vitest';
import { createSidecarCaller } from './useSidecarCall';

type SidecarResponse<T> = {
  ok: boolean;
  result?: T;
  error?: string;
  cancelled?: boolean;
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((next) => {
    resolve = next;
  });
  return { promise, resolve };
}

function installVera(request: (payload: Record<string, unknown>, requestId?: string) => Promise<SidecarResponse<unknown>>) {
  const cancelRequest = vi.fn(async () => undefined);
  vi.stubGlobal('window', {
    vera: {
      request,
      cancelRequest,
    },
  });
  return { cancelRequest };
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('createSidecarCaller', () => {
  it('returns null when a later same-scope call supersedes a successful response', async () => {
    const first = deferred<SidecarResponse<{ id: string }>>();
    const second = deferred<SidecarResponse<{ id: string }>>();
    let requestCount = 0;
    const setErrorMessage = vi.fn();
    installVera(async () => {
      requestCount += 1;
      return requestCount === 1 ? first.promise : second.promise;
    });
    const caller = createSidecarCaller(new Map(), () => ({
      dispatchBackgroundTask: () => undefined,
      setErrorMessage,
      setProviderErrorDetail: () => undefined,
    }));

    const firstCall = caller.call<{ id: string }>(
      { action: 'inspect', path: 'a.vera' },
      'Opening',
      'req-1',
      { timeoutMs: 0 },
    );
    const secondCall = caller.call<{ id: string }>(
      { action: 'inspect', path: 'b.vera' },
      'Opening',
      'req-2',
      { timeoutMs: 0 },
    );

    second.resolve({ ok: true, result: { id: 'second' } });
    await expect(secondCall).resolves.toEqual({ id: 'second' });

    first.resolve({ ok: true, result: { id: 'first' } });
    await expect(firstCall).resolves.toBeNull();
    expect(setErrorMessage).not.toHaveBeenCalledWith(expect.stringMatching(/.+/));
  });

  it('does not apply a superseded error to the banner', async () => {
    const first = deferred<SidecarResponse<{ id: string }>>();
    const second = deferred<SidecarResponse<{ id: string }>>();
    let requestCount = 0;
    const setErrorMessage = vi.fn();
    installVera(async () => {
      requestCount += 1;
      return requestCount === 1 ? first.promise : second.promise;
    });
    const caller = createSidecarCaller(new Map(), () => ({
      dispatchBackgroundTask: () => undefined,
      setErrorMessage,
      setProviderErrorDetail: () => undefined,
    }));

    const firstCall = caller.call(
      { action: 'inspect' },
      'Opening',
      'req-1',
      { timeoutMs: 0 },
    );
    const secondCall = caller.call(
      { action: 'inspect' },
      'Opening',
      'req-2',
      { timeoutMs: 0 },
    );

    second.resolve({ ok: true, result: { id: 'second' } });
    await secondCall;

    first.resolve({ ok: false, error: 'stale inspect failed' });
    await expect(firstCall).resolves.toBeNull();
    expect(setErrorMessage).not.toHaveBeenCalledWith('stale inspect failed');
  });

  it('cancels the sidecar request when the call times out', async () => {
    vi.useFakeTimers();
    const pending = deferred<SidecarResponse<{ id: string }>>();
    const { cancelRequest } = installVera(async () => pending.promise);
    const setErrorMessage = vi.fn();
    const caller = createSidecarCaller(new Map(), () => ({
      dispatchBackgroundTask: () => undefined,
      setErrorMessage,
      setProviderErrorDetail: () => undefined,
    }));

    const call = caller.call({ action: 'inspect' }, 'Opening', 'req-1', { timeoutMs: 1000 });
    await vi.advanceTimersByTimeAsync(1000);

    await expect(call).resolves.toBeNull();
    expect(cancelRequest).toHaveBeenCalledWith('req-1');
    expect(setErrorMessage).toHaveBeenCalledWith('Opening timed out after 1 seconds');
  });

  it('cancelActionScope cancels the in-flight request for that scope', () => {
    const { cancelRequest } = installVera(async () => deferred().promise);
    const dispatchBackgroundTask = vi.fn();
    const caller = createSidecarCaller(new Map(), () => ({
      dispatchBackgroundTask,
      setErrorMessage: () => undefined,
      setProviderErrorDetail: () => undefined,
    }));

    void caller.call({ action: 'inspect' }, 'Opening', 'req-1', { timeoutMs: 0 });
    caller.cancelActionScope('inspect');

    expect(cancelRequest).toHaveBeenCalledWith('req-1');
    expect(dispatchBackgroundTask).toHaveBeenCalledWith({ type: 'finish', id: 'req-1' });
  });
});
