/** Extensions Explorer, the folder listing, and Convert agree on. */

export const CONVERTIBLE_SOURCE_TYPES = ['pdf', 'md', 'docx', 'pptx', 'xlsx'] as const;

export type ConvertibleSourceType = (typeof CONVERTIBLE_SOURCE_TYPES)[number];

export type FolderEntryType = 'vera' | ConvertibleSourceType;

const SOURCE_EXTENSIONS: Record<ConvertibleSourceType, readonly string[]> = {
  pdf: ['.pdf'],
  md: ['.md', '.markdown'],
  docx: ['.docx'],
  pptx: ['.pptx'],
  xlsx: ['.xlsx'],
};

export function folderEntryType(name: string): FolderEntryType | null {
  const lower = name.toLowerCase();
  if (lower.endsWith('.vera')) return 'vera';
  for (const type of CONVERTIBLE_SOURCE_TYPES) {
    if (SOURCE_EXTENSIONS[type].some((suffix) => lower.endsWith(suffix))) return type;
  }
  return null;
}

export function isConvertibleSourceType(type: string | null | undefined): type is ConvertibleSourceType {
  return typeof type === 'string' && (CONVERTIBLE_SOURCE_TYPES as readonly string[]).includes(type);
}

/** Extensions for the Convert file dialog, without the leading dot. */
export function sourceOpenDialogExtensions(): string[] {
  return [...new Set(
    CONVERTIBLE_SOURCE_TYPES.flatMap((type) => SOURCE_EXTENSIONS[type].map((suffix) => suffix.slice(1))),
  )];
}
