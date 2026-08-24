import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { SettingsModal, type SettingsSectionId } from './ProviderManagers';
import type { AppSettings } from '../types';

const settings: AppSettings = {
  providers: [],
  active_provider_id: '',
  active_model: '',
  active_mode_id: '',
  embedding_model: 'hashing',
  ingest_pipeline: 'pymupdf',
  ingest_pipeline_configs: {},
};

function renderSettings(initialSection?: SettingsSectionId) {
  return renderToStaticMarkup(
    <SettingsModal
      providers={[]}
      activeProviderId=""
      activeModel=""
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
  it('titles the dialog Settings and lists LLM Providers as a section', () => {
    const html = renderSettings();
    expect(html).toContain('id="settings-title"');
    expect(html).toContain('Settings');
    expect(html).toContain('LLM Providers');
    expect(html).toContain('Embeddings');
    expect(html).toContain('Hugging Face');
    expect(html).toContain('Diagnostics');
    expect(html).not.toContain('Python plugins');
    expect(html).toContain('Hosted');
    expect(html).toContain('Local');
    expect(html).toContain('OpenAI');
    expect(html).not.toContain('Use an external Python environment');
    expect(html).not.toContain('huggingface.co/settings/tokens');
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
    expect(html).not.toContain('Paste OpenAI key');
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
    expect(html).toContain('OPENAI_API_KEY');
    expect(html).toContain('Paste OPENAI_API_KEY');
    expect(html).toContain('bill per conversion');
  });
});
