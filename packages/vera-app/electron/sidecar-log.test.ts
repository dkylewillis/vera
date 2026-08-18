import { afterEach, describe, expect, it, vi } from 'vitest';

import { logSidecarStderr, sidecarStderrLines } from './sidecar-log.js';

describe('sidecarStderrLines', () => {
  it('turns tqdm carriage returns into separate lines', () => {
    expect(
      sidecarStderrLines('Fetching 5 files:  20%\rFetching 5 files:  80%\rFetching 5 files: 100%\n'),
    ).toEqual([
      'Fetching 5 files:  20%',
      'Fetching 5 files:  80%',
      'Fetching 5 files: 100%',
    ]);
  });

  it('drops empty fragments', () => {
    expect(sidecarStderrLines('\n\r  \r\nhello\n')).toEqual(['hello']);
  });
});

describe('logSidecarStderr', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('prefixes each progress line', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    logSidecarStderr('vera-sidecar', 'a\rb\n');
    expect(error.mock.calls).toEqual([
      ['[vera-sidecar] a'],
      ['[vera-sidecar] b'],
    ]);
  });
});
