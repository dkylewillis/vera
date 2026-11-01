import { useEffect, useMemo, useRef, useState } from 'react';
import type { RegionResult, SourceDocumentResult } from '../types';
import {
  cellInRanges,
  citedSheetRanges,
  rangeStartsBeyondPreview,
  type SheetPreview,
} from './officePreview';

export function SheetSourceViewer({
  source,
  highlightRegions = [],
}: {
  source: SourceDocumentResult;
  highlightRegions?: RegionResult[];
}) {
  const [preview, setPreview] = useState<SheetPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeSheet, setActiveSheet] = useState('');
  const firstHighlight = useRef<HTMLTableCellElement | null>(null);
  const assignedFirst = useRef(false);
  const ranges = useMemo(() => citedSheetRanges(highlightRegions), [highlightRegions]);

  useEffect(() => {
    let cancelled = false;
    setPreview(null);
    setError(null);
    void fetch(source.url)
      .then((response) => {
        if (!response.ok) throw new Error(`Unable to load workbook (${response.status})`);
        return response.json() as Promise<SheetPreview>;
      })
      .then((body) => {
        if (cancelled) return;
        setPreview(body);
        const cited = ranges.find((range) => range.sheet)?.sheet;
        setActiveSheet(cited || body.sheets[0]?.name || '');
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : 'Unable to load workbook');
      });
    return () => { cancelled = true; };
  }, [source.url, ranges]);

  useEffect(() => {
    firstHighlight.current?.scrollIntoView({ block: 'center', inline: 'center', behavior: 'smooth' });
  }, [preview, activeSheet, ranges]);

  if (error) {
    return <div className="unsupportedSource"><strong>{source.filename}</strong><span>{error}</span></div>;
  }
  if (!preview) {
    return <div className="unsupportedSource"><strong>{source.filename}</strong><span>Loading workbook…</span></div>;
  }
  const sheet = preview.sheets.find((item) => item.name === activeSheet) || preview.sheets[0];
  if (!sheet) {
    return <div className="unsupportedSource"><strong>{source.filename}</strong><span>This workbook has no preview rows.</span></div>;
  }
  const sheetRanges = ranges.filter((range) => !range.sheet || range.sheet === sheet.name);
  const beyond = rangeStartsBeyondPreview(sheetRanges, sheet.rows.length);
  assignedFirst.current = false;
  firstHighlight.current = null;
  return (
    <div className="sheetSourceViewer">
      <div className="sheetTabs" role="tablist">
        {preview.sheets.map((item) => (
          <button
            key={item.name}
            type="button"
            role="tab"
            aria-selected={item.name === sheet.name}
            className={item.name === sheet.name ? 'sheetTab is-active' : 'sheetTab'}
            onClick={() => setActiveSheet(item.name)}
          >
            {item.name}
          </button>
        ))}
      </div>
      {sheet.row_count > sheet.rows.length ? (
        <p className="sheetPreviewNote">Showing the first {sheet.rows.length} of {sheet.row_count} rows.</p>
      ) : null}
      {beyond ? <p className="sheetPreviewNote">Cited rows are beyond this preview.</p> : null}
      <div className="sheetGridWrap">
        <table className="sheetGrid">
          <tbody>
            {sheet.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, columnIndex) => {
                  const highlighted = cellInRanges(rowIndex + 1, columnIndex + 1, sheetRanges);
                  return (
                    <td
                      key={columnIndex}
                      className={highlighted ? 'is-highlighted' : undefined}
                      ref={(node) => {
                        if (node && highlighted && !assignedFirst.current) {
                          assignedFirst.current = true;
                          firstHighlight.current = node;
                        }
                      }}
                    >
                      {cell}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
