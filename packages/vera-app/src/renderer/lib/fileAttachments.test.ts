import { describe, expect, it } from 'vitest';

import type { ChatFileAttachment, SessionTurn } from '../types';
import { fullAttachmentIds, nextLabelStart, restoredChatAttachments, splitDroppedFiles, usageLabel } from './fileAttachments';

describe('file attachments', () => {
  it('splits images, documents, and unsupported files', () => {
    const split = splitDroppedFiles([
      { name: 'photo.png', type: 'image/png' },
      { name: 'notes.md', type: '' },
      { name: 'archive.zip', type: 'application/zip' },
    ]);
    expect(split.images.map((file) => file.name)).toEqual(['photo.png']);
    expect(split.documents.map((file) => file.name)).toEqual(['notes.md']);
    expect(split.rejected).toEqual(['archive.zip']);
  });

  it('resends full text for fresh files and files the last answer cited', () => {
    const files: ChatFileAttachment[] = [
      { id: 'new', name: 'a.md', source_path: 'a.md', vera_path: 'a.vera', token_estimate: 10, chunk_count: 1, page_count: 1, fresh: true },
      { id: 'cited', name: 'b.md', source_path: 'b.md', vera_path: 'b.vera', token_estimate: 10, chunk_count: 1, page_count: 1 },
      { id: 'old', name: 'c.md', source_path: 'c.md', vera_path: 'c.vera', token_estimate: 10, chunk_count: 1, page_count: 1 },
    ];
    const turns: SessionTurn[] = [{
      role: 'assistant',
      content: 'See [C1]',
      timestamp: 1,
      citations: [{
        id: 'C1',
        label: '[C1] p. 1',
        result: {
          chunk_id: 'chunk_0001',
          score: 1,
          text: 'text',
          page_start: 1,
          page_end: 1,
          heading_path: null,
          source_filename: 'b.md',
          document_id: 'document_0001',
          file: 'b.vera',
        },
      }],
    }];
    expect(fullAttachmentIds(files, turns)).toEqual(['new', 'cited']);
  });

  it('restores document and image attachments saved on a session', () => {
    const restored = restoredChatAttachments({
      file_attachments: [
        { id: 'doc', name: 'notes.md', source_path: 'notes.md', vera_path: 'notes.vera', token_estimate: 20, chunk_count: 1, page_count: 1 },
      ],
      image_attachments: [
        { id: 'img', name: 'photo.png', mime_type: 'image/png', data_url: 'data:image/png;base64,aa' },
      ],
    });
    expect(restored.files.map((file) => file.id)).toEqual(['doc']);
    expect(restored.images.map((image) => image.id)).toEqual(['img']);
    expect(restoredChatAttachments({}).files).toEqual([]);
  });

  it('starts each new file after the [A#] ranges already used', () => {
    expect(nextLabelStart([])).toBe(1);
    expect(nextLabelStart([
      { vera_path: 'a.vera', chunk_count: 3, label_start: 1 },
      { vera_path: 'b.vera', chunk_count: 2, label_start: 4 },
    ])).toBe(6);
    expect(nextLabelStart([
      { vera_path: 'old.vera', chunk_count: 4 },
      { vera_path: '', chunk_count: 0 },
    ])).toBe(5);
  });

  it('describes how a file was used', () => {
    expect(usageLabel({ delivery: 'full', searches: 0, cited: 1 })).toBe('Read in full');
    expect(usageLabel({ delivery: 'searchable', searches: 2, cited: 0 })).toBe('Searched 2×');
    expect(usageLabel({ delivery: 'searchable', searches: 0, cited: 0 })).toBe('Not used');
  });
});
