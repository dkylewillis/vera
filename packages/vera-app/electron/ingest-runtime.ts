import type { ExternalPythonConfig } from '../src/shared/contracts.js';

export function normalizeExternalPython(raw: unknown): ExternalPythonConfig {
  if (!raw || typeof raw !== 'object') {
    return { enabled: false, executable: '' };
  }
  const value = raw as Record<string, unknown>;
  const executable = typeof value.executable === 'string' ? value.executable.trim() : '';
  const artifacts = typeof value.artifacts_path === 'string' ? value.artifacts_path.trim() : '';
  return {
    enabled: Boolean(value.enabled) && Boolean(executable),
    executable,
    artifacts_path: artifacts || undefined,
    validated_at: typeof value.validated_at === 'number' ? value.validated_at : undefined,
  };
}
