import { AlertTriangle, FolderOpen, RefreshCw } from 'lucide-react';
import type { ExternalPythonConfig, PythonEnvironmentProbe } from '../types';

export function PythonEnvironmentManager({
  config,
  status,
  busy,
  onConfigChange,
  onPick,
  onValidate,
  onRefresh,
}: {
  config: ExternalPythonConfig;
  status: PythonEnvironmentProbe | null;
  busy: boolean;
  onConfigChange: (next: ExternalPythonConfig) => void;
  onPick: () => void;
  onValidate: () => void;
  onRefresh: () => void;
}) {
  const executable = config.executable;
  return (
    <section className="pythonEnvManager">
      <h3>External Python plugins</h3>
      <p className="providerItemDescription">
        Advanced / trusted plugins. The selected interpreter can run arbitrary local code
        with your permissions. Install plugins with
        {' '}<code>python -m pip install …</code> or
        {' '}<code>python -m pip install -e &lt;clone&gt;</code>.
        Raw <code>PYTHONPATH</code> folders are not discovered.
      </p>
      <label className="miniCheck">
        <input
          type="checkbox"
          checked={config.enabled}
          onChange={(event) => onConfigChange({ ...config, enabled: event.target.checked })}
          disabled={busy}
        />
        <span>Use an external Python environment for extra ingest plugins</span>
      </label>
      <label className="field">
        <span>Python interpreter</span>
        <div className="pathInput">
          <input
            value={executable}
            onChange={(event) => onConfigChange({ ...config, executable: event.target.value })}
            placeholder={typeof window !== 'undefined' && window.vera?.platform === 'win32'
              ? 'C:\\venvs\\vera-plugins\\Scripts\\python.exe'
              : '/path/to/venv/bin/python'}
            disabled={busy}
          />
          <button type="button" className="secondaryAction compactAction" onClick={onPick} disabled={busy}>
            <FolderOpen size={14} />Browse
          </button>
        </div>
      </label>
      <label className="field">
        <span>Model cache (optional)</span>
        <input
          value={config.artifacts_path || ''}
          onChange={(event) => onConfigChange({ ...config, artifacts_path: event.target.value })}
          placeholder="DOCLING_ARTIFACTS_PATH"
          disabled={busy}
        />
      </label>
      <div className="editorActions">
        <button type="button" className="secondaryAction" onClick={onValidate} disabled={busy || !executable.trim()}>
          <RefreshCw size={14} className={busy ? 'spinning' : undefined} />
          Validate
        </button>
        <button type="button" className="secondaryAction" onClick={onRefresh} disabled={busy || !config.enabled || !executable.trim()}>
          Refresh plugins
        </button>
      </div>
      {busy ? (
        <p className="sideMuted" role="status">Checking the Python environment…</p>
      ) : status ? (
        <div className={status.ok ? 'pythonEnvStatus ok' : 'pythonEnvStatus error'} role="status">
          {!status.ok ? <AlertTriangle size={14} /> : null}
          <div>
            {status.ok ? (
              <>
                <strong>Ready</strong>
                <span>
                  Python {status.python_version || '?'} · vera-ingest {status.vera_ingest_version || '?'}
                </span>
                <span>
                  {(status.pipelines || []).length
                    ? `Plugins: ${(status.pipelines || []).map((item) => item.spec || item.provider).join(', ')}`
                    : 'No extra ingest plugins found in this environment.'}
                </span>
              </>
            ) : (
              <span>{status.error || 'External Python is not available.'}</span>
            )}
            {(status.load_errors || []).map((entry) => (
              <span key={entry}>{entry}</span>
            ))}
          </div>
        </div>
      ) : (
        <p className="sideMuted">Validate the interpreter after installing plugins.</p>
      )}
    </section>
  );
}
