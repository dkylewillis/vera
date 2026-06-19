export interface VeraResponse<T = unknown> {
  id?: string;
  ok: boolean;
  result?: T;
  error?: string;
  traceback?: string;
}

export interface VeraApi {
  request<T = unknown>(payload: Record<string, unknown>): Promise<VeraResponse<T>>;
  pickArchive(): Promise<string | null>;
  pickFolder(): Promise<string | null>;
  pickPdf(): Promise<string | null>;
  saveVera(): Promise<string | null>;
  saveAny(): Promise<string | null>;
}

export interface InspectResult {
  file: string;
  source?: string;
  pages?: number;
  chunks?: number;
  embeddings?: number;
  format_name?: string;
  format_version?: string;
  default_embedding_model?: string;
  parser_name?: string;
  directory?: string;
  file_count?: number;
  embedding_models?: string[];
}

export interface ValidateResult {
  ok: boolean;
  counts: Record<string, number>;
  checks: Record<string, boolean>;
  issues: string[];
}

export interface FigureResult {
  page_number: number;
  asset_id?: string;
  filename?: string;
  caption?: string | null;
}

export interface SearchResult {
  chunk_id: string;
  score: number;
  text: string;
  page_start: number | null;
  page_end: number | null;
  heading_path: string | null;
  source_filename: string | null;
  document_id: string;
  regions?: Array<Record<string, unknown>>;
  figures?: FigureResult[];
  file?: string;
}

export interface ConvertResult {
  output: string;
}

export interface ExportResult {
  output: string;
  filename: string;
  mime_type: string;
  hash: string;
}

declare global {
  interface Window {
    vera: VeraApi;
  }
}
