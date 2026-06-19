import React, { useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { FileSearch, FolderOpen, Search, ShieldCheck, TerminalSquare } from 'lucide-react';
import type { InspectResult, SearchResult } from './types';
import './styles.css';

function App() {
  const [path, setPath] = useState('');
  const [query, setQuery] = useState('restaurant parking requirements');
  const [mode, setMode] = useState('hybrid');
  const [status, setStatus] = useState('Ready');
  const [inspect, setInspect] = useState<InspectResult | null>(null);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selected, setSelected] = useState<SearchResult | null>(null);

  const citation = useMemo(() => {
    if (!selected) return 'No result selected';
    const page = selected.page_start === selected.page_end ? selected.page_start : `${selected.page_start}-${selected.page_end}`;
    return `${selected.source_filename || 'document'} · p. ${page}`;
  }, [selected]);

  async function call<T>(payload: Record<string, unknown>): Promise<T | null> {
    setStatus('Working');
    const response = await window.vera.request<T>(payload);
    if (!response.ok) {
      setStatus(response.error || 'Request failed');
      return null;
    }
    setStatus('Ready');
    return (response.result || null) as T | null;
  }

  async function inspectDocument() {
    const result = await call<InspectResult>({ action: 'inspect', path });
    if (result) setInspect(result);
  }

  async function searchDocument() {
    const result = await call<SearchResult[]>({
      action: 'search',
      path,
      query,
      mode,
      top_k: 8,
      include_regions: true,
    });
    if (result) {
      setResults(result);
      setSelected(result[0] || null);
    }
  }

  return (
    <main className="shell">
      <header className="titlebar">
        <div className="brand">
          <FileSearch size={20} />
          <span>VERA</span>
        </div>
        <div className="status"><TerminalSquare size={16} />{status}</div>
      </header>

      <section className="workspace">
        <aside className="sidebar">
          <label className="field">
            <span>Archive</span>
            <div className="pathInput">
              <FolderOpen size={16} />
              <input value={path} onChange={(event) => setPath(event.target.value)} placeholder="C:\\docs\\manual.vera" />
            </div>
          </label>

          <div className="actions">
            <button onClick={inspectDocument} disabled={!path.trim()}><ShieldCheck size={16} />Inspect</button>
            <button onClick={searchDocument} disabled={!path.trim() || !query.trim()}><Search size={16} />Search</button>
          </div>

          <label className="field">
            <span>Query</span>
            <textarea value={query} onChange={(event) => setQuery(event.target.value)} />
          </label>

          <label className="field">
            <span>Mode</span>
            <select value={mode} onChange={(event) => setMode(event.target.value)}>
              <option value="hybrid">Hybrid</option>
              <option value="semantic">Semantic</option>
              <option value="keyword">Keyword</option>
            </select>
          </label>

          <section className="metrics">
            <div><span>Pages</span><strong>{inspect?.pages ?? '-'}</strong></div>
            <div><span>Chunks</span><strong>{inspect?.chunks ?? '-'}</strong></div>
            <div><span>Model</span><strong>{inspect?.default_embedding_model ?? '-'}</strong></div>
            <div><span>Parser</span><strong>{inspect?.parser_name ?? '-'}</strong></div>
          </section>
        </aside>

        <section className="resultsPane">
          <div className="paneHeader">
            <h1>Results</h1>
            <span>{results.length} matches</span>
          </div>
          <div className="resultsList">
            {results.map((result) => (
              <button
                className={selected?.chunk_id === result.chunk_id ? 'result selected' : 'result'}
                key={result.chunk_id}
                onClick={() => setSelected(result)}
              >
                <span className="resultMeta">{result.score.toFixed(4)} · p. {result.page_start}</span>
                <strong>{result.heading_path || result.source_filename || result.chunk_id}</strong>
                <span>{result.text}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="evidencePane">
          <div className="paneHeader">
            <h1>Evidence</h1>
            <span>{citation}</span>
          </div>
          {selected ? (
            <article className="evidence">
              <p>{selected.text}</p>
              <dl>
                <div><dt>Chunk</dt><dd>{selected.chunk_id}</dd></div>
                <div><dt>Heading</dt><dd>{selected.heading_path || '-'}</dd></div>
                <div><dt>Regions</dt><dd>{selected.regions?.length ?? 0}</dd></div>
              </dl>
            </article>
          ) : (
            <div className="emptyState">No evidence selected</div>
          )}
        </section>
      </section>
    </main>
  );
}

createRoot(document.getElementById('root')!).render(<App />);
