import { SIDECAR_ACTIONS } from '../../shared/protocol';
import type { PipelineDescriptor } from '../../shared/contracts';
import type { VeraResponse } from '../types';
import { pipelineAcceptsPdf } from './convertPresets';

type Request = <T>(payload: Record<string, unknown>) => Promise<VeraResponse<T>>;

export const DEFAULT_PDF_PIPELINE = 'pymupdf';

export type LibraryPipelineRule = {
  folder: string;
  parser: string;
  pipeline_options?: Record<string, unknown>;
};

export type LibraryPipelines = {
  directory: string;
  parser: string | null;
  rules: LibraryPipelineRule[];
};

/** Providers that never read PDFs; used when the sidecar did not describe a pipeline. */
const NON_PDF_PROVIDERS = new Set(['markdown', 'ooxml']);

function sameSpec(a: string, b: string): boolean {
  return a.trim().toLowerCase() === b.trim().toLowerCase();
}

function findDescriptor(spec: string, descriptors: PipelineDescriptor[] = []): PipelineDescriptor | undefined {
  return descriptors.find((descriptor) => sameSpec(descriptor.spec, spec));
}

function readsPdf(spec: string, descriptors?: PipelineDescriptor[]): boolean {
  const descriptor = findDescriptor(spec, descriptors);
  if (descriptor) return pipelineAcceptsPdf(descriptor);
  return !NON_PDF_PROVIDERS.has(spec.split(':', 1)[0].trim().toLowerCase());
}

function segments(folder: string): string[] {
  return folder.split(/[\\/]+/).filter((part) => part && part !== '.');
}

function sameFolder(a: string, b: string): boolean {
  return segments(a).join('/').toLowerCase() === segments(b).join('/').toLowerCase();
}

function segmentMatches(name: string, pattern: string): boolean {
  const escaped = pattern
    .toLowerCase()
    .replace(/[.+^${}()|[\]\\]/g, '\\$&')
    .replace(/\*/g, '.*')
    .replace(/\?/g, '.');
  return new RegExp(`^${escaped}$`).test(name.toLowerCase());
}

/** `folder` relative to `root` with `/` separators; `''` is the root, `null` when outside. */
export function libraryRelativeFolder(root: string, folder: string): string | null {
  const rootParts = segments(root);
  const folderParts = segments(folder);
  if (folderParts.length < rootParts.length) return null;
  for (let index = 0; index < rootParts.length; index += 1) {
    if (rootParts[index].toLowerCase() !== folderParts[index].toLowerCase()) return null;
  }
  return folderParts.slice(rootParts.length).join('/');
}

export type FolderPdfPipeline = {
  parser: string;
  /** Folder of the rule that chose it, `''` for a whole-library rule, `null` for the default. */
  ruleFolder: string | null;
};

/**
 * The pipeline that converts PDFs in `folder` (library-relative).
 * Mirrors `vera_ingest.library._PipelineResolver`: the deepest matching rule
 * wins, a later rule wins a tie, and `*` matches one folder name.
 */
export function pdfPipelineFor(
  pipelines: LibraryPipelines,
  folder: string,
  options: { ignoreFolder?: string; descriptors?: PipelineDescriptor[] } = {},
): FolderPdfPipeline {
  const path = segments(folder);
  let best: LibraryPipelineRule | null = null;
  let bestDepth = -1;
  for (const rule of pipelines.rules) {
    if (!readsPdf(rule.parser, options.descriptors)) continue;
    if (options.ignoreFolder !== undefined && sameFolder(rule.folder, options.ignoreFolder)) continue;
    const pattern = segments(rule.folder);
    if (pattern.length > path.length || pattern.length < bestDepth) continue;
    if (!pattern.every((part, index) => segmentMatches(path[index], part))) continue;
    best = rule;
    bestDepth = pattern.length;
  }
  if (best) return { parser: best.parser, ruleFolder: segments(best.folder).join('/') };
  const fallback = pipelines.parser && readsPdf(pipelines.parser, options.descriptors)
    ? pipelines.parser
    : DEFAULT_PDF_PIPELINE;
  return { parser: fallback, ruleFolder: null };
}

export type PdfPipelineChoice = {
  spec: string;
  label: string;
  description: string;
  /** Other formats the pipeline also converts when chosen, such as `docx`. */
  alsoReads: string[];
};

const FALLBACK_CHOICES: PdfPipelineChoice[] = [
  { spec: DEFAULT_PDF_PIPELINE, label: 'pymupdf — default PDF pipeline', description: '', alsoReads: [] },
];

/** Installed pipelines that read PDFs, in sidecar order. */
export function pdfPipelineChoices(descriptors: PipelineDescriptor[]): PdfPipelineChoice[] {
  const choices = descriptors
    .filter((descriptor) => descriptor.installed && pipelineAcceptsPdf(descriptor))
    .map((descriptor) => ({
      spec: descriptor.spec,
      label: descriptor.label || descriptor.spec,
      description: descriptor.description || '',
      alsoReads: (descriptor.capabilities?.source_formats ?? [])
        .map((format) => format.replace(/^\./, '').toLowerCase())
        .filter((format) => format !== 'pdf'),
    }));
  return choices.length ? choices : FALLBACK_CHOICES;
}

