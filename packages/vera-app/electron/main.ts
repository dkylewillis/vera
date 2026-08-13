import { app, BrowserWindow, dialog, ipcMain, Menu, net, protocol, safeStorage, shell } from 'electron';
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { copyFileSync, existsSync, mkdirSync, readFileSync, renameSync, statSync, unlinkSync, watch, writeFileSync, type FSWatcher } from 'node:fs';
import { basename, delimiter, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import type {
  AppSettings,
  PipelineOptions,
  CredentialResult,
  ProviderProfile,
  Session,
} from '../src/shared/contracts.js';
import { IPC_CHANNELS, SIDECAR_ACTIONS } from '../src/shared/protocol.js';
import { listFolderEntries } from './folder-listing.js';
import { parseSidecarJsonLine } from './sidecar-json.js';

/** Prefer the workspace uv venv so optional plugins (ml/docling) resolve in source-run. */
function resolveDevPython(): string {
  if (process.env.VERA_APP_PYTHON?.trim()) {
    return process.env.VERA_APP_PYTHON.trim();
  }
  const repoRoot = resolve(process.cwd(), '..', '..');
  const candidates = [
    join(repoRoot, '.venv', 'Scripts', 'python.exe'),
    join(repoRoot, '.venv', 'bin', 'python'),
    join(process.cwd(), '.venv', 'Scripts', 'python.exe'),
    join(process.cwd(), '.venv', 'bin', 'python'),
  ];
  for (const candidate of candidates) {
    if (existsSync(candidate)) {
      return candidate;
    }
  }
  return 'python';
}

interface FolderEntry {
  path: string;
  name: string;
  relativePath: string;
  type: 'vera' | 'pdf';
}

interface WorkspaceFolderResult {
  path: string;
  name: string;
  entries: FolderEntry[];
  truncated?: boolean;
}

interface FolderWatcher {
  path: string;
  watcher: FSWatcher;
}

interface SidecarRequest {
  id?: string;
  action: string;
  [key: string]: unknown;
}

interface SidecarPayload {
  action: string;
  [key: string]: unknown;
}

interface SidecarResponse {
  id?: string;
  ok: boolean;
  result?: unknown;
  error?: string;
  traceback?: string;
  provider_error_detail?: string;
}

interface SidecarEvent {
  id: string;
  event: string;
  [key: string]: unknown;
}

interface SessionStore {
  sessions: Session[];
}

const DEFAULT_SETTINGS: AppSettings = {
  providers: [],
  active_provider_id: '',
  active_model: '',
  active_mode_id: '',
  embedding_model: 'hashing',
  ingest_pipeline: 'pymupdf',
  ingest_pipeline_configs: {},
};

function isJsonPrimitive(value: unknown): value is string | number | boolean | null {
  return value === null
    || typeof value === 'string'
    || typeof value === 'number'
    || typeof value === 'boolean';
}

function normalizePipelineOptions(raw: unknown): PipelineOptions {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {};
  const options: PipelineOptions = {};
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (!key.trim()) continue;
    if (isJsonPrimitive(value)) {
      options[key] = value;
      continue;
    }
    if (Array.isArray(value) && value.every(isJsonPrimitive)) {
      options[key] = value as Array<string | number | boolean | null>;
    }
  }
  return options;
}

function normalizePipelineConfigs(raw: unknown): Record<string, PipelineOptions> {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {};
  const configs: Record<string, PipelineOptions> = {};
  for (const [spec, value] of Object.entries(raw as Record<string, unknown>)) {
    if (!spec.trim()) continue;
    configs[spec] = normalizePipelineOptions(value);
  }
  return configs;
}

// Serve materialized source PDFs without shipping base64 through JSON IPC.
// Must be registered before app.ready so fetch()/PDF.js can use the scheme.
protocol.registerSchemesAsPrivileged([
  {
    scheme: 'vera-source',
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      stream: true,
      bypassCSP: true,
      corsEnabled: true,
    },
  },
]);

function sourceCacheDir(): string {
  return join(app.getPath('userData'), 'source-cache');
}

function isPathInsideDir(filePath: string, dirPath: string): boolean {
  const resolvedFile = resolve(filePath);
  const resolvedDir = resolve(dirPath);
  const rel = relative(resolvedDir, resolvedFile);
  return rel !== '' && !rel.startsWith(`..${sep}`) && !rel.startsWith('..') && !isAbsolute(rel);
}

