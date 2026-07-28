import { useState } from 'react';
import {
  CheckCircle2,
  KeyRound,
  ListChecks,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Settings,
  Trash2,
  X,
} from 'lucide-react';
import type { AppSettings, ProviderProfile } from '../types';
import {
  emptyProvider,
  filterDiscoveredModels,
  newProviderId,
  PROVIDER_PRESETS,
  providerDisplayName,
  providerPresetFor,
  providerTypeLabel,
  type ProviderPreset,
  withPresetModels,
} from '../lib/providers';

export function ModelManager({
  providers,
  busyProviderId,
  message,
  onToggle,
  onRefresh,
  onAddProvider,
  onClose,
}: {
  providers: ProviderProfile[];
  busyProviderId: string;
  message: string;
  onToggle: (providerId: string, model: string) => void;
  onRefresh: (providerId: string) => void;
  onAddProvider: () => void;
  onClose: () => void;
}) {
  const [filter, setFilter] = useState('');
  const normalizedFilter = filter.trim().toLowerCase();

  return (
    <div className="modalBackdrop" onClick={onClose}>
      <div className="modal modelManagerModal" onClick={(event) => event.stopPropagation()}>
        <header className="modalHeader">
          <h2><ListChecks size={18} />Models</h2>
          <button className="iconAction" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </header>
        <div className="modelManagerSearch">
          <Search size={14} />
          <input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Search models" autoFocus />
        </div>
        <div className="modelManagerBody">
          {providers.length === 0 ? <p className="mutedText">Add a provider to discover models.</p> : null}
          {providers.map((profile) => {
            const models = Array.from(new Set([...(profile.available_models ?? []), ...profile.models]))
              .filter((model) => !normalizedFilter || model.toLowerCase().includes(normalizedFilter))
              .sort((a, b) => a.localeCompare(b));
            return (
              <section className="modelManagerGroup" key={profile.id}>
                <div className="modelManagerGroupHead">
                  <span>{providerDisplayName(profile)}</span>
                  <button
                    type="button"
                    className="ghostIcon tiny visible"
                    onClick={() => onRefresh(profile.id)}
                    disabled={Boolean(busyProviderId)}
                    title="Refresh models"
                  >
                    <RefreshCw size={13} className={busyProviderId === profile.id ? 'spinning' : ''} />
                  </button>
                </div>
                {models.length ? models.map((model) => (
                  <label className="modelManagerRow" key={`${profile.id}:${model}`}>
                    <span>{model}</span>
                    <input
                      type="checkbox"
                      checked={profile.models.includes(model)}
                      onChange={() => onToggle(profile.id, model)}
                      aria-label={`Enable ${model}`}
                    />
                  </label>
                )) : (
                  <p className="modelManagerEmpty">{normalizedFilter ? 'No matching models.' : 'Refresh to discover models.'}</p>
                )}
              </section>
            );
          })}
        </div>
        <footer className="modalFooter">
          <button className="modelManagerAdd" onClick={onAddProvider}><Plus size={14} />Add provider…</button>
          <span className="modalMessage">{message}</span>
        </footer>
      </div>
    </div>
  );
}

