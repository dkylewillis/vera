/**
 * Desktop supervisor for OpenAI Secure MCP Tunnel + restricted VERA MCP.
 *
 * The renderer may only request start/stop/status and non-secret config.
 * Executable paths and command strings are resolved in main process code.
 */

import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, statSync, writeFileSync, unlinkSync } from 'node:fs';
import { delimiter, dirname, join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';

export type BridgeState =
  | 'disabled'
  | 'needs_setup'
  | 'starting'
  | 'connected'
  | 'reconnecting'
  | 'error';

export interface BridgeConfig {
  libraryPath: string;
  tunnelId: string;
  /** Absolute path to tunnel-client.exe when discovered; otherwise empty. */
  tunnelClientPath?: string;
}

export interface BridgeStatus {
  state: BridgeState;
  libraryPath: string;
  tunnelId: string;
  hasCredential: boolean;
  message: string;
  lastError?: string;
  ready: boolean;
  libraryValid: boolean;
  tunnelIdValid: boolean;
  tunnelClientPath: string;
  clientDetected: boolean;
}

export interface BridgeManagerOptions {
  userDataDir: string;
  resolveMcpCommand: () => { executable: string; args: string[] };
  resolveTunnelClientPath: () => string | null;
  readTunnelCredential: () => string;
  encryptionAvailable: () => boolean;
  extraChildEnv?: () => NodeJS.ProcessEnv;
  now?: () => number;
  fetchReady?: (url: string) => Promise<boolean>;
  /** Reads the loopback base URL written by tunnel-client after it binds health. */
  readHealthUrl?: (path: string) => string | null;
  /** Receives redacted tunnel-client diagnostics for the local app log. */
  logDiagnostic?: (stream: 'stdout' | 'stderr', chunk: string) => void;
  spawnImpl?: typeof spawn;
  startupTimeoutMs?: number;
  readyPollMs?: number;
  maxRestartAttempts?: number;
}

const STARTUP_TIMEOUT_MS = 45_000;
const READY_POLL_MS = 1_000;
const MAX_RESTART_ATTEMPTS = 3;

export class BridgeManager {
  private state: BridgeState = 'disabled';
  private config: BridgeConfig = { libraryPath: '', tunnelId: '' };
  private child: ChildProcessWithoutNullStreams | null = null;
  private policyPath: string | null = null;
  private healthUrlPath: string | null = null;
  private lastError = '';
  private message = 'Bridge is disabled until you Connect.';
  private restartAttempts = 0;
  private stopping = false;
  private startGeneration = 0;
  private activeStart: Promise<BridgeStatus> | null = null;

  constructor(private readonly options: BridgeManagerOptions) {}

  getStatus(hasCredential?: boolean): BridgeStatus {
    const credential = hasCredential ?? Boolean(this.options.readTunnelCredential().trim());
    const tunnelClient = this.resolveTunnelClient();
    return {
      state: this.state,
      libraryPath: this.config.libraryPath,
      tunnelId: this.config.tunnelId,
      hasCredential: credential,
      message: this.message,
      lastError: this.lastError || undefined,
      ready: this.state === 'connected',
      libraryValid: this.libraryValid(),
      tunnelIdValid: this.tunnelIdValid(),
      tunnelClientPath: tunnelClient || this.config.tunnelClientPath || '',
      clientDetected: Boolean(tunnelClient),
    };
  }

  updateConfig(partial: Partial<BridgeConfig>): BridgeStatus {
    const configChanged =
      (partial.libraryPath !== undefined && partial.libraryPath.trim() !== this.config.libraryPath) ||
      (partial.tunnelId !== undefined && partial.tunnelId.trim() !== this.config.tunnelId) ||
      (partial.tunnelClientPath !== undefined && partial.tunnelClientPath.trim() !== (this.config.tunnelClientPath || ''));
    this.config = {
      libraryPath: partial.libraryPath?.trim() ?? this.config.libraryPath,
      tunnelId: partial.tunnelId?.trim() ?? this.config.tunnelId,
      tunnelClientPath: partial.tunnelClientPath?.trim() ?? this.config.tunnelClientPath,
    };
    if (configChanged && this.state !== 'disabled' && this.state !== 'needs_setup') {
      void this.stop('Bridge settings changed; reconnect to apply them.');
    } else if (this.state === 'disabled' || this.state === 'needs_setup') {
      this.state = this.setupComplete() ? 'disabled' : 'needs_setup';
      this.message = this.setupComplete()
        ? 'Ready to connect.'
        : this.setupIssue();
    }
    return this.getStatus();
  }

  start(): Promise<BridgeStatus> {
    if (this.activeStart) return this.activeStart;
    if (this.state === 'connected' || this.state === 'reconnecting') return Promise.resolve(this.getStatus());
    const operation = this.startInternal();
    this.activeStart = operation;
    void operation.finally(() => {
      if (this.activeStart === operation) this.activeStart = null;
    });
    return operation;
  }

  private async startInternal(): Promise<BridgeStatus> {
    if (!this.options.encryptionAvailable()) {
      return this.fail('Secure credential storage is unavailable on this system.');
    }
    const credential = this.options.readTunnelCredential().trim();
    const issue = this.setupIssue(credential);
    if (issue) {
      this.state = 'needs_setup';
      this.message = issue;
      return this.getStatus();
    }
    const tunnelClient = this.resolveTunnelClient();
    if (!tunnelClient) {
      return this.fail(
        'tunnel-client was not found. Select it in Bridge Setup or install it on PATH.',
      );
    }

    this.stopping = false;
    this.startGeneration += 1;
    const generation = this.startGeneration;
    this.state = 'starting';
    this.message = 'Starting tunnel-client…';
    this.lastError = '';

    try {
      this.policyPath = this.writePolicyFile();
      const healthUrlPath = this.prepareHealthUrlFile();
      this.healthUrlPath = healthUrlPath;
      const mcp = this.options.resolveMcpCommand();
      const args = [
        'run',
        '--control-plane.tunnel-id',
        this.config.tunnelId,
        '--mcp.command',
        [mcp.executable, ...mcp.args].map(quoteArg).join(' '),
        '--health.listen-addr',
        '127.0.0.1:0',
        '--health.url-file',
        healthUrlPath,
      ];
      const env: NodeJS.ProcessEnv = {
        PATH: process.env.PATH,
        SYSTEMROOT: process.env.SYSTEMROOT,
        WINDIR: process.env.WINDIR,
        TEMP: process.env.TEMP,
        TMP: process.env.TMP,
        CONTROL_PLANE_API_KEY: credential,
        VERA_BRIDGE_POLICY_PATH: this.policyPath,
        VERA_AUTO_INSTALL_SEMANTIC_DEPS: '0',
        ...(this.options.extraChildEnv?.() || {}),
      };
      const minilm = process.env.VERA_ONNX_MINILM_HOME || process.env.VERA_SENTENCE_TRANSFORMERS_HOME;
      if (minilm) {
        env.VERA_ONNX_MINILM_HOME = minilm;
        env.VERA_SENTENCE_TRANSFORMERS_HOME = minilm;
      }

      const spawnImpl = this.options.spawnImpl || spawn;
      this.child = spawnImpl(tunnelClient, args, {
        cwd: dirname(tunnelClient),
        env,
        windowsHide: true,
        stdio: ['ignore', 'pipe', 'pipe'],
      }) as unknown as ChildProcessWithoutNullStreams;

      const child = this.child;
      child.stdout?.on('data', (chunk: Buffer) => {
        this.logDiagnostic('stdout', chunk.toString('utf8'), credential);
      });
      child.stderr?.on('data', (chunk: Buffer) => {
        this.logDiagnostic('stderr', chunk.toString('utf8'), credential);
      });
      child.on('error', (error: Error) => {
        if (this.child === child) this.child = null;
        void this.handleExit(generation, error.message);
      });
      child.on('exit', (code, signal) => {
        if (this.child === child) this.child = null;
        if (this.stopping) return;
        void this.handleExit(
          generation,
          `tunnel-client exited (code=${code ?? 'null'}, signal=${signal ?? 'null'})`,
        );
      });

      const ready = await this.waitUntilReady(generation, healthUrlPath);
      if (!ready) {
        await this.stopInternal('Startup timed out before tunnel-client became ready.');
        return this.fail('Startup timed out before tunnel-client became ready.');
      }
      this.restartAttempts = 0;
      this.state = 'connected';
      this.message = 'Connected. ChatGPT developer-mode apps can use the approved library.';
      return this.getStatus();
    } catch (error) {
      const text = error instanceof Error ? error.message : String(error);
      await this.stopInternal(text);
      return this.fail(text);
    }
  }

  async stop(reason = 'Disconnected.'): Promise<BridgeStatus> {
    await this.stopInternal(reason);
    this.state = this.setupComplete() ? 'disabled' : 'needs_setup';
    this.message = reason;
    this.lastError = '';
    return this.getStatus();
  }

  private async stopInternal(reason: string): Promise<void> {
    this.stopping = true;
    this.startGeneration += 1;
    const child = this.child;
    this.child = null;
    if (child && !child.killed) {
      try {
        child.kill();
      } catch {
        /* ignore */
      }
      // Best-effort tree kill on Windows.
      if (process.platform === 'win32' && child.pid) {
        try {
          spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], {
            windowsHide: true,
            stdio: 'ignore',
          });
        } catch {
          /* ignore */
        }
      }
      await delay(50);
    }
    this.cleanupPolicy();
    this.cleanupHealthUrlFile();
    this.stopping = false;
    if (reason) this.message = reason;
  }

  private async handleExit(generation: number, reason: string): Promise<void> {
    if (generation !== this.startGeneration || this.stopping) return;
    this.cleanupPolicy();
    // A startup promise can still be awaiting readiness after the child exits.
    // Do not let that stale promise suppress the scheduled reconnect.
    this.activeStart = null;
    if (this.restartAttempts >= (this.options.maxRestartAttempts ?? MAX_RESTART_ATTEMPTS)) {
      this.fail(reason);
      return;
    }
    this.restartAttempts += 1;
    this.state = 'reconnecting';
    this.message = `Reconnecting (attempt ${this.restartAttempts})…`;
    this.lastError = reason;
    await delay(Math.min(5_000, 500 * 2 ** (this.restartAttempts - 1)));
    if (generation !== this.startGeneration || this.stopping) return;
    this.state = 'disabled';
    await this.start();
  }

  private async waitUntilReady(generation: number, healthUrlPath: string): Promise<boolean> {
    const timeout = this.options.startupTimeoutMs ?? STARTUP_TIMEOUT_MS;
    const poll = this.options.readyPollMs ?? READY_POLL_MS;
    const started = (this.options.now || Date.now)();
    const fetchReady =
      this.options.fetchReady ||
      (async (url: string) => {
        try {
          const response = await fetch(url);
          return response.ok;
        } catch {
          return false;
        }
      });
    while ((this.options.now || Date.now)() - started < timeout) {
      if (generation !== this.startGeneration || this.stopping || !this.child) return false;
      const baseUrl = this.readValidatedHealthUrl(healthUrlPath);
      if (baseUrl && await fetchReady(`${baseUrl}/readyz`)) return true;
      // Some client builds expose liveness only on /healthz.
      if (baseUrl && await fetchReady(`${baseUrl}/healthz`)) return true;
      await delay(poll);
    }
    return false;
  }

  private writePolicyFile(): string {
    const dir = join(this.options.userDataDir, 'bridge');
    mkdirSync(dir, { recursive: true });
    const path = join(dir, 'policy.json');
    const payload = {
      library_root: this.config.libraryPath,
      max_top_k: 20,
      max_context_chunks: 2,
      max_sources: 12,
    };
    writeFileSync(path, JSON.stringify(payload, null, 2), 'utf8');
    return path;
  }

  private prepareHealthUrlFile(): string {
    const dir = join(this.options.userDataDir, 'bridge');
    mkdirSync(dir, { recursive: true });
    const path = join(dir, 'health-url.txt');
    try {
      unlinkSync(path);
    } catch {
      /* A missing file is expected before tunnel-client starts. */
    }
    return path;
  }

  private cleanupPolicy(): void {
    if (!this.policyPath) return;
    try {
      unlinkSync(this.policyPath);
    } catch {
      /* ignore */
    }
    this.policyPath = null;
  }

  private cleanupHealthUrlFile(): void {
    if (!this.healthUrlPath) return;
    try {
      unlinkSync(this.healthUrlPath);
    } catch {
      /* The client may have failed before creating the file. */
    }
    this.healthUrlPath = null;
  }

  private readValidatedHealthUrl(path: string): string | null {
    const readHealthUrl = this.options.readHealthUrl || defaultReadHealthUrl;
    const value = readHealthUrl(path);
    if (!value) return null;
    try {
      const url = new URL(value.trim());
      const loopback = url.hostname === '127.0.0.1' || url.hostname === '::1' || url.hostname === '[::1]';
      if (url.protocol !== 'http:' || !loopback || !url.port || url.pathname !== '/') return null;
      return url.toString().replace(/\/$/u, '');
    } catch {
      return null;
    }
  }

  private logDiagnostic(stream: 'stdout' | 'stderr', chunk: string, credential: string): void {
    const logger = this.options.logDiagnostic;
    if (!logger || !chunk) return;
    logger(stream, redactBridgeDiagnostic(chunk, credential));
  }

  private setupComplete(credential?: string): boolean {
    return !this.setupIssue(credential);
  }

  private setupIssue(credential?: string): string {
    if (!this.config.libraryPath) return 'Choose the approved library folder.';
    if (!this.libraryValid()) return 'The approved library folder does not exist or is not a folder.';
    if (!this.config.tunnelId) return 'Enter the Secure MCP Tunnel ID.';
    if (!this.tunnelIdValid()) return 'Tunnel IDs must start with tunnel_ and contain only letters, numbers, underscores, or hyphens.';
    const key = credential ?? this.options.readTunnelCredential().trim();
    if (!key) return 'Save the tunnel runtime API key.';
    if (!this.resolveTunnelClient()) return 'Select tunnel-client or install it on PATH.';
    return '';
  }

  private libraryValid(): boolean {
    if (!this.config.libraryPath) return false;
    try {
      return statSync(this.config.libraryPath).isDirectory();
    } catch {
      return false;
    }
  }

  private tunnelIdValid(): boolean {
    return /^tunnel_[A-Za-z0-9_-]+$/u.test(this.config.tunnelId);
  }

  private resolveTunnelClient(): string | null {
    if (this.config.tunnelClientPath && existsSync(this.config.tunnelClientPath)) {
      return this.config.tunnelClientPath;
    }
    return this.options.resolveTunnelClientPath();
  }

  private fail(message: string): BridgeStatus {
    this.state = 'error';
    this.lastError = message;
    this.message = message;
    return this.getStatus();
  }
}

