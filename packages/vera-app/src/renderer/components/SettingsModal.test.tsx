import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import {
  accountSummary,
  askSummary,
  matchSettingsSections,
  SettingsModal,
  type SettingsSectionId,
} from './SettingsModal';
import type { ProAccount } from '../../shared/pro';
import type { AppSettings, ProviderProfile } from '../types';

const settings: AppSettings = {
  providers: [],
  active_provider_id: '',
  active_model: '',
  active_mode_id: '',
  embedding_model: 'hashing',
  ingest_pipeline: 'pymupdf',
  ingest_pipeline_configs: {},
};

const openai: ProviderProfile = {
  id: 'p1',
  label: 'OpenAI',
  provider: 'openai_compatible',
  preset_key: 'openai',
  base_url: 'https://api.openai.com/v1',
  api_key_env: 'OPENAI_API_KEY',
  auth_type: 'api_key',
  has_api_key: true,
  models: ['gpt-4o-mini'],
  temperature: 0.2,
};

function renderSettings(initialSection?: SettingsSectionId, providers: ProviderProfile[] = []) {
  return renderToStaticMarkup(
    <SettingsModal
      providers={providers}
      activeProviderId={providers[0]?.id ?? ''}
      activeModel={providers[0]?.models[0] ?? ''}
      activeModeId=""
      embeddingModel="hashing"
      ingestPipeline="pymupdf"
      ingestPipelineConfigs={{}}
      embedderConfigs={{}}
      initialSection={initialSection}
      onPersist={async () => settings}
      onRefresh={async () => settings}
      onClose={() => undefined}
    />,
  );
}

describe('SettingsModal', () => {
  it('opens on an overview with grouped, searchable sections', () => {
    const html = renderSettings();
    expect(html).toContain('id="settings-title"');
    expect(html).toContain('Search settings');
    expect(html).toContain('Search and Convert are ready.');
    for (const label of ['Overview', 'Account', 'AI providers', 'Embeddings', 'Agent access', 'Hugging Face', 'Diagnostics']) {
      expect(html).toContain(label);
    }
    expect(html).toContain('AI and search');
    expect(html).toContain('Advanced');
    expect(html).toContain('VERA Pro');
    expect(html).toContain('Changes save automatically');
    expect(html).toContain('Done');
    expect(html).not.toContain('LLM Providers');
    expect(html).not.toContain('Save &amp; Close');
    expect(html).not.toContain('Python plugins');
    expect(html).not.toContain('huggingface.co/settings/tokens');
  });

  it('groups AI providers by where they run and shows the chat model picker', () => {
    const html = renderSettings('providers');
    expect(html).toContain('Chat model');
    expect(html).toContain('Chat is not set up yet.');
    expect(html).not.toContain('Ask');
    expect(html).toContain('Online services');
    expect(html).toContain('On this computer');
    expect(html).toContain('OpenAI');
    expect(html).toContain('OpenRouter');
    expect(html).toContain('Ollama');
    expect(html).toContain('LM Studio');
    expect(html).toContain('Add a custom endpoint');
    expect(html).not.toContain('Use an external Python environment');
  });

  it('marks a configured provider as ready and the default', () => {
    const html = renderSettings('providers', [openai]);
    expect(html).toContain('>Default<');
    expect(html).toContain('Ready');
    expect(html).toContain('gpt-4o-mini');
    expect(html).not.toContain('Chat is not set up yet.');
    expect(html).not.toContain('Used for Ask');
  });

  it('opens Account with sign-in and Get VERA Pro', () => {
    const html = renderSettings('account');
    expect(html).toContain('Sign in');
    expect(html).toContain('Get VERA Pro');
    expect(html).not.toContain('Activate Pro');
    expect(html).toContain('Search stays on this computer');
  });

  it('opens the Diagnostics section when requested', () => {
    const html = renderToStaticMarkup(
      <SettingsModal
        providers={[]}
        activeProviderId=""
        activeModel=""
        activeModeId=""
        embeddingModel="hashing"
        ingestPipeline="pymupdf"
        ingestPipelineConfigs={{}}
        embedderConfigs={{}}
        convertLogPath="C:\\Users\\me\\AppData\\Roaming\\VERA\\logs\\sidecar.log"
        initialSection="diagnostics"
        onPersist={async () => settings}
        onRefresh={async () => settings}
        onClose={() => undefined}
      />,
    );
    expect(html).toContain('sidecar.log');
    expect(html).toContain('Open convert log');
    expect(html).toContain('Show convert log in folder');
    expect(html).toContain('app:dev');
    expect(html).toContain('Check for updates');
    expect(html).not.toContain('Paste OpenAI key');
  });

  it('explains that the Hugging Face token is optional', () => {
    const html = renderSettings('huggingface');
    expect(html).toContain('Most people can skip this.');
    expect(html).toContain('Get a token');
    expect(html).toContain('HF_TOKEN');
    expect(html).not.toContain('huggingface.co/settings/tokens');
  });

  it('opens Agent access on the cloud assistant path for a first-time user', () => {
    const html = renderSettings('agents');
    expect(html).toContain('Off. Add a folder to get started.');
    expect(html).toContain('Choose folders');
    expect(html).toContain('Add folder');
    expect(html).toContain('Where does your AI run?');
    expect(html).toContain('In the cloud');
    expect(html).toContain('on the web, desktop, or phone');
    expect(html).not.toContain('web browser');
    expect(html).toContain('On this computer');
    expect(html).toContain('Cursor, VS Code, Claude Desktop');
    expect(html).toContain('Connect a cloud assistant');
    expect(html).toContain('secure relay');
    expect(html).toContain('Sign in');
    expect(html).toContain('Get Agent Access');
    expect(html).toContain('VERA Pro does not include it.');
    expect(html).toContain('model provider');
    expect(html).not.toContain('Setup snippet');
    expect(html).not.toContain('Rotate token');
    expect(html).not.toContain('Manage computers');
  });

  it('opens the Embeddings section with hosted credential fields', () => {
    const html = renderToStaticMarkup(
      <SettingsModal
        providers={[]}
        activeProviderId=""
        activeModel=""
        activeModeId=""
        embeddingModel="hashing"
        ingestPipeline="pymupdf"
        ingestPipelineConfigs={{}}
        embedderConfigs={{}}
        embeddingDescriptors={[
          {
            provider: 'openai',
            label: 'openai — hosted embeddings',
            description: 'OpenAI embeddings API',
            installed: true,
            fields: [],
            capabilities: { requires_api_key: true, credential_env: 'OPENAI_API_KEY' },
          },
        ]}
        initialSection="embeddings"
        onPersist={async () => settings}
        onRefresh={async () => settings}
        onClose={() => undefined}
      />,
    );
    expect(html).toContain('Convert uses');
    expect(html).toContain('OPENAI_API_KEY');
    expect(html).toContain('Paste OPENAI_API_KEY');
    expect(html).toContain('bill per conversion');
  });

  it('warns when Convert uses an embedder whose key is missing', () => {
    const html = renderToStaticMarkup(
      <SettingsModal
        providers={[]}
        activeProviderId=""
        activeModel=""
        activeModeId=""
        embeddingModel="openai:text-embedding-3-small"
        ingestPipeline="pymupdf"
        ingestPipelineConfigs={{}}
        embedderConfigs={{}}
        embeddingDescriptors={[
          {
            provider: 'openai',
            label: 'openai — hosted embeddings',
            description: 'OpenAI embeddings API',
            installed: true,
            fields: [],
            capabilities: { requires_api_key: true, credential_env: 'OPENAI_API_KEY' },
          },
        ]}
        initialSection="embeddings"
        onPersist={async () => settings}
        onRefresh={async () => settings}
        onClose={() => undefined}
      />,
    );
    expect(html).toContain('Convert needs OPENAI_API_KEY.');
    expect(html).toContain('Needs key');
  });
});

