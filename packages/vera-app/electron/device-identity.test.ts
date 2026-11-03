import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { loadDevice, regenerateDevice, renameDevice } from './device-identity.js';

const dirs: string[] = [];

afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

function userData(): string {
  const dir = mkdtempSync(join(tmpdir(), 'vera-device-'));
  dirs.push(dir);
  return dir;
}

describe('device identity', () => {
  it('creates a stable id and uses the host name', () => {
    const dir = userData();
    const created = loadDevice(dir, 'Work PC');
    expect(created.name).toBe('Work PC');
    expect(created.id).toMatch(/^[0-9a-f-]{36}$/i);
    expect(loadDevice(dir, 'Other').id).toBe(created.id);
    expect(JSON.parse(readFileSync(join(dir, 'device.json'), 'utf8'))).toEqual(created);
  });

  it('renames without changing the id and clips the name', () => {
    const dir = userData();
    const created = loadDevice(dir, 'Work PC');
    const renamed = renameDevice(dir, `  ${'A'.repeat(80)}  `, created);
    expect(renamed.id).toBe(created.id);
    expect(renamed.name).toHaveLength(64);
    expect(loadDevice(dir).name).toBe(renamed.name);
  });

  it('regenerates the id and keeps the name', () => {
    const dir = userData();
    const created = loadDevice(dir, 'Laptop');
    const next = regenerateDevice(dir, created);
    expect(next.name).toBe('Laptop');
    expect(next.id).not.toBe(created.id);
    expect(loadDevice(dir).id).toBe(next.id);
  });
});
