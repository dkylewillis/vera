/**
 * Keep Explorer scannable around the active library without fighting file
 * selection: expand the active library and collapse the rest when one is set;
 * when none is active (e.g. a single .vera is scoped), preserve the user's
 * expand/collapse state and only drop folders that are no longer open.
 */
export function syncCollapsedFolders(
  folderPaths: string[],
  activeLibraryPath: string,
  previousCollapsed: string[],
): string[] {
  const active = activeLibraryPath.trim();
  if (!active) {
    return previousCollapsed.filter((folderPath) => folderPaths.includes(folderPath));
  }
  return folderPaths.filter((folderPath) => folderPath !== active);
}
