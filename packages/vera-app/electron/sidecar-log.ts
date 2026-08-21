import {
  appendFileSync,
  existsSync,
  mkdirSync,
  renameSync,
  statSync,
  unlinkSync,
  writeFileSync,
} from 'node:fs';
import { dirname, join } from 'node:path';

const DEFAULT_MAX_BYTES = 2 * 1024 * 1024;

let logFilePath: string | null = null;
let maxBytes = DEFAULT_MAX_BYTES;

/** `userData/logs/sidecar.log` in both `app:dev` and packaged VERA. */
export function sidecarLogFilePath(userData: string): string {
  return join(userData, 'logs', 'sidecar.log');
}

export function configuredSidecarLogPath(): string | null {
  return logFilePath;
}

export function configureSidecarLogFile(
  filePath: string,
  options?: { maxBytes?: number },
): string {
  logFilePath = filePath;
  maxBytes = options?.maxBytes ?? DEFAULT_MAX_BYTES;
  return ensureSidecarLogFile();
}

export function resetSidecarLogFileForTests(): void {
  logFilePath = null;
  maxBytes = DEFAULT_MAX_BYTES;
}

export function ensureSidecarLogFile(): string {
  if (!logFilePath) {
    throw new Error('Sidecar log is not configured');
  }
  mkdirSync(dirname(logFilePath), { recursive: true });
  if (!existsSync(logFilePath)) {
    writeFileSync(logFilePath, '');
  }
  return logFilePath;
}

export function formatSidecarTimingLine(
  step: string,
  fields: Record<string, unknown> = {},
): string {
  const parts = [`${new Date().toISOString()} timing step=${step}`];
  for (const [key, value] of Object.entries(fields)) {
    if (value === undefined || value === null || value === '') continue;
    parts.push(`${key}=${String(value).replace(/ /g, '_')}`);
  }
  return parts.join(' ');
}

function rotateSidecarLogIfNeeded(): void {
  if (!logFilePath || !existsSync(logFilePath)) return;
  if (statSync(logFilePath).size < maxBytes) return;
  const rotated = `${logFilePath}.1`;
  if (existsSync(rotated)) unlinkSync(rotated);
  renameSync(logFilePath, rotated);
}

export function appendSidecarLog(line: string): void {
  if (!logFilePath) return;
  rotateSidecarLogIfNeeded();
  const text = line.endsWith('\n') ? line : `${line}\n`;
  appendFileSync(logFilePath, text, 'utf8');
}

/** Split sidecar stderr so tqdm `\r` updates become visible `app:dev` lines. */
export function sidecarStderrLines(chunk: string): string[] {
  return chunk
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .split('\n')
    .filter((line) => line.trim().length > 0);
}

export function logSidecarMessage(label: string, line: string): void {
  console.error(`[${label}] ${line}`);
  appendSidecarLog(line);
}

export function logSidecarStderr(label: string, chunk: string): void {
  for (const line of sidecarStderrLines(chunk)) {
    logSidecarMessage(label, line);
  }
}