/** New libraries only ask which PDF pipeline to use when a plugin adds a second one. */
export function shouldAskPdfPipeline(descriptors: PipelineDescriptor[]): boolean {
  return pdfPipelineChoices(descriptors).length > 1;
}

/** What the new-library dialog returns. `null` from the caller means "use pymupdf and start". */
export type LibraryPdfSetup = {
  /** Whole-library PDF pipeline, or `null` to keep pymupdf with no root rule. */
  parser: string | null;
  /** Extra folder rules. Each `folder` is library-relative and may use `*` or `?`. */
  rules: { folder: string; parser: string }[];
};

export type SetupFolderDraft = { folder: string; parser: string };

/**
 * Turn one typed or picked folder into a library-relative rule path.
 * `folder: ''` means the path is the library root, which the dialog's main
 * choice already covers.
 */
export function normalizeLibraryRuleFolder(
  root: string,
  folder: string,
): { folder: string } | { error: string } {
  const text = folder.trim();
  if (!text || text === '.') return { folder: '' };
  const absolute = /^[A-Za-z]:[\\/]/.test(text) || text.startsWith('\\\\') || text.startsWith('/');
  let relative = text.replace(/\\/g, '/');
  if (absolute) {
    const inside = libraryRelativeFolder(root, text);
    if (inside === null) return { error: 'That folder is outside this library.' };
    relative = inside;
  }
  const parts = relative.split('/').filter((part) => part && part !== '.');
  if (parts.some((part) => part === '..')) return { error: 'Folder must stay inside the library.' };
  if (parts[0]?.toLowerCase() === '.vera') {
    return { error: '.vera is managed by VERA and cannot have a pipeline rule.' };
  }
  return { folder: parts.join('/') };
}

/**
 * Folder rules to store before the first sync. Blank rows are skipped.
 * Two rows for the same folder keep the later pipeline.
 */
export function librarySetupPipelineRules(
  root: string,
  drafts: SetupFolderDraft[],
): { rules: { folder: string; parser: string }[]; error: string | null } {
  const rules: { folder: string; parser: string }[] = [];
  const seen = new Map<string, number>();
  for (const draft of drafts) {
    if (!draft.folder.trim()) continue;
    const normalized = normalizeLibraryRuleFolder(root, draft.folder);
    if ('error' in normalized) return { rules: [], error: normalized.error };
    if (!normalized.folder) return { rules: [], error: 'The whole library uses the choice above.' };
    const parser = draft.parser.trim();
    if (!parser) return { rules: [], error: 'Choose a pipeline for each folder.' };
    const key = normalized.folder.toLowerCase();
    const rule = { folder: normalized.folder, parser };
    const existing = seen.get(key);
    if (existing === undefined) {
      seen.set(key, rules.length);
      rules.push(rule);
    } else {
      rules[existing] = rule;
    }
  }
  return { rules, error: null };
}

/** Short name for a pipeline spec, for example `plans` from its descriptor label. */
export function pipelineDisplayName(spec: string, descriptors?: PipelineDescriptor[]): string {
  const label = findDescriptor(spec, descriptors)?.label;
  return label || spec;
}

/** Where an inherited pipeline comes from, for example "the library default" or "Projects/*\/Plans". */
export function pipelineSourceLabel(ruleFolder: string | null): string {
  if (ruleFolder === null) return 'the library default';
  if (ruleFolder === '') return 'the whole library';
  return ruleFolder;
}

export type FolderPipelineState = {
  /** The PDF rule stored on exactly this folder, if any. */
  own: string | null;
  /** What PDFs here would use without `own`. */
  inherited: FolderPdfPipeline;
  /** What PDFs here use now. */
  effective: FolderPdfPipeline;
};

export function folderPipelineState(
  pipelines: LibraryPipelines,
  folder: string,
  descriptors?: PipelineDescriptor[],
): FolderPipelineState {
  const ownRules = pipelines.rules.filter((rule) => sameFolder(rule.folder, folder) && readsPdf(rule.parser, descriptors));
  const own = ownRules.length ? ownRules[ownRules.length - 1].parser : null;
  return {
    own,
    inherited: pdfPipelineFor(pipelines, folder, { ignoreFolder: folder, descriptors }),
    effective: pdfPipelineFor(pipelines, folder, { descriptors }),
  };
}

export async function loadLibraryPipelines(root: string, request: Request): Promise<LibraryPipelines | null> {
  const response = await request<LibraryPipelines>({ action: SIDECAR_ACTIONS.libraryPipelines, path: root });
  return response.ok ? response.result ?? null : null;
}

/**
 * Set the PDF pipeline for `folderPath`, an absolute folder in a library.
 * `parser: null` removes the folder's PDF rule so it follows its parent again.
 */
export async function saveFolderPipeline(
  folderPath: string,
  parser: string | null,
  request: Request,
): Promise<LibraryPipelines> {
  const response = await request<LibraryPipelines>({
    action: SIDECAR_ACTIONS.librarySetPipeline,
    path: folderPath,
    parser,
    source_format: 'pdf',
  });
  if (!response.ok || !response.result) throw new Error(response.error || 'Unable to change the folder pipeline');
  return response.result;
}
