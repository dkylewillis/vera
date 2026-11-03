import { describe, expect, it } from 'vitest';
import { encodeFrame, takeFrame } from './relay-socket.js';

describe('relay frames', () => {
  it('round-trips a frame larger than 64 KB', () => {
    const payload = Buffer.alloc(200 * 1024, 0x61);
    const encoded = encodeFrame(0x1, payload, true);
    expect(encoded[1]! & 0x7f).toBe(127);
    const decoded = takeFrame(encoded);
    expect(decoded?.frame.opcode).toBe(0x1);
    expect(decoded?.frame.fin).toBe(true);
    expect(Buffer.compare(decoded!.frame.payload, payload)).toBe(0);
    expect(decoded?.rest.byteLength).toBe(0);
  });
});
