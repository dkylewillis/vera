import { SIDECAR_ACTIONS } from '../../shared/protocol';
import { useState } from 'react';
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  KeyRound,
  ListChecks,
  Plus,
  RefreshCw,
  Search,
  Settings,
  Trash2,
  X,
} from 'lucide-react';
import type { AppSettings, ProviderProfile } from '../types';
import {
  defaultEnabledModels,
  emptyProvider,
  filterDiscoveredModels,
  newProviderId,
  PROVIDER_PRESETS,
  providerDisplayName,
  providerPresetFor,
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

/** One entry in the flat provider list: a preset (configured or not) or a custom profile. */
type ProviderRowInfo = {
  key: string;
  label: string;
  description: string;
  kind: 'hosted' | 'local' | 'custom';
  preset: ProviderPreset | null;
  profile: ProviderProfile | null;
};

export function ProviderManager({
  providers,
  activeProviderId,
  activeModel,
  activeModeId,
  embeddingModel,
  ingestPipeline,
  ingestPipelineConfigs,
  hasHfToken = false,
  onPersist,
  onRefresh,
  onClose,
}: {
  providers: ProviderProfile[];
  activeProviderId: string;
  activeModel: string;
  activeModeId: string;
  embeddingModel: string;
  ingestPipeline: string;
  ingestPipelineConfigs: AppSettings['ingest_pipeline_configs'];
  hasHfToken?: boolean;
  onPersist: (next: AppSettings) => Promise<AppSettings>;
  onRefresh: () => Promise<AppSettings>;
  onClose: () => void;
}) {
  const [list, setList] = useState<ProviderProfile[]>(() => providers.map(withPresetModels));
  const [activeId, setActiveId] = useState(activeProviderId);
  const [activeModelLocal, setActiveModelLocal] = useState(activeModel);
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [keyInputs, setKeyInputs] = useState<Record<string, string>>({});
  const [hfTokenInput, setHfTokenInput] = useState('');
  const [hfTokenStored, setHfTokenStored] = useState(hasHfToken);
  const [modelInput, setModelInput] = useState('');
  const [modelFilter, setModelFilter] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [availableModels, setAvailableModels] = useState<string[]>([]);

  // Flat Hermes-style row list: hosted presets, local presets, then customs.
  const rows: ProviderRowInfo[] = [];
  const matchedIds = new Set<string>();
  const orderedPresets = [
    ...PROVIDER_PRESETS.filter((preset) => preset.kind === 'hosted'),
    ...PROVIDER_PRESETS.filter((preset) => preset.kind === 'local'),
  ];
  for (const preset of orderedPresets) {
    const profile = list.find((entry) => !matchedIds.has(entry.id) && providerPresetFor(entry)?.key === preset.key) ?? null;
    if (profile) matchedIds.add(profile.id);
    rows.push({
      key: preset.key,
      label: profile ? providerDisplayName(profile) : preset.label,
      description: preset.description,
      kind: preset.kind,
      preset,
      profile,
    });
  }
  for (const profile of list) {
    if (matchedIds.has(profile.id)) continue;
    rows.push({
      key: profile.id,
      label: providerDisplayName(profile),
      description: 'Custom OpenAI-compatible endpoint.',
      kind: 'custom',
      preset: null,
      profile,
    });
  }

  const normalizedModelFilter = modelFilter.trim().toLowerCase();

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
      embedding_model: overrides?.embedding_model ?? embeddingModel,
      ingest_pipeline: overrides?.ingest_pipeline ?? ingestPipeline,
      ingest_pipeline_configs: overrides?.ingest_pipeline_configs ?? ingestPipelineConfigs,
    };
  }

  /** Materialize a draft profile for an unconfigured preset row on first edit. */
  function ensureProfile(row: ProviderRowInfo): { nextList: ProviderProfile[]; profile: ProviderProfile } {
    if (row.profile) return { nextList: list, profile: row.profile };
    const preset = row.preset!;
    const profile: ProviderProfile = {
      ...preset.value,
      models: [...preset.value.models],
      preset_key: preset.key,
      id: newProviderId(),
    };
    return { nextList: [...list, profile], profile };
  }

  function patchProfile(row: ProviderRowInfo, patch: Partial<ProviderProfile>) {
    const { nextList, profile } = ensureProfile(row);
    setList(nextList.map((entry) => (entry.id === profile.id ? { ...entry, ...patch } : entry)));
  }

  function toggleExpanded(rowKey: string) {
    setExpandedKey((prev) => (prev === rowKey ? null : rowKey));
    setModelInput('');
    setModelFilter('');
    setAvailableModels([]);
  }

  function addCustomProvider() {
    const profile = emptyProvider();
    setList((prev) => [...prev, profile]);
    setExpandedKey(profile.id);
    setModelInput('');
    setModelFilter('');
    setAvailableModels([]);
  }

  function removeProfile(row: ProviderRowInfo) {
    const id = row.profile?.id;
    if (!id) return;
    setList((prev) => prev.filter((profile) => profile.id !== id));
    if (activeId === id) {
      setActiveId('');
      setActiveModelLocal('');
    }
    if (expandedKey === row.key) setExpandedKey(null);
    setMessage('Provider removed (Save to apply)');
  }

  function setAsActive(row: ProviderRowInfo) {
    const profile = row.profile;
    if (!profile) return;
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
      setList(saved.providers.map(withPresetModels));
      setActiveId(saved.active_provider_id);
      setActiveModelLocal(saved.active_model || '');
      setMessage('Settings saved');
      if (close) onClose();
    } finally {
      setBusy(false);
    }
  }

  async function saveKey(row: ProviderRowInfo) {
    const token = (keyInputs[row.key] ?? '').trim();
    if (!token) {
      setMessage('Enter an API key first');
      return;
    }
    const { nextList, profile } = ensureProfile(row);
    setList(nextList);
    setBusy(true);
    try {
      await onPersist(settingsPayload({ providers: nextList }));
      const result = await window.vera.saveApiKey(profile.base_url, token);
      if (!result.ok) {
        setMessage(result.error || 'Unable to save API key');
        return;
      }
      setKeyInputs((prev) => ({ ...prev, [row.key]: '' }));
      const refreshed = await onRefresh();
      setList(refreshed.providers.map(withPresetModels));
      setMessage(`${row.label} key saved`);
    } finally {
      setBusy(false);
    }
  }

  async function clearKey(row: ProviderRowInfo) {
    if (!row.profile) return;
    setBusy(true);
    try {
      await window.vera.clearApiKey(row.profile.base_url);
      const refreshed = await onRefresh();
      setList(refreshed.providers.map(withPresetModels));
      setMessage('API key cleared');
    } finally {
      setBusy(false);
    }
  }

  async function saveHfToken() {
    if (!hfTokenInput.trim()) {
      setMessage('Enter a Hugging Face token first');
      return;
    }
    setBusy(true);
    try {
      const result = await window.vera.saveHfToken(hfTokenInput.trim());
      if (!result.ok) {
        setMessage(result.error || 'Unable to save Hugging Face token');
        return;
      }
      setHfTokenInput('');
      const refreshed = await onRefresh();
      setHfTokenStored(Boolean(refreshed.has_hf_token));
      setMessage('Hugging Face token saved');
    } finally {
      setBusy(false);
    }
  }

  async function clearHfToken() {
    setBusy(true);
    try {
      const result = await window.vera.clearHfToken();
      if (!result.ok) {
        setMessage(result.error || 'Unable to clear Hugging Face token');
        return;
      }
      setHfTokenInput('');
      const refreshed = await onRefresh();
      setHfTokenStored(Boolean(refreshed.has_hf_token));
      setMessage(result.has_api_key
        ? 'App token cleared; process environment still provides HF_TOKEN'
        : 'Hugging Face token cleared');
    } finally {
      setBusy(false);
    }
  }

  async function fetchModels(row: ProviderRowInfo) {
    const { nextList, profile } = ensureProfile(row);
    setList(nextList);
    if (!profile.base_url.trim()) {
      setMessage('Set a base URL first');
      return;
    }
    setBusy(true);
    setMessage('Fetching models…');
    try {
      const llm: Record<string, unknown> = {
        provider: profile.provider,
        base_url: profile.base_url,
        api_key_env: profile.api_key_env,
        auth_type: profile.auth_type,
      };
      // Use the just-typed key if present so fetch works before saving.
      const typedKey = (keyInputs[row.key] ?? '').trim();
      if (typedKey) llm.api_key = typedKey;
      const response = await window.vera.request<{ models: string[] }>({ action: SIDECAR_ACTIONS.listModels, llm });
      if (!response.ok) {
        setAvailableModels([]);
        setMessage(response.error || 'Unable to fetch models');
        return;
      }
      const models = filterDiscoveredModels(profile, response.result?.models ?? []);
      setAvailableModels(models);
      setList((prev) => prev.map((entry) => (entry.id === profile.id
        ? {
          ...entry,
          available_models: models,
          models_refreshed_at: Date.now(),
          models: entry.models.length === 0 ? defaultEnabledModels(entry, models) : entry.models,
        }
        : entry)));
      setMessage(models.length ? `Found ${models.length} models` : 'No models returned');
    } finally {
      setBusy(false);
    }
  }

  function renderModelsSection(row: ProviderRowInfo) {
    const profile = row.profile;
    const enabledModels = new Set(profile?.models ?? []);
    const modelOptions = Array.from(new Set([
      ...(profile?.models ?? []),
      ...(profile?.available_models ?? []),
      ...availableModels,
    ]))
      .filter((model) => !normalizedModelFilter || model.toLowerCase().includes(normalizedModelFilter))
      .sort((a, b) => a.localeCompare(b));
    const baseUrl = profile?.base_url ?? row.preset?.value.base_url ?? '';

    return (
      <div className="modelsSection">
        <div className="modelsHead">
          <span>Models <em>{profile?.models.length ?? 0} enabled</em></span>
          <button type="button" className="secondaryAction compactAction" onClick={() => void fetchModels(row)} disabled={busy || !baseUrl.trim()}>
            <ListChecks size={14} />Refresh models
          </button>
        </div>
        {(profile?.available_models?.length || availableModels.length || profile?.models.length) ? (
          <div className="modelManagerSearch">
            <Search size={14} />
            <input value={modelFilter} onChange={(event) => setModelFilter(event.target.value)} placeholder="Search models" />
          </div>
        ) : null}
        {modelOptions.length ? (
          <div className="modelChecklist">
            {modelOptions.map((model) => (
              <label className="modelCheck" key={model}>
                <input
                  type="checkbox"
                  checked={enabledModels.has(model)}
                  onChange={() => {
                    const next = enabledModels.has(model)
                      ? (profile?.models ?? []).filter((value) => value !== model)
                      : [...(profile?.models ?? []), model];
                    patchProfile(row, { models: next });
                  }}
                />
                <span>{model}</span>
              </label>
            ))}
          </div>
        ) : (
          <p className="mutedText">
            {normalizedModelFilter
              ? 'No matching models.'
              : 'No models found yet. Refresh the provider or add a model ID.'}
          </p>
        )}
        <div className="modelAddRow">
          <input
            value={modelInput}
            onChange={(event) => setModelInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                const model = modelInput.trim();
                if (!model) return;
                if (!(profile?.models ?? []).includes(model)) {
                  patchProfile(row, { models: [...(profile?.models ?? []), model] });
                }
                setModelInput('');
                setMessage(`Added model ${model}`);
              }
            }}
            placeholder="Add model id manually (e.g. gpt-4o-mini)"
          />
          <button
            type="button"
            className="secondaryAction compactAction"
            onClick={() => {
              const model = modelInput.trim();
              if (!model) return;
              if (!(profile?.models ?? []).includes(model)) {
                patchProfile(row, { models: [...(profile?.models ?? []), model] });
              }
              setModelInput('');
              setMessage(`Added model ${model}`);
            }}
            disabled={!modelInput.trim()}
          >
            <Plus size={14} />Add
          </button>
        </div>
      </div>
    );
  }

  function renderExpandedBody(row: ProviderRowInfo) {
    const profile = row.profile;
    const preset = row.preset;
    const hasKey = Boolean(profile?.has_api_key);

    return (
      <div className="providerItemBody">
        <p className="providerItemDescription">{row.description}</p>

        {row.kind === 'local' ? (
          <label className="field">
            <span>Server URL</span>
            <input
              value={profile?.base_url ?? preset?.value.base_url ?? ''}
              onChange={(event) => patchProfile(row, { base_url: event.target.value })}
              placeholder={preset?.value.base_url}
            />
          </label>
        ) : null}

        {row.kind === 'hosted' ? (
          <label className="field">
            <span>Base URL override</span>
            <input
              value={profile?.base_url ?? preset?.value.base_url ?? ''}
              onChange={(event) => patchProfile(row, { base_url: event.target.value })}
              placeholder={preset?.value.base_url}
            />
          </label>
        ) : null}

        {row.kind === 'custom' && profile ? (
          <div className="editorGrid">
            <label className="field">
              <span>Display Name</span>
              <input value={profile.label} onChange={(event) => patchProfile(row, { label: event.target.value })} placeholder="My Provider" />
            </label>
            <label className="field">
              <span>Type</span>
              <select value={profile.provider} onChange={(event) => patchProfile(row, { provider: event.target.value })}>
                <option value="openai_compatible">OpenAI Compatible</option>
                <option value="ollama">Ollama</option>
                <option value="lmstudio">LM Studio</option>
              </select>
            </label>
            <label className="field wideField">
              <span>Base URL</span>
              <input value={profile.base_url} onChange={(event) => patchProfile(row, { base_url: event.target.value })} placeholder="https://api.example.com/v1" />
            </label>
            <label className="field">
              <span>Authentication</span>
              <select value={profile.auth_type} onChange={(event) => patchProfile(row, { auth_type: event.target.value })}>
                <option value="none">None</option>
                <option value="api_key">API Key</option>
                <option value="env">Environment variable</option>
              </select>
            </label>
            <label className="field">
              <span>API environment variable</span>
              <input value={profile.api_key_env} onChange={(event) => patchProfile(row, { api_key_env: event.target.value })} placeholder="PROVIDER_API_KEY" />
            </label>
            <label className="field">
              <span>Temperature</span>
              <input className="numberInput" type="number" min={0} max={2} step={0.1} value={profile.temperature} onChange={(event) => patchProfile(row, { temperature: Number(event.target.value) })} />
            </label>
          </div>
        ) : null}

        {renderModelsSection(row)}

        <div className="editorActions">
          <button
            className={profile && profile.id === activeId ? 'secondaryAction activeNow' : 'secondaryAction'}
            onClick={() => setAsActive(row)}
            disabled={busy || !profile || profile.models.length === 0}
          >
            <CheckCircle2 size={16} />{profile && profile.id === activeId ? 'Active provider' : 'Set as active'}
          </button>
          {hasKey ? (
            <button className="secondaryAction" onClick={() => void clearKey(row)} disabled={busy}>
              <Trash2 size={16} />Clear key
            </button>
          ) : null}
          {profile ? (
            <button className="secondaryAction danger" onClick={() => removeProfile(row)} disabled={busy}>
              <Trash2 size={16} />Remove
            </button>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div className="modalBackdrop" onClick={onClose}>
      <div className="modal providerModal" onClick={(event) => event.stopPropagation()}>
        <header className="modalHeader">
          <h2><Settings size={18} />LLM Providers</h2>
          <button className="iconAction" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </header>

        <div className="providerStack">
          {rows.map((row) => {
            const profile = row.profile;
            const expanded = expandedKey === row.key;
            const authType = profile?.auth_type ?? row.preset?.value.auth_type ?? 'none';
            const hasKey = Boolean(profile?.has_api_key);
            const keyValue = keyInputs[row.key] ?? '';
            const configured = Boolean(profile && (profile.models.length || hasKey));
            return (
              <section key={row.key} className={expanded ? 'providerItem expanded' : 'providerItem'}>
                <div className="providerItemHead">
                  <button type="button" className="providerItemToggle" onClick={() => toggleExpanded(row.key)}>
                    <span className={configured ? 'providerDot configured' : 'providerDot'} />
                    <span className="providerItemName">{row.label}</span>
                    {profile && profile.id === activeId ? <em className="activeTag">Active</em> : null}
                    {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </button>
                  <div className="providerItemSide">
                    {authType === 'api_key' ? (
                      hasKey && !keyValue ? (
                        <span className="connectedTag"><CheckCircle2 size={13} />Key saved</span>
                      ) : (
                        <div className="providerKeyInline">
                          <input
                            type="password"
                            value={keyValue}
                            onChange={(event) => setKeyInputs((prev) => ({ ...prev, [row.key]: event.target.value }))}
                            onKeyDown={(event) => {
                              if (event.key === 'Enter') {
                                event.preventDefault();
                                void saveKey(row);
                              }
                            }}
                            placeholder={`Paste ${row.label} key`}
                            autoComplete="off"
                            disabled={busy}
                          />
                          {keyValue.trim() ? (
                            <button type="button" className="secondaryAction compactAction" onClick={() => void saveKey(row)} disabled={busy}>
                              <KeyRound size={13} />Save
                            </button>
                          ) : null}
                        </div>
                      )
                    ) : (
                      <span className="providerItemHint">{profile?.base_url || row.preset?.value.base_url || ''}</span>
                    )}
                  </div>
                </div>
                {expanded ? renderExpandedBody(row) : null}
              </section>
            );
          })}

          <button type="button" className="providerAddCustom" onClick={addCustomProvider} disabled={busy}>
            <Plus size={14} />Local / custom endpoint
            <small>Point VERA at any OpenAI-compatible endpoint (vLLM, llama.cpp, etc.)</small>
          </button>

          <section className={expandedKey === '__hf__' ? 'providerItem expanded' : 'providerItem'}>
            <div className="providerItemHead">
              <button type="button" className="providerItemToggle" onClick={() => toggleExpanded('__hf__')}>
                <span className={hfTokenStored ? 'providerDot configured' : 'providerDot'} />
                <span className="providerItemName">Hugging Face</span>
                {expandedKey === '__hf__' ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              </button>
              <div className="providerItemSide">
                {hfTokenStored && !hfTokenInput ? (
                  <span className="connectedTag"><CheckCircle2 size={13} />Token saved</span>
                ) : (
                  <div className="providerKeyInline">
                    <input
                      type="password"
                      value={hfTokenInput}
                      onChange={(event) => setHfTokenInput(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') {
                          event.preventDefault();
                          void saveHfToken();
                        }
                      }}
                      placeholder="Paste Hugging Face token"
                      autoComplete="off"
                      disabled={busy}
                    />
                    {hfTokenInput.trim() ? (
                      <button type="button" className="secondaryAction compactAction" onClick={() => void saveHfToken()} disabled={busy}>
                        <KeyRound size={13} />Save
                      </button>
                    ) : null}
                  </div>
                )}
              </div>
            </div>
            {expandedKey === '__hf__' ? (
              <div className="providerItemBody">
                <p className="providerItemDescription">
                  Optional token for Docling layout models and other Hub downloads. Stored securely
                  like provider API keys and passed to the sidecar as <code>HF_TOKEN</code>. Get one
                  at huggingface.co/settings/tokens.
                </p>
                <div className="editorActions">
                  <button className="secondaryAction" onClick={() => void clearHfToken()} disabled={busy || !hfTokenStored}>
                    <Trash2 size={16} />Clear token
                  </button>
                </div>
              </div>
            ) : null}
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
