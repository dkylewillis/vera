import { createElement, memo, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from 'react';
import Markdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { RegionResult, SourceDocumentResult } from '../types';

/** Split stored Markdown into 1-based display lines, matching ingest locators. */
export function markdownDisplayLines(text: string): string[] {
  return text.replace(/^\uFEFF/, '').split(/\r?\n/);
}

export interface MarkdownRenderBlock {
  start: number;
  end: number;
  source: string;
}

function fenceOpen(line: string): { char: string; length: number } | null {
  const match = /^ {0,3}(`{3,}|~{3,})/.exec(line);
  if (!match) return null;
  return { char: match[1][0], length: match[1].length };
}

function fenceCloses(line: string, open: { char: string; length: number }): boolean {
  const match = /^ {0,3}(`{3,}|~{3,})\s*$/.exec(line);
  return Boolean(match && match[1][0] === open.char && match[1].length >= open.length);
}

function isTableDelimiter(line: string): boolean {
  const trimmed = line.trim();
  if (!trimmed.includes('-')) return false;
  const cells = trimmed.replace(/^\|/, '').replace(/\|$/, '').split('|');
  return cells.length > 0 && cells.every((cell) => /^\s*:?-{3,}:?\s*$/.test(cell));
}

function isTableRow(line: string): boolean {
  return line.includes('|');
}

/** Group source lines into blocks react-markdown can render, keeping line ranges. */
export function markdownRenderBlocks(text: string): MarkdownRenderBlock[] {
  const lines = markdownDisplayLines(text);
  const blocks: MarkdownRenderBlock[] = [];
  let index = 0;
  while (index < lines.length) {
    if (!lines[index].trim()) {
      index += 1;
      continue;
    }
    const start = index;
    const fence = fenceOpen(lines[index]);
    if (fence) {
      index += 1;
      while (index < lines.length && !fenceCloses(lines[index], fence)) index += 1;
      if (index < lines.length) index += 1;
    } else if (isTableRow(lines[index]) && index + 1 < lines.length && isTableDelimiter(lines[index + 1])) {
      index += 2;
      while (index < lines.length && lines[index].trim() && isTableRow(lines[index])) index += 1;
    } else {
      while (index < lines.length && lines[index].trim()) {
        if (index > start && fenceOpen(lines[index])) break;
        if (
          index > start
          && isTableRow(lines[index])
          && index + 1 < lines.length
          && isTableDelimiter(lines[index + 1])
        ) break;
        index += 1;
      }
    }
    blocks.push({
      start: start + 1,
      end: index,
      source: lines.slice(start, index).join('\n'),
    });
  }
  return blocks;
}

function highlightLines(regions: RegionResult[]): Set<number> {
  const lines = new Set<number>();
  for (const region of regions) {
    const start = region.start?.line;
    const end = region.end?.line ?? start;
    if (!start || start < 1) continue;
    const last = Math.max(start, end || start);
    for (let line = start; line <= last; line += 1) lines.add(line);
  }
  return lines;
}

type PositionedNode = {
  position?: {
    start?: { line?: number };
    end?: { line?: number };
  };
};

/** True when a Markdown node's source span covers any highlighted line. */
export function markdownNodeOverlaps(node: unknown, lines: ReadonlySet<number>): boolean {
  const position = (node as PositionedNode | null | undefined)?.position;
  const start = position?.start?.line;
  const end = position?.end?.line ?? start;
  if (!start || !end || lines.size === 0) return false;
  const from = Math.min(start, end);
  const to = Math.max(start, end);
  for (const line of lines) {
    if (line >= from && line <= to) return true;
  }
  return false;
}

const HIGHLIGHT_TAGS = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'pre', 'table', 'blockquote'] as const;

function markdownComponents(
  lines: RefObject<ReadonlySet<number>>,
  claim: RefObject<boolean>,
  firstHighlight: RefObject<HTMLElement | null>,
): Components {
  function mark(node: unknown): { className?: string; ref?: (element: HTMLElement | null) => void } {
    if (!markdownNodeOverlaps(node, lines.current)) return {};
    return {
      className: 'is-highlighted',
      ref: (element) => {
        if (element && !claim.current) {
          claim.current = true;
          firstHighlight.current = element;
        }
      },
    };
  }

  const components: Record<string, (props: { node?: unknown; children?: ReactNode }) => ReactNode> = {
    a: ({ children, node: _node, ...props }) => (
      createElement('a', { ...props, target: '_blank', rel: 'noreferrer' }, children)
    ),
  };
  for (const tag of HIGHLIGHT_TAGS) {
    components[tag] = ({ node, children, ...props }) => {
      const extra = mark(node);
      return createElement(tag, { ...props, className: extra.className, ref: extra.ref }, children);
    };
  }
  return components as Components;
}

