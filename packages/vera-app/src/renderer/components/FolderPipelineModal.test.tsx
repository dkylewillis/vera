import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { FolderPipelineModal, type FolderPipelinePrompt } from './FolderPipelineModal';

const choices = [
  { spec: 'pymupdf', label: 'PyMuPDF', description: 'Default PDF pipeline', alsoReads: [] },
  { spec: 'plans', label: 'Plans', description: 'Drawing sets', alsoReads: [] },
];

function prompt(extra: Partial<FolderPipelinePrompt> = {}): FolderPipelinePrompt {
  return {
    title: 'How should this library convert PDFs?',
    subtitle: 'C:\\Jobs',
    choices,
    selected: 'pymupdf',
    saveLabel: 'Continue',
    cancelLabel: 'Use default',
    ...extra,
  };
}

describe('FolderPipelineModal', () => {
  it('keeps folder rules collapsed on a new library', () => {
    const html = renderToStaticMarkup(
      <FolderPipelineModal
        prompt={prompt({
          collectFolderRules: true,
          rootPath: 'C:\\Jobs',
          note: 'Folders you leave out keep this choice.',
        })}
        onSave={() => undefined}
        onCancel={() => undefined}
      />,
    );
    expect(html).toContain('Different folders use a different pipeline');
    expect(html).toContain('aria-expanded="false"');
    expect(html).not.toContain('Projects/*/Plans');
    expect(html).toContain('Folders you leave out keep this choice.');
  });

  it('leaves the folder list off the dialog that edits one existing folder', () => {
    const html = renderToStaticMarkup(
      <FolderPipelineModal
        prompt={prompt({
          title: 'PDF pipeline for this folder',
          inheritLabel: 'Uses PyMuPDF.',
          inheritTitle: 'Same as parent folder',
          selected: '',
          saveLabel: 'Save and sync',
        })}
        onSave={() => undefined}
        onCancel={() => undefined}
      />,
    );
    expect(html).not.toContain('Different folders use a different pipeline');
    expect(html).toContain('Same as parent folder');
  });
});
