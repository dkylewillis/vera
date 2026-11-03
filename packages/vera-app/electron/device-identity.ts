import { randomUUID } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { hostname } from 'node:os';
import { join } from 'node:path';

export interface DeviceIdentity {
  id: string;
  name: string;
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function deviceFile(userData: string): string {
  return join(userData, 'device.json');
}

export function loadDevice(userData: string, hostName = hostname()): DeviceIdentity {
  try {
    const parsed = JSON.parse(readFileSync(deviceFile(userData), 'utf8')) as { id?: unknown; name?: unknown };
    if (typeof parsed.id === 'string' && UUID.test(parsed.id)) {
      return { id: parsed.id, name: cleanName(typeof parsed.name === 'string' ? parsed.name : hostName, hostName) };
    }
  } catch {
    /* missing or unreadable: create one */
  }
  const created = { id: randomUUID(), name: cleanName(hostName, hostName) };
  saveDevice(userData, created);
  return created;
}

export function renameDevice(userData: string, name: string, current: DeviceIdentity): DeviceIdentity {
  const next = { id: current.id, name: cleanName(name, current.name) };
  saveDevice(userData, next);
  return next;
}

export function regenerateDevice(userData: string, current: DeviceIdentity): DeviceIdentity {
  const next = { id: randomUUID(), name: current.name };
  saveDevice(userData, next);
  return next;
}

export function cleanName(value: string, fallback: string): string {
  const cleaned = value.replace(/[\u0000-\u001f\u007f]/g, ' ').replace(/\s+/g, ' ').trim();
  const clipped = [...cleaned].slice(0, 64).join('').trim();
  if (clipped) return clipped;
  const host = [...fallback.replace(/[\u0000-\u001f\u007f]/g, ' ').replace(/\s+/g, ' ').trim()].slice(0, 64).join('').trim();
  return host || 'This computer';
}

function saveDevice(userData: string, device: DeviceIdentity): void {
  mkdirSync(userData, { recursive: true });
  writeFileSync(deviceFile(userData), JSON.stringify(device), 'utf8');
}
