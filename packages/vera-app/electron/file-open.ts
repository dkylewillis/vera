import { resolve } from 'node:path';

/** Return the first `.vera` archive passed to an Electron process by the OS shell. */
export function veraArchivePathFromArgs(args: readonly string[]): string | null {
  for (const arg of args) {
    const trimmed = arg.trim().replace(/^"(.*)"$/, '$1');
    if (trimmed.toLowerCase().endsWith('.vera')) {
      return resolve(trimmed);
    }
  }
  return null;
}
