import { useEffect, useRef, useState, type ReactNode } from 'react';
import {
  Bot,
  CheckCircle2,
  ChevronRight,
  FileText,
  KeyRound,
  LayoutGrid,
  MessageSquareText,
  RefreshCw,
  Search,
  Settings,
  Sparkles,
  UserRound,
  X,
} from 'lucide-react';
import { PRO_PRESET_KEY, subscriptionActive, type ProAccount } from '../../shared/pro';
import { EMBEDDING_MODEL_PRESETS, embeddingProviderFromSpec } from '../lib/convertPresets';
import { useProAccount } from '../lib/proAccount';
import { providerDisplayName, withPresetModels } from '../lib/providers';
import type { AgentServiceStatus, AppSettings, EmbedderDescriptor, ProviderProfile } from '../types';
import { AccountSection } from './AccountSection';
import { AgentAccessSection } from './AgentAccessSection';
import { ProvidersSection } from './ProviderSettings';
import { Callout, CopyField, SecretField, SettingsCard, StatusPill, type PillTone } from './SettingsWidgets';

export type SettingsSectionId =
  | 'overview'
  | 'account'
  | 'providers'
  | 'embeddings'
  | 'agents'
  | 'huggingface'
  | 'diagnostics';

type SettingsSection = {
  id: SettingsSectionId;
  label: string;
  /** Short plain-language line under the label in the sidebar. */
  hint: string;
  description: string;
  group: 'start' | 'ai' | 'advanced';
  icon: typeof Settings;
  /** Extra words people may search for. */
  keywords: string;
};

export const SETTINGS_SECTIONS: SettingsSection[] = [
  {
    id: 'overview',
    label: 'Overview',
    hint: 'What is set up',
    description: 'See what is ready and what still needs setup.',
    group: 'start',
    icon: LayoutGrid,
    keywords: 'home start status summary setup getting started',
  },
  {
    id: 'account',
    label: 'Account',
    hint: 'VERA Pro sign-in',
    description: 'Sign in to VERA Pro and see included and on-demand usage.',
    group: 'start',
    icon: UserRound,
    keywords: 'sign in sign out login log in subscription pro plan billing usage email upgrade',
  },
  {
    id: 'providers',
    label: 'AI providers',
    hint: 'Models that answer in Chat',
    description: 'Choose the AI service and default model that write answers in Chat.',
    group: 'ai',
    icon: MessageSquareText,
    keywords: 'ask chat llm model models answer answers openai openrouter ollama lm studio api key gpt claude gemini custom endpoint temperature context tokens provider providers',
  },
  {
    id: 'embeddings',
    label: 'Embeddings',
    hint: 'Search models for Convert',
    description: 'The search model Convert uses, and keys for online search models.',
    group: 'ai',
    icon: Sparkles,
    keywords: 'embedding search model convert conversion openai api key OPENAI_API_KEY semantic vectors minilm',
  },
  {
    id: 'agents',
    label: 'Agent access',
    hint: 'Share with other AI apps',
    description: 'Let AI apps on this computer, or cloud assistants, search your libraries.',
    group: 'ai',
    icon: Bot,
    keywords: 'agent agents mcp claude chatgpt cursor connector share sharing library libraries token snippet cloud relay computer',
  },
  {
    id: 'huggingface',
    label: 'Hugging Face',
    hint: 'Optional download token',
    description: 'Optional Hub token for Hugging Face model downloads.',
    group: 'advanced',
    icon: KeyRound,
    keywords: 'hugging face huggingface hf token HF_TOKEN hub download rate limit',
  },
  {
    id: 'diagnostics',
    label: 'Diagnostics',
    hint: 'Logs and updates',
    description: 'The convert log and app updates.',
    group: 'advanced',
    icon: FileText,
    keywords: 'diagnostics log logs troubleshoot troubleshooting convert sidecar timing updates update version help',
  },
];

const NAV_GROUPS: { id: SettingsSection['group']; label: string }[] = [
  { id: 'start', label: '' },
  { id: 'ai', label: 'AI and search' },
  { id: 'advanced', label: 'Advanced' },
];

