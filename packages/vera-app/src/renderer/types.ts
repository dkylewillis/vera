export interface VeraResponse<T = unknown> {
  id?: string;
  ok: boolean;
  result?: T;
  error?: string;
  traceback?: string;
}

export type ContentPart =
  | { type: 'text'; text: string }
  | { type: 'image_url'; image_url: { url: string } };

export interface TraceMessage {
  role: string;
  content?: string | ContentPart[] | null;
  name?: string;
  tool_call_id?: string;
  tool_calls?: { id?: string; type?: string; function?: { name?: string; arguments?: string } }[];
}

export interface TraceToolCall {
  id?: string;
  name?: string;
  arguments?: Record<string, unknown>;
}

export interface StreamEvent {
  event: 'search_start' | 'search_done' | 'llm_request' | 'llm_response' | 'tool_call' | 'answer_delta' | 'answer_reset';
  turn?: number;
  query?: string;
  mode?: string;
  top_k?: number;
  hits?: number;
  // llm_request
  model?: string;
  tools?: string[];
  messages?: TraceMessage[];
  // llm_response
  content?: string;
  tool_calls?: TraceToolCall[];
  usage?: Record<string, unknown> | null;
  // tool_call
  name?: string;
  arguments?: Record<string, unknown>;
  output?: unknown;
  // answer_delta
  text?: string;
}

export interface VeraApi {
  platform: string;
  showMenu(menuId: string, x: number, y: number): Promise<boolean>;
  request<T = unknown>(payload: Record<string, unknown>): Promise<VeraResponse<T>>;
  getSettings(): Promise<AppSettings>;
  saveSettings(settings: AppSettings): Promise<AppSettings>;
  saveApiKey(providerId: string, apiKey: string): Promise<CredentialResult>;
  clearApiKey(providerId: string): Promise<CredentialResult>;
  getSessions(): Promise<Session[]>;
  saveSession(session: Session): Promise<Session[]>;
  deleteSession(id: string): Promise<Session[]>;
  listModes(): Promise<VeraResponse<{ modes: Mode[] }>>;
  openModesFolder(): Promise<unknown>;
  pickArchive(): Promise<string | null>;
  pickFolder(): Promise<string | null>;
  listFolder(dir: string): Promise<WorkspaceFolderResult | null>;
  setWatchedFolders(paths: string[]): Promise<void>;
  pickPdf(): Promise<string | null>;
  saveVera(defaultPath?: string): Promise<string | null>;
  saveAny(): Promise<string | null>;
  onOpenTarget(callback: (path: string) => void): () => void;
  onOpenSettings(callback: () => void): () => void;
  onFolderChanged(callback: (path: string) => void): () => void;
  onAnswerEvent(callback: (data: StreamEvent) => void): () => void;
}

export interface FolderEntry {
  path: string;
  name: string;
  relativePath: string;
  type: 'vera' | 'pdf';
}

export interface WorkspaceFolderResult {
  path: string;
  name: string;
  entries: FolderEntry[];
  index?: LibraryIndexStatus;
}

export interface LibraryIndexStatus {
  directory: string;
  index: string;
  exists: boolean;
  fresh: boolean;
  reasons: string[];
  recursive?: boolean;
  excludes?: string[];
  file_count?: number;
  skipped?: number;
  discovered?: number;
}

export interface LibraryIndexBuildReport {
  ok: boolean;
  operation: 'build' | 'update';
  directory: string;
  index: string;
  recursive: boolean;
  excludes: string[];
  discovered: number;
  indexed: number;
  chunks: number;
  skipped: number;
  invalid: { file: string; reason: string }[];
  incompatible: { file: string; reason: string }[];
  added: number;
  changed: number;
  removed: number;
  moved: number;
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
  recursive?: boolean;
  index?: LibraryIndexStatus;
}

