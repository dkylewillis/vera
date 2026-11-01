import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { FolderEntryType } from '../../shared/source-types';
import { FileTypeIcon } from './FileTypeIcon';

const types: FolderEntryType[] = ['pdf', 'md', 'docx', 'pptx', 'xlsx', 'vera'];

describe('FileTypeIcon', () => {
  it('gives every supported type its own Lucide mark', () => {
    const marks = types.map((type) => renderToStaticMarkup(<FileTypeIcon type={type} />));
    expect(new Set(marks).size).toBe(types.length);
    expect(marks[0]).toContain('lucide-file-text');
    expect(marks[1]).toContain('lucide-file-code-corner');
    expect(marks[2]).toContain('lucide-file-type');
    expect(marks[3]).toContain('lucide-presentation');
    expect(marks[4]).toContain('lucide-file-spreadsheet');
    expect(marks[5]).toContain('data-file-type="vera"');
    for (const [index, type] of types.entries()) {
      expect(marks[index]).toContain(`fileRowIcon ${type}`);
    }
  });
});
