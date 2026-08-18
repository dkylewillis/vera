import type { ChildProcessWithoutNullStreams } from 'node:child_process';
import { spawn } from 'node:child_process';
import { parseSidecarJsonLine } from './sidecar-json.js';
import { logSidecarStderr } from './sidecar-log.js';

export interface JsonLineRequest {
  action: string;
  [key: string]: unknown;
}

export interface JsonLineResponse {
  id?: string;
  ok: boolean;
  result?: unknown;
  error?: string;
  traceback?: string;
  cancelled?: boolean;
  provider_error_detail?: string;
}

export interface JsonLineEvent {
  id: string;
  event: string;
  [key: string]: unknown;
}

export interface JsonLineSpawnCommand {
  executable: string;
  args: string[];
  cwd?: string;
  env?: NodeJS.ProcessEnv;
}

interface PendingRequest {
  child: ChildProcessWithoutNullStreams;
  resolve: (value: JsonLineResponse) => void;
  reject: (reason?: unknown) => void;
  onEvent?: (event: JsonLineEvent) => void;
}

export class JsonLineProcess {
  private child: ChildProcessWithoutNullStreams | null = null;
  private pending = new Map<string, PendingRequest>();
  private nextId = 1;
  private stdoutBuffer = '';
  private restartWhenIdle = false;

  constructor(
    private readonly label: string,
    private readonly resolveCommand: () => JsonLineSpawnCommand,
  ) {}

  request(
    payload: JsonLineRequest,
    onEvent?: (event: JsonLineEvent) => void,
    requestId?: string,
  ): Promise<JsonLineResponse> {
    const child = this.ensureStarted();
    const id = requestId || String(this.nextId++);
    const message = { ...payload, id };
    return new Promise((resolve, reject) => {
      this.pending.set(id, { child, resolve, reject, onEvent });
      const failWrite = (error: unknown) => {
        this.pending.delete(id);
        reject(error);
      };
      try {
        if (child.stdin.destroyed || !child.stdin.writable) {
          failWrite(new Error(`${this.label} stdin is not writable`));
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
    this.rejectPending(new Error(`${this.label} stopped`));
  }

  async cancelAnswer(requestId: string): Promise<{ cancelled: boolean }> {
    const response = await this.request({ action: 'cancel', target_id: requestId });
    const result = (response.result || {}) as { cancelled?: boolean };
    return { cancelled: Boolean(result.cancelled) };
  }

  async skipConversion(requestId: string): Promise<{ skipped: boolean }> {
    const response = await this.request({ action: 'skip', target_id: requestId });
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

  restart(): void {
    if (this.pending.size > 0) {
      this.restartWhenIdle = true;
      return;
    }
    this.killChild(`${this.label} restarted`);
  }

  /** Kill even when a request is still in flight (timed-out probes). */
  forceRestart(): void {
    this.killChild(`${this.label} restarted`);
  }

  get running(): boolean {
    return this.child !== null;
  }

  private maybeRestartWhenIdle(): void {
    if (!this.restartWhenIdle || this.pending.size > 0) return;
    this.killChild(`${this.label} restarted`);
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
    const command = this.resolveCommand();
    this.child = spawn(command.executable, command.args, {
      cwd: command.cwd,
      env: command.env,
      windowsHide: true,
      shell: false,
    });
    this.child.stdout.on('data', (chunk: Buffer) => this.handleStdout(chunk.toString('utf8')));
    this.child.stderr.on('data', (chunk: Buffer) => logSidecarStderr(this.label, chunk.toString('utf8')));
    const child = this.child;
    child.on('error', (error: Error) => {
      if (this.child === child) this.child = null;
      this.rejectPending(error, child);
      this.maybeRestartWhenIdle();
    });
    child.on('exit', () => {
      if (this.child === child) this.child = null;
      this.rejectPending(new Error(`${this.label} exited`), child);
      this.maybeRestartWhenIdle();
    });
    return this.child;
  }

  private handleStdout(data: string): void {
    this.stdoutBuffer += data;
    const lines = this.stdoutBuffer.split('\n');
    this.stdoutBuffer = lines.pop() || '';
    for (const line of lines) {
      if (!line.trim()) continue;
      const parsed = parseSidecarJsonLine(line);
      if (!parsed.ok) {
        console.error(`[${this.label}] Ignoring invalid stdout line (${parsed.error}): ${line}`);
        continue;
      }
      const response = parsed.payload as unknown as JsonLineResponse & { event?: string };
      if (!response.id) continue;
      const pending = this.pending.get(response.id);
      if (!pending) continue;
      if ('event' in response && !('ok' in response)) {
        pending.onEvent?.(response as unknown as JsonLineEvent);
        continue;
      }
      this.pending.delete(response.id);
      pending.resolve(response);
      this.maybeRestartWhenIdle();
    }
  }
}