export const MarkdownDocument = memo(function MarkdownDocument({
  text,
  highlighted,
}: {
  text: string;
  highlighted: ReadonlySet<number>;
}) {
  const lines = useRef(highlighted);
  const claim = useRef(false);
  const firstHighlight = useRef<HTMLElement | null>(null);
  lines.current = highlighted;
  claim.current = false;
  firstHighlight.current = null;
  const components = useMemo(
    () => markdownComponents(lines, claim, firstHighlight),
    [],
  );

  useLayoutEffect(() => {
    firstHighlight.current?.scrollIntoView({ block: 'center' });
  }, [text, highlighted]);

  return (
    <div className="markdownSourceViewer">
      <div className="markdownBody markdownSourceDocument">
        <Markdown remarkPlugins={[remarkGfm]} components={components}>
          {markdownDisplayLines(text).join('\n')}
        </Markdown>
      </div>
    </div>
  );
});

export interface LineRange {
  start: number;
  end: number;
}

/** Indexes of the ranges that cover any highlighted line. */
export function overlappingRanges(ranges: readonly LineRange[], lines: ReadonlySet<number>): number[] {
  if (lines.size === 0) return [];
  const hits: number[] = [];
  ranges.forEach((range, index) => {
    for (const line of lines) {
      if (line >= range.start && line <= range.end) {
        hits.push(index);
        return;
      }
    }
  });
  return hits;
}

type IndexedElement = LineRange & { element: HTMLElement };

const PreparedHtml = memo(function PreparedHtml({
  html,
  containerRef,
}: {
  html: string;
  containerRef: RefObject<HTMLDivElement | null>;
}) {
  return (
    <div
      className="markdownBody markdownSourceDocument"
      ref={containerRef}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
});

/** Sidecar-rendered Markdown. Highlights toggle classes instead of re-rendering. */
export function MarkdownHtmlDocument({
  html,
  highlighted,
}: {
  html: string;
  highlighted: ReadonlySet<number>;
}) {
  const container = useRef<HTMLDivElement>(null);
  const indexed = useRef<IndexedElement[]>([]);
  const marked = useRef<HTMLElement[]>([]);

  useLayoutEffect(() => {
    const root = container.current;
    marked.current = [];
    if (!root) {
      indexed.current = [];
      return;
    }
    indexed.current = Array.from(root.querySelectorAll<HTMLElement>('[data-ls]')).map((node) => {
      const parent = node.parentElement;
      const element = node.tagName === 'CODE' && parent?.tagName === 'PRE' ? parent : node;
      return {
        element,
        start: Number(node.dataset.ls),
        end: Number(node.dataset.le),
      };
    });
  }, [html]);

  useLayoutEffect(() => {
    for (const element of marked.current) element.classList.remove('is-highlighted');
    const hits = overlappingRanges(indexed.current, highlighted);
    marked.current = hits.map((index) => indexed.current[index].element);
    for (const element of marked.current) element.classList.add('is-highlighted');
    marked.current[0]?.scrollIntoView({ block: 'center' });
  }, [html, highlighted]);

  return (
    <div className="markdownSourceViewer">
      <PreparedHtml html={html} containerRef={container} />
    </div>
  );
}

type LoadedMarkdown = { kind: 'html' | 'markdown'; body: string };

async function fetchText(url: string): Promise<string> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Unable to load Markdown (${response.status})`);
  return response.text();
}

export function MarkdownSourceViewer({
  source,
  highlightRegions = [],
}: {
  source: SourceDocumentResult;
  highlightRegions?: RegionResult[];
}) {
  const [loaded, setLoaded] = useState<LoadedMarkdown | null>(null);
  const [error, setError] = useState<string | null>(null);
  const highlighted = useMemo(() => highlightLines(highlightRegions), [highlightRegions]);

  useEffect(() => {
    let cancelled = false;
    setLoaded(null);
    setError(null);
    const load = async (): Promise<LoadedMarkdown> => {
      if (source.html_url) {
        try {
          return { kind: 'html', body: await fetchText(source.html_url) };
        } catch {
          // Fall back to parsing the Markdown in the renderer.
        }
      }
      return { kind: 'markdown', body: await fetchText(source.url) };
    };
    void load()
      .then((result) => {
        if (!cancelled) setLoaded(result);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : 'Unable to load Markdown');
      });
    return () => {
      cancelled = true;
    };
  }, [source.url, source.html_url]);

  if (error) {
    return (
      <div className="unsupportedSource">
        <strong>{source.filename}</strong>
        <span>{error}</span>
      </div>
    );
  }
  if (loaded === null) {
    return (
      <div className="unsupportedSource">
        <strong>{source.filename}</strong>
        <span>Loading Markdown…</span>
      </div>
    );
  }

  if (loaded.kind === 'html') {
    return <MarkdownHtmlDocument html={loaded.body} highlighted={highlighted} />;
  }
  return <MarkdownDocument text={loaded.body} highlighted={highlighted} />;
}
