/**
 * Desktop supervisor for OpenAI Secure MCP Tunnel + restricted VERA MCP.
 *
 * The renderer may only request start/stop/status and non-secret config.
 * Executable paths and command strings are resolved in main process code.
 */

import { spawn, type ChildProcess } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync, unlinkSync } from 'node:fs';
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
  private child: ChildProcess | null = null;
  private policyPath: string | null = null;
  private lastError = '';
  private message = 'Bridge is disabled until you Connect.';
  private restartAttempts = 0;
  private stopping = false;
  private startGeneration = 0;

  constructor(private readonly options: BridgeManagerOptions) {}

  getStatus(hasCredential?: boolean): BridgeStatus {
    const credential = hasCredential ?? Boolean(this.options.readTunnelCredential().trim());
    return {
      state: this.state,
      libraryPath: this.config.libraryPath,
      tunnelId: this.config.tunnelId,
      hasCredential: credential,
      message: this.message,
      lastError: this.lastError || undefined,
      ready: this.state === 'connected',
    };
  }

  updateConfig(partial: Partial<BridgeConfig>): BridgeStatus {
    const libraryChanged =
      partial.libraryPath !== undefined &&
      partial.libraryPath.trim() !== this.config.libraryPath;
    this.config = {
      libraryPath: partial.libraryPath?.trim() ?? this.config.libraryPath,
      tunnelId: partial.tunnelId?.trim() ?? this.config.tunnelId,
      tunnelClientPath: partial.tunnelClientPath ?? this.config.tunnelClientPath,
    };
    if (libraryChanged && this.state !== 'disabled' && this.state !== 'needs_setup') {
      void this.stop('Library changed; reconnect with the new grant.');
    } else if (this.state === 'disabled' || this.state === 'needs_setup') {
      this.state = this.setupComplete() ? 'disabled' : 'needs_setup';
      this.message = this.setupComplete()
        ? 'Ready to connect.'
        : 'Select a library folder, tunnel ID, and save a tunnel runtime API key.';
    }
    return this.getStatus();
  }

  async start(): Promise<BridgeStatus> {
    if (this.state === 'starting' || this.state === 'connected' || this.state === 'reconnecting') {
      return this.getStatus();
    }
    if (!this.options.encryptionAvailable()) {
      return this.fail('Secure credential storage is unavailable on this system.');
    }
    const credential = this.options.readTunnelCredential().trim();
    if (!this.setupComplete(credential)) {
      this.state = 'needs_setup';
      this.message = 'Select a library folder, tunnel ID, and save a tunnel runtime API key.';
      return this.getStatus();
    }
    const tunnelClient = this.resolveTunnelClient();
    if (!tunnelClient) {
      return this.fail(
        'tunnel-client was not found. Install the Windows client and set VERA_TUNNEL_CLIENT, or place it on PATH.',
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
      const mcp = this.options.resolveMcpCommand();
      const args = [
        'run',
        '--tunnel-id',
        this.config.tunnelId,
        '--mcp-command',
        [mcp.executable, ...mcp.args].map(quoteArg).join(' '),
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
      // stdin is ignored on purpose: the tunnel client must not accept piped input.
      this.child = spawnImpl(tunnelClient, args, {
        cwd: dirname(tunnelClient),
        env,
        windowsHide: true,
        stdio: ['ignore', 'pipe', 'pipe'],
      });

      const child = this.child;
      child.stdout?.on('data', () => {
        /* tunnel-client diagnostics stay local; never log secrets */
      });
      child.stderr?.on('data', () => {
        /* intentionally not forwarded to renderer logs in PoC */
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

      const ready = await this.waitUntilReady(generation);
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
    this.stopping = false;
    if (reason) this.message = reason;
  }

  private async handleExit(generation: number, reason: string): Promise<void> {
    if (generation !== this.startGeneration || this.stopping) return;
    this.cleanupPolicy();
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

  private async waitUntilReady(generation: number): Promise<boolean> {
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
      if (await fetchReady('http://127.0.0.1:8787/readyz')) return true;
      // Some builds expose readiness only on /healthz.
      if (await fetchReady('http://127.0.0.1:8787/healthz')) return true;
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

  private cleanupPolicy(): void {
    if (!this.policyPath) return;
    try {
      unlinkSync(this.policyPath);
    } catch {
      /* ignore */
    }
    this.policyPath = null;
  }

  private setupComplete(credential?: string): boolean {
    const key = credential ?? this.options.readTunnelCredential().trim();
    return Boolean(this.config.libraryPath && this.config.tunnelId && key);
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
  if (!/[ \t"]/u.test(value)) return value;
  return `"${value.replace(/"/g, '\\"')}"`;
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
