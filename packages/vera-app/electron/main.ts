import { app, BrowserWindow, dialog, ipcMain, Menu, safeStorage, shell } from 'electron';
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { existsSync, mkdirSync, readdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { basename, delimiter, join } from 'node:path';
import { fileURLToPath } from 'node:url';

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
}

interface SidecarEvent {
  id: string;
  event: string;
  [key: string]: unknown;
}

interface SessionTurn {
  role: 'user' | 'assistant';
  content: string;
  citations?: unknown[];
  searches?: unknown[];
  answer_mode?: string;
  mode_label?: string;
  llm?: { provider: string; model: string; usage?: unknown };
  timestamp: number;
}

interface Session {
  id: string;
  title: string;
  source_path: string;
  turns: SessionTurn[];
  created_at: number;
  updated_at: number;
}

interface SessionStore {
  sessions: Session[];
}

interface ProviderProfile {
  id: string;
  label: string;
  provider: string;
  base_url: string;
  api_key_env: string;
  auth_type: string;
  temperature: number;
  max_tokens: number;
  models: string[];
  has_api_key?: boolean;
}

interface AppSettings {
  providers: ProviderProfile[];
  active_provider_id: string;
  active_model: string;
  active_mode_id: string;
}

interface CredentialResult {
  ok: boolean;
  has_api_key: boolean;
  error?: string;
}

const DEFAULT_SETTINGS: AppSettings = {
  providers: [],
  active_provider_id: '',
  active_model: '',
  active_mode_id: '',
};

class PythonSidecar {
  private child: ChildProcessWithoutNullStreams | null = null;
  private pending = new Map<string, { resolve: (value: SidecarResponse) => void; reject: (reason?: unknown) => void; onEvent?: (e: SidecarEvent) => void }>();
  private nextId = 1;
  private stdoutBuffer = '';

