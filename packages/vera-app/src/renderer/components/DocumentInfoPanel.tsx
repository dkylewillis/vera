import { SIDECAR_ACTIONS } from '../../shared/protocol';
import { CheckCircle2, Download, Info, ShieldCheck } from 'lucide-react';
import type { SidecarCall } from '../lib/sidecarCall';
import { formatChunkingStrategy, formatOcrSummary } from '../lib/documentInfo';
import { formatBytes, formatTimestamp } from '../lib/formatting';
import type {
  ExportResult,
  InspectResult,
  LibraryIndexStatus,
  PageResult,
  SourceDocumentResult,
  ValidateResult,
} from '../types';

export function DocumentInfoPanel({
  viewerInfoPath,
  viewerInfoIsCorpus,
  viewerInfoIsArchive,
  viewerInfoInspectable,
  viewerInspect,
  viewerIndexStatus,
  activeLibraryIsEmpty,
  busy,
  validation,
  exportResult,
  sourceDocument,
  pageNumber,
  pageResult,
  call,
  onInspect,
  onValidation,
  onExportResult,
  onPageNumberChange,
  onPageResult,
}: {
  viewerInfoPath: string;
  viewerInfoIsCorpus: boolean;
  viewerInfoIsArchive: boolean;
  viewerInfoInspectable: boolean;
  viewerInspect: InspectResult | null;
  viewerIndexStatus?: LibraryIndexStatus;
  activeLibraryIsEmpty: boolean;
  busy: boolean;
  validation: ValidateResult | null;
  exportResult: ExportResult | null;
  sourceDocument: SourceDocumentResult | null;
  pageNumber: number;
  pageResult: PageResult | null;
  call: SidecarCall;
  onInspect: (path: string) => void;
  onValidation: (result: ValidateResult) => void;
  onExportResult: (result: ExportResult) => void;
  onPageNumberChange: (value: number) => void;
  onPageResult: (result: PageResult) => void;
}) {
  async function handleValidate() {
    const result = await call<ValidateResult>({ action: SIDECAR_ACTIONS.validate, path: viewerInfoPath }, 'Validating');
    if (result) onValidation(result);
  }

  async function handleExport() {
    const output = await window.vera.saveAny();
    if (!output) return;
    const result = await call<ExportResult>({ action: SIDECAR_ACTIONS.export, path: viewerInfoPath, output }, 'Exporting source');
    if (result) onExportResult(result);
  }

  async function handleLoadPage() {
    const result = await call<PageResult>(
      { action: SIDECAR_ACTIONS.page, path: viewerInfoPath, page_number: pageNumber },
      'Loading page',
    );
    if (result) onPageResult(result);
  }

  return (
    <article className="viewerInfoView infoView">
      {viewerInfoPath ? (
        <>
          <div className="infoActions">
            {viewerInfoIsCorpus ? (
              <button className="secondaryAction" onClick={() => void onInspect(viewerInfoPath)} disabled={!viewerInfoInspectable || activeLibraryIsEmpty || busy}><ShieldCheck size={15} />Inspect</button>
            ) : (
              <>
                <button className="secondaryAction" onClick={() => { void handleValidate(); }} disabled={!viewerInfoInspectable || busy}><CheckCircle2 size={15} />Validate</button>
                <button className="secondaryAction" onClick={() => { void handleExport(); }} disabled={!viewerInfoInspectable || busy}><Download size={15} />Export</button>
              </>
            )}
          </div>
          {viewerInfoIsCorpus ? (
            <>
              <dl className="infoList">
                <div><dt>Library</dt><dd>{viewerInfoPath}</dd></div>
                <div>
                  <dt>Documents</dt>
                  <dd>
                    {viewerInspect?.file_count ?? viewerIndexStatus?.file_count ?? '-'} indexed
                    {' / '}{viewerInspect?.discovered_file_count ?? viewerIndexStatus?.discovered ?? '-'} discovered
                    {' / '}{viewerInspect?.skipped ?? viewerIndexStatus?.skipped ?? 0} skipped
                  </dd>
                </div>
                <div><dt>Pages</dt><dd>{viewerInspect?.pages ?? '-'}</dd></div>
                <div><dt>Chunks</dt><dd>{viewerInspect?.chunks ?? viewerIndexStatus?.indexed_chunks ?? '-'}</dd></div>
                <div><dt>Models</dt><dd>{viewerInspect?.embedding_models?.join(', ') || viewerIndexStatus?.model_groups?.map((group) => group.model).join(', ') || '-'}</dd></div>
                <div>
                  <dt>Index</dt>
                  <dd className={viewerIndexStatus?.fresh ? 'infoStatus infoStatus--good' : 'infoStatus infoStatus--warn'}>
                    {viewerIndexStatus?.fresh ? 'Fresh' : viewerIndexStatus?.exists ? 'Stale' : 'Missing'}
                  </dd>
                </div>
                <div>
                  <dt>Coverage</dt>
                  <dd>
                    {viewerIndexStatus?.indexed_chunks ?? '-'} / {viewerIndexStatus?.source_chunks ?? '-'} chunks embedded
                    {viewerIndexStatus?.source_chunks
                      ? ` (${Math.round(((viewerIndexStatus.indexed_chunks ?? 0) / viewerIndexStatus.source_chunks) * 100)}%)`
                      : ''}
                  </dd>
                </div>
                <div><dt>Storage</dt><dd>{formatBytes(viewerIndexStatus?.index_size_bytes)} total · {formatBytes(viewerIndexStatus?.database_size_bytes)} database · {formatBytes(viewerIndexStatus?.vector_size_bytes)} vectors</dd></div>
                <div><dt>Built</dt><dd>{formatTimestamp(viewerIndexStatus?.created_at)}</dd></div>
                <div><dt>Checked</dt><dd>{formatTimestamp(viewerIndexStatus?.checked_at)}</dd></div>
                <div><dt>Verified</dt><dd>{formatTimestamp(viewerIndexStatus?.verified_at)}</dd></div>
                <div><dt>Generation</dt><dd>{viewerIndexStatus?.generation_id || '-'}</dd></div>
                <div><dt>Recursive</dt><dd>{viewerIndexStatus?.recursive ? 'Yes' : 'No'}</dd></div>
                <div><dt>Excludes</dt><dd>{viewerIndexStatus?.excludes?.length ? viewerIndexStatus.excludes.join(', ') : 'None'}</dd></div>
                <div><dt>Summary</dt><dd>{viewerInspect?.summary_source === 'index' ? 'Persistent index' : viewerInspect?.summary_source === 'archives' ? 'Archive scan' : 'File discovery only'}</dd></div>
              </dl>
              {viewerIndexStatus?.model_groups?.length ? (
                <section className="infoSection">
                  <h3>Model groups</h3>
                  <div className="modelGroupList">
                    {viewerIndexStatus.model_groups.map((group) => (
                      <article className="modelGroupCard" key={`${group.model}-${group.dimension}`}>
                        <strong>{group.model}</strong>
                        <span>{group.dimension} dimensions</span>
                        <span>{group.documents} document{group.documents === 1 ? '' : 's'} · {group.chunks} chunks</span>
                        <span>{formatBytes(group.vector_size_bytes)} vectors</span>
                      </article>
                    ))}
                  </div>
                </section>
              ) : null}
              {(viewerIndexStatus?.reasons.length || viewerIndexStatus?.skipped_files?.length) ? (
                <section className="infoSection">
                  <h3>Index health</h3>
                  <div className="indexHealthList">
                    {viewerIndexStatus.reasons.map((reason) => <p key={reason}>{reason}</p>)}
                    {viewerIndexStatus.skipped_files?.map((entry) => (
                      <p key={entry.file}><strong>{entry.file}</strong> · {entry.category}: {entry.reason}</p>
                    ))}
                  </div>
                </section>
              ) : null}
            </>
          ) : (
            <dl className="infoList">
              {viewerInfoIsArchive ? <div><dt>Archive</dt><dd>{viewerInfoPath}</dd></div> : null}
              <div><dt>Title</dt><dd>{viewerInspect?.title || '-'}</dd></div>
              <div><dt>Created</dt><dd>{formatTimestamp(viewerInspect?.created_at)}</dd></div>
              <div><dt>Archive size</dt><dd>{formatBytes(viewerInspect?.archive_size_bytes ?? undefined)}</dd></div>
              <div><dt>Format</dt><dd>{viewerInspect ? `${viewerInspect.format_name || 'VERA'} ${viewerInspect.format_version || ''}` : '-'}</dd></div>
              <div><dt>Source</dt><dd>{viewerInspect?.source || '-'}</dd></div>
              <div><dt>Pages</dt><dd>{viewerInspect?.pages ?? '-'}</dd></div>
              <div><dt>Chunks</dt><dd>{viewerInspect?.chunks ?? '-'}</dd></div>
              <div><dt>Model</dt><dd>{viewerInspect?.default_embedding_model || viewerInspect?.embedding_models?.join(', ') || '-'}</dd></div>
              <div><dt>Dimensions</dt><dd>{viewerInspect?.default_embedding_dimension ?? viewerInspect?.embedding_dimension ?? '-'}</dd></div>
              <div><dt>Normalization</dt><dd>{viewerInspect?.default_embedding_normalization ?? viewerInspect?.embedding_normalization ?? 'unknown'}</dd></div>
              <div><dt>Parser</dt><dd>{viewerInspect?.parser_name ? `${viewerInspect.parser_name}${viewerInspect.parser_version ? ` ${viewerInspect.parser_version}` : ''}` : '-'}</dd></div>
              <div><dt>Chunking</dt><dd>{formatChunkingStrategy(viewerInspect?.chunking_strategy)}</dd></div>
              <div><dt>OCR</dt><dd>{formatOcrSummary(viewerInspect?.ocr)}</dd></div>
              <div><dt>Attachments</dt><dd>{viewerInspect?.attachments ?? '-'}</dd></div>
              <div><dt>Validation</dt><dd>{validation ? (validation.ok ? 'PASS' : 'FAIL') : '-'}</dd></div>
              <div><dt>Issues</dt><dd>{validation?.issues?.length ? validation.issues.join('; ') : '0'}</dd></div>
              <div><dt>Export</dt><dd>{exportResult?.output || '-'}</dd></div>
            </dl>
          )}
          {sourceDocument ? (
            <section className="infoSection">
              <h3>Source Document</h3>
              <dl className="infoList">
                <div><dt>File</dt><dd>{sourceDocument.filename}</dd></div>
                <div><dt>Type</dt><dd>{sourceDocument.mime_type}</dd></div>
                <div><dt>Size</dt><dd>{Math.round(sourceDocument.size / 1024).toLocaleString()} KB</dd></div>
              </dl>
            </section>
          ) : null}
          {!viewerInfoIsCorpus ? <section className="infoSection">
            <h3>Page Text</h3>
            <div className="pageControls">
              <input className="numberInput" type="number" min={1} max={viewerInspect?.pages || undefined} value={pageNumber} onChange={(event) => onPageNumberChange(Number(event.target.value))} />
              <button className="secondaryAction" onClick={() => { void handleLoadPage(); }} disabled={!viewerInfoInspectable || viewerInfoIsCorpus || busy}>Load Page</button>
            </div>
            {pageResult ? (
              <article className="pageText">
                <span>p. {pageResult.page_number} · {pageResult.width ?? '-'} x {pageResult.height ?? '-'}</span>
                <p>{pageResult.text || 'No text was extracted for this page.'}</p>
              </article>
            ) : (
              <p className="sideMuted">Load a page to inspect extracted text.</p>
            )}
          </section> : null}
        </>
      ) : (
        <div className="emptyState">
          <Info size={28} />
          <p>Open a document to see its details.</p>
        </div>
      )}
    </article>
  );
}
