export interface VeraResponse<T = unknown> {
  id?: string;
  ok: boolean;
  result?: T;
  error?: string;
  traceback?: string;
}

export interface VeraApi {
  request<T = unknown>(payload: Record<string, unknown>): Promise<VeraResponse<T>>;
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
}

declare global {
  interface Window {
    vera: VeraApi;
  }
}
