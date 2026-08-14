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
  id: string;
  event: 'search_start' | 'search_done' | 'llm_request' | 'llm_response' | 'tool_call' | 'answer_delta' | 'answer_reset' | 'conversion_progress' | 'index_progress' | 'inspection_progress';
  turn?: number;
  query?: string;
  mode?: string;
  top_k?: number;
  hits?: number;
  model?: string;
  tools?: string[];
  messages?: TraceMessage[];
  content?: string;
  tool_calls?: TraceToolCall[];
  usage?: Record<string, unknown> | null;
  name?: string;
  arguments?: Record<string, unknown>;
  output?: unknown;
  text?: string;
  completed?: number;
  total?: number;
  input?: string;
  phase?: string;
  chunks?: number;
  skipped?: number;
}

export interface FigureResult {
  page_number: number;
  bbox?: number[];
  page_width?: number;
  page_height?: number;
  asset_id?: string;
  mime_type?: string;
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

export interface SessionTurn {
  role: 'user' | 'assistant';
  content: string;
  citations?: ChatCitationResult[];
  attachments?: ChatAttachment[];
  searches?: { query: string; mode: string; top_k: number; hits: number }[];
  selected_paths?: string[];
  answer_mode?: 'retrieval' | 'agent';
  mode_label?: string;
  trace?: StreamEvent[];
  images_sent?: number;
  vision_fallback?: boolean;
  llm?: { provider: string; model: string; usage?: Record<string, unknown> | null };
  timestamp: number;
}

export interface Session {
  id: string;
  title: string;
  source_path: string;
  selected_paths?: string[];
  turns: SessionTurn[];
  created_at: number;
  updated_at: number;
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
  ingest_pipeline?: string;
  external_python?: ExternalPythonConfig | null;
  /**
   * Runtime-only: true when a Hugging Face token is available from secure
   * storage or the process environment (`HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN`).
   * Not persisted in settings.json.
   */
  has_hf_token?: boolean;
  /** Runtime-only probe of the configured external Python environment. */
  external_python_status?: PythonEnvironmentProbe | null;
}

export type PipelineRuntimeSource = 'bundled' | 'external';

export interface PipelineFieldDescriptor {
  key: string;
  label: string;
  type?: string;
  default?: unknown;
  unit?: string;
}

export interface PipelineDescriptor {
  provider: string;
  variant?: string;
  spec: string;
  label?: string;
  description?: string;
  installed: boolean;
  capabilities?: Record<string, unknown>;
  fields?: PipelineFieldDescriptor[];
  notes?: string[];
  source?: PipelineRuntimeSource;
}

export interface ExternalPythonConfig {
  enabled: boolean;
  executable: string;
  artifacts_path?: string;
  validated_at?: number;
}

export interface PythonEnvironmentProbe {
  ok: boolean;
  executable?: string;
  python_version?: string;
  vera_ingest_version?: string;
  protocol?: number;
  plugin_api?: number;
  pipelines?: PipelineDescriptor[];
  load_errors?: string[];
  error?: string;
}

export interface CredentialResult {
  ok: boolean;
  has_api_key: boolean;
  error?: string;
}
