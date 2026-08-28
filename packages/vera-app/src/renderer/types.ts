import type {
  AppSettings,
  ChatCitationResult,
  CredentialResult,
  Session,
  StreamEvent,
} from '../shared/contracts';

export type {
  AppSettings,
  ChatAttachment,
  ChatCitationResult,
  ContentPart,
  ContextChunkResult,
  CredentialResult,
  FigureResult,
  JsonValue,
  EmbedderDescriptor,
  PipelineCapabilities,
  PipelineDescriptor,
  PipelineFieldChoice,
  PipelineFieldDescriptor,
  PipelineFieldType,
  PipelineOptions,
  ProviderProfile,
  RegionResult,
  SearchReport,
  SearchResult,
  Session,
  SkippedSemanticModelGroup,
  SessionTurn,
  StreamEvent,
  TraceMessage,
  TraceToolCall,
} from '../shared/contracts';

export interface VeraResponse<T = unknown> {
  id?: string;
  ok: boolean;
  result?: T;
  error?: string;
  traceback?: string;
  provider_error_detail?: string;
  cancelled?: boolean;
}

export interface VeraApi {
  platform: string;
  showMenu(menuId: string, x: number, y: number): Promise<boolean>;
  request<T = unknown>(payload: Record<string, unknown>, requestId?: string): Promise<VeraResponse<T>>;
  cancelAnswer(requestId: string): Promise<{ cancelled: boolean } | void>;
  cancelRequest(requestId: string): Promise<boolean>;
  skipConversion(requestId: string): Promise<{ skipped: boolean }>;
  getSettings(): Promise<AppSettings>;
  saveSettings(settings: AppSettings): Promise<AppSettings>;
  saveApiKey(providerId: string, apiKey: string): Promise<CredentialResult>;
  clearApiKey(providerId: string): Promise<CredentialResult>;
  saveHfToken(token: string): Promise<CredentialResult>;
  clearHfToken(): Promise<CredentialResult>;
  saveEnvSecret(name: string, value: string): Promise<CredentialResult>;
  clearEnvSecret(name: string): Promise<CredentialResult>;
  getSessions(): Promise<Session[]>;
  saveSession(session: Session): Promise<Session[]>;
  deleteSession(id: string): Promise<Session[]>;
  listModes(): Promise<VeraResponse<{ modes: Mode[] }>>;
  openModesFolder(): Promise<unknown>;
  pickArchive(): Promise<string | null>;
  pickFolder(): Promise<string | null>;
  listFolder(dir: string): Promise<WorkspaceFolderResult | null>;
  pathExists(targetPath: string): Promise<boolean>;
  showInFolder(targetPath: string): Promise<void>;
  openConvertLog(): Promise<string>;
  showConvertLogFolder(): Promise<void>;
  getConvertLogPath(): Promise<string>;
  trashWorkspaceFile(filePath: string, folderPath: string): Promise<'trashed' | 'deleted' | 'cancelled'>;
  setWatchedFolders(paths: string[]): Promise<void>;
  pickPdf(): Promise<string[]>;
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
  type: 'vera' | 'pdf' | 'md';
}

export interface WorkspaceFolderResult {
  path: string;
  name: string;
  entries: FolderEntry[];
  truncated?: boolean;
  index?: LibraryIndexStatus;
}

export interface LibraryIndexStatus {
  directory: string;
  index: string;
  exists: boolean;
  fresh: boolean;
  reasons: string[];
  generation_id?: string | null;
  created_at?: string | null;
  checked_at?: string | null;
  verified_at?: string | null;
  index_size_bytes?: number;
  database_size_bytes?: number;
  vector_size_bytes?: number;
  recursive?: boolean;
  excludes?: string[];
  file_count?: number;
  skipped?: number;
  skipped_files?: { file: string; category: string; reason: string }[];
  discovered?: number;
  indexed_chunks?: number;
  source_chunks?: number;
  model_groups?: {
    model: string;
    dimension: number;
    documents: number;
    chunks: number;
    vector_file: string;
    vector_size_bytes: number;
  }[];
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
  /** Single-document inspections use `path`; `file` is retained for older sidecars. */
  path?: string;
  file?: string;
  title?: string;
  source?: string;
  source_file_name?: string;
  source_file_hash?: string;
  source_mime_type?: string;
  pages?: number;
  chunks?: number;
  embeddings?: number;
  attachments?: number;
  archive_size_bytes?: number | null;
  created_at?: string;
  format_name?: string;
  format_version?: string;
  default_embedding_model?: string;
  embedding_model?: string;
  default_embedding_dimension?: number;
  embedding_dimension?: number;
  default_embedding_normalization?: 'l2' | 'none' | 'unknown';
  embedding_normalization?: 'l2' | 'none' | 'unknown';
  parser_name?: string;
  parser_version?: string;
  source_attachment_id?: string | null;
  chunking_strategy?: string;
  ocr?: {
    ocr_engine?: string;
    ocr_mode?: 'auto' | 'off' | 'force';
    ocr_language?: string;
    ocr_dpi?: number;
    ocr_pages?: number[];
  };
  ocr_engine?: string;
  ocr_mode?: 'auto' | 'off' | 'force';
  ocr_language?: string;
  ocr_dpi?: string;
  ocr_pages?: string;
  directory?: string;
  file_count?: number;
  discovered_file_count?: number;
  skipped?: number;
  skipped_files?: { file: string; category: string; reason: string }[];
  embedding_models?: string[];
  recursive?: boolean;
  index?: LibraryIndexStatus;
  summary_source?: 'index' | 'discovery' | 'archives';
  summary_complete?: boolean;
}

export interface ValidateResult {
  ok: boolean;
  counts: Record<string, number>;
  checks: Record<string, boolean>;
  issues: string[];
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
  vision_fallback?: boolean;
  llm?: {
    provider: string;
    model: string;
    usage?: Record<string, unknown> | null;
  };
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
  user_skipped?: number;
  malformed: number;
  failed: number;
  outputs: string[];
  skipped_existing: string[];
  skipped_by_user?: string[];
  malformed_existing: { input: string; output: string; issues: string[] }[];
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
  /** Privileged app URL for the cached source bytes (not a base64 data URL). */
  url: string;
}

export interface OcrLanguageStatus {
  code: string;
  name: string;
  bundled: boolean;
  downloadable: boolean;
  cached: boolean;
  size_bytes?: number;
}

export interface OcrLanguagesListResult {
  languages: OcrLanguageStatus[];
}

export interface OcrLanguagesDownloadResult {
  language: string;
  downloaded: string[];
  cache_dir: string;
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
