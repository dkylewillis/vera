import { useEffect, useState } from 'react';
import { FolderOpen, Package, Terminal, Upload } from 'lucide-react';
import type { InstalledPlugin, PluginsListResult } from '../types';
import { Callout, ConfirmButton, SettingsCard, StatusPill } from './SettingsWidgets';

/** One line naming the pipelines a plugin adds, for example "Adds the plans pipeline." */
export function pluginPipelinesLabel(plugin: Pick<InstalledPlugin, 'pipelines'>): string {
  const names = plugin.pipelines;
  if (!names.length) return 'Adds no ingest pipelines.';
  if (names.length === 1) return `Adds the ${names[0]} pipeline.`;
  return `Adds the ${names.slice(0, -1).join(', ')} and ${names[names.length - 1]} pipelines.`;
}

/** Load errors that mention one of this plugin's pipelines. */
export function pluginLoadErrors(plugin: Pick<InstalledPlugin, 'pipelines'>, loadErrors: string[]): string[] {
  return loadErrors.filter((error) => plugin.pipelines.some((name) => error.includes(`'${name}'`)));
}

/** One line naming what the separate Python environment runs, for example "Runs the docling pipeline." */
export function environmentPipelinesLabel(pipelines: string[]): string {
  if (!pipelines.length) return 'It has no pipelines beyond the ones VERA already includes.';
  if (pipelines.length === 1) return `Runs the ${pipelines[0]} pipeline.`;
  return `Runs the ${pipelines.slice(0, -1).join(', ')} and ${pipelines[pipelines.length - 1]} pipelines.`;
}

/** Load errors about the separate Python environment itself. */
export function environmentErrors(loadErrors: string[]): string[] {
  return loadErrors.filter((error) => error.startsWith('Separate Python environment'));
}

