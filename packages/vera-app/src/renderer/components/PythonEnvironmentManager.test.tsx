import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { PythonEnvironmentManager } from './PythonEnvironmentManager';
import type { ExternalPythonConfig, PythonEnvironmentProbe } from '../types';

const config: ExternalPythonConfig = {
  enabled: true,
  executable: '/tmp/venv/bin/python',
};

describe('PythonEnvironmentManager', () => {
  it('shows a trusted-code warning and pip install instructions', () => {
    const html = renderToStaticMarkup(
      <PythonEnvironmentManager
        config={config}
        status={null}
        busy={false}
        onConfigChange={() => undefined}
        onPick={() => undefined}
        onValidate={() => undefined}
        onRefresh={() => undefined}
      />,
    );
    expect(html).toContain('trusted');
    expect(html).toContain('python -m pip install');
    expect(html).toContain('pip install -e');
    expect(html).toContain('PYTHONPATH');
  });

  it('renders ready status and discovered plugins', () => {
    const status: PythonEnvironmentProbe = {
      ok: true,
      python_version: '3.12.3',
      vera_ingest_version: '0.3.0',
      pipelines: [{
        provider: 'docling',
        variant: 'hybrid',
        spec: 'docling',
        label: 'docling',
        description: '',
        installed: true,
        capabilities: {},
        fields: [],
        source: 'external',
      }],
    };
    const html = renderToStaticMarkup(
      <PythonEnvironmentManager
        config={config}
        status={status}
        busy={false}
        onConfigChange={() => undefined}
        onPick={() => undefined}
        onValidate={() => undefined}
        onRefresh={() => undefined}
      />,
    );
    expect(html).toContain('Ready');
    expect(html).toContain('Python 3.12.3');
    expect(html).toContain('vera-ingest 0.3.0');
    expect(html).toContain('docling');
  });

  it('renders compatibility errors', () => {
    const html = renderToStaticMarkup(
      <PythonEnvironmentManager
        config={config}
        status={{ ok: false, error: 'vera-ingest 0.2.5 is not compatible with this app (requires 0.3.x).' }}
        busy={false}
        onConfigChange={() => undefined}
        onPick={() => undefined}
        onValidate={() => undefined}
        onRefresh={() => undefined}
      />,
    );
    expect(html).toContain('not compatible');
  });
});
