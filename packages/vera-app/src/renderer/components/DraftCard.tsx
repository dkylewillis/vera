import React, { useState } from 'react';
import { ChevronDown, Copy, FolderOpen, Save } from 'lucide-react';
import type { SessionTurn } from '../types';
import { ChatMarkdown } from './ChatMarkdown';

export function DraftCard({
  draft,
  onSave,
  onShow,
}: {
  draft: NonNullable<SessionTurn['drafts']>[number];
  onSave: (path: string, filename: string) => void;
  onShow: (path: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');

  async function toggle() {
    const next = !open;
    setOpen(next);
    if (next && !text) {
      setText(await window.vera.readDraft(draft.path));
    }
  }

  return (
    <div className="draftCard">
      <div className="draftCardBar">
        <button type="button" className="draftCardTitle" onClick={() => void toggle()}>
          <ChevronDown size={14} className={open ? 'draftCardChevron draftCardChevron--open' : 'draftCardChevron'} />
          {draft.filename}
        </button>
        <button type="button" className="ghostIcon" title="Copy Markdown" aria-label="Copy Markdown" onClick={() => void copyDraft(draft.path)}>
          <Copy size={14} />
        </button>
        <button type="button" className="ghostIcon" title="Save as" aria-label="Save as" onClick={() => onSave(draft.path, draft.filename)}>
          <Save size={14} />
        </button>
        <button type="button" className="ghostIcon" title="Show in folder" aria-label="Show in folder" onClick={() => onShow(draft.path)}>
          <FolderOpen size={14} />
        </button>
      </div>
      {open ? <ChatMarkdown>{text || '…'}</ChatMarkdown> : null}
    </div>
  );
}

async function copyDraft(path: string) {
  const text = await window.vera.readDraft(path);
  await navigator.clipboard.writeText(text);
}
