/**
 * Library names for Agent access. Keep this in step with
 * `library_slug` and `_assign_library_names` in vera_mcp.access_policy.
 */

export const LIBRARY_NAME_MAX = 64;
export const LIBRARY_NAME_PATTERN = /^[a-z0-9][a-z0-9_-]{0,63}$/;

export function librarySlug(text: string): string {
  const slug = text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, LIBRARY_NAME_MAX)
    .replace(/-+$/g, '');
  return LIBRARY_NAME_PATTERN.test(slug) ? slug : '';
}

export function isLibraryName(name: string): boolean {
  return LIBRARY_NAME_PATTERN.test(name);
}

function pathsEqual(left: string, right: string): boolean {
  if (left === right) return true;
  const platform = (globalThis as { process?: { platform?: string } }).process?.platform;
  return platform === 'win32' && left.toLowerCase() === right.toLowerCase();
}

function folderParts(folder: string): { base: string; parent: string } {
  const segments = folder.replace(/[\\/]+$/, '').split(/[\\/]/).filter((part) => part.length > 0);
  const base = segments[segments.length - 1] ?? '';
  let parent = segments.length >= 2 ? segments[segments.length - 2] : '';
  if (/^[A-Za-z]:$/.test(parent)) parent = '';
  return { base, parent };
}

function lookup(explicit: Record<string, string>, root: string): string | undefined {
  for (const [key, value] of Object.entries(explicit)) {
    if (pathsEqual(key, root)) return value;
  }
  return undefined;
}

function disambiguate(root: string, base: string): string {
  const parent = librarySlug(folderParts(root).parent);
  if (!parent || !base) {
    throw new Error(
      `Bridge policy library name '${base}' is not unique and could not be disambiguated for ${root}.`,
    );
  }
  let candidate = `${parent}-${base}`;
  if (candidate.length > LIBRARY_NAME_MAX) {
    candidate = candidate.slice(0, LIBRARY_NAME_MAX).replace(/-+$/g, '');
  }
  if (!isLibraryName(candidate)) {
    throw new Error(
      `Bridge policy library name '${base}' is not unique and could not be disambiguated for ${root}.`,
    );
  }
  return candidate;
}

/** Explicit names win. Other folders take a unique slug of their folder name. */
export function assignLibraryNames(roots: string[], explicit: Record<string, string>): Record<string, string> {
  const assigned: Record<string, string> = {};
  const used = new Set<string>();
  const chosen = new Map<string, string>();
  for (const root of roots) {
    const name = lookup(explicit, root);
    if (name === undefined || name === '') continue;
    if (!isLibraryName(name)) {
      throw new Error(
        'Bridge policy library name must be a lowercase slug of at most 64 characters (letters, numbers, hyphens, underscores).',
      );
    }
    chosen.set(root, name);
  }
  for (const root of roots) {
    const name = chosen.get(root);
    if (name === undefined) continue;
    if (used.has(name)) {
      throw new Error(`Bridge policy library name '${name}' is used more than once.`);
    }
    assigned[root] = name;
    used.add(name);
  }
  const bases: { root: string; base: string }[] = [];
  for (const root of roots) {
    if (assigned[root]) continue;
    const slug = librarySlug(folderParts(root).base);
    if (!slug) throw new Error(`Bridge policy could not derive a library name for ${root}.`);
    bases.push({ root, base: slug });
  }
  const counts = new Map<string, number>();
  for (const item of bases) counts.set(item.base, (counts.get(item.base) ?? 0) + 1);
  for (const item of bases) {
    const name = (counts.get(item.base) ?? 0) === 1 && !used.has(item.base)
      ? item.base
      : disambiguate(item.root, item.base);
    if (used.has(name)) {
      throw new Error(`Bridge policy library name '${name}' is used more than once.`);
    }
    assigned[item.root] = name;
    used.add(name);
  }
  return assigned;
}

export function fallbackLibraryName(roots: string[], explicit: Record<string, string>, root: string): string {
  const without: Record<string, string> = {};
  for (const [key, value] of Object.entries(explicit)) {
    if (!pathsEqual(key, root)) without[key] = value;
  }
  return assignLibraryNames(roots, without)[root] ?? '';
}

export function libraryNameError(roots: string[], explicit: Record<string, string>): string {
  for (const name of Object.values(explicit)) {
    if (!isLibraryName(name)) return 'Use lowercase letters, numbers, hyphens, or underscores.';
  }
  try {
    assignLibraryNames(roots, explicit);
  } catch (error) {
    const message = error instanceof Error ? error.message : '';
    if (message.includes('could not derive')) return 'This folder needs a name before agents can use it.';
    return 'That name is already used by another library.';
  }
  return '';
}

/** Keep explicit names whose folders are still shared and whose values are valid slugs. */
export function namesForRoots(roots: string[], explicit: Record<string, string>): Record<string, string> {
  const next: Record<string, string> = {};
  const used = new Set<string>();
  for (const root of roots) {
    const name = lookup(explicit, root);
    if (!name || !isLibraryName(name) || used.has(name)) continue;
    next[root] = name;
    used.add(name);
  }
  return next;
}
