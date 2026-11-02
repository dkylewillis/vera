import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import type { ChatFileAttachment } from '../types';
import { ChatComposer } from './ChatComposer';

const ready: ChatFileAttachment & { preparing?: boolean; status?: string } = {
  id: 'notes',
  name: 'notes.md',
  source_path: 'notes.md',
  vera_path: 'notes.vera',
  token_estimate: 20,
  chunk_count: 1,
  page_count: 1,
};

function renderComposer(file: ChatFileAttachment & { preparing?: boolean; status?: string }) {
  return renderToStaticMarkup(
    <ChatComposer
      attachments={[]}
      fileAttachments={[file]}
      attachmentUsage={{ notes: { delivery: 'full', searches: 0, cited: 1 } }}
      busy={false}
      busyAction={null}
      hasSearchableScope
      hasPreviousTurns={false}
      resetVersion={0}
      restoredDraft={{ version: 0, text: '' }}
      onAddAttachments={async () => {}}
      onRemoveAttachment={() => {}}
      onRemoveFile={() => {}}
      onAsk={async () => {}}
      onStopAnswer={() => {}}
    />,
  );
}

describe('ChatComposer file chips', () => {
  it('shows a preparing file and keeps Send unavailable', () => {
    const html = renderComposer({ ...ready, preparing: true, status: 'Reading pages…' });
    expect(html).toContain('notes.md');
    expect(html).toContain('Reading pages…');
    expect(html).toContain('disabled');
  });

  it('uses the card layout and shows the size of a new file', () => {
    const html = renderToStaticMarkup(
      <ChatComposer
        attachments={[]}
        fileAttachments={[{ ...ready, size_bytes: 172_000 }]}
        busy={false}
        busyAction={null}
        hasSearchableScope
        hasPreviousTurns={false}
        resetVersion={0}
        restoredDraft={{ version: 0, text: '' }}
        onAddAttachments={async () => {}}
        onRemoveAttachment={() => {}}
        onAsk={async () => {}}
        onStopAnswer={() => {}}
      />,
    );
    expect(html).toContain('askComposer--multiline');
    expect(html).toContain('172kB');
  });

  it('keeps typing and attaching available with no documents selected', () => {
    const html = renderToStaticMarkup(
      <ChatComposer
        attachments={[]}
        fileAttachments={[]}
        busy={false}
        busyAction={null}
        hasSearchableScope={false}
        hasPreviousTurns={false}
        resetVersion={0}
        restoredDraft={{ version: 0, text: '' }}
        onAddAttachments={async () => {}}
        onRemoveAttachment={() => {}}
        onAsk={async () => {}}
        onStopAnswer={() => {}}
      />,
    );
    expect(html).toContain('Select documents or attach a file to ask');
    expect(html).not.toMatch(/<textarea[^>]*disabled/);
    expect(html).not.toMatch(/<button[^>]*attachButton[^>]*disabled/);
    expect(html).toMatch(/<button[^>]*askSendButton[^>]*disabled/);
  });

  it('labels a ready file from the last answer', () => {
    const html = renderComposer(ready);
    expect(html).toContain('Read in full');
    expect(html).toContain('Remove notes.md');
  });
});