export function PluginsSection({ onChanged }: { onChanged: () => void }) {
  const [listing, setListing] = useState<PluginsListResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [warnings, setWarnings] = useState<string[]>([]);

  async function refresh() {
    const response = await window.vera.pluginsList();
    if (response.ok && response.result) setListing(response.result);
    else setMessage(response.error || 'Unable to list plugins.');
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function install() {
    setBusy(true);
    setMessage('');
    setWarnings([]);
    try {
      const response = await window.vera.pluginsInstall();
      if (!response) return;
      if (!response.ok || !response.result) {
        setMessage(response.error || 'Unable to install the plugin.');
        return;
      }
      const installed = response.result;
      setMessage(`Installed ${installed.name} ${installed.version}. ${pluginPipelinesLabel(installed)}`);
      setWarnings(installed.warnings ?? []);
      onChanged();
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  async function remove(plugin: InstalledPlugin) {
    setBusy(true);
    setMessage('');
    setWarnings([]);
    try {
      const response = await window.vera.pluginsRemove(plugin.name);
      if (!response.ok) {
        setMessage(response.error || `Unable to remove ${plugin.name}.`);
        return;
      }
      setMessage(`Removed ${plugin.name}. Library folders set to its pipelines need a new pipeline before they convert again.`);
      onChanged();
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  async function chooseEnvironment() {
    setBusy(true);
    setMessage('');
    setWarnings([]);
    try {
      const response = await window.vera.pluginsChooseEnvironment();
      if (!response) return;
      if (!response.ok || !response.result) {
        setMessage(response.error || 'Unable to use that environment.');
        return;
      }
      setListing(response.result);
      const chosen = response.result.environment;
      setMessage(
        environmentErrors(response.result.load_errors).length
          ? 'VERA could not use that environment.'
          : `Using ${chosen?.python ?? 'that environment'}. ${environmentPipelinesLabel(chosen?.pipelines ?? [])}`,
      );
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  async function clearEnvironment() {
    setBusy(true);
    setMessage('');
    setWarnings([]);
    try {
      const response = await window.vera.pluginsClearEnvironment();
      if (!response.ok || !response.result) {
        setMessage(response.error || 'Unable to stop using that environment.');
        return;
      }
      setListing(response.result);
      setMessage('Stopped using the separate environment. Library folders set to its pipelines need a new pipeline before they convert again.');
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  const plugins = listing?.plugins ?? [];
  const loadErrors = listing?.load_errors ?? [];
  const environment = listing?.environment ?? { python: '', pipelines: [] };
  const environmentProblems = environmentErrors(loadErrors);
  return (
    <div className="settingsStack">
      <Callout title="Plugins add ingest pipelines.">
        <p>
          A plugin is a pure-Python wheel (<code>.whl</code>) that registers a pipeline under
          <code> vera.ingest_pipelines</code>. It can use the libraries VERA already includes, such as PyMuPDF.
          Plugins run with the same access as VERA, so only install ones you trust.
        </p>
      </Callout>
      <SettingsCard
        icon={<Package size={16} />}
        title="Installed plugins"
        badge={<StatusPill tone={plugins.length ? 'good' : 'neutral'}>{plugins.length ? `${plugins.length} installed` : 'None'}</StatusPill>}
        actions={(
          <div className="editorActions">
            <button type="button" className="secondaryAction compactAction" disabled={busy} onClick={() => void install()}>
              <Upload size={14} />Install from file…
            </button>
            <button type="button" className="secondaryAction compactAction" onClick={() => { void window.vera.openPluginsFolder(); }}>
              <FolderOpen size={14} />Open plugins folder
            </button>
          </div>
        )}
      >
        {plugins.length ? (
          <ul className="pluginList">
            {plugins.map((plugin) => {
              const errors = plugin.error ? [plugin.error] : pluginLoadErrors(plugin, loadErrors);
              return (
                <li key={plugin.path} className="pluginRow">
                  <div className="pluginRowText">
                    <strong>{plugin.name}</strong> <span className="sideMuted">{plugin.version}</span>
                    {errors.length ? <StatusPill tone="warn">Did not load</StatusPill> : null}
                    <p className="sideMuted">{plugin.summary ? `${plugin.summary} ` : ''}{pluginPipelinesLabel(plugin)}</p>
                    {errors.map((error) => <p key={error} className="pluginError">{error}</p>)}
                  </div>
                  <ConfirmButton label="Remove" confirmLabel="Click to remove" disabled={busy} onConfirm={() => void remove(plugin)} />
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="sideMuted">No plugins installed. New pipelines appear in Convert and the folder pipeline picker after you install one.</p>
        )}
      </SettingsCard>
      <SettingsCard
        icon={<Terminal size={16} />}
        title="Separate Python environment"
        badge={(
          <StatusPill tone={environmentProblems.length ? 'warn' : environment.python ? 'good' : 'neutral'}>
            {environmentProblems.length ? 'Not working' : environment.python ? 'In use' : 'None'}
          </StatusPill>
        )}
        actions={(
          <div className="editorActions">
            <button type="button" className="secondaryAction compactAction" disabled={busy} onClick={() => void chooseEnvironment()}>
              <FolderOpen size={14} />Choose folder…
            </button>
            {environment.python ? (
              <ConfirmButton label="Stop using" confirmLabel="Click to stop" disabled={busy} onConfirm={() => void clearEnvironment()} />
            ) : null}
          </div>
        )}
      >
        <p className="sideMuted">
          Some pipelines, such as Docling, need libraries VERA does not include. Install VERA and the pipeline in a
          Python environment of your own, for example <code>pip install &quot;vera[docling]&quot;</code>, then choose
          that environment&apos;s folder, such as <code>.venv</code>. Files that use those pipelines are converted
          there, with the same access as VERA. Search stays in VERA.
        </p>
        {environment.python ? (
          <p className="pluginRowText">
            <code>{environment.python}</code>{' '}
            {environmentProblems.length ? null : <span className="sideMuted">{environmentPipelinesLabel(environment.pipelines)}</span>}
          </p>
        ) : null}
        {environmentProblems.map((error) => <p key={error} className="pluginError">{error}</p>)}
      </SettingsCard>
      {message ? <p className="sideMuted" role="status">{message}</p> : null}
      {warnings.length ? (
        <Callout tone="warn" title="The plugin installed with warnings.">
          {warnings.map((warning) => <p key={warning}>{warning}</p>)}
        </Callout>
      ) : null}
    </div>
  );
}
