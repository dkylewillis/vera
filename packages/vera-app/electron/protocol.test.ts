import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import {
  IPC_CHANNELS,
  PLUGIN_API_VERSION,
  PLUGIN_HOST_PROTOCOL,
  SIDECAR_ACTIONS,
} from '../src/shared/protocol.js';

const here = dirname(fileURLToPath(import.meta.url));
const preload = readFileSync(join(here, 'preload.cts'), 'utf8');

describe('plugin host protocol contract', () => {
  it('keeps IPC channel names stable', () => {
    expect(IPC_CHANNELS.pickPythonInterpreter).toBe('vera:pickPythonInterpreter');
    expect(IPC_CHANNELS.validatePythonEnvironment).toBe('vera:validatePythonEnvironment');
    expect(IPC_CHANNELS.refreshExternalPipelines).toBe('vera:refreshExternalPipelines');
    expect(IPC_CHANNELS.skipConversion).toBe('vera:skipConversion');
    expect(SIDECAR_ACTIONS.describeIngestPipelines).toBe('describe_ingest_pipelines');
    expect(PLUGIN_HOST_PROTOCOL).toBe(1);
    expect(PLUGIN_API_VERSION).toBe(1);
  });

  it('exposes the new IPC methods on the preload bridge', () => {
    for (const channel of Object.values(IPC_CHANNELS)) {
      expect(preload).toContain(channel);
    }
  });
});
