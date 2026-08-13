import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { IPC_CHANNELS, SIDECAR_ACTIONS, STREAM_EVENTS } from '../src/shared/protocol.js';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function pythonTuple(name: string, source: string): string[] {
  const match = source.match(new RegExp(`${name} = \\(([\\s\\S]*?)\\n\\)`));
  if (!match) {
    throw new Error(`Could not find ${name} in Python protocol`);
  }
  return [...match[1].matchAll(/"([^"]+)"/g)].map((item) => item[1]);
}

/**
 * Electron's sandboxed preload can't `require()` protocol.ts's compiled
 * output (see preload.cts), so it duplicates IPC_CHANNELS as an object
 * literal. Parse that literal back out of the source text to guard against
 * drift instead of trusting the "keep in sync" comment alone.
 */
function preloadIpcChannels(source: string): Record<string, string> {
  const match = source.match(/const IPC_CHANNELS[^=]*=\s*\{([\s\S]*?)\n\};/);
  if (!match) {
    throw new Error('Could not find IPC_CHANNELS literal in preload.cts');
  }
  const entries = [...match[1].matchAll(/(\w+):\s*'([^']+)'/g)];
  return Object.fromEntries(entries.map(([, key, value]) => [key, value]));
}

describe('sidecar protocol contract', () => {
  const pythonProtocol = readFileSync(join(root, 'src/vera_app/protocol.py'), 'utf8');
  const sidecar = readFileSync(join(root, 'src/vera_app/sidecar.py'), 'utf8');
  const preload = readFileSync(join(root, 'electron/preload.cts'), 'utf8');

  it('keeps TypeScript STREAM_EVENTS aligned with Python', () => {
    expect([...STREAM_EVENTS]).toEqual(pythonTuple('STREAM_EVENTS', pythonProtocol));
  });

  it('keeps TypeScript SIDECAR_ACTIONS aligned with Python', () => {
    expect(Object.values(SIDECAR_ACTIONS)).toEqual(pythonTuple('SIDECAR_ACTIONS', pythonProtocol));
  });

  it('only emits StreamEvent names declared in the shared contract', () => {
    const emitted = [...sidecar.matchAll(/"event": "([a-z_]+)"/g)].map((item) => item[1]);
    expect(emitted.length).toBeGreaterThan(0);
    expect(new Set(emitted)).toEqual(new Set(STREAM_EVENTS));
  });

  it('keeps preload.cts IPC_CHANNELS duplicate aligned with the shared contract', () => {
    expect(preloadIpcChannels(preload)).toEqual(IPC_CHANNELS);
  });
});
