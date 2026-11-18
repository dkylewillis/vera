import { describe, expect, it } from 'vitest';
import type { PipelineDescriptor } from '../../shared/contracts';
import {
  folderPipelineState,
  libraryRelativeFolder,
  pdfPipelineChoices,
  pdfPipelineFor,
  saveFolderPipeline,
  shouldAskPdfPipeline,
  type LibraryPipelines,
} from './libraryPipelines';

const PLANS = 'plans';

const library = (rules: LibraryPipelines['rules'], parser: string | null = null): LibraryPipelines => ({
  directory: 'C:\\Projects',
  parser,
  rules,
});

describe('libraryRelativeFolder', () => {
  it('maps folders inside the library and rejects others', () => {
    expect(libraryRelativeFolder('C:\\Projects', 'C:\\Projects')).toBe('');
    expect(libraryRelativeFolder('C:\\Projects', 'c:\\projects\\Lagrange\\Plans')).toBe('Lagrange/Plans');
    expect(libraryRelativeFolder('C:\\Projects', 'C:\\Other')).toBeNull();
    expect(libraryRelativeFolder('/home/me/lib', '/home/me/lib/Plans/')).toBe('Plans');
  });
});

describe('pdfPipelineFor', () => {
  it('uses the deepest matching rule and lets * match one folder', () => {
    const pipelines = library([
      { folder: '', parser: PLANS },
      { folder: 'Lagrange/*/Reports', parser: 'pymupdf' },
      { folder: 'Lagrange', parser: 'markdown' },
    ]);
    expect(pdfPipelineFor(pipelines, 'Lagrange')).toEqual({ parser: PLANS, ruleFolder: '' });
    expect(pdfPipelineFor(pipelines, 'lagrange/Phase 1/reports/old')).toEqual({
      parser: 'pymupdf',
      ruleFolder: 'Lagrange/*/Reports',
    });
    expect(pdfPipelineFor(pipelines, 'Lagrange/A/B/Reports').parser).toBe(PLANS);
  });

  it('falls back to the library parser, then pymupdf', () => {
    expect(pdfPipelineFor(library([]), 'Plans')).toEqual({ parser: 'pymupdf', ruleFolder: null });
    expect(pdfPipelineFor(library([], PLANS), 'Plans').parser).toBe(PLANS);
    expect(pdfPipelineFor(library([], 'markdown'), 'Plans').parser).toBe('pymupdf');
  });
});

const descriptor = (spec: string, formats: string[], installed = true): PipelineDescriptor => ({
  provider: spec.split(':')[0],
  variant: spec.split(':')[1] ?? '',
  spec,
  label: `${spec} label`,
  description: `${spec} description`,
  installed,
  capabilities: { source_formats: formats },
  fields: [],
});

describe('folderPipelineState', () => {
  it('separates the folder rule from what the parent gives', () => {
    const pipelines = library([
      { folder: 'Projects/*/Plans', parser: PLANS },
      { folder: 'Projects/Tower/Plans', parser: 'markdown' },
      { folder: 'Projects/Tower/Plans', parser: 'docling' },
    ]);
    const descriptors = [descriptor('markdown', ['md']), descriptor('docling', ['pdf', 'docx'])];
    expect(folderPipelineState(pipelines, 'projects/tower/plans', descriptors)).toEqual({
      own: 'docling',
      inherited: { parser: PLANS, ruleFolder: 'Projects/*/Plans' },
      effective: { parser: 'docling', ruleFolder: 'Projects/Tower/Plans' },
    });
    expect(folderPipelineState(pipelines, 'Projects/Mall/Plans', descriptors).own).toBeNull();
  });
});

describe('pdfPipelineChoices', () => {
  it('lists installed PDF pipelines with the other formats they take over', () => {
    const choices = pdfPipelineChoices([
      descriptor('pymupdf', ['pdf']),
      descriptor('markdown', ['md']),
      descriptor('docling', ['pdf', '.docx']),
      descriptor('fancy', ['pdf'], false),
    ]);
    expect(choices.map((choice) => [choice.spec, choice.alsoReads])).toEqual([
      ['pymupdf', []],
      ['docling', ['docx']],
    ]);
    expect(pdfPipelineChoices([]).map((choice) => choice.spec)).toEqual(['pymupdf']);
  });

  it('only asks new libraries to pick when a plugin adds a second PDF pipeline', () => {
    expect(shouldAskPdfPipeline([])).toBe(false);
    expect(shouldAskPdfPipeline([descriptor('pymupdf', ['pdf']), descriptor('markdown', ['md'])])).toBe(false);
    expect(shouldAskPdfPipeline([descriptor('pymupdf', ['pdf']), descriptor(PLANS, ['pdf'])])).toBe(true);
  });
});

describe('saveFolderPipeline', () => {
  it('sends the folder path and surfaces sidecar errors', async () => {
    const calls: Record<string, unknown>[] = [];
    const ok = await saveFolderPipeline('C:\\Projects\\Plans', PLANS, async <T>(payload: Record<string, unknown>) => {
      calls.push(payload);
      return { ok: true, result: library([{ folder: 'Plans', parser: PLANS }]) as T };
    });
    expect(calls).toEqual([{
      action: 'library_set_pipeline',
      path: 'C:\\Projects\\Plans',
      parser: PLANS,
      source_format: 'pdf',
    }]);
    expect(ok.rules).toHaveLength(1);
    await expect(
      saveFolderPipeline('C:\\Projects\\Plans', null, async () => ({ ok: false, error: 'No managed library' })),
    ).rejects.toThrow('No managed library');
  });
});
