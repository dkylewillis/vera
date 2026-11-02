import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { ArrowUp, FileUp, Plus, Square, X } from 'lucide-react';
import type { AttachmentUsage, ChatAttachment, ChatFileAttachment } from '../types';
import { FileTypeIcon } from './FileTypeIcon';
import { fileIconType, formatFileSize, usageLabel } from '../lib/fileAttachments';

// Horizontal padding of `.askComposer .askInput` in the single-line layout (3px + 175px).
const SINGLE_LINE_TEXT_INSET = 178;
let measureCanvas: HTMLCanvasElement | null = null;

/** Whether the placeholder needs more than one line in the single-line layout. */
function placeholderOverflows(row: HTMLElement, textarea: HTMLTextAreaElement, placeholder: string): boolean {
  const context = (measureCanvas ??= document.createElement('canvas')).getContext('2d');
  if (!context) return false;
  const style = getComputedStyle(textarea);
  context.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
  const gap = parseFloat(getComputedStyle(row).columnGap) || 0;
  let siblings = 0;
  for (const child of Array.from(row.children)) {
    if (child === textarea || !(child instanceof HTMLElement)) continue;
    const childStyle = getComputedStyle(child);
    siblings += child.offsetWidth + parseFloat(childStyle.marginLeft) + parseFloat(childStyle.marginRight) + gap;
  }
  const available = row.clientWidth - siblings - SINGLE_LINE_TEXT_INSET;
  return context.measureText(placeholder).width > available;
}

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
  // Attachments sit above the input, so the composer uses the card layout
  // (fixed corner radius, buttons on the bottom row) as soon as any exist.
  const placeholder = !hasSearchableScope ? 'Select documents or attach a file to ask' : hasPreviousTurns ? 'Follow up…' : 'Ask anything';
  const inputRowRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [placeholderWraps, setPlaceholderWraps] = useState(false);
  const expanded = multiline
    || (!draft && placeholderWraps)
    || attachments.length > 0
    || fileAttachments.length > 0;

  // A wrapping placeholder uses the same card layout as wrapping text. Measured
  // against the row width, so switching layouts cannot flip the result back.
  useLayoutEffect(() => {
    const row = inputRowRef.current;
    const textarea = textareaRef.current;
    if (!row || !textarea) return;
    const measure = () => setPlaceholderWraps(placeholderOverflows(row, textarea, placeholder));
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(row);
    return () => observer.disconnect();
  }, [placeholder]);
  // Typing and attaching stay available without a scope, since an attached file is itself context.
  const inputUnavailable = filesPreparing || (busy && busyAction !== 'Asking');

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
      className={`askComposer${isDraggingFiles ? ' askComposer--dragging' : ''}${expanded ? ' askComposer--multiline' : ''}`}
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
            const label = file.preparing
              ? (file.status || 'Preparing…')
              : usageLabel(attachmentUsage?.[file.id]) || formatFileSize(file.size_bytes);
            return (
              <span className="attachChip attachChip--file" key={file.id} title={file.name}>
                <span className="attachChipIcon">
                  <FileTypeIcon type={fileIconType(file.name)} size={18} />
                </span>
                <span className="attachChipText">
                  <span className="attachChipName">{file.name}</span>
                  {label ? <span className="attachChipMeta">{label}</span> : null}
                </span>
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
      <div className="askInputRow" ref={inputRowRef}>
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
          ref={textareaRef}
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
          placeholder={placeholder}
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