  request(payload: SidecarPayload, onEvent?: (e: SidecarEvent) => void): Promise<SidecarResponse> {
    const child = this.ensureStarted();
    const id = String(this.nextId++);
    const message: SidecarRequest = { ...payload, id };
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject, onEvent });
      child.stdin.write(`${JSON.stringify(message)}\n`, (error) => {
        if (error) {
          this.pending.delete(id);
          reject(error);
        }
      });
    });
  }

  stop(): void {
    if (this.child) {
      this.child.kill();
      this.child = null;
    }
    for (const entry of this.pending.values()) {
      entry.reject(new Error('VERA sidecar stopped'));
    }
    this.pending.clear();
  }

  private ensureStarted(): ChildProcessWithoutNullStreams {
    if (this.child) {
      return this.child;
    }

    const python = process.env.VERA_APP_PYTHON || 'python';
    const env = { ...process.env };
    const sourcePaths = [join(process.cwd(), 'src'), join(process.cwd(), '..', 'vera-doc', 'src')];
    env.PYTHONPATH = [sourcePaths.join(delimiter), env.PYTHONPATH || ''].filter(Boolean).join(delimiter);

    this.child = spawn(python, ['-m', 'vera_app.sidecar'], {
      cwd: process.cwd(),
      env,
    });

    this.child.stdout.on('data', (chunk: Buffer) => this.handleStdout(chunk.toString('utf8')));
    this.child.stderr.on('data', (chunk: Buffer) => console.error(`[vera-sidecar] ${chunk.toString('utf8')}`));
    this.child.on('exit', () => {
      this.child = null;
      for (const entry of this.pending.values()) {
        entry.reject(new Error('VERA sidecar exited'));
      }
      this.pending.clear();
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
      const response = JSON.parse(line) as SidecarResponse & { event?: string };
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
  return dir;
}

function secretPath(): string {
  return join(app.getPath('userData'), 'llm-api-keys.bin');
}

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
  writeFileSync(secretPath(), safeStorage.encryptString(JSON.stringify(keys)));
}

function credentialKey(baseUrl: unknown): string {
  return typeof baseUrl === 'string' ? baseUrl.trim().replace(/\/+$/, '').toLowerCase() : '';
}

function withRuntime(settings: AppSettings): AppSettings {
  const keys = readApiKeys();
  return {
    ...settings,
    providers: settings.providers.map((profile) => ({
      ...profile,
      has_api_key: Boolean(keys[credentialKey(profile.base_url)]),
    })),
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
  return {
    id,
    label: typeof profile.label === 'string' ? profile.label : '',
    provider: typeof profile.provider === 'string' ? profile.provider : 'openai_compatible',
    base_url: typeof profile.base_url === 'string' ? profile.base_url : '',
    api_key_env: typeof profile.api_key_env === 'string' ? profile.api_key_env : '',
    auth_type: typeof profile.auth_type === 'string' ? profile.auth_type : 'none',
    temperature: typeof profile.temperature === 'number' ? profile.temperature : 0.2,
    max_tokens: typeof profile.max_tokens === 'number' ? profile.max_tokens : 700,
    models,
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
  if (typeof dir !== 'string' || !dir.trim() || !existsSync(dir)) {
    return null;
  }
  const entries: FolderEntry[] = [];
  const walk = (current: string, depth: number): void => {
    if (depth > 5) return;
    let dirents;
    try {
      dirents = readdirSync(current, { withFileTypes: true });
    } catch {
      return;
    }
    for (const dirent of dirents) {
      if (dirent.name.startsWith('.')) continue;
      const full = join(current, dirent.name);
      if (dirent.isDirectory()) {
        if (dirent.name === 'node_modules' || dirent.name === '__pycache__') continue;
        walk(full, depth + 1);
      } else {
        const lower = dirent.name.toLowerCase();
        const type = lower.endsWith('.vera') ? 'vera' : lower.endsWith('.pdf') ? 'pdf' : null;
        if (!type) continue;
        entries.push({
          path: full,
          name: dirent.name,
          relativePath: full.slice(dir.length + 1).replace(/\\/g, '/'),
          type,
        });
      }
    }
  };
  walk(dir, 0);
  entries.sort((a, b) => a.relativePath.localeCompare(b.relativePath));
  return { path: dir, name: basename(dir) || dir, entries };
}

function sendOpenTarget(path: string | null): void {
  if (!path) return;
  BrowserWindow.getFocusedWindow()?.webContents.send('vera:openTarget', path);
}

function sendOpenSettings(): void {
  BrowserWindow.getFocusedWindow()?.webContents.send('vera:openSettings');
}

function configureMenu(): void {
  const template: Electron.MenuItemConstructorOptions[] = [
    {
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
    { role: 'editMenu' },
    { role: 'viewMenu' },
    { role: 'windowMenu' },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

function createWindow(): void {
  const preload = fileURLToPath(new URL('./preload.js', import.meta.url));
  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 980,
    minHeight: 660,
    title: 'VERA',
    backgroundColor: '#f3f1ec',
    webPreferences: {
      preload,
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (app.isPackaged) {
    win.loadFile(join(process.cwd(), 'dist', 'index.html'));
  } else {
    win.loadURL('http://127.0.0.1:5173');
  }
}

app.whenReady().then(() => {
  configureMenu();
  ipcMain.handle('vera:getSessions', async () => readSessions());
  ipcMain.handle('vera:saveSession', async (_event, session: Session) => upsertSession(session));
  ipcMain.handle('vera:deleteSession', async (_event, id: string) => deleteSession(id));
  ipcMain.handle('vera:request', async (event, payload: SidecarPayload) => {
    const sender = event.sender;
    const onEvent = (e: SidecarEvent) => {
      if (!sender.isDestroyed()) sender.send('vera:answerEvent', e);
    };
    return sidecar.request(withModesDir(withStoredApiKey(payload)), onEvent);
  });
  ipcMain.handle('vera:listModes', async () => sidecar.request({ action: 'list_modes', modes_dir: modesDir() }));
  ipcMain.handle('vera:openModesFolder', async () => shell.openPath(modesDir()));
  ipcMain.handle('vera:getSettings', async () => readSettings());
  ipcMain.handle('vera:saveSettings', async (_event, settings: AppSettings) => writeSettings(settings));
  ipcMain.handle('vera:saveApiKey', async (_event, providerId: string, apiKey: string) => saveApiKey(providerId, apiKey));
  ipcMain.handle('vera:clearApiKey', async (_event, providerId: string) => clearApiKey(providerId));
  ipcMain.handle('vera:pickArchive', async () => pickArchivePath());
  ipcMain.handle('vera:pickFolder', async () => pickFolderPath());
  ipcMain.handle('vera:listFolder', async (_event, dir: string) => listFolder(dir));
  ipcMain.handle('vera:pickPdf', async () => {
    const result = await dialog.showOpenDialog({
      title: 'Open PDF',
      properties: ['openFile'],
      filters: [{ name: 'PDF Documents', extensions: ['pdf'] }],
    });
    return result.canceled ? null : result.filePaths[0];
  });
  ipcMain.handle('vera:saveVera', async (_event, defaultPath?: string) => {
    const result = await dialog.showSaveDialog({
      title: 'Save VERA archive',
      defaultPath,
      filters: [{ name: 'VERA Archives', extensions: ['vera'] }],
    });
    return result.canceled ? null : result.filePath;
  });
  ipcMain.handle('vera:saveAny', async () => {
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

app.on('before-quit', () => sidecar.stop());

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
