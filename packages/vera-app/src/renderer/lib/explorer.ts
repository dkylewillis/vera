/** Paths that should start collapsed so only the active library's files show. */
export function collapsedFoldersForActiveLibrary(
  folderPaths: string[],
  activeLibraryPath: string,
): string[] {
  const active = activeLibraryPath.trim();
  return folderPaths.filter((folderPath) => folderPath !== active);
}
