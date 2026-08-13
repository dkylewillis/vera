import { existsSync, readdirSync } from 'node:fs';
import { basename, join, relative } from 'node:path';

/** Walk this many directory levels below the folder root (root itself is depth 0). */
export const LIST_FOLDER_MAX_DEPTH = 32;

export interface FolderListingEntry {
  path: string;
  name: string;
  relativePath: string;
  type: 'vera' | 'pdf';
}

export interface FolderListing {
  path: string;
  name: string;
  entries: FolderListingEntry[];
  truncated: boolean;
}

export function folderRelativePath(root: string, filePath: string): string {
  return relative(root, filePath).replace(/\\/g, '/');
}

export function listFolderEntries(
  dir: string,
  maxDepth: number = LIST_FOLDER_MAX_DEPTH,
): FolderListing | null {
  if (typeof dir !== 'string' || !dir.trim() || !existsSync(dir)) {
    return null;
  }
  const entries: FolderListingEntry[] = [];
  let truncated = false;
  const walk = (current: string, depth: number): void => {
    if (depth > maxDepth) {
      truncated = true;
      return;
    }
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
          relativePath: folderRelativePath(dir, full),
          type,
        });
      }
    }
  };
  walk(dir, 0);
  entries.sort((a, b) => a.relativePath.localeCompare(b.relativePath));
  return { path: dir, name: basename(dir) || dir, entries, truncated };
}
