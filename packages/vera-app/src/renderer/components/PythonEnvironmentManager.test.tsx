import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { PythonEnvironmentManager } from './PythonEnvironmentManager';
import type { ExternalPythonConfig, PythonEnvironmentProbe } from '../types';

const idle: ExternalPythonConfig = { enabled: false, executable: '' };
const configured: ExternalPythonConfig = {
  enabled: true,
  executable: '/home/user/vera-plugins/bin/python',
};

function renderManager(options: {
  config?: ExternalPythonConfig;
  status?: PythonEnvironmentProbe | null;
  busy?: boolean;
} = {}) {
  (globalThis as unknown as { window: { vera: { platform: string } } }).window = {
    vera: { platform: 'linux' },
  };
  return renderToStaticMarkup(
    <PythonEnvironmentManager
      config={options.config || idle}
      status={options.status ?? null}
      busy={Boolean(options.busy)}
      onConfigChange={() => {}}
      onPick={() => {}}
      onValidate={() => {}}
      onRefresh={() => {}}
    />,
  );
}

describe('PythonEnvironmentManager', () => {
  it('warns that the interpreter is trusted local code', () => {
    const html = renderManager();
    expect(html).toContain('trusted');
    expect(html).toContain('pip install -e');
    expect(html).toContain('PYTHONPATH');
  });

  it('disables validate and refresh until an interpreter is chosen', () => {
    const html = renderManager();
    expect(html).toMatch(/Validate<\/button>/);
    expect(html).toContain('disabled=""');
    expect(html).toContain('Validate the interpreter after installing plugins.');
  });

  it('shows ready plugin status after a successful probe', () => {
    const html = renderManager({
      config: configured,
      status: {
        ok: true,
        executable: configured.executable,
        python_version: '3.12.3',
        vera_ingest_version: '0.2.5',
        pipelines: [{ provider: 'docling', spec: 'docling', installed: true, source: 'external' }],
      },
    });
    expect(html).toContain('Ready');
    expect(html).toContain('Plugins: docling');
    expect(html).toContain('vera-ingest 0.2.5');
  });

  it('shows compatibility errors from a failed probe', () => {
    const html = renderManager({
      config: configured,
      status: {
        ok: false,
        executable: configured.executable,
        error: 'vera-ingest 0.3.0 is not compatible with this app (requires 0.2.x).',
        load_errors: ['Failed to load ingest pipeline plugin \'broken\': ImportError()'],
      },
    });
    expect(html).toContain('not compatible');
    expect(html).toContain('broken');
  });
});