describe('matchSettingsSections', () => {
  it('returns every section for an empty query', () => {
    expect(matchSettingsSections('  ').map((entry) => entry.id)).toContain('diagnostics');
  });

  it('finds sections by everyday words, not only their labels', () => {
    expect(matchSettingsSections('api key').map((entry) => entry.id)).toContain('providers');
    expect(matchSettingsSections('ollama').map((entry) => entry.id)).toEqual(['providers']);
    expect(matchSettingsSections('log').map((entry) => entry.id)).toContain('diagnostics');
    expect(matchSettingsSections('HF_TOKEN').map((entry) => entry.id)).toEqual(['huggingface']);
    expect(matchSettingsSections('subscription').map((entry) => entry.id)).toContain('account');
    expect(matchSettingsSections('mcp claude').map((entry) => entry.id)).toEqual(['agents']);
  });

  it('returns nothing when no section matches every word', () => {
    expect(matchSettingsSections('zzzz nothing')).toEqual([]);
  });
});

describe('settings summaries', () => {
  it('summarizes the chat model', () => {
    expect(askSummary([], '', '').pill).toBe('Not set up');
    expect(askSummary([openai], 'p1', 'gpt-4o-mini')).toMatchObject({ tone: 'good', pill: 'Ready' });
    expect(askSummary([openai], 'p1', 'gpt-4o-mini').detail).toContain('gpt-4o-mini');
    expect(askSummary([{ ...openai, has_api_key: false }], 'p1', 'gpt-4o-mini')).toMatchObject({ tone: 'warn', pill: 'Needs key' });
    expect(askSummary([openai], 'p1', 'retired-model').pill).toBe('Choose a model');
  });

  it('summarizes the VERA Pro account', () => {
    const base: ProAccount = {
      configured: true,
      siteUrl: '',
      signedIn: false,
      email: '',
      subscriptionStatus: '',
      agentAccessStatus: '',
      hasProKey: false,
      usageUsd: null,
      limitUsd: null,
      remainingUsd: null,
      includedPercent: null,
      onDemandEnabled: false,
      onDemandUsedUsd: null,
      onDemandLimitUsd: null,
    };
    expect(accountSummary(base).pill).toBe('Signed out');
    expect(accountSummary({ ...base, signedIn: true, email: 'me@example.com', subscriptionStatus: 'active' })).toMatchObject({
      tone: 'accent',
      pill: 'Pro',
    });
    expect(accountSummary({ ...base, signedIn: true, email: 'me@example.com' }).pill).toBe('Signed in');
    expect(accountSummary({ ...base, configured: false }).pill).toBe('Unavailable');
  });
});