/** Sections whose name, hint, description, or keywords contain every search word. */
export function matchSettingsSections(query: string): SettingsSection[] {
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return SETTINGS_SECTIONS;
  return SETTINGS_SECTIONS.filter((section) => {
    const text = `${section.label} ${section.hint} ${section.description} ${section.keywords}`.toLowerCase();
    return words.every((word) => text.includes(word));
  });
}

const EMBEDDER_NAMES: Record<string, string> = {
  openai: 'OpenAI',
  voyage: 'Voyage AI',
  cohere: 'Cohere',
};

function embedderDisplayName(descriptor: EmbedderDescriptor): string {
  return EMBEDDER_NAMES[descriptor.provider] || descriptor.label.split(' — ')[0] || descriptor.provider;
}

type Summary = { tone: PillTone; pill: string; detail: string };

export function accountSummary(account: ProAccount | null): Summary {
  if (!account) return { tone: 'neutral', pill: 'Checking', detail: 'Sign in to VERA Pro for Chat without your own key.' };
  if (!account.configured) return { tone: 'neutral', pill: 'Unavailable', detail: 'This build is not connected to VERA Pro.' };
  if (account.signedIn && subscriptionActive(account.subscriptionStatus)) {
    return { tone: 'accent', pill: 'Pro', detail: account.email || 'Signed in' };
  }
  if (account.signedIn) return { tone: 'good', pill: 'Signed in', detail: `${account.email || 'Signed in'} · no subscription` };
  return { tone: 'neutral', pill: 'Signed out', detail: 'Sign in to use VERA Pro for Chat.' };
}

export function askSummary(list: ProviderProfile[], activeId: string, activeModel: string): Summary {
  const active = list.find((profile) => profile.id === activeId);
  if (active && active.models.includes(activeModel)) {
    if (active.auth_type === 'api_key' && !active.has_api_key) {
      return { tone: 'warn', pill: 'Needs key', detail: `Save a key for ${providerDisplayName(active)} to use ${activeModel}.` };
    }
    return { tone: 'good', pill: 'Ready', detail: `${activeModel} · ${providerDisplayName(active)}` };
  }
  if (list.some((profile) => profile.models.length)) {
    return { tone: 'warn', pill: 'Choose a model', detail: 'Pick the model that answers in Chat.' };
  }
  return { tone: 'neutral', pill: 'Not set up', detail: 'Use VERA Pro, or connect OpenAI, OpenRouter, Ollama, or LM Studio.' };
}

function OverviewCard({
  icon,
  title,
  summary,
  onOpen,
}: {
  icon: ReactNode;
  title: string;
  summary: Summary;
  onOpen: () => void;
}) {
  return (
    <button type="button" className="overviewCard" onClick={onOpen}>
      <span className="overviewCardIcon" aria-hidden="true">{icon}</span>
      <span className="overviewCardText">
        <span className="overviewCardTitle">
          {title}
          <StatusPill tone={summary.tone}>{summary.pill}</StatusPill>
        </span>
        <span className="overviewCardDetail">{summary.detail}</span>
      </span>
      <ChevronRight size={16} className="overviewCardChevron" aria-hidden="true" />
    </button>
  );
}

