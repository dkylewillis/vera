import { useEffect, useRef, useState } from 'react';
import {
  ChevronDown,
  Cloud,
  HardDrive,
  MessageSquareText,
  Plug,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
} from 'lucide-react';
import { PRO_PRESET_KEY, proFirst } from '../../shared/pro';
import { SIDECAR_ACTIONS } from '../../shared/protocol';
import { formatTimeAgo } from '../lib/formatting';
import {
  canListModels,
  emptyProvider,
  filterDiscoveredModels,
  isModelListStale,
  listModelsLlm,
  MODEL_LIST_MAX_AGE_MS,
  MODEL_LIST_RECHECK_MS,
  newProviderId,
  PROVIDER_PRESETS,
  providerDisplayName,
  providerPresetFor,
  withDiscoveredModels,
  type ProviderPreset,
} from '../lib/providers';
import type { ProviderProfile, VeraResponse } from '../types';
import {
  Callout,
  ConfirmButton,
  HelpLinkButton,
  SecretField,
  SettingsCard,
  StatusPill,
  ToggleSwitch,
  type PillTone,
} from './SettingsWidgets';

/** One provider card: a preset (configured or not) or a custom profile. */
export type ProviderRow = {
  key: string;
  label: string;
  description: string;
  kind: 'hosted' | 'local' | 'custom';
  preset: ProviderPreset | null;
  profile: ProviderProfile | null;
};

export function providerRows(list: ProviderProfile[]): ProviderRow[] {
  const rows: ProviderRow[] = [];
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
      description: profile.base_url.trim() || 'Any OpenAI-compatible server.',
      kind: 'custom',
      preset: null,
      profile,
    });
  }
  return rows;
}

export function providerRowStatus(row: ProviderRow): { tone: PillTone; label: string } {
  const profile = row.profile;
  if (row.preset?.key === PRO_PRESET_KEY) {
    return profile?.has_api_key ? { tone: 'good', label: 'Ready' } : { tone: 'neutral', label: 'Sign in to use' };
  }
  if (!profile) return { tone: 'neutral', label: 'Not set up' };
  if (profile.auth_type === 'api_key' && !profile.has_api_key) return { tone: 'warn', label: 'Needs key' };
  if (!profile.models.length) return { tone: 'warn', label: 'No models on' };
  return { tone: 'good', label: 'Ready' };
}

type FetchState = { status: 'loading' } | { status: 'error'; error: string };

type Draft = { list: ProviderProfile[]; activeId: string; activeModel: string };

const ASK_OPTION_SEPARATOR = '::';

function rowIcon(row: ProviderRow) {
  if (row.preset?.key === PRO_PRESET_KEY) return <Sparkles size={16} />;
  if (row.kind === 'local') return <HardDrive size={16} />;
  if (row.kind === 'custom') return <Plug size={16} />;
  return <Cloud size={16} />;
}

