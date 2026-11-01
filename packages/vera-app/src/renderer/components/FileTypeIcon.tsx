import { FileCode2, FileSpreadsheet, FileText, FileType, Presentation, type LucideIcon } from 'lucide-react';
import type { SVGProps } from 'react';
import type { FolderEntryType } from '../../shared/source-types';
import { VeraIcon } from './VeraIcon';

const SOURCE_ICONS: Record<Exclude<FolderEntryType, 'vera'>, LucideIcon> = {
  pdf: FileText,
  docx: FileType,
  md: FileCode2,
  xlsx: FileSpreadsheet,
  pptx: Presentation,
};

/** Explorer file mark. Color comes from `.fileRowIcon.<type>` in styles.css. */
export function FileTypeIcon({
  type,
  size = 16,
  className,
  ...props
}: SVGProps<SVGSVGElement> & { type: FolderEntryType; size?: number }) {
  const classes = ['fileRowIcon', type, className].filter(Boolean).join(' ');
  if (type === 'vera') {
    return <VeraIcon size={size} className={classes} data-file-type="vera" {...props} />;
  }
  const Icon = SOURCE_ICONS[type];
  return <Icon size={size} className={classes} data-file-type={type} aria-hidden {...props} />;
}
