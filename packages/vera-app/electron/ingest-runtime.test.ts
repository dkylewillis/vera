import { describe, expect, it } from 'vitest';
import { normalizeExternalPython } from './ingest-runtime.js';

describe('normalizeExternalPython', () => {
  it('normalizes external Python settings and disables empty interpreters', () => {
    expect(normalizeExternalPython(null)).toEqual({ enabled: false, executable: '' });
    expect(normalizeExternalPython({
      enabled: true,
      executable: '  C:\\venvs\\plugins\\Scripts\\python.exe  ',
      artifacts_path: '  D:\\models  ',
      validated_at: 42,
    })).toEqual({
      enabled: true,
      executable: 'C:\\venvs\\plugins\\Scripts\\python.exe',
      artifacts_path: 'D:\\models',
      validated_at: 42,
    });
    expect(normalizeExternalPython({ enabled: true, executable: '   ' }).enabled).toBe(false);
  });
});
