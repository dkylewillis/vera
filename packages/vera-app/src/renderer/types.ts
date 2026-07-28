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
  ProviderProfile,
  RegionResult,
  SearchResult,
  Session,
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
  cancelled?: boolean;
}

export interface VeraApi {
  platform: string;
  showMenu(menuId: string, x: number, y: number): Promise<boolean>;
  request<T = unknown>(payload: Record<string, unknown>, requestId?: string): Promise<VeraResponse<T>>;
  cancelAnswer(requestId: string): Promise<void>;
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
  skipped_files?: { file: string; category: string; reason: string }[];
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
  malformed: number;
  failed: number;
  outputs: string[];
  skipped_existing: string[];
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
