import { describe, expect, it } from 'vitest';

import { parseSidecarJsonLine } from './sidecar-json.js';

describe('parseSidecarJsonLine', () => {
  it('parses a response line', () => {
    expect(parseSidecarJsonLine('{"id":"1","ok":true,"result":{"pages":3}}')).toEqual({
      ok: true,
      payload: { id: '1', ok: true, result: { pages: 3 } },
    });
  });

  it('parses a streaming event line', () => {
    expect(parseSidecarJsonLine('{"id":"1","event":"answer_delta","text":"hello"}')).toEqual({
      ok: true,
      payload: { id: '1', event: 'answer_delta', text: 'hello' },
    });
  });

  it('rejects malformed JSON', () => {
    const result = parseSidecarJsonLine('{"id":');
    expect(result.ok).toBe(false);
  });

  it.each(['null', '"message"', '42', 'true', '[]'])('rejects non-object JSON: %s', (line) => {
    expect(parseSidecarJsonLine(line)).toEqual({
      ok: false,
      error: 'payload must be a non-null JSON object',
    });
  });
});