function toSourceViewerResult(result: Record<string, unknown>): Record<string, unknown> {
  const cachePath = typeof result.cache_path === 'string' ? result.cache_path : '';
  if (!cachePath) {
    return result;
  }
  const resolved = resolve(cachePath);
  const root = resolve(sourceCacheDir());
  if (!isPathInsideDir(resolved, root)) {
    throw new Error('Source cache path escaped the cache directory');
  }
  const rel = relative(root, resolved).split(/[/\\]/).map(encodeURIComponent).join('/');
  const { cache_path: _cachePath, ...rest } = result;
  return {
    ...rest,
    url: `vera-source://cache/${rel}`,
  };
}

function packagedSidecarExecutable(): string {
  const dir = join(process.resourcesPath, 'python', 'sidecar');
  const preferred = process.platform === 'win32' ? 'vera-sidecar.exe' : 'vera-sidecar';
  const fallback = process.platform === 'win32' ? 'vera-sidecar' : 'vera-sidecar.exe';
  const preferredPath = join(dir, preferred);
  if (existsSync(preferredPath)) return preferredPath;
  return join(dir, fallback);
}

class PythonSidecar {
  private child: ChildProcessWithoutNullStreams | null = null;
  private pending = new Map<string, {
    child: ChildProcessWithoutNullStreams;
    resolve: (value: SidecarResponse) => void;
    reject: (reason?: unknown) => void;
    onEvent?: (e: SidecarEvent) => void;
  }>();
  private nextId = 1;
  private stdoutBuffer = '';
  private restartWhenIdle = false;

  request(
    payload: SidecarPayload,
    onEvent?: (e: SidecarEvent) => void,
    requestId?: string,
  ): Promise<SidecarResponse> {
    const child = this.ensureStarted();
    const id = requestId || String(this.nextId++);
    const message: SidecarRequest = { ...payload, id };
    return new Promise((resolve, reject) => {
      this.pending.set(id, { child, resolve, reject, onEvent });
      const failWrite = (error: unknown) => {
        this.pending.delete(id);
        reject(error);
      };
      try {
        if (child.stdin.destroyed || !child.stdin.writable) {
          failWrite(new Error('VERA sidecar stdin is not writable'));
          return;
        }
        child.stdin.write(`${JSON.stringify(message)}\n`, (error) => {
          if (error) failWrite(error);
        });
      } catch (error) {
        failWrite(error);
      }
    });
  }

  stop(): void {
    this.restartWhenIdle = false;
    if (this.child) {
      this.child.kill();
      this.child = null;
    }
    this.rejectPending(new Error('VERA sidecar stopped'));
  }

  async cancelAnswer(requestId: string): Promise<{ cancelled: boolean }> {
    const response = await this.request({ action: SIDECAR_ACTIONS.cancel, target_id: requestId });
    const result = (response.result || {}) as { cancelled?: boolean };
    return { cancelled: Boolean(result.cancelled) };
  }

  async skipConversion(requestId: string): Promise<{ skipped: boolean }> {
    const response = await this.request({ action: SIDECAR_ACTIONS.skip, target_id: requestId });
    const result = (response.result || {}) as { skipped?: boolean };
    return { skipped: Boolean(result.skipped) };
  }

  async cancelRequest(requestId: string): Promise<boolean> {
    if (!this.pending.has(requestId)) return false;
    try {
      const { cancelled } = await this.cancelAnswer(requestId);
      return cancelled;
    } catch {
      return false;
    }
  }

  /** Kill the sidecar so the next request respawns with updated env (e.g. HF_TOKEN). */
  restart(): void {
    if (this.pending.size > 0) {
      this.restartWhenIdle = true;
      return;
    }
    this.killChild('VERA sidecar restarted');
  }

  private maybeRestartWhenIdle(): void {
    if (!this.restartWhenIdle || this.pending.size > 0) return;
    this.killChild('VERA sidecar restarted');
  }

  private killChild(reason: string): void {
    this.restartWhenIdle = false;
    const child = this.child;
    if (!child) return;
    this.child = null;
    this.rejectPending(new Error(reason), child);
    child.kill();
  }

  private rejectPending(reason: Error, child?: ChildProcessWithoutNullStreams): void {
    for (const [id, entry] of this.pending) {
      if (child && entry.child !== child) continue;
      this.pending.delete(id);
      entry.reject(reason);
    }
  }