export function SettingsModal({
  providers,
  activeProviderId,
  activeModel,
  activeModeId,
  embeddingModel,
  ingestPipeline,
  ingestPipelineConfigs,
  embedderConfigs,
  embeddingDescriptors = [],
  hasHfToken = false,
  hasEnvSecrets = {},
  convertLogPath = '',
  initialSection = 'overview',
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
  embedderConfigs: AppSettings['embedder_configs'];
  embeddingDescriptors?: EmbedderDescriptor[];
  hasHfToken?: boolean;
  hasEnvSecrets?: Record<string, boolean>;
  convertLogPath?: string;
  initialSection?: SettingsSectionId;
  onPersist: (next: AppSettings) => Promise<AppSettings>;
  onRefresh: () => Promise<AppSettings>;
  onClose: () => void;
}) {
  const [section, setSection] = useState<SettingsSectionId>(initialSection);
  const [query, setQuery] = useState('');
  const [list, setList] = useState<ProviderProfile[]>(() => providers.map(withPresetModels));
  const [activeId, setActiveId] = useState(activeProviderId);
  const [activeModelLocal, setActiveModelLocal] = useState(activeModel);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [hfTokenStored, setHfTokenStored] = useState(hasHfToken);
  const [envSecretsStored, setEnvSecretsStored] = useState<Record<string, boolean>>(hasEnvSecrets);
  const [agentStatus, setAgentStatus] = useState<AgentServiceStatus | null>(null);
  const account = useProAccount();
  const contentRef = useRef<HTMLDivElement>(null);

  function buildPayload(nextList: ProviderProfile[], nextActiveId: string, nextActiveModel: string): AppSettings {
    const activeProfile = nextList.find((profile) => profile.id === nextActiveId);
    const model = activeProfile && activeProfile.models.includes(nextActiveModel)
      ? nextActiveModel
      : activeProfile?.models[0] ?? '';
    return {
      providers: nextList,
      active_provider_id: activeProfile ? nextActiveId : '',
      active_model: model,
      active_mode_id: activeModeId,
      embedding_model: embeddingModel,
      ingest_pipeline: ingestPipeline,
      ingest_pipeline_configs: ingestPipelineConfigs,
      embedder_configs: embedderConfigs,
    };
  }

  // Latest edits, readable from async handlers before React re-renders.
  const draftRef = useRef({ list, activeId, activeModel: activeModelLocal });
  draftRef.current = { list, activeId, activeModel: activeModelLocal };
  const lastSavedRef = useRef<string | null>(null);
  if (lastSavedRef.current === null) {
    lastSavedRef.current = JSON.stringify(buildPayload(list, activeId, activeModelLocal));
  }
  const payloadJson = JSON.stringify(buildPayload(list, activeId, activeModelLocal));

  async function persist(next: AppSettings) {
    const json = JSON.stringify(next);
    if (json === lastSavedRef.current) return;
    lastSavedRef.current = json;
    setSaveState('saving');
    try {
      await onPersist(next);
      setSaveState('saved');
    } catch (error) {
      lastSavedRef.current = '';
      setSaveState('error');
      setMessage(error instanceof Error ? error.message : 'Unable to save settings');
    }
  }

  function flush(): Promise<void> {
    const draft = draftRef.current;
    return persist(buildPayload(draft.list, draft.activeId, draft.activeModel));
  }

  useEffect(() => {
    if (payloadJson === lastSavedRef.current) return undefined;
    const timer = window.setTimeout(() => { void flush(); }, 450);
    return () => window.clearTimeout(timer);
  }, [payloadJson]);

  useEffect(() => {
    if (!message) return undefined;
    const timer = window.setTimeout(() => setMessage(''), 6000);
    return () => window.clearTimeout(timer);
  }, [message]);

  useEffect(() => {
    contentRef.current?.scrollTo?.({ top: 0 });
  }, [section]);

  useEffect(() => {
    if (section !== 'overview' || !window.vera?.serviceGetStatus) return undefined;
    let cancelled = false;
    void window.vera.serviceGetStatus().then((next) => {
      if (!cancelled) setAgentStatus(next);
    }).catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [section]);

  function updateList(updater: (prev: ProviderProfile[]) => ProviderProfile[]) {
    const next = updater(draftRef.current.list);
    draftRef.current = { ...draftRef.current, list: next };
    setList(next);
  }

  function setAsk(providerId: string, model: string) {
    draftRef.current = { ...draftRef.current, activeId: providerId, activeModel: model };
    setActiveId(providerId);
    setActiveModelLocal(model);
  }

  /** Replace the draft with settings read back from disk, without saving them again. */
  function applySaved(saved: AppSettings) {
    const nextList = saved.providers.map(withPresetModels);
    const nextActiveId = saved.active_provider_id;
    const nextActiveModel = saved.active_model || '';
    lastSavedRef.current = JSON.stringify(buildPayload(nextList, nextActiveId, nextActiveModel));
    draftRef.current = { list: nextList, activeId: nextActiveId, activeModel: nextActiveModel };
    setList(nextList);
    setActiveId(nextActiveId);
    setActiveModelLocal(nextActiveModel);
    setHfTokenStored(Boolean(saved.has_hf_token));
    setEnvSecretsStored(saved.has_env_secrets || {});
  }

  async function close() {
    await flush();
    onClose();
  }

  async function saveProviderKey(profile: ProviderProfile, key: string): Promise<ProviderProfile | null> {
    setBusy(true);
    try {
      if (!draftRef.current.list.some((entry) => entry.id === profile.id)) {
        updateList((prev) => [...prev, profile]);
      }
      await flush();
      const result = await window.vera.saveApiKey(profile.base_url, key);
      if (!result.ok) {
        setMessage(result.error || 'Unable to save the API key');
        return null;
      }
      const saved = await onRefresh();
      applySaved(saved);
      setMessage(`${providerDisplayName(profile)} key saved`);
      const refreshed = saved.providers.find((entry) => entry.id === profile.id);
      return refreshed ? withPresetModels(refreshed) : { ...profile, has_api_key: true };
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to save the API key');
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function clearProviderKey(profile: ProviderProfile) {
    setBusy(true);
    try {
      if (profile.preset_key === PRO_PRESET_KEY) {
        const result = await window.vera.proClearKey();
        if (!result.ok) {
          setMessage(result.error || 'Unable to remove the VERA Pro key');
          return;
        }
      } else {
        await window.vera.clearApiKey(profile.base_url);
      }
      await flush();
      applySaved(await onRefresh());
      setMessage('API key removed');
    } finally {
      setBusy(false);
    }
  }

  async function saveHfToken(value: string): Promise<boolean> {
    setBusy(true);
    try {
      await flush();
      const result = await window.vera.saveHfToken(value);
      if (!result.ok) {
        setMessage(result.error || 'Unable to save the Hugging Face token');
        return false;
      }
      const refreshed = await onRefresh();
      setHfTokenStored(Boolean(refreshed.has_hf_token));
      setMessage('Hugging Face token saved');
      return true;
    } finally {
      setBusy(false);
    }
  }

  async function clearHfToken() {
    setBusy(true);
    try {
      await flush();
      const result = await window.vera.clearHfToken();
      if (!result.ok) {
        setMessage(result.error || 'Unable to remove the Hugging Face token');
        return;
      }
      const refreshed = await onRefresh();
      setHfTokenStored(Boolean(refreshed.has_hf_token));
      setMessage(result.has_api_key
        ? 'App token removed; the process environment still provides HF_TOKEN'
        : 'Hugging Face token removed');
    } finally {
      setBusy(false);
    }
  }

  async function saveEmbeddingSecret(envName: string, value: string): Promise<boolean> {
    setBusy(true);
    try {
      await flush();
      const result = await window.vera.saveEnvSecret(envName, value);
      if (!result.ok) {
        setMessage(result.error || `Unable to save ${envName}`);
        return false;
      }
      const refreshed = await onRefresh();
      setEnvSecretsStored(refreshed.has_env_secrets || {});
      setMessage(`${envName} saved`);
      return true;
    } finally {
      setBusy(false);
    }
  }

  async function clearEmbeddingSecret(envName: string) {
    setBusy(true);
    try {
      await flush();
      const result = await window.vera.clearEnvSecret(envName);
      if (!result.ok) {
        setMessage(result.error || `Unable to remove ${envName}`);
        return;
      }
      const refreshed = await onRefresh();
      setEnvSecretsStored(refreshed.has_env_secrets || {});
      setMessage(result.has_api_key
        ? `${envName} removed from the app; the process environment still provides it`
        : `${envName} removed`);
    } finally {
      setBusy(false);
    }
  }

  const embeddingCredentialProviders = embeddingDescriptors.filter(
    (item) => item.capabilities?.requires_api_key && item.capabilities.credential_env,
  );
  const convertProvider = embeddingProviderFromSpec(embeddingModel);
  const convertDescriptor = embeddingDescriptors.find((item) => item.provider === convertProvider);
  const convertEnv = convertDescriptor?.capabilities?.requires_api_key
    ? convertDescriptor.capabilities.credential_env?.trim() || ''
    : '';
  const convertNeedsKey = Boolean(convertEnv && !envSecretsStored[convertEnv]);
  const convertLabel = EMBEDDING_MODEL_PRESETS.find((preset) => preset.value === embeddingModel.trim())?.label
    || embeddingModel.trim()
    || 'Standard — local semantic (MiniLM)';
  const savedEmbeddingKeys = embeddingCredentialProviders.filter((item) => envSecretsStored[item.capabilities?.credential_env?.trim() || '']);

  function embeddingsSummary(): Summary {
    if (convertNeedsKey) return { tone: 'warn', pill: 'Needs key', detail: `Convert uses ${convertLabel}, but no ${convertEnv} is saved.` };
    const keys = savedEmbeddingKeys.length
      ? `${savedEmbeddingKeys.map(embedderDisplayName).join(', ')} key saved.`
      : 'No key needed.';
    return { tone: 'good', pill: 'Ready', detail: `Convert uses ${convertLabel}. ${keys}` };
  }

  function agentSummary(): Summary {
    if (!agentStatus) return { tone: 'neutral', pill: 'Off', detail: 'Let Claude, Cursor, and other AI apps search your libraries.' };
    if (!agentStatus.enabled) {
      return { tone: 'neutral', pill: 'Off', detail: 'Let Claude, Cursor, and other AI apps search your libraries.' };
    }
    const count = agentStatus.libraryRoots.length;
    const shared = `${count} ${count === 1 ? 'library' : 'libraries'} shared`;
    return { tone: 'good', pill: 'On', detail: agentStatus.cloudEnabled ? `${shared} · cloud agents on` : shared };
  }

  function renderOverview() {
    return (
      <div className="settingsStack">
        <Callout tone="good" title="Search and Convert are ready.">
          <p>They run on this computer with no account or key. Set up the items below only when you need them.</p>
        </Callout>
        <div className="overviewGrid">
          <OverviewCard icon={<UserRound size={18} />} title="Account" summary={accountSummary(account)} onOpen={() => setSection('account')} />
          <OverviewCard icon={<MessageSquareText size={18} />} title="Chat" summary={askSummary(list, activeId, activeModelLocal)} onOpen={() => setSection('providers')} />
          <OverviewCard icon={<Sparkles size={18} />} title="Embeddings" summary={embeddingsSummary()} onOpen={() => setSection('embeddings')} />
          <OverviewCard icon={<Bot size={18} />} title="Agent access" summary={agentSummary()} onOpen={() => setSection('agents')} />
        </div>
        <h4 className="settingsGroupLabel">Advanced</h4>
        <div className="overviewGrid">
          <OverviewCard
            icon={<KeyRound size={18} />}
            title="Hugging Face"
            summary={hfTokenStored
              ? { tone: 'good', pill: 'Token saved', detail: 'Used for Hugging Face Hub downloads.' }
              : { tone: 'neutral', pill: 'Optional', detail: 'Most people do not need a token.' }}
            onOpen={() => setSection('huggingface')}
          />
          <OverviewCard
            icon={<FileText size={18} />}
            title="Diagnostics"
            summary={{ tone: 'neutral', pill: 'Help', detail: 'Open the convert log or check for updates.' }}
            onOpen={() => setSection('diagnostics')}
          />
        </div>
      </div>
    );
  }

  function renderEmbeddings() {
    return (
      <div className="settingsStack">
        <SettingsCard
          icon={<Sparkles size={16} />}
          title="Convert uses"
          badge={convertNeedsKey ? <StatusPill tone="warn">Needs key</StatusPill> : <StatusPill tone="good">Ready</StatusPill>}
        >
          <p className="settingsValue">{convertLabel}</p>
          <p className="providerHint">
            Change it in Convert under Advanced → Search model. The built-in Standard (MiniLM) model runs on this
            computer, works offline, and needs no key.
          </p>
        </SettingsCard>
        {convertNeedsKey ? (
          <Callout tone="warn" title={`Convert needs ${convertEnv}.`}>
            <p>Save the key below, or switch Convert back to the built-in model.</p>
          </Callout>
        ) : null}
        <div className="providerGroupHead">
          <h4 className="settingsGroupLabel">Online search model keys</h4>
        </div>
        <p className="settingsNote">
          Online embedders such as OpenAI bill per conversion, and semantic or hybrid search of those archives needs the
          same key later. Keyword search still works without a key. Keys are stored encrypted and given to VERA's
          converter as environment variables.
        </p>
        {embeddingCredentialProviders.length === 0 ? (
          <p className="mutedText">No online embedding providers that need a key are installed.</p>
        ) : embeddingCredentialProviders.map((descriptor) => {
          const envName = descriptor.capabilities?.credential_env?.trim() || '';
          const stored = Boolean(envSecretsStored[envName]);
          const name = embedderDisplayName(descriptor);
          return (
            <SettingsCard
              key={descriptor.provider}
              icon={<KeyRound size={16} />}
              title={name}
              badge={stored ? <StatusPill tone="good">Key saved</StatusPill> : <StatusPill>Not set</StatusPill>}
              description={descriptor.description || undefined}
            >
              <SecretField
                label={`${name} API key (${envName})`}
                saved={stored}
                placeholder={`Paste ${envName}`}
                onSave={(value) => saveEmbeddingSecret(envName, value)}
                onClear={() => void clearEmbeddingSecret(envName)}
                busy={busy}
                helpLink={envName === 'OPENAI_API_KEY' ? 'openai_api_keys' : undefined}
              />
            </SettingsCard>
          );
        })}
      </div>
    );
  }

  function renderHuggingFace() {
    return (
      <div className="settingsStack">
        <Callout title="Most people can skip this.">
          <p>
            VERA's built-in models are already on this computer. A token only matters when a plugin or a custom model
            downloads files from the Hugging Face Hub, where it raises download rate limits. Public models work without one.
          </p>
        </Callout>
        <SettingsCard
          icon={<KeyRound size={16} />}
          title="Access token"
          badge={hfTokenStored ? <StatusPill tone="good">Saved</StatusPill> : <StatusPill>Not set</StatusPill>}
        >
          <SecretField
            label="Hugging Face token"
            saved={hfTokenStored}
            savedLabel="Token saved"
            placeholder="Paste a Hugging Face token"
            onSave={saveHfToken}
            onClear={() => void clearHfToken()}
            busy={busy}
            helpLink="huggingface_tokens"
            helpLabel="Get a token"
            hint={<>Stored encrypted like provider API keys and passed to the sidecar as <code>HF_TOKEN</code>.</>}
          />
        </SettingsCard>
      </div>
    );
  }

  function renderDiagnostics() {
    return (
      <div className="settingsStack">
        <SettingsCard
          icon={<FileText size={16} />}
          title="Convert log"
          description={(
            <>
              Convert and sidecar messages, including timed convert steps, append to this file in both
              <code> app:dev</code> and packaged VERA. It does not include PDF text or API keys.
            </>
          )}
        >
          <CopyField value={convertLogPath || 'logs/sidecar.log'} />
          <div className="editorActions">
            <button type="button" className="secondaryAction compactAction" onClick={() => { void window.vera.openConvertLog(); }}>
              <FileText size={14} />Open convert log
            </button>
            <button type="button" className="secondaryAction compactAction" onClick={() => { void window.vera.showConvertLogFolder(); }}>
              Show convert log in folder
            </button>
          </div>
        </SettingsCard>
        <SettingsCard
          icon={<RefreshCw size={16} />}
          title="Updates"
          description="Installed Windows builds check GitHub Releases for new versions when VERA starts."
        >
          <div className="editorActions">
            <button type="button" className="secondaryAction compactAction" onClick={() => { void window.vera.checkForUpdates(); }}>
              Check for updates
            </button>
          </div>
        </SettingsCard>
      </div>
    );
  }

  function renderNavButton(entry: SettingsSection) {
    const Icon = entry.icon;
    const active = section === entry.id;
    return (
      <button
        key={entry.id}
        type="button"
        className={active ? 'settingsNavButton active' : 'settingsNavButton'}
        aria-current={active ? 'page' : undefined}
        onClick={() => setSection(entry.id)}
      >
        <Icon size={16} aria-hidden="true" />
        <span className="settingsNavText">
          <span className="settingsNavLabel">{entry.label}</span>
          <span className="settingsNavHint">{entry.hint}</span>
        </span>
      </button>
    );
  }

  const matches = matchSettingsSections(query);
  const searching = query.trim().length > 0;
  const activeSection = SETTINGS_SECTIONS.find((entry) => entry.id === section) ?? SETTINGS_SECTIONS[0];
  let footerStatus: ReactNode = 'Changes save automatically';
  if (message) footerStatus = message;
  else if (saveState === 'saving') footerStatus = 'Saving…';
  else if (saveState === 'saved') footerStatus = <><CheckCircle2 size={14} />All changes saved</>;

  return (
    <div
      className="modalBackdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) void close();
      }}
    >
      <div
        className="modal settingsModal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        onKeyDown={(event) => {
          if (event.key === 'Escape' && !event.defaultPrevented) {
            event.preventDefault();
            void close();
          }
        }}
      >
        <header className="modalHeader">
          <h2 id="settings-title"><Settings size={18} />Settings</h2>
          <button type="button" className="iconAction" onClick={() => void close()} aria-label="Close"><X size={18} /></button>
        </header>

        <div className="settingsLayout">
          <nav className="settingsNav" aria-label="Settings sections">
            <div className="settingsSearch">
              <Search size={14} aria-hidden="true" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && matches[0]) {
                    event.preventDefault();
                    setSection(matches[0].id);
                  }
                  if (event.key === 'Escape' && query) {
                    event.preventDefault();
                    setQuery('');
                  }
                }}
                placeholder="Search settings"
                aria-label="Search settings"
              />
              {query ? (
                <button type="button" className="settingsSearchClear" onClick={() => setQuery('')} aria-label="Clear search">
                  <X size={13} />
                </button>
              ) : null}
            </div>
            {searching ? (
              matches.length ? (
                <div className="settingsNavGroup">{matches.map(renderNavButton)}</div>
              ) : (
                <p className="settingsNavEmpty">No settings match “{query.trim()}”.</p>
              )
            ) : NAV_GROUPS.map((group) => (
              <div className="settingsNavGroup" key={group.id}>
                {group.label ? <h4 className="settingsNavGroupLabel">{group.label}</h4> : null}
                {SETTINGS_SECTIONS.filter((entry) => entry.group === group.id).map(renderNavButton)}
              </div>
            ))}
          </nav>

          <div className="settingsContent" ref={contentRef}>
            <header className="settingsSectionHead">
              <h3>{activeSection.label}</h3>
              <p>{activeSection.description}</p>
            </header>

            {section === 'overview' ? renderOverview() : null}
            {section === 'account' ? (
              <AccountSection onChanged={async () => {
                await flush();
                applySaved(await onRefresh());
              }} />
            ) : null}
            {section === 'providers' ? (
              <ProvidersSection
                providers={list}
                activeProviderId={activeId}
                activeModel={activeModelLocal}
                busy={busy}
                getDraft={() => draftRef.current}
                onProvidersChange={updateList}
                onActiveChange={setAsk}
                onSaveKey={saveProviderKey}
                onClearKey={clearProviderKey}
                onOpenAccount={() => setSection('account')}
                onMessage={setMessage}
              />
            ) : null}
            {section === 'embeddings' ? renderEmbeddings() : null}
            {section === 'agents' ? <AgentAccessSection /> : null}
            {section === 'huggingface' ? renderHuggingFace() : null}
            {section === 'diagnostics' ? renderDiagnostics() : null}
          </div>
        </div>

        <footer className="modalFooter settingsFooter">
          <span className={saveState === 'error' ? 'modalMessage settingsSaveState error' : 'modalMessage settingsSaveState'} role="status" aria-live="polite">
            {footerStatus}
          </span>
          <button type="button" className="primaryAction" onClick={() => void close()}>Done</button>
        </footer>
      </div>
    </div>
  );
}