export function ProvidersSection({
  providers,
  activeProviderId,
  activeModel,
  busy,
  getDraft,
  onProvidersChange,
  onActiveChange,
  onSaveKey,
  onClearKey,
  onOpenAccount,
  onMessage,
}: {
  providers: ProviderProfile[];
  activeProviderId: string;
  activeModel: string;
  busy: boolean;
  /** Latest provider list and default chat selection, including changes not rendered yet. */
  getDraft: () => Draft;
  onProvidersChange: (updater: (prev: ProviderProfile[]) => ProviderProfile[]) => void;
  onActiveChange: (providerId: string, model: string) => void;
  /** Persist the profile, store the key, and return the refreshed profile. */
  onSaveKey: (profile: ProviderProfile, key: string) => Promise<ProviderProfile | null>;
  onClearKey: (profile: ProviderProfile) => Promise<void>;
  onOpenAccount: () => void;
  onMessage: (message: string) => void;
}) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [fetchStates, setFetchStates] = useState<Record<string, FetchState | undefined>>({});
  const [discovered, setDiscovered] = useState<Record<string, string[]>>({});
  const [modelFilter, setModelFilter] = useState('');
  const [modelInput, setModelInput] = useState('');
  const autoRefreshed = useRef(false);

  const rows = providerRows(providers);

  function setFetchState(rowKey: string, state: FetchState | undefined) {
    setFetchStates((current) => ({ ...current, [rowKey]: state }));
  }

  function latestProfile(row: ProviderRow): ProviderProfile | null {
    const list = getDraft().list;
    if (row.preset) {
      return list.find((entry) => providerPresetFor(entry)?.key === row.preset?.key) ?? null;
    }
    return list.find((entry) => entry.id === row.key) ?? null;
  }

  function draftProfile(row: ProviderRow): ProviderProfile {
    const preset = row.preset!;
    const found = discovered[row.key];
    return {
      ...preset.value,
      models: [...preset.value.models],
      preset_key: preset.key,
      id: newProviderId(),
      ...(found ? { available_models: found, models_refreshed_at: Date.now() } : {}),
    };
  }

  /** Add a profile for an unconfigured preset the first time the user changes it. */
  function materialize(row: ProviderRow, patch: Partial<ProviderProfile> = {}): ProviderProfile {
    const existing = latestProfile(row);
    if (existing) return existing;
    const profile = { ...draftProfile(row), ...patch };
    onProvidersChange((prev) => [...prev, profile]);
    return profile;
  }

  function patchProfile(row: ProviderRow, patch: Partial<ProviderProfile>): ProviderProfile {
    const existing = latestProfile(row);
    if (!existing) return materialize(row, patch);
    onProvidersChange((prev) => prev.map((entry) => (entry.id === existing.id ? { ...entry, ...patch } : entry)));
    return { ...existing, ...patch };
  }

  function hasUsableAskModel(): boolean {
    const draft = getDraft();
    const active = draft.list.find((entry) => entry.id === draft.activeId);
    return Boolean(active?.models.length);
  }

  async function fetchModels(
    row: ProviderRow,
    options: { profile?: ProviderProfile; connect?: boolean } = {},
  ) {
    const existing = options.profile ?? latestProfile(row);
    const base = existing ?? (row.preset ? draftProfile(row) : null);
    if (!base) return;
    if (!base.base_url.trim()) {
      setFetchState(row.key, { status: 'error', error: 'Enter the server address first.' });
      return;
    }
    setFetchState(row.key, { status: 'loading' });
    let response: VeraResponse<{ models: string[] }>;
    try {
      response = await window.vera.request<{ models: string[] }>({
        action: SIDECAR_ACTIONS.listModels,
        llm: listModelsLlm(base),
      });
    } catch (error) {
      response = { ok: false, error: error instanceof Error ? error.message : String(error) };
    }
    if (!response.ok) {
      const reason = row.kind === 'local'
        ? `Could not reach ${row.label} at ${base.base_url}. Make sure it is running, then check again.`
        : `Could not load models${response.error ? `: ${response.error}` : '.'}`;
      setFetchState(row.key, { status: 'error', error: reason });
      return;
    }
    setFetchState(row.key, undefined);
    const raw = response.result?.models ?? [];
    const target = existing ?? (options.connect ? materialize(row) : null);
    if (!target) {
      setDiscovered((current) => ({ ...current, [row.key]: filterDiscoveredModels(base, raw) }));
      return;
    }
    const refreshed = withDiscoveredModels(latestProfile(row) ?? target, raw);
    onProvidersChange((prev) => prev.map((entry) => (entry.id === target.id ? withDiscoveredModels(entry, raw) : entry)));
    if (!hasUsableAskModel() && refreshed.models.length) {
      onActiveChange(target.id, refreshed.models[0]);
      onMessage(`${row.label} is now the default chat provider`);
    }
  }

  // Keep configured model lists current without a manual refresh.
  useEffect(() => {
    if (autoRefreshed.current) return;
    autoRefreshed.current = true;
    for (const row of providerRows(getDraft().list)) {
      const profile = row.profile;
      if (!profile || row.preset?.key === PRO_PRESET_KEY) continue;
      if (canListModels(profile) && isModelListStale(profile, MODEL_LIST_MAX_AGE_MS)) {
        void fetchModels(row, { profile });
      }
    }
  }, []);

  useEffect(() => {
    if (!expandedKey) return;
    const row = rows.find((entry) => entry.key === expandedKey);
    if (!row || row.preset?.key === PRO_PRESET_KEY || fetchStates[row.key]?.status === 'loading') return;
    if (row.profile) {
      if (canListModels(row.profile) && isModelListStale(row.profile, MODEL_LIST_RECHECK_MS)) void fetchModels(row);
    } else if (row.kind === 'local' && !discovered[row.key]) {
      void fetchModels(row);
    }
  }, [expandedKey]);

  useEffect(() => {
    if (!expandedKey) return;
    const card = document.getElementById(`provider-card-${expandedKey}`);
    const scroller = card?.closest('.settingsContent');
    if (!card || !scroller) return;
    const cardBox = card.getBoundingClientRect();
    const viewBox = scroller.getBoundingClientRect();
    if (cardBox.bottom > viewBox.bottom) {
      card.scrollIntoView({ block: cardBox.height > viewBox.height ? 'start' : 'nearest', behavior: 'smooth' });
    }
  }, [expandedKey]);

  function toggleExpanded(rowKey: string) {
    setExpandedKey((current) => (current === rowKey ? null : rowKey));
    setModelFilter('');
    setModelInput('');
  }

  function toggleModel(row: ProviderRow, model: string) {
    const current = latestProfile(row)?.models ?? [];
    const enabling = !current.includes(model);
    const next = enabling ? [...current, model] : current.filter((entry) => entry !== model);
    const profile = patchProfile(row, { models: next });
    if (enabling && !hasUsableAskModel()) onActiveChange(profile.id, model);
  }

  function addModel(row: ProviderRow) {
    const model = modelInput.trim();
    if (!model) return;
    const current = latestProfile(row)?.models ?? [];
    if (!current.includes(model)) toggleModel(row, model);
    setModelInput('');
    onMessage(`Added ${model}`);
  }

  async function saveKey(row: ProviderRow, key: string): Promise<boolean> {
    const profile = latestProfile(row) ?? (row.preset ? draftProfile(row) : row.profile);
    if (!profile) return false;
    const saved = await onSaveKey(profile, key);
    if (!saved) return false;
    void fetchModels(row, { profile: saved });
    return true;
  }

  function removeProvider(row: ProviderRow) {
    const profile = latestProfile(row);
    if (!profile) return;
    onProvidersChange((prev) => prev.filter((entry) => entry.id !== profile.id));
    if (getDraft().activeId === profile.id) onActiveChange('', '');
    setExpandedKey(null);
    onMessage(`${row.label} removed`);
  }

  function addCustomProvider() {
    const profile = emptyProvider();
    onProvidersChange((prev) => [...prev, profile]);
    setExpandedKey(profile.id);
    setModelFilter('');
    setModelInput('');
  }

  function renderAskPicker() {
    const groups = proFirst(providers).filter((profile) => profile.models.length > 0);
    const active = providers.find((profile) => profile.id === activeProviderId);
    const activeValid = Boolean(active?.models.includes(activeModel));
    const value = activeValid ? `${activeProviderId}${ASK_OPTION_SEPARATOR}${activeModel}` : '';
    return (
      <SettingsCard
        icon={<MessageSquareText size={16} />}
        title="Chat model"
        description="Chat sends your question and the passages it finds to this model in every chat mode. You can also switch models from the chat composer."
        className="askModelCard"
      >
        {groups.length ? (
          <select
            aria-label="Chat model"
            value={value}
            onChange={(event) => {
              const raw = event.target.value;
              const cut = raw.indexOf(ASK_OPTION_SEPARATOR);
              if (cut < 0) return;
              onActiveChange(raw.slice(0, cut), raw.slice(cut + ASK_OPTION_SEPARATOR.length));
            }}
          >
            {activeValid ? null : <option value="">Choose a model…</option>}
            {groups.map((profile) => (
              <optgroup key={profile.id} label={providerDisplayName(profile)}>
                {profile.models.map((model) => (
                  <option key={model} value={`${profile.id}${ASK_OPTION_SEPARATOR}${model}`}>{model}</option>
                ))}
              </optgroup>
            ))}
          </select>
        ) : (
          <Callout title="Chat is not set up yet.">
            <p>Sign in to VERA Pro, or connect one of the services below. Search works either way.</p>
            <div className="editorActions">
              <button type="button" className="primaryAction compactAction" onClick={onOpenAccount}>Use VERA Pro</button>
            </div>
          </Callout>
        )}
      </SettingsCard>
    );
  }

  function renderModels(row: ProviderRow) {
    const profile = row.profile;
    const fetchState = fetchStates[row.key];
    const loading = fetchState?.status === 'loading';
    const found = discovered[row.key] ?? [];
    if (!profile && row.kind !== 'local') {
      return <p className="providerHint">Save your {row.label} API key and VERA loads its models for you.</p>;
    }
    if (!profile && !found.length) return null;

    const enabled = new Set(profile?.models ?? []);
    const all = Array.from(new Set([...(profile?.models ?? []), ...(profile?.available_models ?? []), ...found]));
    const filter = modelFilter.trim().toLowerCase();
    const shown = all
      .filter((model) => !filter || model.toLowerCase().includes(filter))
      .sort((a, b) => Number(enabled.has(b)) - Number(enabled.has(a)) || a.localeCompare(b));
    const canRefresh = profile ? canListModels(profile) : true;
    const refreshedAt = profile?.models_refreshed_at;
    let emptyText = 'No models found. Add a model ID below.';
    if (filter) emptyText = 'No models match your search.';
    else if (loading) emptyText = 'Loading models…';
    else if (profile && !canRefresh && profile.auth_type === 'api_key') emptyText = 'Save an API key above and the model list loads automatically.';

    return (
      <div className="modelsPanel">
        <div className="modelsPanelHead">
          <span className="modelsPanelTitle">
            Models <em>{enabled.size} on{all.length ? ` of ${all.length}` : ''}</em>
          </span>
          <span className="modelsPanelStatus" aria-live="polite">
            {loading ? 'Checking for new models…' : refreshedAt ? `Updated ${formatTimeAgo(refreshedAt)}` : ''}
            <button
              type="button"
              className="ghostIcon tiny visible"
              title="Check for new models"
              aria-label="Check for new models"
              onClick={() => void fetchModels(row)}
              disabled={loading || !canRefresh}
            >
              <RefreshCw size={13} className={loading ? 'spinning' : ''} />
            </button>
          </span>
        </div>
        {fetchState?.status === 'error' && profile ? (
          <p className="modelsPanelError">
            {fetchState.error}{' '}
            <button type="button" className="settingsLink" onClick={() => void fetchModels(row)}>Try again</button>
          </p>
        ) : null}
        {all.length > 8 ? (
          <div className="modelManagerSearch modelsPanelSearch">
            <Search size={14} />
            <input value={modelFilter} onChange={(event) => setModelFilter(event.target.value)} placeholder="Search models" aria-label="Search models" />
          </div>
        ) : null}
        {shown.length ? (
          <div className="modelToggleList">
            {shown.map((model) => (
              <label className="modelToggleRow" key={model}>
                <span title={model}>{model}</span>
                <ToggleSwitch checked={enabled.has(model)} onChange={() => toggleModel(row, model)} label={`Use ${model}`} />
              </label>
            ))}
          </div>
        ) : (
          <p className="modelsPanelEmpty">{emptyText}</p>
        )}
        <form
          className="modelAddRow"
          onSubmit={(event) => {
            event.preventDefault();
            addModel(row);
          }}
        >
          <input
            type="text"
            value={modelInput}
            onChange={(event) => setModelInput(event.target.value)}
            placeholder="Add a model by ID, for example gpt-4o-mini"
            aria-label="Model ID"
          />
          <button type="submit" className="secondaryAction compactAction" disabled={!modelInput.trim()}>
            <Plus size={14} />Add
          </button>
        </form>
      </div>
    );
  }

  function renderLocalConnection(row: ProviderRow) {
    const profile = row.profile;
    const fetchState = fetchStates[row.key];
    const loading = fetchState?.status === 'loading';
    const found = discovered[row.key] ?? [];
    const baseUrl = profile?.base_url ?? row.preset?.value.base_url ?? '';
    let status = null;
    if (loading) {
      status = <p className="providerHint"><RefreshCw size={12} className="spinning" /> Looking for {row.label} at {baseUrl}…</p>;
    } else if (fetchState?.status === 'error') {
      status = (
        <Callout tone="warn" title={`${row.label} is not responding.`}>
          <p>{fetchState.error}</p>
          {row.preset?.setupLink ? <HelpLinkButton link={row.preset.setupLink}>Download {row.label}</HelpLinkButton> : null}
        </Callout>
      );
    } else if (!profile && found.length) {
      status = <Callout tone="good" title={`${row.label} is running.`}><p>It has {found.length} {found.length === 1 ? 'model' : 'models'}. Select Connect to use {found.length === 1 ? 'it' : 'them'} in Chat.</p></Callout>;
    } else if (!profile) {
      status = (
        <p className="providerHint">
          Install and start {row.label}, then select Connect.{' '}
          {row.preset?.setupLink ? <HelpLinkButton link={row.preset.setupLink}>Download {row.label}</HelpLinkButton> : null}
        </p>
      );
    }
    return (
      <>
        <label className="field">
          <span>Server address</span>
          <div className="inlineFieldRow">
            <input
              type="text"
              value={baseUrl}
              onChange={(event) => patchProfile(row, { base_url: event.target.value })}
              placeholder={row.preset?.value.base_url}
              spellCheck={false}
            />
            <button
              type="button"
              className={profile ? 'secondaryAction compactAction' : 'primaryAction compactAction'}
              onClick={() => void fetchModels(row, { connect: true })}
              disabled={loading || !baseUrl.trim()}
            >
              {profile ? 'Check again' : 'Connect'}
            </button>
          </div>
        </label>
        {status}
      </>
    );
  }

  function renderCustomFields(row: ProviderRow, profile: ProviderProfile) {
    return (
      <>
        <div className="editorGrid">
          <label className="field">
            <span>Display name</span>
            <input type="text" value={profile.label} onChange={(event) => patchProfile(row, { label: event.target.value })} placeholder="My provider" />
          </label>
          <label className="field">
            <span>Server type</span>
            <select value={profile.provider} onChange={(event) => patchProfile(row, { provider: event.target.value })}>
              <option value="openai_compatible">OpenAI compatible</option>
              <option value="ollama">Ollama</option>
              <option value="lmstudio">LM Studio</option>
            </select>
          </label>
          <label className="field wideField">
            <span>Base URL</span>
            <input
              type="text"
              value={profile.base_url}
              onChange={(event) => patchProfile(row, { base_url: event.target.value })}
              placeholder="https://api.example.com/v1"
              spellCheck={false}
            />
          </label>
          <label className="field">
            <span>Sign-in</span>
            <select value={profile.auth_type} onChange={(event) => patchProfile(row, { auth_type: event.target.value })}>
              <option value="none">None</option>
              <option value="api_key">API key</option>
              <option value="env">Environment variable</option>
            </select>
          </label>
          {profile.auth_type === 'env' ? (
            <label className="field">
              <span>Environment variable</span>
              <input
                type="text"
                value={profile.api_key_env}
                onChange={(event) => patchProfile(row, { api_key_env: event.target.value })}
                placeholder="PROVIDER_API_KEY"
                spellCheck={false}
              />
            </label>
          ) : null}
        </div>
        {profile.auth_type === 'api_key' ? (
          <SecretField
            label="API key"
            saved={Boolean(profile.has_api_key)}
            placeholder="Paste the API key"
            onSave={(value) => saveKey(row, value)}
            onClear={() => void onClearKey(profile)}
            busy={busy}
            hint={profile.base_url.trim() ? 'Stored encrypted on this computer.' : 'Enter the base URL before saving a key.'}
          />
        ) : null}
      </>
    );
  }

  function renderAdvanced(row: ProviderRow, profile: ProviderProfile) {
    const pro = row.preset?.key === PRO_PRESET_KEY;
    return (
      <details className="providerAdvanced">
        <summary>Advanced options</summary>
        <div className="editorGrid">
          {row.kind === 'hosted' && !pro ? (
            <label className="field wideField">
              <span>Base URL</span>
              <input
                type="text"
                value={profile.base_url}
                onChange={(event) => patchProfile(row, { base_url: event.target.value })}
                placeholder={row.preset?.value.base_url}
                spellCheck={false}
              />
            </label>
          ) : null}
          <label className="field">
            <span>Temperature</span>
            <input
              className="numberInput"
              type="number"
              min={0}
              max={2}
              step={0.1}
              value={profile.temperature}
              onChange={(event) => patchProfile(row, { temperature: Number(event.target.value) })}
            />
          </label>
          <label className="field">
            <span>Context tokens</span>
            <input
              className="numberInput"
              type="number"
              min={256}
              step={256}
              placeholder="Provider default"
              value={profile.context_tokens ?? ''}
              onChange={(event) => {
                const value = event.target.value.trim();
                patchProfile(row, { context_tokens: value ? Number(value) : undefined });
              }}
            />
          </label>
        </div>
        <p className="providerHint">
          Lower temperature gives steadier answers. Context tokens sets how much text Chat sends at once; leave it empty to use the provider default.
        </p>
        <div className="editorActions">
          {pro && profile.has_api_key ? (
            <button type="button" className="secondaryAction compactAction danger" onClick={() => void onClearKey(profile)} disabled={busy}>
              Remove Pro key
            </button>
          ) : null}
          <ConfirmButton label="Remove provider" confirmLabel="Select again to remove" onConfirm={() => removeProvider(row)} disabled={busy} />
        </div>
      </details>
    );
  }

  function renderBody(row: ProviderRow) {
    const profile = row.profile;
    const pro = row.preset?.key === PRO_PRESET_KEY;
    const isActive = Boolean(profile && profile.id === activeProviderId);
    return (
      <div className="providerCardBody">
        {pro ? (
          <div className="providerStep">
            <p className="providerHint">
              VERA Pro is managed from your account. Signing in with an active subscription saves its key and makes it the default for Chat.
            </p>
            <div className="editorActions">
              <button type="button" className="secondaryAction compactAction" onClick={onOpenAccount}>Open Account</button>
            </div>
          </div>
        ) : null}
        {row.kind === 'hosted' && !pro ? (
          <SecretField
            label="API key"
            saved={Boolean(profile?.has_api_key)}
            placeholder={`Paste your ${row.label} API key`}
            onSave={(value) => saveKey(row, value)}
            onClear={profile ? () => void onClearKey(profile) : undefined}
            busy={busy}
            helpLink={row.preset?.keyLink}
            hint="Stored encrypted on this computer. VERA loads the model list as soon as the key is saved."
          />
        ) : null}
        {row.kind === 'local' ? renderLocalConnection(row) : null}
        {row.kind === 'custom' && profile ? renderCustomFields(row, profile) : null}
        {renderModels(row)}
        {profile && profile.models.length && !isActive ? (
          <div className="editorActions">
            <button
              type="button"
              className="secondaryAction compactAction"
              onClick={() => onActiveChange(profile.id, profile.models[0])}
              disabled={busy}
            >
              Make {row.label} the default
            </button>
          </div>
        ) : null}
        {profile ? renderAdvanced(row, profile) : null}
      </div>
    );
  }

  function renderRow(row: ProviderRow) {
    const expanded = expandedKey === row.key;
    const status = providerRowStatus(row);
    const isActive = Boolean(row.profile && row.profile.id === activeProviderId);
    const bodyId = `provider-body-${row.key}`;
    return (
      <section key={row.key} id={`provider-card-${row.key}`} className={expanded ? 'providerCard expanded' : 'providerCard'}>
        <button
          type="button"
          className="providerCardHead"
          onClick={() => toggleExpanded(row.key)}
          aria-expanded={expanded}
          aria-controls={bodyId}
        >
          <span
            className={`providerAvatar providerAvatar--${row.preset?.key === PRO_PRESET_KEY ? 'pro' : row.kind}`}
            aria-hidden="true"
          >
            {rowIcon(row)}
          </span>
          <span className="providerCardText">
            <span className="providerCardName">{row.label}</span>
            <span className="providerCardDescription">{row.description}</span>
          </span>
          <span className="providerCardStatus">
            {isActive ? <StatusPill tone="accent">Default</StatusPill> : null}
            <StatusPill tone={status.tone}>{status.label}</StatusPill>
          </span>
          <ChevronDown size={16} className="providerCardChevron" aria-hidden="true" />
        </button>
        {expanded ? <div id={bodyId}>{renderBody(row)}</div> : null}
      </section>
    );
  }

  function renderGroup(title: string, description: string, groupRows: ProviderRow[]) {
    if (!groupRows.length) return null;
    return (
      <div className="providerGroup">
        <div className="providerGroupHead">
          <h4 className="settingsGroupLabel">{title}</h4>
          <span>{description}</span>
        </div>
        {groupRows.map(renderRow)}
      </div>
    );
  }

  return (
    <div className="settingsStack">
      {renderAskPicker()}
      {renderGroup('Online services', 'Your question and the passages Chat finds are sent to the service.', rows.filter((row) => row.kind === 'hosted'))}
      {renderGroup('On this computer', 'Free and private; needs a capable computer.', rows.filter((row) => row.kind === 'local'))}
      {renderGroup('Custom endpoints', 'Your own OpenAI-compatible servers.', rows.filter((row) => row.kind === 'custom'))}
      <button type="button" className="providerAddCustom" onClick={addCustomProvider} disabled={busy}>
        <Plus size={14} />Add a custom endpoint
        <small>Any OpenAI-compatible server, such as vLLM or llama.cpp</small>
      </button>
    </div>
  );
}
