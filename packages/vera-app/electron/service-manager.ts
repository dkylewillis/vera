/**
 * Desktop supervisor for the loopback VERA agent service.
 *
 * One process serves every local agent. The bearer token is stored with
 * safeStorage and passed in the child environment, never on argv.
 */

import { randomBytes } from 'node:crypto';
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { createServer } from 'node:net';
import { existsSync, mkdirSync, statSync, unlinkSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import {
  AGENT_SERVICE_CLOUD_DISCLOSURE,
  AGENT_SERVICE_DISCLOSURE,
  DEFAULT_AGENT_SERVICE_PORT,
  agentServiceSnippets,
  type AgentSnippets,
} from '../src/shared/agent-snippets.js';
import type { RelayCloudStatus } from '../src/shared/contracts.js';

export type ServiceState = 'disabled' | 'starting' | 'running' | 'error';

export interface ServiceConfig {
  enabled: boolean;
  libraryRoots: string[];
  port: number;
  cloudEnabled: boolean;
}

export interface ServiceStatus {
  state: ServiceState;
  enabled: boolean;
  libraryRoots: string[];
  port: number;
  url: string;
  connectFile: string;
  command: string;
  args: string[];
  token: string;
  message: string;
  lastError?: string;
  portChanged: boolean;
  cloudEnabled: boolean;
  cloud: RelayCloudStatus;
  snippets: AgentSnippets;
}

export interface ServiceCommand {
  executable: string;
  args: string[];
}

export interface ServiceManagerOptions {
  userDataDir: string;
  /** Command that already ends with the `mcp-service` mode. */
  resolveCommand: () => ServiceCommand;
  readToken: () => string;
  writeToken: (token: string) => void;
  encryptionAvailable: () => boolean;
  extraChildEnv?: () => NodeJS.ProcessEnv;
  fetchHealth?: (url: string) => Promise<boolean>;
  findFreePort?: (preferred: number) => Promise<number>;
  spawnImpl?: typeof spawn;
  logDiagnostic?: (chunk: string) => void;
  cloudStatus?: () => RelayCloudStatus;
  startupTimeoutMs?: number;
  readyPollMs?: number;
  maxRestartAttempts?: number;
}

const STARTUP_TIMEOUT_MS = 30_000;
const READY_POLL_MS = 250;
const MAX_RESTART_ATTEMPTS = 3;
const PORT_ATTEMPTS = 8;

export class ServiceManager {
  private state: ServiceState = 'disabled';
  private config: ServiceConfig = {
    enabled: false,
    libraryRoots: [],
    port: DEFAULT_AGENT_SERVICE_PORT,
    cloudEnabled: false,
  };
  private child: ChildProcessWithoutNullStreams | null = null;
  private boundPort: number | null = null;
  private portChanged = false;
  private lastError = '';
  private message = 'Agent access is off.';
  private restartAttempts = 0;
  private stopping = false;
  private startGeneration = 0;
  private activeStart: Promise<ServiceStatus> | null = null;

  constructor(private readonly options: ServiceManagerOptions) {}

  getStatus(): ServiceStatus {
    const port = this.boundPort ?? this.normalizePort(this.config.port);
    const token = this.options.readToken().trim();
    const connectFile = this.connectFilePath();
    const command = this.safeCommand();
    const args = connectLaunchArgs(command.args, connectFile);
    const url = `http://127.0.0.1:${port}/mcp`;
    return {
      state: this.state,
      enabled: this.config.enabled,
      libraryRoots: [...this.config.libraryRoots],
      port,
      url,
      connectFile,
      command: command.executable,
      args,
      token,
      message: this.message,
      lastError: this.lastError || undefined,
      portChanged: this.portChanged,
      cloudEnabled: this.config.cloudEnabled,
      cloud: this.options.cloudStatus?.() ?? { state: 'off', message: '', connectorUrl: '' },
      snippets: agentServiceSnippets({
        url,
        token,
        command: command.executable,
        args,
      }),
    };
  }

  updateConfig(partial: Partial<ServiceConfig>): ServiceStatus {
    const nextRoots = partial.libraryRoots
      ? normalizeRoots(partial.libraryRoots)
      : this.config.libraryRoots;
    const nextPort = partial.port === undefined ? this.config.port : this.normalizePort(partial.port);
    const nextEnabled = partial.enabled === undefined ? this.config.enabled : partial.enabled;
    const nextCloud = partial.cloudEnabled === undefined ? this.config.cloudEnabled : partial.cloudEnabled;
    this.config = { enabled: nextEnabled, libraryRoots: nextRoots, port: nextPort, cloudEnabled: nextCloud };
    if (!nextEnabled && this.state === 'disabled') {
      this.message = 'Agent access is off.';
      this.boundPort = null;
      this.portChanged = false;
    }
    return this.getStatus();
  }

  /** Apply settings. Restarts a live process when the libraries or port change. */
  async reconfigure(partial: Partial<ServiceConfig>): Promise<ServiceStatus> {
    const wasLive = this.state === 'running' || this.state === 'starting';
    const nextRoots = partial.libraryRoots ? normalizeRoots(partial.libraryRoots) : this.config.libraryRoots;
    const nextPort = partial.port === undefined ? this.config.port : this.normalizePort(partial.port);
    const nextEnabled = partial.enabled === undefined ? this.config.enabled : partial.enabled;
    const nextCloud = partial.cloudEnabled === undefined ? this.config.cloudEnabled : partial.cloudEnabled;
    const rootsChanged = !sameRoots(nextRoots, this.config.libraryRoots);
    const portChanged = nextPort !== this.normalizePort(this.config.port);
    const cloudChanged = nextCloud !== this.config.cloudEnabled;
    this.updateConfig({ enabled: nextEnabled, libraryRoots: nextRoots, port: nextPort, cloudEnabled: nextCloud });
    if (!nextEnabled) {
      if (wasLive) return this.stop('Agent access is off.');
      this.state = 'disabled';
      this.message = 'Agent access is off.';
      return this.getStatus();
    }
    if (wasLive && (rootsChanged || portChanged || cloudChanged)) return this.restart();
    if (!wasLive) return this.start();
    return this.getStatus();
  }

  start(): Promise<ServiceStatus> {
    if (this.activeStart) return this.activeStart;
    if (this.state === 'running' || this.state === 'starting') return Promise.resolve(this.getStatus());
    this.config.enabled = true;
    const operation = this.startInternal();
    this.activeStart = operation;
    void operation.finally(() => {
      if (this.activeStart === operation) this.activeStart = null;
    });
    return operation;
  }

  async stop(reason = 'Agent access is off.'): Promise<ServiceStatus> {
    this.config.enabled = false;
    await this.stopInternal(reason);
    this.state = 'disabled';
    this.boundPort = null;
    this.portChanged = false;
    this.lastError = '';
    this.message = reason;
    this.deleteGrantFiles();
    return this.getStatus();
  }

  async rotateToken(): Promise<ServiceStatus> {
    if (!this.options.encryptionAvailable()) {
      return this.fail('Secure credential storage is unavailable on this system.');
    }
    const token = randomBytes(32).toString('hex');
    this.options.writeToken(token);
    if (this.boundPort) this.writeConnectFile(this.boundPort, token);
    this.message = 'Token rotated. Copy the snippets again.';
    if (this.state === 'running' || this.state === 'starting') {
      await this.restart();
    }
    return this.getStatus();
  }

  private async restart(): Promise<ServiceStatus> {
    const roots = [...this.config.libraryRoots];
    const port = this.config.port;
    const cloudEnabled = this.config.cloudEnabled;
    await this.stopInternal('Restarting agent service…');
    this.config.enabled = true;
    this.config.libraryRoots = roots;
    this.config.port = port;
    this.config.cloudEnabled = cloudEnabled;
    this.state = 'disabled';
    return this.start();
  }

  private async startInternal(): Promise<ServiceStatus> {
    if (!this.options.encryptionAvailable()) {
      return this.fail('Secure credential storage is unavailable on this system.');
    }
    const roots = this.existingRoots();
    if (!roots.length) {
      return this.fail('Choose at least one library folder that exists.');
    }
    let token = this.options.readToken().trim();
    if (!token) {
      token = randomBytes(32).toString('hex');
      this.options.writeToken(token);
    }

    this.stopping = false;
    this.startGeneration += 1;
    const generation = this.startGeneration;
    this.state = 'starting';
    this.message = 'Starting agent service…';
    this.lastError = '';

    try {
      const preferred = this.normalizePort(this.config.port);
      const port = await (this.options.findFreePort ?? findFreePort)(preferred);
      this.boundPort = port;
      this.portChanged = port !== preferred;
      const policyPath = this.writePolicy(roots);
      this.writeConnectFile(port, token);
      const command = this.options.resolveCommand();
      const args = [
        ...command.args,
        '--policy',
        policyPath,
        '--port',
        String(port),
        '--state-file',
        this.stateFilePath(),
        '--warm',
      ];
      if (args.some((arg) => arg.includes(token)) || command.executable.includes(token)) {
        throw new Error('Refusing to put the agent service token on the command line.');
      }
      const env: NodeJS.ProcessEnv = {
        PATH: process.env.PATH,
        SYSTEMROOT: process.env.SYSTEMROOT,
        WINDIR: process.env.WINDIR,
        TEMP: process.env.TEMP,
        TMP: process.env.TMP,
        VERA_SERVICE_TOKEN: token,
        VERA_AUTO_INSTALL_SEMANTIC_DEPS: '0',
        ...(this.options.extraChildEnv?.() || {}),
      };
      const minilm = process.env.VERA_ONNX_MINILM_HOME || process.env.VERA_SENTENCE_TRANSFORMERS_HOME;
      if (minilm) {
        env.VERA_ONNX_MINILM_HOME = minilm;
        env.VERA_SENTENCE_TRANSFORMERS_HOME = minilm;
      }
      const spawnImpl = this.options.spawnImpl || spawn;
      this.child = spawnImpl(command.executable, args, {
        cwd: dirname(command.executable),
        env,
        windowsHide: true,
        stdio: ['ignore', 'pipe', 'pipe'],
      }) as unknown as ChildProcessWithoutNullStreams;
      const child = this.child;
      const onChunk = (chunk: Buffer) => {
        this.options.logDiagnostic?.(redact(chunk.toString('utf8'), token));
      };
      child.stdout?.on('data', onChunk);
      child.stderr?.on('data', onChunk);
      child.on('error', (error: Error) => {
        if (this.child === child) this.child = null;
        void this.handleExit(generation, error.message);
      });
      child.on('exit', (code, signal) => {
        if (this.child === child) this.child = null;
        if (this.stopping) return;
        void this.handleExit(
          generation,
          `agent service exited (code=${code ?? 'null'}, signal=${signal ?? 'null'})`,
        );
      });

      const ready = await this.waitUntilReady(generation, port);
      if (generation !== this.startGeneration) return this.getStatus();
      if (!ready) {
        await this.stopInternal('Startup timed out before the agent service answered.');
        return this.fail('Startup timed out before the agent service answered.');
      }
      this.restartAttempts = 0;
      this.state = 'running';
      this.message = this.portChanged
        ? `Listening on port ${port}. Update any saved snippets.`
        : 'Local agents can use the shared libraries.';
      return this.getStatus();
    } catch (error) {
      if (generation !== this.startGeneration) return this.getStatus();
      const text = error instanceof Error ? error.message : String(error);
      await this.stopInternal(text);
      return this.fail(text);
    }
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
      await delay(20);
    }
    this.stopping = false;
    if (reason) this.message = reason;
  }

  private async handleExit(generation: number, reason: string): Promise<void> {
    if (generation !== this.startGeneration || this.stopping) return;
    this.activeStart = null;
    if (this.restartAttempts >= (this.options.maxRestartAttempts ?? MAX_RESTART_ATTEMPTS)) {
      this.fail(reason);
      return;
    }
    this.restartAttempts += 1;
    this.state = 'starting';
    this.message = `Restarting agent service (attempt ${this.restartAttempts})…`;
    this.lastError = reason;
    await delay(Math.min(2_000, 200 * 2 ** (this.restartAttempts - 1)));
    if (generation !== this.startGeneration || this.stopping || !this.config.enabled) return;
    this.state = 'disabled';
    await this.start();
  }

  private async waitUntilReady(generation: number, port: number): Promise<boolean> {
    const timeout = this.options.startupTimeoutMs ?? STARTUP_TIMEOUT_MS;
    const poll = this.options.readyPollMs ?? READY_POLL_MS;
    const fetchHealth = this.options.fetchHealth ?? defaultFetchHealth;
    const started = Date.now();
    const url = `http://127.0.0.1:${port}/healthz`;
    while (Date.now() - started < timeout) {
      if (generation !== this.startGeneration || this.stopping || !this.child) return false;
      if (await fetchHealth(url)) return true;
      await delay(poll);
    }
    return false;
  }

  private existingRoots(): string[] {
    return this.config.libraryRoots.filter((root) => {
      try {
        return existsSync(root) && statSync(root).isDirectory();
      } catch {
        return false;
      }
    });
  }

  private writePolicy(roots: string[]): string {
    const dir = this.serviceDir();
    mkdirSync(dir, { recursive: true });
    const path = join(dir, 'policy.json');
    writeFileSync(
      path,
      `${JSON.stringify({ library_roots: roots, disclosure: this.config.cloudEnabled ? AGENT_SERVICE_CLOUD_DISCLOSURE : AGENT_SERVICE_DISCLOSURE }, null, 2)}\n`,
      { encoding: 'utf8', mode: 0o600 },
    );
    return path;
  }

  private writeConnectFile(port: number, token: string): void {
    mkdirSync(this.serviceDir(), { recursive: true });
    writeFileSync(
      this.connectFilePath(),
      `${JSON.stringify({ url: `http://127.0.0.1:${port}/mcp`, token }, null, 2)}\n`,
      { encoding: 'utf8', mode: 0o600 },
    );
  }

  private deleteGrantFiles(): void {
    for (const path of [this.connectFilePath(), join(this.serviceDir(), 'policy.json'), this.stateFilePath()]) {
      try {
        unlinkSync(path);
      } catch {
        /* already gone */
      }
    }
  }

  private serviceDir(): string {
    return join(this.options.userDataDir, 'service');
  }

  private connectFilePath(): string {
    return join(this.serviceDir(), 'connect.json');
  }

  private stateFilePath(): string {
    return join(this.serviceDir(), 'state.json');
  }

  private safeCommand(): ServiceCommand {
    try {
      return this.options.resolveCommand();
    } catch {
      return { executable: '', args: ['mcp-service'] };
    }
  }

  private normalizePort(port: number): number {
    if (!Number.isInteger(port) || port < 1 || port > 65535) return DEFAULT_AGENT_SERVICE_PORT;
    return port;
  }

  private fail(message: string): ServiceStatus {
    this.state = 'error';
    this.lastError = message;
    this.message = message;
    return this.getStatus();
  }
}

