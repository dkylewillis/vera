import React, { useEffect, useRef, useState } from 'react';
import { ArrowUp, FileUp, Plus, Square, X } from 'lucide-react';
import type { AttachmentUsage, ChatAttachment, ChatFileAttachment } from '../types';
import { FileTypeIcon } from './FileTypeIcon';
import { fileIconType, usageLabel } from '../lib/fileAttachments';

export const ChatComposer = React.memo(function ChatComposer({
  attachments,
  fileAttachments = [],
  attachmentUsage,
  busy,
  busyAction,
  hasSearchableScope,
  hasPreviousTurns,
  resetVersion,
  restoredDraft,
  onAddAttachments,
  onRemoveAttachment,
  onRemoveFile,
  onAsk,
  onStopAnswer,
}: {
  attachments: ChatAttachment[];
  fileAttachments?: Array<ChatFileAttachment & { preparing?: boolean; status?: string }>;
  attachmentUsage?: Record<string, AttachmentUsage>;
  busy: boolean;
  busyAction: string | null;
  hasSearchableScope: boolean;
  hasPreviousTurns: boolean;
  resetVersion: number;
  restoredDraft: { version: number; text: string };
  onAddAttachments: (files: FileList | File[]) => Promise<void>;
  onRemoveAttachment: (id: string) => void;
  onRemoveFile?: (id: string) => void;
  onAsk: (prompt: string, onAccepted: () => void) => Promise<void>;
  onStopAnswer: () => void;
}) {
  const [draft, setDraft] = useState('');
  const [multiline, setMultiline] = useState(false);
  const [isDraggingFiles, setIsDraggingFiles] = useState(false);
  const attachmentInputRef = useRef<HTMLInputElement>(null);
  const filesPreparing = fileAttachments.some((file) => file.preparing);
  const inputUnavailable = !hasSearchableScope || filesPreparing || (busy && busyAction !== 'Asking');

  useEffect(() => {
    setDraft('');
    setMultiline(false);
  }, [resetVersion]);

  useEffect(() => {
    setDraft(restoredDraft.text);
    setMultiline(false);
  }, [restoredDraft]);

  function updateMultiline(textarea: HTMLTextAreaElement) {
    const nextMultiline = Boolean(textarea.value) && textarea.scrollHeight > 40;
    setMultiline((current) => current === nextMultiline ? current : nextMultiline);
  }

  function submitDraft() {
    if (busy || !hasSearchableScope) return;
    const prompt = draft;
    void onAsk(prompt, () => {
      setDraft('');
      setMultiline(false);
    });
  }

  return (
    <div
      className={`askComposer${isDraggingFiles ? ' askComposer--dragging' : ''}${multiline ? ' askComposer--multiline' : ''}`}
      onDragOver={(event) => {
        if (!event.dataTransfer.types.includes('Files')) return;
        event.preventDefault();
        setIsDraggingFiles(true);
      }}
      onDragLeave={(event) => {
        if (event.currentTarget.contains(event.relatedTarget as Node)) return;
        setIsDraggingFiles(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        setIsDraggingFiles(false);
        if (!inputUnavailable && event.dataTransfer.files.length) void onAddAttachments(event.dataTransfer.files);
      }}
    >
      <input
        ref={attachmentInputRef}
        type="file"
        accept="image/*,.pdf,.docx,.pptx,.xlsx,.md,.markdown,.html,.htm,.txt,.vera"
        multiple
        disabled={inputUnavailable}
        style={{ display: 'none' }}
        onChange={(event) => {
          if (event.target.files?.length) void onAddAttachments(event.target.files);
          event.target.value = '';
        }}
      />
      {fileAttachments.length ? (
        <div className="attachRow">
          {fileAttachments.map((file) => {
            const label = file.preparing ? (file.status || 'Preparing…') : usageLabel(attachmentUsage?.[file.id]);
            return (
              <span className="attachChip attachChip--file" key={file.id} title={file.name}>
                <FileTypeIcon type={fileIconType(file.name)} size={14} />
                <span className="attachChipName">{file.name}</span>
                {label ? <span className="attachChipMeta">{label}</span> : null}
                <button
                  type="button"
                  className="attachChipRemove"
                  onClick={() => onRemoveFile?.(file.id)}
                  aria-label={`Remove ${file.name}`}
                  title="Remove"
                >
                  <X size={11} />
                </button>
              </span>
            );
          })}
        </div>
      ) : null}
      {attachments.length ? (
        <div className="attachRow">
          {attachments.map((att) => (
            <span className="attachChip" key={att.id} title={att.name}>
              <img className="attachChipThumb" src={att.data_url} alt="" />
              <span className="attachChipName">{att.name}</span>
              <button
                type="button"
                className="attachChipRemove"
                onClick={() => onRemoveAttachment(att.id)}
                aria-label={`Remove ${att.name}`}
                title="Remove"
              >
                <X size={11} />
              </button>
            </span>
          ))}
        </div>
      ) : null}
      {isDraggingFiles ? (
        <div className="attachDropHint">
          <FileUp size={16} />
          <span>Drop files to attach</span>
        </div>
      ) : null}
      <div className="askInputRow">
        <button
          type="button"
          className="ghostIcon attachButton"
          onClick={() => attachmentInputRef.current?.click()}
          title="Attach files"
          aria-label="Attach files"
          disabled={inputUnavailable}
        >
          <Plus size={16} />
        </button>
        <textarea
          className="askInput"
          value={draft}
          rows={1}
          disabled={inputUnavailable}
          onChange={(event) => {
            setDraft(event.target.value);
            updateMultiline(event.currentTarget);
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              submitDraft();
            }
          }}
          placeholder={!hasSearchableScope ? 'Select a document or library to ask' : hasPreviousTurns ? 'Follow up…' : 'Ask anything'}
        />
        <button
          className="askSendButton"
          onClick={busyAction === 'Asking' ? onStopAnswer : submitDraft}
          disabled={busy ? busyAction !== 'Asking' : !hasSearchableScope || filesPreparing || !draft.trim()}
          title={busyAction === 'Asking' ? 'Stop generating' : 'Send (Enter)'}
          aria-label={busyAction === 'Asking' ? 'Stop generating' : 'Send'}
        >
          {busyAction === 'Asking' ? <Square size={10} fill="currentColor" /> : <ArrowUp size={16} strokeWidth={2.5} />}
        </button>
      </div>
    </div>
  );
});
