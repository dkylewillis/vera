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
      externalPython={{ enabled: false, executable: '' }}
      pythonStatus={null}
      initialSection={initialSection}
      onPersist={async () => settings}
      onRefresh={async () => settings}
      onExternalPythonChange={() => undefined}
      onPickPython={() => undefined}
      onValidatePython={() => undefined}
      onRefreshPipelines={() => undefined}
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
    expect(html).toContain('Hugging Face');
    expect(html).toContain('Python plugins');
    expect(html).toContain('Hosted');
    expect(html).toContain('Local');
    expect(html).toContain('OpenAI');
    expect(html).not.toContain('Use an external Python environment');
    expect(html).not.toContain('huggingface.co/settings/tokens');
  });

  it('opens the Hugging Face section when requested', () => {
    const html = renderSettings('huggingface');
    expect(html).toContain('huggingface.co/settings/tokens');
    expect(html).toContain('HF_TOKEN');
    expect(html).not.toContain('Paste OpenAI key');
  });

  it('opens the Python plugins section when requested', () => {
    const html = renderSettings('python');
    expect(html).toContain('Use an external Python environment');
    expect(html).toContain('trusted');
    expect(html).not.toContain('Paste OpenAI key');
  });
});