  private ensureStarted(): ChildProcessWithoutNullStreams {
    if (this.child) {
      return this.child;
    }

    const env = { ...process.env };
    applyHfTokenEnv(env);
    const executable = app.isPackaged ? packagedSidecarExecutable() : resolveDevPython();
    const args = app.isPackaged ? [] : ['-m', 'vera_app.sidecar'];
    if (!app.isPackaged) {
      const sourcePaths = [
        join(process.cwd(), 'src'),
        join(process.cwd(), '..', 'vera-doc', 'src'),
        join(process.cwd(), '..', 'vera-ingest', 'src'),
        join(process.cwd(), '..', 'vera-ingest-pymupdf', 'src'),
        join(process.cwd(), '..', 'vera-ingest-docling', 'src'),
      ];
      env.PYTHONPATH = [sourcePaths.join(delimiter), env.PYTHONPATH || ''].filter(Boolean).join(delimiter);
    }

    this.child = spawn(executable, args, {
      cwd: process.cwd(),
      env,
      windowsHide: true,
    });

    this.child.stdout.on('data', (chunk: Buffer) => this.handleStdout(chunk.toString('utf8')));
    this.child.stderr.on('data', (chunk: Buffer) => console.error(`[vera-sidecar] ${chunk.toString('utf8')}`));
    const child = this.child;
    child.on('error', (error: Error) => {
      if (this.child === child) this.child = null;
      this.rejectPending(error, child);
      this.maybeRestartWhenIdle();
    });
    child.on('exit', () => {
      if (this.child === child) this.child = null;
      this.rejectPending(new Error('VERA sidecar exited'), child);
      this.maybeRestartWhenIdle();
    });

    return this.child;
  }

  private handleStdout(data: string): void {
    this.stdoutBuffer += data;
    const lines = this.stdoutBuffer.split('\n');
    this.stdoutBuffer = lines.pop() || '';
    for (const line of lines) {
      if (!line.trim()) {
        continue;
      }
      const parsed = parseSidecarJsonLine(line);
      if (!parsed.ok) {
        console.error(`[vera-sidecar] Ignoring invalid stdout line (${parsed.error}): ${line}`);
        continue;
      }
      const response = parsed.payload as unknown as SidecarResponse & { event?: string };
      if (!response.id) {
        continue;
      }
      const pending = this.pending.get(response.id);
      if (!pending) {
        continue;
      }
      // Intermediate event (no `ok` field — not a final response).
      if ('event' in response && !('ok' in response)) {
        pending.onEvent?.(response as unknown as SidecarEvent);
        continue;
      }
      this.pending.delete(response.id);
      pending.resolve(response as SidecarResponse);
      this.maybeRestartWhenIdle();
    }
  }
}

const sidecar = new PythonSidecar();

function settingsPath(): string {
  return join(app.getPath('userData'), 'settings.json');
}

function sessionsPath(): string {
  return join(app.getPath('userData'), 'sessions.json');
}

function readSessions(): Session[] {
  try {
    const raw = JSON.parse(readFileSync(sessionsPath(), 'utf8')) as SessionStore;
    return Array.isArray(raw?.sessions) ? raw.sessions : [];
  } catch {
    return [];
  }
}

function writeSessions(sessions: Session[]): Session[] {
  mkdirSync(app.getPath('userData'), { recursive: true });
  const store: SessionStore = { sessions };
  const target = sessionsPath();
  const temp = `${target}.tmp`;
  writeFileSync(temp, JSON.stringify(store, null, 2), 'utf8');
  renameSync(temp, target);
  return sessions;
}

function upsertSession(session: Session): Session[] {
  const sessions = readSessions();
  const idx = sessions.findIndex((s) => s.id === session.id);
  if (idx >= 0) {
    sessions[idx] = session;
  } else {
    sessions.unshift(session);
  }
  return writeSessions(sessions);
}

function deleteSession(id: string): Session[] {
  return writeSessions(readSessions().filter((s) => s.id !== id));
}

function modesDir(): string {
  const dir = join(app.getPath('userData'), 'modes');
  mkdirSync(dir, { recursive: true });
  const bundledModesDir = app.isPackaged
    ? join(process.resourcesPath, 'python', 'vera_app', 'modes_builtin')
    : join(process.cwd(), 'src', 'vera_app', 'modes_builtin');
  for (const filename of ['ask.md', 'research.md']) {
    const source = join(bundledModesDir, filename);
    const target = join(dir, filename);
    if (!existsSync(target) && existsSync(source)) {
      copyFileSync(source, target);
    }
  }
  return dir;
}

function secretPath(): string {
  return join(app.getPath('userData'), 'llm-api-keys.bin');
}

/** Reserved key inside the encrypted credential store (not a provider base URL). */
const HF_TOKEN_SECRET_KEY = '__vera_hf_token__';

