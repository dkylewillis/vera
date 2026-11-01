import { useEffect, useMemo, useRef, useState } from 'react';
import type { RegionResult, SourceDocumentResult } from '../types';
import { citedBlockIds, citedSlides, type SlidePreview } from './officePreview';

export function SlideSourceViewer({
  source,
  highlightRegions = [],
}: {
  source: SourceDocumentResult;
  highlightRegions?: RegionResult[];
}) {
  const [preview, setPreview] = useState<SlidePreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const firstHighlight = useRef<HTMLElement | null>(null);
  const assignedFirst = useRef(false);
  const slides = useMemo(() => citedSlides(highlightRegions), [highlightRegions]);
  const blockIds = useMemo(() => citedBlockIds(highlightRegions), [highlightRegions]);

  useEffect(() => {
    let cancelled = false;
    setPreview(null);
    setError(null);
    void fetch(source.url)
      .then((response) => {
        if (!response.ok) throw new Error(`Unable to load slides (${response.status})`);
        return response.json() as Promise<SlidePreview>;
      })
      .then((body) => {
        if (!cancelled) setPreview(body);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : 'Unable to load slides');
      });
    return () => { cancelled = true; };
  }, [source.url]);

  useEffect(() => {
    firstHighlight.current?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [preview, slides, blockIds]);

  if (error) {
    return <div className="unsupportedSource"><strong>{source.filename}</strong><span>{error}</span></div>;
  }
  if (!preview) {
    return <div className="unsupportedSource"><strong>{source.filename}</strong><span>Loading slides…</span></div>;
  }
  assignedFirst.current = false;
  firstHighlight.current = null;
  return (
    <div className="slideSourceViewer">
      {(preview.slides || []).map((slide) => {
        const cited = slides.size === 0 || slides.has(slide.slide);
        return (
          <section
            key={slide.slide}
            className={cited && slides.has(slide.slide) ? 'slideCard is-highlighted' : 'slideCard'}
            ref={(node) => {
              if (node && slides.has(slide.slide) && !assignedFirst.current) {
                assignedFirst.current = true;
                firstHighlight.current = node;
              }
            }}
          >
            <header>Slide {slide.slide}</header>
            {(slide.blocks || []).map((block) => {
              const highlighted = blockIds.has(block.block_id);
              if (block.kind === 'image') {
                return <p key={block.block_id} className={highlighted ? 'is-highlighted' : ''}>Picture</p>;
              }
              if (block.kind === 'notes') {
                return <p key={block.block_id} className={highlighted ? 'slideNotes is-highlighted' : 'slideNotes'}>{block.text}</p>;
              }
              return (
                <p key={block.block_id} className={highlighted ? 'is-highlighted' : ''}>
                  {block.kind === 'heading' ? <strong>{block.text}</strong> : block.text}
                </p>
              );
            })}
          </section>
        );
      })}
    </div>
  );
}
