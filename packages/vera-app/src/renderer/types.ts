import type {
  AgentServiceStatus,
  AppSettings,
  AttachmentUsage,
  ChatCitationResult,
  CredentialResult,
  Session,
  StreamEvent,
} from '../shared/contracts';
import type { HelpLinkId } from '../shared/help-links';
import type { ProAccount, ProActionResult } from '../shared/pro';
import type { FolderPickPurpose } from '../shared/protocol';

export type {
  AgentServiceSettings,
  AgentServiceState,
  AgentServiceStatus,
  AppSettings,
  ChatAttachment,
  ChatFileAttachment,
  AttachmentUsage,
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

export type { ProAccount, ProActionResult } from '../shared/pro';

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
  proGetAccount(): Promise<ProAccount>;
  proSignIn(): Promise<ProActionResult>;
  proSignOut(): Promise<ProActionResult>;
  proActivate(): Promise<ProActionResult>;
  proClearKey(): Promise<ProActionResult>;
  proOpenPage(page: 'pricing' | 'account'): Promise<ProActionResult>;
  openHelpLink(id: HelpLinkId): Promise<boolean>;
  checkForUpdates(): Promise<void>;
  onProAccountChanged(callback: (account: ProAccount) => void): () => void;
  getSessions(): Promise<Session[]>;
  saveSession(session: Session): Promise<Session[]>;
  deleteSession(id: string): Promise<Session[]>;
  listModes(): Promise<VeraResponse<{ modes: Mode[] }>>;
  openModesFolder(): Promise<unknown>;
  pickArchive(): Promise<string | null>;
  pickFolder(purpose?: FolderPickPurpose): Promise<string | null>;
  listFolder(dir: string): Promise<WorkspaceFolderResult | null>;
  pathExists(targetPath: string): Promise<boolean>;
  showInFolder(targetPath: string): Promise<void>;
  openConvertLog(): Promise<string>;
  showConvertLogFolder(): Promise<void>;
  getConvertLogPath(): Promise<string>;
  trashWorkspaceFile(filePath: string, folderPath: string): Promise<'trashed' | 'deleted' | 'cancelled'>;
  setWatchedFolders(paths: string[]): Promise<void>;
  /** `requestId` routes `library_progress` events to `onAnswerEvent` and lets `cancelAnswer` stop the sync. */
  syncLibrary(folderPath: string, requestId?: string): Promise<LibrarySyncReport | null>;
  /** Syncs the main process is running, so a window can attach after it loads. */
  librarySyncStatus(): Promise<{ folderPath: string; requestId: string }[]>;
  shareArchive(archivePath: string): Promise<string | null>;
  pathForFile(file: File): string;
  saveDroppedFile(name: string, data: ArrayBuffer): Promise<string>;
  saveDraftAs(sourcePath: string, suggestedName: string): Promise<string | null>;
  readDraft(sourcePath: string): Promise<string>;
  onLibrarySync(callback: (folderPath: string, report: LibrarySyncReport | null, requestId?: string) => void): () => void;
  onLibrarySyncProgress(callback: (folderPath: string, requestId: string, event: StreamEvent) => void): () => void;
  pickPdf(): Promise<string[]>;
  saveAny(): Promise<string | null>;
  openTargetReady(): Promise<void>;
  onOpenTarget(callback: (path: string, kind?: 'library' | 'folder') => void): () => void;
  onOpenSettings(callback: () => void): () => void;
  onFolderChanged(callback: (path: string) => void): () => void;
  onAnswerEvent(callback: (data: StreamEvent) => void): () => void;
  serviceGetStatus(): Promise<AgentServiceStatus>;
  serviceSave(config: { enabled?: boolean; libraryRoots?: string[]; libraryNames?: Record<string, string>; port?: number; cloudEnabled?: boolean }): Promise<AgentServiceStatus>;
  serviceStart(): Promise<AgentServiceStatus>;
  serviceStop(): Promise<AgentServiceStatus>;
  serviceRotateToken(): Promise<AgentServiceStatus>;
  onServiceEvent(callback: (status: AgentServiceStatus) => void): () => void;
  relaySetRouting(routing: { mode: 'auto' | 'pinned'; deviceId?: string }): Promise<AgentServiceStatus>;
  relayRenameDevice(name: string): Promise<AgentServiceStatus>;
  relayForgetDevice(deviceId: string): Promise<AgentServiceStatus>;
  relayRefreshDevices(): Promise<AgentServiceStatus>;
}

export interface FolderEntry {
  path: string;
  name: string;
  relativePath: string;
  type: 'vera' | 'pdf' | 'md' | 'docx' | 'pptx' | 'xlsx';
}

export interface WorkspaceFolderResult {
  path: string;
  name: string;
  entries: FolderEntry[];
  truncated?: boolean;
  index?: LibraryIndexStatus;
}

export interface LibrarySyncReport {
  managed?: boolean;
  needs_confirmation?: boolean;
  ok?: boolean;
  error?: string;
  converted?: number;
  moved?: number;
  trashed?: number;
  pending_trash?: number;
  failed?: number;
  errors?: { input: string; error: string }[];
  busy?: boolean;
  cancelled?: boolean;
  actions?: {
    action?: string;
    source?: string;
    output?: string;
    warnings?: string[];
    notes?: string[];
  }[];
  adoptable?: string[];
  inside_library?: boolean;
  library_root?: string | null;
}

export interface LibraryTrashEntry {
  entry: string;
  source_path: string;
  trashed_at: string;
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
  ingest_warnings?: string[];
  ingest_notes?: string[];
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
  answered_from?: 'prior_evidence' | 'search' | 'attachments' | 'none';
  citations: ChatCitationResult[];
  instructions: string;
  llm_prompt?: string;
  mode?: string;
  mode_label?: string;
  searches?: { query: string; mode: string; top_k: number; hits: number }[];
  attachment_usage?: Record<string, AttachmentUsage>;
  drafts?: { path: string; filename: string; title: string; version: number }[];
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
  search_policy?: 'auto' | 'first_turn' | 'always';
  tools?: string[];
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
  warnings?: { input: string; output: string; warnings: string[] }[];
  notes?: { input: string; output: string; notes: string[] }[];
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
  /** Pre-rendered HTML for Markdown sources, with `data-ls`/`data-le` line ranges. */
  html_url?: string;
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