function quoteArg(value: string): string {
  // tunnel-client parses this embedded command. Its Windows parser treats
  // backslashes as escapes, while Windows accepts forward-slash file paths.
  // Always normalize so packaged Windows sidecar paths stay valid when unit
  // tests (or a Linux host) feed a Windows-style executable path.
  const normalized = value.replace(/\\/g, '/');
  if (!/[ \t"]/u.test(normalized)) return normalized;
  return `"${normalized.replace(/"/g, '\\"')}"`;
}

function defaultReadHealthUrl(path: string): string | null {
  try {
    return readFileSync(path, 'utf8').trim() || null;
  } catch {
    return null;
  }
}

/** Remove credentials from tunnel-client output before it reaches a local log. */
export function redactBridgeDiagnostic(text: string, credential: string): string {
  let redacted = text;
  if (credential) {
    redacted = redacted.replaceAll(credential, '[REDACTED]');
  }
  return redacted
    .replace(/\bsk-[A-Za-z0-9_-]+\b/gu, '[REDACTED]')
    .replace(/\b(Bearer\s+)[^\s]+/giu, '$1[REDACTED]')
    .replace(/\b(CONTROL_PLANE_API_KEY|OPENAI_API_KEY)\s*=\s*[^\s]+/giu, '$1=[REDACTED]');
}

/** Locate tunnel-client without accepting renderer-supplied executables. */
export function findTunnelClientOnPath(env: NodeJS.ProcessEnv = process.env): string | null {
  const configured = (env.VERA_TUNNEL_CLIENT || '').trim();
  if (configured && existsSync(configured)) return configured;
  const pathEnv = env.PATH || env.Path || '';
  const exe = process.platform === 'win32' ? 'tunnel-client.exe' : 'tunnel-client';
  for (const entry of pathEnv.split(delimiter)) {
    if (!entry) continue;
    const candidate = join(entry, exe);
    if (existsSync(candidate)) return candidate;
  }
  return null;
}