export function ProviderManager({
  providers,
  activeProviderId,
  activeModel,
  activeModeId,
  onPersist,
  onRefresh,
  onClose,
}: {
  providers: ProviderProfile[];
  activeProviderId: string;
  activeModel: string;
  activeModeId: string;
  onPersist: (next: AppSettings) => Promise<AppSettings>;
  onRefresh: () => Promise<AppSettings>;
  onClose: () => void;
}) {
  const [list, setList] = useState<ProviderProfile[]>(() => providers.map(withPresetModels));
  const [activeId, setActiveId] = useState(activeProviderId);
  const [activeModelLocal, setActiveModelLocal] = useState(activeModel);
  const [selectedId, setSelectedId] = useState<string>(providers[0]?.id ?? '');
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [modelInput, setModelInput] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [availableModels, setAvailableModels] = useState<string[]>([]);

  const selected = list.find((profile) => profile.id === selectedId) ?? null;
  const selectedPreset = selected ? providerPresetFor(selected) : null;
  const enabledModels = new Set(selected?.models ?? []);
  const modelOptions = Array.from(new Set([
    ...(selected?.models ?? []),
    ...(selected?.available_models ?? []),
    ...availableModels,
  ])).sort((a, b) =>
    a.localeCompare(b),
  );

  function settingsPayload(overrides?: Partial<AppSettings>): AppSettings {
    const nextList = overrides?.providers ?? list;
    const nextActiveId = overrides?.active_provider_id ?? activeId;
    const activeProfile = nextList.find((profile) => profile.id === nextActiveId);
    const requestedModel = overrides?.active_model ?? activeModelLocal;
    const nextActiveModel =
      activeProfile && activeProfile.models.includes(requestedModel)
        ? requestedModel
        : activeProfile?.models[0] ?? '';
    return {
      providers: nextList,
      active_provider_id: activeProfile ? nextActiveId : '',
      active_model: nextActiveModel,
      active_mode_id: overrides?.active_mode_id ?? activeModeId,
    };
  }

  function updateSelected(patch: Partial<ProviderProfile>) {
    setList((prev) => prev.map((profile) => (profile.id === selectedId ? { ...profile, ...patch } : profile)));
  }

  function toggleModel(model: string) {
    if (!selected) return;
    const next = enabledModels.has(model)
      ? selected.models.filter((value) => value !== model)
      : [...selected.models, model];
    updateSelected({ models: next });
  }

  function addManualModel() {
    const model = modelInput.trim();
    if (!selected || !model) return;
    if (!selected.models.includes(model)) {
      updateSelected({ models: [...selected.models, model] });
    }
    setModelInput('');
    setMessage(`Added model ${model}`);
  }

  function addProvider(preset?: ProviderPreset) {
    const profile: ProviderProfile = preset
      ? { ...preset.value, models: [...preset.value.models], preset_key: preset.key, id: newProviderId() }
      : emptyProvider();
    setList((prev) => [...prev, profile]);
    setSelectedId(profile.id);
    setApiKeyInput('');
    setModelInput('');
    setAvailableModels([]);
    setMessage(`Added ${providerDisplayName(profile)}`);
  }

  function deleteProvider(id: string) {
    setList((prev) => prev.filter((profile) => profile.id !== id));
    if (activeId === id) {
      setActiveId('');
      setActiveModelLocal('');
    }
    if (selectedId === id) setSelectedId('');
    setMessage('Provider removed (Save to apply)');
  }

  function setAsActive(profile: ProviderProfile) {
    if (activeId === profile.id) {
      setActiveId('');
      setActiveModelLocal('');
      return;
    }
    setActiveId(profile.id);
    setActiveModelLocal(profile.models[0] ?? '');
  }

  async function saveAll(close: boolean) {
    setBusy(true);
    try {
      const saved = await onPersist(settingsPayload());
      setList(saved.providers);
      setActiveId(saved.active_provider_id);
      setActiveModelLocal(saved.active_model || '');
      setMessage('Settings saved');
      if (close) onClose();
    } finally {
      setBusy(false);
    }
  }

  async function saveKey() {
    if (!selected) return;
    if (!apiKeyInput.trim()) {
      setMessage('Enter an API key first');
      return;
    }
    setBusy(true);
    try {
      await onPersist(settingsPayload());
      const result = await window.vera.saveApiKey(selected.base_url, apiKeyInput.trim());
      if (!result.ok) {
        setMessage(result.error || 'Unable to save API key');
        return;
      }
      setApiKeyInput('');
      const refreshed = await onRefresh();
      setList(refreshed.providers);
      setMessage('API key saved');
    } finally {
      setBusy(false);
    }
  }

  async function clearKey() {
    if (!selected) return;
    setBusy(true);
    try {
      await window.vera.clearApiKey(selected.base_url);
      const refreshed = await onRefresh();
      setList(refreshed.providers);
      setMessage('API key cleared');
    } finally {
      setBusy(false);
    }
  }

  async function fetchModels() {
    if (!selected) return;
    if (!selected.base_url.trim()) {
      setMessage('Set a base URL first');
      return;
    }
    setBusy(true);
    setMessage('Fetching models…');
    try {
      const llm: Record<string, unknown> = {
        provider: selected.provider,
        base_url: selected.base_url,
        api_key_env: selected.api_key_env,
        auth_type: selected.auth_type,
      };
      // Use the just-typed key if present so fetch works before saving.
      if (apiKeyInput.trim()) llm.api_key = apiKeyInput.trim();
      const response = await window.vera.request<{ models: string[] }>({ action: 'list_models', llm });
      if (!response.ok) {
        setAvailableModels([]);
        setMessage(response.error || 'Unable to fetch models');
        return;
      }
      const models = filterDiscoveredModels(selected, response.result?.models ?? []);
      setAvailableModels(models);
      updateSelected({
        available_models: models,
        models_refreshed_at: Date.now(),
        models: selected.models.length === 0 ? models : selected.models,
      });
      setMessage(models.length ? `Found ${models.length} models` : 'No models returned');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modalBackdrop" onClick={onClose}>
      <div className="modal providerModal" onClick={(event) => event.stopPropagation()}>
        <header className="modalHeader">
          <h2><Settings size={18} />LLM Providers</h2>
          <button className="iconAction" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </header>

        <div className="providerLayout">
          <aside className="providerList">
            <div className="providerListHead">
              <span>Providers</span>
              <button className="secondaryAction compactAction" onClick={() => addProvider()} disabled={busy}><Plus size={14} />Custom</button>
            </div>
            {list.length === 0 ? <p className="mutedText">No providers configured yet.</p> : null}
            {list.map((profile) => (
              <button
                key={profile.id}
                type="button"
                className={profile.id === selectedId ? 'providerRow selected' : 'providerRow'}
                onClick={() => { setSelectedId(profile.id); setApiKeyInput(''); setModelInput(''); setAvailableModels([]); }}
              >
                <span className="providerRowName">
                  {providerDisplayName(profile)}
                  {profile.id === activeId ? <em className="activeTag">Active</em> : null}
                </span>
                <small>{providerTypeLabel(profile.provider)} · {profile.models.length} model{profile.models.length === 1 ? '' : 's'}</small>
              </button>
            ))}
            <div className="presetRow">
              <span>Add provider</span>
              <div className="presetButtons">
                {PROVIDER_PRESETS.map((preset) => (
                  <button key={preset.key} type="button" className="secondaryAction compactAction" onClick={() => addProvider(preset)} disabled={busy}>{preset.label}</button>
                ))}
              </div>
            </div>
          </aside>

          <section className="providerEditor">
            {selected ? (
              <>
                <div className="providerEditorIntro">
                  <div>
                    <h3>{providerDisplayName(selected)}</h3>
                    <p>{selectedPreset?.description ?? 'Connect any service with an OpenAI-compatible API.'}</p>
                  </div>
                  {selected.has_api_key ? <span className="connectedTag"><CheckCircle2 size={13} />Key saved</span> : null}
                </div>

                {selected.auth_type === 'api_key' ? <div className="apiKeyRow">
                  <label className="field apiKeyField">
                    <span>API Key</span>
                    <input type="password" value={apiKeyInput} onChange={(event) => setApiKeyInput(event.target.value)} placeholder={selected.has_api_key ? '•••••••• stored securely' : `Paste ${providerDisplayName(selected)} key`} />
                  </label>
                  <button className="secondaryAction" onClick={saveKey} disabled={busy || !apiKeyInput.trim()}><KeyRound size={16} />Save Key</button>
                  <button className="secondaryAction" onClick={clearKey} disabled={busy || !selected.has_api_key}><Trash2 size={16} />Clear</button>
                </div> : null}

                {selectedPreset?.kind === 'local' ? (
                  <label className="field">
                    <span>Server URL</span>
                    <input value={selected.base_url} onChange={(event) => updateSelected({ base_url: event.target.value })} placeholder={selectedPreset.value.base_url} />
                  </label>
                ) : null}

                <div className="modelsSection">
                  <div className="modelsHead">
                    <span>Models <em>{selected.models.length} enabled</em></span>
                    <button type="button" className="secondaryAction compactAction" onClick={fetchModels} disabled={busy || !selected.base_url.trim()}><ListChecks size={14} />Refresh models</button>
                  </div>
                  {modelOptions.length ? (
                    <div className="modelChecklist">
                      {modelOptions.map((model) => (
                        <label className="modelCheck" key={model}>
                          <input type="checkbox" checked={enabledModels.has(model)} onChange={() => toggleModel(model)} />
                          <span>{model}</span>
                        </label>
                      ))}
                    </div>
                  ) : (
                    <p className="mutedText">No models found yet. Refresh the provider or add a model ID.</p>
                  )}
                  <div className="modelAddRow">
                    <input
                      value={modelInput}
                      onChange={(event) => setModelInput(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') {
                          event.preventDefault();
                          addManualModel();
                        }
                      }}
                      placeholder="Add model id manually (e.g. gpt-4o-mini)"
                    />
                    <button type="button" className="secondaryAction compactAction" onClick={addManualModel} disabled={!modelInput.trim()}><Plus size={14} />Add</button>
                  </div>
                </div>

                {selectedPreset ? (
                  <details className="providerAdvanced">
                    <summary>Advanced</summary>
                    <div className="editorGrid">
                      <label className="field">
                        <span>Display Name</span>
                        <input value={selected.label} onChange={(event) => updateSelected({ label: event.target.value })} />
                      </label>
                      {selectedPreset.kind === 'hosted' ? (
                        <label className="field">
                          <span>Base URL override</span>
                          <input value={selected.base_url} onChange={(event) => updateSelected({ base_url: event.target.value })} placeholder={selectedPreset.value.base_url} />
                        </label>
                      ) : null}
                      <label className="field">
                        <span>Temperature</span>
                        <input className="numberInput" type="number" min={0} max={2} step={0.1} value={selected.temperature} onChange={(event) => updateSelected({ temperature: Number(event.target.value) })} />
                      </label>
                    </div>
                  </details>
                ) : (
                  <div className="customProviderFields">
                    <div className="editorGrid">
                      <label className="field">
                        <span>Display Name</span>
                        <input value={selected.label} onChange={(event) => updateSelected({ label: event.target.value })} placeholder="My Provider" />
                      </label>
                      <label className="field">
                        <span>Type</span>
                        <select value={selected.provider} onChange={(event) => updateSelected({ provider: event.target.value })}>
                          <option value="openai_compatible">OpenAI Compatible</option>
                          <option value="ollama">Ollama</option>
                          <option value="lmstudio">LM Studio</option>
                        </select>
                      </label>
                      <label className="field wideField">
                        <span>Base URL</span>
                        <input value={selected.base_url} onChange={(event) => updateSelected({ base_url: event.target.value })} placeholder="https://api.example.com/v1" />
                      </label>
                      <label className="field">
                        <span>Authentication</span>
                        <select value={selected.auth_type} onChange={(event) => updateSelected({ auth_type: event.target.value })}>
                          <option value="none">None</option>
                          <option value="api_key">API Key</option>
                          <option value="env">Environment variable</option>
                        </select>
                      </label>
                      <label className="field">
                        <span>API environment variable</span>
                        <input value={selected.api_key_env} onChange={(event) => updateSelected({ api_key_env: event.target.value })} placeholder="PROVIDER_API_KEY" />
                      </label>
                      <label className="field">
                        <span>Temperature</span>
                        <input className="numberInput" type="number" min={0} max={2} step={0.1} value={selected.temperature} onChange={(event) => updateSelected({ temperature: Number(event.target.value) })} />
                      </label>
                    </div>
                  </div>
                )}

                <div className="editorActions">
                  <button
                    className={selected.id === activeId ? 'secondaryAction activeNow' : 'secondaryAction'}
                    onClick={() => setAsActive(selected)}
                    disabled={busy || selected.models.length === 0}
                  >
                    <CheckCircle2 size={16} />{selected.id === activeId ? 'Active provider' : 'Set as active'}
                  </button>
                  <button className="secondaryAction danger" onClick={() => deleteProvider(selected.id)} disabled={busy}><Trash2 size={16} />Delete</button>
                </div>
              </>
            ) : (
              <div className="emptyState"><Pencil size={20} />Select a provider to edit, or add a new one.</div>
            )}
          </section>
        </div>

        <footer className="modalFooter">
          <span className="modalMessage">{message}</span>
          <div className="modalFooterActions">
            <button className="secondaryAction" onClick={onClose} disabled={busy}>Cancel</button>
            <button className="primaryAction" onClick={() => void saveAll(true)} disabled={busy}>Save &amp; Close</button>
          </div>
        </footer>
      </div>
    </div>
  );
}
