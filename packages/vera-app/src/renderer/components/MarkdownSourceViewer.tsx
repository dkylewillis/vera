import { useEffect, useMemo, useRef, useState } from 'react';
import type { RegionResult, SourceDocumentResult } from '../types';

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

export function MarkdownSourceViewer({
  source,
  highlightRegions = [],
}: {
  source: SourceDocumentResult;
  highlightRegions?: RegionResult[];
}) {
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const firstHighlight = useRef<HTMLElement | null>(null);
  const highlighted = useMemo(() => highlightLines(highlightRegions), [highlightRegions]);

  useEffect(() => {
    let cancelled = false;
    setText(null);
    setError(null);
    void fetch(source.url)
      .then((response) => {
        if (!response.ok) throw new Error(`Unable to load Markdown (${response.status})`);
        return response.text();
      })
      .then((body) => {
        if (!cancelled) setText(body);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : 'Unable to load Markdown');
      });
    return () => {
      cancelled = true;
    };
  }, [source.url]);

  useEffect(() => {
    firstHighlight.current?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [text, highlighted]);

  if (error) {
    return (
      <div className="unsupportedSource">
        <strong>{source.filename}</strong>
        <span>{error}</span>
      </div>
    );
  }
  if (text === null) {
    return (
      <div className="unsupportedSource">
        <strong>{source.filename}</strong>
        <span>Loading Markdown…</span>
      </div>
    );
  }

  const lines = text.split(/\r?\n/);
  let assignedFirst = false;
  return (
    <div className="markdownSourceViewer">
      <pre className="markdownSourcePre">
        {lines.map((line, index) => {
          const lineNumber = index + 1;
          const active = highlighted.has(lineNumber);
          const ref = active && !assignedFirst
            ? (node: HTMLElement | null) => {
              firstHighlight.current = node;
            }
            : undefined;
          if (active && !assignedFirst) assignedFirst = true;
          return (
            <span
              key={lineNumber}
              ref={ref}
              className={active ? 'markdownSourceLine is-highlighted' : 'markdownSourceLine'}
            >
              <span className="markdownSourceGutter">{lineNumber}</span>
              <span className="markdownSourceText">{line || ' '}</span>
            </span>
          );
        })}
      </pre>
    </div>
  );
}
