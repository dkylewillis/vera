import { useState } from 'react';
import { AlertTriangle, FolderOpen, KeyRound, RefreshCw, Trash2 } from 'lucide-react';
import type { ExternalPythonConfig, PythonEnvironmentProbe } from '../types';

function credentialEnvNames(status: PythonEnvironmentProbe | null): string[] {
  const names = new Set<string>();
  for (const item of status?.embedders || []) {
    const env = item.capabilities?.credential_env?.trim();
    if (env) names.add(env);
  }
  return [...names].sort();
}

export function PythonEnvironmentManager({
  config,
  status,
  busy,
  hasEnvSecrets = {},
  onConfigChange,
  onPick,
  onValidate,
  onRefresh,
  onSecretsChange,
}: {
  config: ExternalPythonConfig;
  status: PythonEnvironmentProbe | null;
  busy: boolean;
  hasEnvSecrets?: Record<string, boolean>;
  onConfigChange: (next: ExternalPythonConfig) => void;
  onPick: () => void;
  onValidate: () => void;
  onRefresh: () => void;
  onSecretsChange?: () => Promise<unknown> | void;
}) {
  const executable = config.executable;
  const credentialNames = credentialEnvNames(status);
  const [secretInputs, setSecretInputs] = useState<Record<string, string>>({});
  const [secretBusy, setSecretBusy] = useState('');

  async function saveSecret(name: string) {
    const value = (secretInputs[name] ?? '').trim();
    if (!value) return;
    setSecretBusy(name);
    try {
      const result = await window.vera.saveEnvSecret(name, value);
      if (result.ok) {
        setSecretInputs((prev) => ({ ...prev, [name]: '' }));
        await onSecretsChange?.();
      }
    } finally {
      setSecretBusy('');
    }
  }

  async function clearSecret(name: string) {
    setSecretBusy(name);
    try {
      await window.vera.clearEnvSecret(name);
      setSecretInputs((prev) => ({ ...prev, [name]: '' }));
      await onSecretsChange?.();
    } finally {
      setSecretBusy('');
    }
  }

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
        <span>Use an external Python environment for extra ingest and embedding plugins</span>
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
                  {status.vera_doc_version ? ` · vera-doc ${status.vera_doc_version}` : ''}
                </span>
                <span>
                  {(status.pipelines || []).length
                    ? `Parsers: ${(status.pipelines || []).map((item) => item.spec || item.provider).join(', ')}`
                    : 'No extra ingest plugins found in this environment.'}
                </span>
                <span>
                  {(status.embedders || []).length
                    ? `Embedders: ${(status.embedders || []).map((item) => item.provider).join(', ')}`
                    : 'No extra embedding plugins found in this environment.'}
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
      {credentialNames.length ? (
        <div className="pythonEnvSecrets">
          <p className="providerItemDescription">
            Embedder credentials advertised as <code>credential_env</code>. Stored
            securely like provider API keys and forwarded to the sidecar and plugin host.
          </p>
          {credentialNames.map((name) => {
            const stored = Boolean(hasEnvSecrets[name]);
            const typed = secretInputs[name] ?? '';
            return (
              <label className="field" key={name}>
                <span>{name}</span>
                {stored && !typed ? (
                  <div className="editorActions">
                    <span className="connectedTag">Saved</span>
                    <button
                      type="button"
                      className="secondaryAction compactAction"
                      onClick={() => void clearSecret(name)}
                      disabled={busy || secretBusy === name}
                    >
                      <Trash2 size={13} />Clear
                    </button>
                  </div>
                ) : (
                  <div className="pathInput">
                    <input
                      type="password"
                      value={typed}
                      onChange={(event) => setSecretInputs((prev) => ({ ...prev, [name]: event.target.value }))}
                      placeholder={`Paste ${name}`}
                      autoComplete="off"
                      disabled={busy || secretBusy === name}
                    />
                    {typed.trim() ? (
                      <button
                        type="button"
                        className="secondaryAction compactAction"
                        onClick={() => void saveSecret(name)}
                        disabled={busy || secretBusy === name}
                      >
                        <KeyRound size={13} />Save
                      </button>
                    ) : null}
                  </div>
                )}
              </label>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
