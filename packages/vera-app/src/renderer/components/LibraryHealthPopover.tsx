import { useEffect, useRef } from 'react';
import { AlertTriangle, Database, RefreshCw } from 'lucide-react';
import type {
  LibraryHealth,
  LibraryHealthAction,
  LibraryHealthItem,
  LibraryHealthItemKind,
} from '../lib/libraryHealth';

export function LibraryStatusChip({
  health,
  expanded,
  onClick,
}: {
  health: LibraryHealth;
  expanded: boolean;
  onClick: (anchor: { left: number; top: number; bottom: number }, trigger: HTMLButtonElement) => void;
}) {
  const spinning = health.state === 'working' || health.state === 'checking';
  return (
    <button
      type="button"
      className={`libraryStatusChip ${health.state}`}
      title={health.title}
      aria-label={`Library health: ${health.label}`}
      aria-haspopup="dialog"
      aria-expanded={expanded}
      onClick={(event) => {
        event.stopPropagation();
        const bounds = event.currentTarget.getBoundingClientRect();
        onClick({ left: bounds.left, top: bounds.top, bottom: bounds.bottom }, event.currentTarget);
      }}
    >
      {health.state === 'attention'
        ? <AlertTriangle size={11} aria-hidden="true" />
        : spinning
          ? <RefreshCw size={11} className="spinning" aria-hidden="true" />
          : health.state === 'pending'
            ? <RefreshCw size={11} aria-hidden="true" />
            : <Database size={11} aria-hidden="true" />}
      <span>{health.label}</span>
    </button>
  );
}

const ACTION_LABELS: Record<LibraryHealthAction, string> = {
  retry: 'Retry',
  convertWithOptions: 'Convert with options…',
  showInFolder: 'Show in folder',
  tryAgain: 'Try again',
  openConvertLog: 'Open convert log',
  review: 'Review',
  viewReport: 'View report',
  convertNow: 'Convert now',
  updateIndex: 'Update index',
  buildIndex: 'Build index',
  checkNow: 'Check for changes now',
  libraryInfo: 'Library info',
};

const LOCKED_WHILE_BUSY = new Set<LibraryHealthAction>([
  'retry',
  'convertWithOptions',
  'tryAgain',
  'review',
  'convertNow',
  'updateIndex',
  'buildIndex',
  'checkNow',
]);

const SECTIONS: { title: string; kinds: LibraryHealthItemKind[] }[] = [
  { title: 'Problems', kinds: ['failedFile', 'syncError', 'moreFailures'] },
  { title: 'Needs confirmation', kinds: ['needsConfirmation'] },
  { title: 'Skipped while indexing', kinds: ['skippedIndex'] },
  { title: 'Not searchable yet', kinds: ['pendingFiles'] },
  { title: 'Index', kinds: ['index'] },
];

export function LibraryHealthPopover({
  health,
  anchor,
  actionsLocked,
  revealLabel,
  onClose,
  onAction,
}: {
  health: LibraryHealth;
  anchor: { left: number; top: number; bottom: number };
  actionsLocked: boolean;
  revealLabel: string;
  onClose: () => void;
  onAction: (action: LibraryHealthAction, item: LibraryHealthItem | null) => void;
}) {
  const popoverRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    popoverRef.current?.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus();
  }, []);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
      const actions = [...(popoverRef.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? [])];
      if (actions.length === 0) return;
      event.preventDefault();
      const currentIndex = actions.indexOf(document.activeElement as HTMLButtonElement);
      const nextIndex = event.key === 'Home'
        ? 0
        : event.key === 'End'
          ? actions.length - 1
          : (currentIndex + (event.key === 'ArrowDown' ? 1 : -1) + actions.length) % actions.length;
      actions[nextIndex]?.focus();
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  const width = 320;
  const left = Math.max(8, Math.min(anchor.left, window.innerWidth - width - 8));
  const spaceBelow = window.innerHeight - anchor.bottom;
  const openAbove = spaceBelow < 220 && anchor.top > spaceBelow;
  const position = openAbove
    ? { left, bottom: window.innerHeight - anchor.top + 4, maxHeight: Math.max(120, anchor.top - 12) }
    : { left, top: anchor.bottom + 4, maxHeight: Math.max(120, spaceBelow - 12) };

  return (
    <div className="folderContextMenuBackdrop" onClick={onClose}>
      <div
        ref={popoverRef}
        className="libraryHealthPopover"
        role="dialog"
        aria-label="Library health"
        style={position}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="libraryHealthTitle">Library health</div>
        {health.state === 'working' ? (
          <p className="libraryHealthStatus">{health.label}</p>
        ) : null}
        {health.items.length === 0 && health.state !== 'working' ? (
          <p className="libraryHealthEmpty">{health.title}</p>
        ) : null}
        {SECTIONS.map((section) => {
          const rows = health.items.filter((item) => section.kinds.includes(item.kind));
          if (rows.length === 0) return null;
          return (
            <section key={section.title} className="libraryHealthSection">
              <h3>{section.title}</h3>
              {rows.map((item, index) => (
                <div key={`${item.kind}-${item.path ?? item.text}-${index}`} className="libraryHealthRow">
                  <div className="libraryHealthRowText">
                    <span className="libraryHealthName">{item.text}</span>
                    {item.detail ? (
                      <span className="libraryHealthDetail" title={item.detail}>{item.detail}</span>
                    ) : null}
                  </div>
                  {item.actions.length > 0 ? (
                    <div className="libraryHealthActions">
                      {item.actions.map((action) => (
                        <ActionButton
                          key={action}
                          action={action}
                          revealLabel={revealLabel}
                          locked={actionsLocked && LOCKED_WHILE_BUSY.has(action)}
                          onClick={() => onAction(action, item)}
                        />
                      ))}
                    </div>
                  ) : null}
                </div>
              ))}
            </section>
          );
        })}
        <div className="libraryHealthFooter">
          <ActionButton
            action="checkNow"
            revealLabel={revealLabel}
            locked={actionsLocked && LOCKED_WHILE_BUSY.has('checkNow')}
            onClick={() => onAction('checkNow', null)}
          />
          <ActionButton
            action="libraryInfo"
            revealLabel={revealLabel}
            locked={false}
            onClick={() => onAction('libraryInfo', null)}
          />
        </div>
      </div>
    </div>
  );
}

function ActionButton({
  action,
  revealLabel,
  locked,
  onClick,
}: {
  action: LibraryHealthAction;
  revealLabel: string;
  locked: boolean;
  onClick: () => void;
}) {
  const label = action === 'showInFolder' ? revealLabel : ACTION_LABELS[action];
  return (
    <button
      type="button"
      disabled={locked}
      title={locked ? 'Wait for the current library update to finish' : undefined}
      onClick={onClick}
    >
      {label}
    </button>
  );
}
