import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  appendSidecarLog,
  configureSidecarLogFile,
  ensureSidecarLogFile,
  formatSidecarTimingLine,
  logSidecarStderr,
  resetSidecarLogFileForTests,
  sidecarLogFilePath,
  sidecarStderrLines,
} from './sidecar-log.js';

describe('sidecarStderrLines', () => {
  it('turns tqdm carriage returns into separate lines', () => {
    expect(
      sidecarStderrLines('Fetching 5 files:  20%\rFetching 5 files:  80%\rFetching 5 files: 100%\n'),
    ).toEqual([
      'Fetching 5 files:  20%',
      'Fetching 5 files:  80%',
      'Fetching 5 files: 100%',
    ]);
  });

  it('drops empty fragments', () => {
    expect(sidecarStderrLines('\n\r  \r\nhello\n')).toEqual(['hello']);
  });
});

describe('sidecar log file', () => {
  const dirs: string[] = [];

  afterEach(() => {
    vi.restoreAllMocks();
    resetSidecarLogFileForTests();
    for (const dir of dirs.splice(0)) {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  function tempLog(): string {
    const dir = mkdtempSync(join(tmpdir(), 'vera-sidecar-log-'));
    dirs.push(dir);
    return join(dir, 'sidecar.log');
  }

  it('places the log under userData/logs/sidecar.log', () => {
    expect(sidecarLogFilePath(join('C:\\', 'Users', 'me', 'AppData', 'Roaming', 'VERA')).replace(/\\/g, '/'))
      .toMatch(/\/logs\/sidecar\.log$/);
  });

  it('creates an empty file so Open log never fails', () => {
    const filePath = tempLog();
    expect(configureSidecarLogFile(filePath)).toBe(filePath);
    expect(readFileSync(ensureSidecarLogFile(), 'utf8')).toBe('');
  });

  it('tees stderr lines to the log file and the console', () => {
    const filePath = tempLog();
    configureSidecarLogFile(filePath);
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    logSidecarStderr('vera-sidecar', 'a\rb\n');
    expect(error.mock.calls).toEqual([
      ['[vera-sidecar] a'],
      ['[vera-sidecar] b'],
    ]);
    expect(readFileSync(filePath, 'utf8')).toBe('a\nb\n');
  });

  it('rotates sidecar.log to sidecar.log.1 at the size limit', () => {
    const filePath = tempLog();
    configureSidecarLogFile(filePath, { maxBytes: 20 });
    appendSidecarLog('this-line-is-already-long-enough');
    appendSidecarLog('second');
    expect(readFileSync(`${filePath}.1`, 'utf8')).toContain('this-line-is-already-long-enough');
    expect(readFileSync(filePath, 'utf8')).toBe('second\n');
  });

  it('formats spawn timing lines without empty fields', () => {
    const line = formatSidecarTimingLine('sidecar_spawn', {
      executable: 'C:\\vera-sidecar.exe',
      isPackaged: true,
      DOCLING_ARTIFACTS_PATH: '',
    });
    expect(line).toMatch(/^\d{4}-\d{2}-\d{2}T.*Z timing step=sidecar_spawn /);
    expect(line).toContain('executable=C:\\vera-sidecar.exe');
    expect(line).toContain('isPackaged=true');
    expect(line).not.toContain('DOCLING_ARTIFACTS_PATH=');
  });
});

describe('logSidecarStderr', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    resetSidecarLogFileForTests();
  });

  it('prefixes each progress line when no log file is configured', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    logSidecarStderr('vera-sidecar', 'a\rb\n');
    expect(error.mock.calls).toEqual([
      ['[vera-sidecar] a'],
      ['[vera-sidecar] b'],
    ]);
  });
});