function readApiKeys(): Record<string, string> {
  if (!safeStorage.isEncryptionAvailable() || !existsSync(secretPath())) {
    return {};
  }
  try {
    const decoded = safeStorage.decryptString(readFileSync(secretPath()));
    const parsed = JSON.parse(decoded) as Record<string, string>;
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function writeApiKeys(keys: Record<string, string>): void {
  mkdirSync(app.getPath('userData'), { recursive: true });
  const target = secretPath();
  const temp = `${target}.tmp`;
  writeFileSync(temp, safeStorage.encryptString(JSON.stringify(keys)));
  renameSync(temp, target);
}

function credentialKey(baseUrl: unknown): string {
  return typeof baseUrl === 'string' ? baseUrl.trim().replace(/\/+$/, '').toLowerCase() : '';
}

function storedHfToken(): string {
  const value = readApiKeys()[HF_TOKEN_SECRET_KEY];
  return typeof value === 'string' ? value.trim() : '';
}

function environmentHfToken(): string {
  return (process.env.HF_TOKEN || process.env.HUGGING_FACE_HUB_TOKEN || '').trim();
}

/** Prefer the app-stored token; fall back to process environment. */
function resolveHfToken(): string {
  return storedHfToken() || environmentHfToken();
}

function applyHfTokenEnv(env: NodeJS.ProcessEnv): void {
  const token = resolveHfToken();
  if (!token) return;
  env.HF_TOKEN = token;
  env.HUGGING_FACE_HUB_TOKEN = token;
}

function withRuntime(settings: AppSettings): AppSettings {
  const keys = readApiKeys();
  return {
    ...settings,
    providers: settings.providers.map((profile) => ({
      ...profile,
      has_api_key: Boolean(keys[credentialKey(profile.base_url)]),
    })),
    has_hf_token: Boolean(resolveHfToken()),
  };
}

function normalizeProvider(raw: unknown): ProviderProfile | null {
  if (!raw || typeof raw !== 'object') return null;
  const profile = raw as Record<string, unknown>;
  const id = typeof profile.id === 'string' && profile.id ? profile.id : `prov_${Math.random().toString(36).slice(2)}`;
  let models: string[] = [];
  if (Array.isArray(profile.models)) {
    models = profile.models.filter((value): value is string => typeof value === 'string' && value.trim().length > 0);
  } else if (typeof profile.model === 'string' && profile.model.trim()) {
    // Migrate the legacy single-model shape.
    models = [profile.model.trim()];
  }
  const availableModels = Array.isArray(profile.available_models)
    ? profile.available_models.filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
    : [...models];
  const modelOptions: Record<string, { reasoning_effort?: string; fast?: boolean }> = {};
  if (profile.model_options && typeof profile.model_options === 'object' && !Array.isArray(profile.model_options)) {
    for (const [model, rawOptions] of Object.entries(profile.model_options as Record<string, unknown>)) {
      if (!rawOptions || typeof rawOptions !== 'object' || Array.isArray(rawOptions)) continue;
      const options = rawOptions as Record<string, unknown>;
      modelOptions[model] = {
        reasoning_effort: typeof options.reasoning_effort === 'string' ? options.reasoning_effort : undefined,
        fast: typeof options.fast === 'boolean' ? options.fast : undefined,
      };
    }
  }
  return {
    id,
    preset_key: typeof profile.preset_key === 'string' ? profile.preset_key : undefined,
    label: typeof profile.label === 'string' ? profile.label : '',
    provider: typeof profile.provider === 'string' ? profile.provider : 'openai_compatible',
    base_url: typeof profile.base_url === 'string' ? profile.base_url : '',
    api_key_env: typeof profile.api_key_env === 'string' ? profile.api_key_env : '',
    auth_type: typeof profile.auth_type === 'string' ? profile.auth_type : 'none',
    temperature: typeof profile.temperature === 'number' ? profile.temperature : 0.2,
    models,
    available_models: availableModels,
    models_refreshed_at: typeof profile.models_refreshed_at === 'number' ? profile.models_refreshed_at : undefined,
    model_options: modelOptions,
  };
}

function readSettings(): AppSettings {
  try {
    const raw = JSON.parse(readFileSync(settingsPath(), 'utf8')) as Partial<AppSettings> & Record<string, unknown>;
    const providers = Array.isArray(raw.providers)
      ? raw.providers.map(normalizeProvider).filter((value): value is ProviderProfile => value !== null)
      : [];
    let activeModel = typeof raw.active_model === 'string' ? raw.active_model : '';
    if (!activeModel) {
      // Migrate: legacy active provider stored its model on the profile.
      const legacyActive = (raw.providers as Array<Record<string, unknown>> | undefined)?.find(
        (entry) => entry && entry.id === raw.active_provider_id,
      );
      if (legacyActive && typeof legacyActive.model === 'string') {
        activeModel = legacyActive.model;
      }
    }
    const merged: AppSettings = {
      providers,
      active_provider_id: typeof raw.active_provider_id === 'string' ? raw.active_provider_id : '',
      active_model: activeModel,
      active_mode_id: typeof raw.active_mode_id === 'string' ? raw.active_mode_id : '',
      embedding_model: typeof raw.embedding_model === 'string' && raw.embedding_model.trim()
        ? raw.embedding_model.trim()
        : 'hashing',
      ingest_pipeline: typeof raw.ingest_pipeline === 'string' && raw.ingest_pipeline.trim()
        ? raw.ingest_pipeline.trim()
        : 'pymupdf',
      ingest_pipeline_configs: normalizePipelineConfigs(raw.ingest_pipeline_configs),
    };
    return withRuntime(merged);
  } catch {
    return withRuntime({ ...DEFAULT_SETTINGS });
  }
}

function writeSettings(settings: AppSettings): AppSettings {
  mkdirSync(app.getPath('userData'), { recursive: true });
  const sanitized: AppSettings = {
    providers: (settings.providers || [])
      .map(normalizeProvider)
      .filter((value): value is ProviderProfile => value !== null),
    active_provider_id: settings.active_provider_id || '',
    active_model: settings.active_model || '',
    active_mode_id: settings.active_mode_id || '',
    embedding_model: settings.embedding_model?.trim() || 'hashing',
    ingest_pipeline: settings.ingest_pipeline?.trim() || 'pymupdf',
    ingest_pipeline_configs: normalizePipelineConfigs(settings.ingest_pipeline_configs),
  };
  const target = settingsPath();
  const temp = `${target}.tmp`;
  writeFileSync(temp, JSON.stringify(sanitized, null, 2), 'utf8');
  renameSync(temp, target);
  return withRuntime(sanitized);
}

function saveApiKey(baseUrl: string, apiKey: string): CredentialResult {
  if (!safeStorage.isEncryptionAvailable()) {
    return { ok: false, has_api_key: false, error: 'Secure credential storage is unavailable on this system.' };
  }
  const key = credentialKey(baseUrl);
  if (!key) {
    return { ok: false, has_api_key: false, error: 'Set the provider base URL before storing an API key.' };
  }
  const keys = readApiKeys();
  keys[key] = apiKey;
  writeApiKeys(keys);
  return { ok: true, has_api_key: true };
}

function clearApiKey(baseUrl: string): CredentialResult {
  const key = credentialKey(baseUrl);
  const keys = readApiKeys();
  if (key in keys) {
    delete keys[key];
    writeApiKeys(keys);
  }
  return { ok: true, has_api_key: false };
}

function saveHfToken(token: string): CredentialResult {
  if (!safeStorage.isEncryptionAvailable()) {
    return { ok: false, has_api_key: false, error: 'Secure credential storage is unavailable on this system.' };
  }
  const trimmed = token.trim();
  if (!trimmed) {
    return { ok: false, has_api_key: false, error: 'Enter a Hugging Face token first.' };
  }
  const keys = readApiKeys();
  keys[HF_TOKEN_SECRET_KEY] = trimmed;
  writeApiKeys(keys);
  sidecar.restart();
  return { ok: true, has_api_key: true };
}

function clearHfToken(): CredentialResult {
  const keys = readApiKeys();
  if (HF_TOKEN_SECRET_KEY in keys) {
    delete keys[HF_TOKEN_SECRET_KEY];
    writeApiKeys(keys);
  }
  sidecar.restart();
  return { ok: true, has_api_key: Boolean(environmentHfToken()) };
}

function withStoredApiKey(payload: SidecarPayload): SidecarPayload {
  if ((payload.action !== 'answer' && payload.action !== 'list_models') || typeof payload.llm !== 'object' || payload.llm === null) {
    return payload;
  }
  const llm = payload.llm as Record<string, unknown>;
  if (llm.auth_type !== 'api_key') {
    return payload;
  }
  const key = credentialKey(llm.base_url);
  const apiKey = key ? readApiKeys()[key] : undefined;
  return apiKey ? { ...payload, llm: { ...llm, api_key: apiKey } } : payload;
}

function withModesDir(payload: SidecarPayload): SidecarPayload {
  if (payload.action === 'answer' || payload.action === 'list_modes') {
    return { ...payload, modes_dir: modesDir() };
  }
  return payload;
}

async function pickArchivePath(): Promise<string | null> {
  const result = await dialog.showOpenDialog({
    title: 'Open VERA archive',
    properties: ['openFile'],
    filters: [{ name: 'VERA Archives', extensions: ['vera'] }],
  });
  return result.canceled ? null : result.filePaths[0];
}

async function pickFolderPath(): Promise<string | null> {
  const result = await dialog.showOpenDialog({
    title: 'Open VERA library folder',
    properties: ['openDirectory'],
  });
  return result.canceled ? null : result.filePaths[0];
}

function listFolder(dir: string): WorkspaceFolderResult | null {
  return listFolderEntries(dir);
}

function isWorkspaceFile(filePath: string, folderPath: string): boolean {
  if (typeof filePath !== 'string' || typeof folderPath !== 'string') return false;
  const file = resolve(filePath);
  const folder = resolve(folderPath);
  const relativePath = relative(folder, file);
  const lower = file.toLowerCase();
  return Boolean(relativePath)
    && !relativePath.startsWith('..')
    && !isAbsolute(relativePath)
    && (lower.endsWith('.vera') || lower.endsWith('.pdf'));
}

async function showInFolder(targetPath: string): Promise<void> {
  if (typeof targetPath !== 'string' || !targetPath.trim()) {
    throw new Error('Path is required');
  }
  const resolved = resolve(targetPath);
  if (!existsSync(resolved)) {
    throw new Error('This path is no longer available.');
  }
  if (statSync(resolved).isDirectory()) {
    const error = await shell.openPath(resolved);
    if (error) throw new Error(error);
    return;
  }
  shell.showItemInFolder(resolved);
}

async function trashWorkspaceFile(filePath: string, folderPath: string): Promise<'trashed' | 'deleted' | 'cancelled'> {
  if (!isWorkspaceFile(filePath, folderPath) || !existsSync(filePath) || !statSync(filePath).isFile()) {
    throw new Error('This file is no longer available in the open folder.');
  }
  const confirmation = await dialog.showMessageBox({
    type: 'warning',
    buttons: ['Cancel', 'Move to Recycle Bin'],
    defaultId: 0,
    cancelId: 0,
    noLink: true,
    message: `Move "${basename(filePath)}" to the Recycle Bin?`,
    detail: 'The file will be removed from this library.',
  });
  if (confirmation.response !== 1) return 'cancelled';
  try {
    await shell.trashItem(filePath);
    return 'trashed';
  } catch {
    const permanentConfirmation = await dialog.showMessageBox({
      type: 'warning',
      buttons: ['Cancel', 'Delete permanently'],
      defaultId: 0,
      cancelId: 0,
      noLink: true,
      message: 'The Recycle Bin is unavailable for this location.',
      detail: `This may be a removable drive. Permanently delete "${basename(filePath)}" instead?`,
    });
    if (permanentConfirmation.response !== 1) return 'cancelled';
    unlinkSync(filePath);
    return 'deleted';
  }
}

const folderWatchers = new Map<string, FolderWatcher>();
const folderChangeTimers = new Map<string, NodeJS.Timeout>();

function folderWatcherKey(path: string): string {
  const absolute = resolve(path);
  return process.platform === 'win32' ? absolute.toLowerCase() : absolute;
}

function scheduleFolderChanged(folderPath: string): void {
  const key = folderWatcherKey(folderPath);
  const existing = folderChangeTimers.get(key);
  if (existing) clearTimeout(existing);
  folderChangeTimers.set(key, setTimeout(() => {
    folderChangeTimers.delete(key);
    for (const win of BrowserWindow.getAllWindows()) {
      if (!win.isDestroyed()) win.webContents.send(IPC_CHANNELS.folderChanged, folderPath);
    }
  }, 200));
}

function setWatchedFolders(paths: string[]): void {
  const requested = new Map<string, string>();
  for (const path of paths) {
    if (typeof path !== 'string' || !path.trim() || !existsSync(path)) continue;
    requested.set(folderWatcherKey(path), resolve(path));
  }

  for (const [key, entry] of folderWatchers) {
    if (requested.has(key)) continue;
    entry.watcher.close();
    folderWatchers.delete(key);
    const timer = folderChangeTimers.get(key);
    if (timer) clearTimeout(timer);
    folderChangeTimers.delete(key);
  }

  for (const [key, folderPath] of requested) {
    if (folderWatchers.has(key)) continue;
    try {
      const watcher = watch(folderPath, { recursive: true }, () => scheduleFolderChanged(folderPath));
      watcher.on('error', () => {
        watcher.close();
        folderWatchers.delete(key);
      });
      folderWatchers.set(key, { path: folderPath, watcher });
    } catch {
      // The folder may have been removed or become inaccessible between listing and watching.
    }
  }
}

function stopFolderWatchers(): void {
  for (const entry of folderWatchers.values()) entry.watcher.close();
  folderWatchers.clear();
  for (const timer of folderChangeTimers.values()) clearTimeout(timer);
  folderChangeTimers.clear();
}

function sendOpenTarget(path: string | null): void {
  if (!path) return;
  BrowserWindow.getFocusedWindow()?.webContents.send(IPC_CHANNELS.openTarget, path);
}

function sendOpenSettings(): void {
  BrowserWindow.getFocusedWindow()?.webContents.send(IPC_CHANNELS.openSettings);
}

function configureMenu(): void {
  const template: Electron.MenuItemConstructorOptions[] = [
    {
      id: 'fileMenu',
      label: 'File',
      submenu: [
        {
          label: 'Open...',
          accelerator: 'CmdOrCtrl+O',
          click: async () => sendOpenTarget(await pickArchivePath()),
        },
        {
          label: 'Open Folder...',
          accelerator: 'CmdOrCtrl+Shift+O',
          click: async () => sendOpenTarget(await pickFolderPath()),
        },
        { type: 'separator' },
        {
          label: 'LLM Providers...',
          accelerator: 'CmdOrCtrl+,',
          click: () => sendOpenSettings(),
        },
        {
          label: 'Answer Modes Folder...',
          click: () => {
            void shell.openPath(modesDir());
          },
        },
        { type: 'separator' },
        { role: process.platform === 'darwin' ? 'close' : 'quit' },
      ],
    },
    { id: 'editMenu', role: 'editMenu' },
    {
      id: 'viewMenu',
      label: 'View',
      submenu: [
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        ...(!app.isPackaged ? [{ role: 'toggleDevTools' as const }] : []),
        { role: 'togglefullscreen' },
      ],
    },
    {
      id: 'helpMenu',
      label: 'Help',
      submenu: [
        {
          label: 'About VERA',
          click: () => {
            void dialog.showMessageBox({
              type: 'info',
              title: 'About VERA',
              message: 'VERA',
              detail: `Version ${app.getVersion()}`,
            });
          },
        },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

function createWindow(): void {
  const preload = fileURLToPath(new URL('./preload.cjs', import.meta.url));
  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    // Match the three-pane CSS floor (side + 420px chat + 400px viewer) so the
    // window cannot shrink into document-level scrollbars or wrap the PDF toolbar.
    minWidth: 1200,
    minHeight: 660,
    title: 'VERA',
    backgroundColor: '#f3f1ec',
    ...(process.platform !== 'darwin' ? {
      titleBarStyle: 'hidden' as const,
      titleBarOverlay: {
        color: '#181818',
        symbolColor: '#cccccc',
        height: 30,
      },
    } : {}),
    webPreferences: {
      preload,
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  if (process.platform !== 'darwin') win.setMenuBarVisibility(false);

  if (app.isPackaged) {
    const packagedIndex = join(app.getAppPath(), 'dist', 'index.html');
    win.loadFile(packagedIndex);
  } else {
    win.loadURL('http://127.0.0.1:5173');
  }
}

app.whenReady().then(() => {
  configureMenu();
  mkdirSync(sourceCacheDir(), { recursive: true });
  protocol.handle('vera-source', (request) => {
    try {
      const parsed = new URL(request.url);
      if (parsed.hostname !== 'cache') {
        return new Response('Not found', { status: 404 });
      }
      const relativePath = decodeURIComponent(parsed.pathname.replace(/^\/+/, ''));
      if (!relativePath || relativePath.includes('\0')) {
        return new Response('Not found', { status: 404 });
      }
      const root = resolve(sourceCacheDir());
      const filePath = resolve(root, relativePath);
      if (!isPathInsideDir(filePath, root) || !existsSync(filePath) || !statSync(filePath).isFile()) {
        return new Response('Not found', { status: 404 });
      }
      return net.fetch(pathToFileURL(filePath).href);
    } catch (error) {
      console.error('[vera-source] Failed to serve cached source document', error);
      return new Response('Not found', { status: 404 });
    }
  });
  ipcMain.handle(IPC_CHANNELS.showMenu, (event, menuId: string, x: number, y: number) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    const item = Menu.getApplicationMenu()?.getMenuItemById(menuId);
    if (!win || !item?.submenu) return false;
    item.submenu.popup({
      window: win,
      x: Math.round(x),
      y: Math.round(y),
    });
    return true;
  });
  ipcMain.handle(IPC_CHANNELS.getSessions, async () => readSessions());
  ipcMain.handle(IPC_CHANNELS.saveSession, async (_event, session: Session) => upsertSession(session));
  ipcMain.handle(IPC_CHANNELS.deleteSession, async (_event, id: string) => deleteSession(id));
  ipcMain.handle(IPC_CHANNELS.request, async (event, payload: SidecarPayload, requestId?: string) => {
    const sender = event.sender;
    const onEvent = (e: SidecarEvent) => {
      if (!sender.isDestroyed()) sender.send(IPC_CHANNELS.answerEvent, e);
    };
    const prepared = withModesDir(withStoredApiKey(payload));
    const request = prepared.action === 'source'
      ? { ...prepared, cache_dir: sourceCacheDir() }
      : prepared;
    const response = await sidecar.request(request, onEvent, requestId);
    if (
      response.ok
      && request.action === 'source'
      && response.result
      && typeof response.result === 'object'
    ) {
      try {
        return {
          ...response,
          result: toSourceViewerResult(response.result as Record<string, unknown>),
        };
      } catch (error) {
        return {
          ...response,
          ok: false,
          result: undefined,
          error: error instanceof Error ? error.message : 'Unable to prepare source document',
        };
      }
    }
    return response;
  });
  ipcMain.handle(IPC_CHANNELS.cancelAnswer, (_event, requestId: string) => sidecar.cancelAnswer(requestId));
  ipcMain.handle(IPC_CHANNELS.cancelRequest, (_event, requestId: string) => sidecar.cancelRequest(requestId));
  ipcMain.handle(IPC_CHANNELS.skipConversion, (_event, requestId: string) => sidecar.skipConversion(requestId));
  ipcMain.handle(IPC_CHANNELS.listModes, async () => sidecar.request({ action: SIDECAR_ACTIONS.listModes, modes_dir: modesDir() }));
  ipcMain.handle(IPC_CHANNELS.openModesFolder, async () => shell.openPath(modesDir()));
  ipcMain.handle(IPC_CHANNELS.getSettings, async () => readSettings());
  ipcMain.handle(IPC_CHANNELS.saveSettings, async (_event, settings: AppSettings) => writeSettings(settings));
  ipcMain.handle(IPC_CHANNELS.saveApiKey, async (_event, providerId: string, apiKey: string) => saveApiKey(providerId, apiKey));
  ipcMain.handle(IPC_CHANNELS.clearApiKey, async (_event, providerId: string) => clearApiKey(providerId));
  ipcMain.handle(IPC_CHANNELS.saveHfToken, async (_event, token: string) => saveHfToken(token));
  ipcMain.handle(IPC_CHANNELS.clearHfToken, async () => clearHfToken());
  ipcMain.handle(IPC_CHANNELS.pickArchive, async () => pickArchivePath());
  ipcMain.handle(IPC_CHANNELS.pickFolder, async () => pickFolderPath());
  ipcMain.handle(IPC_CHANNELS.listFolder, async (_event, dir: string) => listFolder(dir));
  ipcMain.handle(IPC_CHANNELS.pathExists, async (_event, targetPath: string) => (
    typeof targetPath === 'string' && Boolean(targetPath.trim()) && existsSync(resolve(targetPath))
  ));
  ipcMain.handle(IPC_CHANNELS.showInFolder, async (_event, targetPath: string) => showInFolder(targetPath));
  ipcMain.handle(IPC_CHANNELS.trashWorkspaceFile, async (_event, filePath: string, folderPath: string) => trashWorkspaceFile(filePath, folderPath));
  ipcMain.handle(IPC_CHANNELS.setWatchedFolders, async (_event, paths: string[]) => {
    setWatchedFolders(Array.isArray(paths) ? paths : []);
  });
  ipcMain.handle(IPC_CHANNELS.pickPdf, async (event) => {
    const owner = BrowserWindow.fromWebContents(event.sender);
    const options: Electron.OpenDialogOptions = {
      title: 'Open PDFs',
      buttonLabel: 'Select',
      properties: ['openFile', 'multiSelections'],
      filters: [{ name: 'PDF Documents', extensions: ['pdf'] }],
    };
    const result = owner
      ? await dialog.showOpenDialog(owner, options)
      : await dialog.showOpenDialog(options);
    return result.canceled ? [] : result.filePaths;
  });
  ipcMain.handle(IPC_CHANNELS.saveAny, async () => {
    const result = await dialog.showSaveDialog({ title: 'Save file' });
    return result.canceled ? null : result.filePath;
  });
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('before-quit', () => {
  stopFolderWatchers();
  sidecar.stop();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
