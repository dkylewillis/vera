import { describe, expect, it, vi } from 'vitest';
import { awaitConversionRequest } from './conversion';

describe('awaitConversionRequest', () => {
  it('settles the active request before follow-up work starts', async () => {
    const events: string[] = [];

    const result = await awaitConversionRequest(
      Promise.resolve('converted'),
      () => events.push('request settled'),
    );
    events.push('refresh library');

    expect(result).toBe('converted');
    expect(events).toEqual(['request settled', 'refresh library']);
  });

  it('settles the active request when the sidecar rejects', async () => {
    const onSettled = vi.fn();

    await expect(
      awaitConversionRequest(Promise.reject(new Error('sidecar exited')), onSettled),
    ).rejects.toThrow('sidecar exited');

    expect(onSettled).toHaveBeenCalledOnce();
  });
});