export interface ValidateResult {
  ok: boolean;
  counts: Record<string, number>;
  checks: Record<string, boolean>;
  issues: string[];
}

export interface FigureResult {
  page_number: number;
  bbox?: number[];
  page_width?: number;
  page_height?: number;
  asset_id?: string;
  filename?: string;
  caption?: string | null;
  data_url?: string;
  included_in_context?: boolean;
}

export interface RegionResult {
  page_number?: number;
  bbox?: number[];
  page_width?: number;
  page_height?: number;
}

export interface ContextChunkResult {
  chunk_id: string;
  text: string;
  page_start: number | null;
  page_end: number | null;
  heading_path: string | null;
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
  regions?: RegionResult[];
  figures?: FigureResult[];
  before_chunks?: ContextChunkResult[];
  after_chunks?: ContextChunkResult[];
  file?: string;
}

export interface ChatCitationResult {
  id: string;
  label: string;
  result: SearchResult;
}

export interface ChatAttachment {
  id: string;
  name: string;
  mime_type: string;
  data_url: string;
}

export interface ChatAnswerResult {
  prompt: string;
  answer: string;
  answer_mode?: 'retrieval' | 'agent';
  citations: ChatCitationResult[];
  instructions: string;
  llm_prompt?: string;
  mode?: string;
  mode_label?: string;
  searches?: { query: string; mode: string; top_k: number; hits: number }[];
  trace?: StreamEvent[];
  images_sent?: number;
  llm?: {
    provider: string;
    model: string;
    usage?: Record<string, unknown> | null;
  };
}

export interface SessionTurn {
  role: 'user' | 'assistant';
  content: string;
  citations?: ChatCitationResult[];
  attachments?: ChatAttachment[];
  searches?: { query: string; mode: string; top_k: number; hits: number }[];
  answer_mode?: 'retrieval' | 'agent';
  mode_label?: string;
  trace?: StreamEvent[];
  images_sent?: number;
  llm?: { provider: string; model: string; usage?: Record<string, unknown> | null };
  timestamp: number;
}

export interface Session {
  id: string;
  title: string;
  source_path: string;
  turns: SessionTurn[];
  created_at: number;
  updated_at: number;
}

export interface Mode {
  id: string;
  label: string;
  description: string;
  instructions: string;
  search_mode: 'hybrid' | 'semantic' | 'keyword';
  top_k: number;
  context_chunks: number;
  include_figures: boolean;
  max_searches: number;
  max_chunks: number;
  max_figure_images: number;
  builtin: boolean;
  path: string;
}

export interface ProviderProfile {
  id: string;
  preset_key?: string;
  label: string;
  provider: string;
  base_url: string;
  api_key_env: string;
  auth_type: string;
  temperature: number;
  models: string[];
  available_models?: string[];
  models_refreshed_at?: number;
  model_options?: Record<string, {
    reasoning_effort?: string;
    fast?: boolean;
  }>;
  has_api_key?: boolean;
}

export interface AppSettings {
  providers: ProviderProfile[];
  active_provider_id: string;
  active_model: string;
  active_mode_id: string;
}

export interface CredentialResult {
  ok: boolean;
  has_api_key: boolean;
  error?: string;
}

export interface ConvertResult {
  output: string;
}

export interface BatchConvertResult {
  directory: string;
  recursive: boolean;
  overwrite: boolean;
  discovered: number;
  converted: number;
  skipped: number;
  failed: number;
  outputs: string[];
  skipped_existing: string[];
  errors: { input: string; error: string }[];
}

export interface ExportResult {
  output: string;
  filename: string;
  mime_type: string;
  hash: string;
}

export interface SourceDocumentResult {
  filename: string;
  mime_type: string;
  hash: string;
  size: number;
  data_url: string;
}

export interface PageResult {
  page_number: number;
  width: number | null;
  height: number | null;
  text: string | null;
}

declare global {
  interface Window {
    vera: VeraApi;
  }
}