export async function findFreePort(preferred: number): Promise<number> {
  for (let offset = 0; offset < PORT_ATTEMPTS; offset += 1) {
    const port = preferred + offset;
    if (port > 65535) break;
    if (await portIsFree(port)) return port;
  }
  throw new Error(`No free loopback port near ${preferred}.`);
}

function portIsFree(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const probe = createServer();
    probe.once('error', () => resolve(false));
    probe.listen(port, '127.0.0.1', () => {
      probe.close(() => resolve(true));
    });
  });
}

async function defaultFetchHealth(url: string): Promise<boolean> {
  try {
    const response = await fetch(url);
    return response.ok;
  } catch {
    return false;
  }
}

function normalizeRoots(roots: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const root of roots) {
    const trimmed = root.trim();
    if (!trimmed) continue;
    const key = process.platform === 'win32' ? trimmed.toLowerCase() : trimmed;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(trimmed);
  }
  return result;
}

function sameRoots(left: string[], right: string[]): boolean {
  if (left.length !== right.length) return false;
  return left.every((value, index) => value === right[index]);
}

function connectLaunchArgs(serviceArgs: string[], connectFile: string): string[] {
  const prefix = serviceArgs[serviceArgs.length - 1] === 'mcp-service'
    ? serviceArgs.slice(0, -1)
    : serviceArgs;
  return [...prefix, 'mcp-connect', '--connect-file', connectFile];
}

function redact(text: string, token: string): string {
  if (!token) return text;
  return text.split(token).join('[redacted]');
}
