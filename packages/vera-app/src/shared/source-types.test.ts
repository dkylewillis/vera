import { describe, expect, it } from 'vitest';

import { folderEntryType, sourceOpenDialogExtensions } from './source-types';

describe('source open dialog', () => {
  it('offers Word, PowerPoint, and Excel beside PDF and Markdown', () => {
    expect(sourceOpenDialogExtensions()).toEqual(['pdf', 'md', 'markdown', 'docx', 'pptx', 'xlsx']);
    expect(folderEntryType('memo.docx')).toBe('docx');
    expect(folderEntryType('deck.pptx')).toBe('pptx');
    expect(folderEntryType('budget.xlsx')).toBe('xlsx');
    expect(folderEntryType('~$budget.xlsx')).toBeNull();
    expect(folderEntryType('~$memo.docx')).toBeNull();
  });
});
