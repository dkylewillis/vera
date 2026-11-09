import type { BackgroundTask } from './backgroundTasks';
import { fileName } from './formatting';
import type { LibrarySyncReport } from '../types';

export type LibraryHealthState = 'working' | 'attention' | 'pending' | 'setup' | 'ready' | 'checking';

export type LibraryHealthAction =
  | 'retry'
  | 'convertWithOptions'
  | 'showInFolder'
  | 'tryAgain'
  | 'openConvertLog'
  | 'review'
  | 'viewReport'
  | 'convertNow'
  | 'updateIndex'
  | 'buildIndex'
  | 'checkNow'
  | 'libraryInfo';

export type LibraryHealthItemKind =
  | 'failedFile'
  | 'moreFailures'
  | 'syncError'
  | 'needsConfirmation'
  | 'skippedIndex'
  | 'pendingFiles'
  | 'index';

export interface LibraryHealthItem {
  kind: LibraryHealthItemKind;
  text: string;
  detail?: string;
  path?: string;
  actions: LibraryHealthAction[];
}

export interface LibraryHealth {
  state: LibraryHealthState;
  label: string;
  title: string;
  /** Problems and pending work, in popover order. */
  items: LibraryHealthItem[];
}

export interface LibraryHealthInput {
  libraryPath: string;
  pendingCount: number;
  index?: { exists: boolean; fresh: boolean; reasons?: string[] } | null;
  indexChecking?: boolean;
  indexReport?: { skipped?: number } | null;
  syncReport?: LibrarySyncReport | null;
  indexing?: 'build' | 'update' | null;
  syncing?: boolean;
  converting?: boolean;
  /** Progress phrase from the running task, such as "Converting 2 of 3". */
  workMessage?: string;
}

const FAILURE_ROW_LIMIT = 20;

/** Keep the last finished sync. A busy or cancelled pass is not a new result. */
export function nextSyncReport(
  previous: LibrarySyncReport | null | undefined,
  incoming: LibrarySyncReport | null | undefined,
): LibrarySyncReport | null {
  if (!incoming || incoming.busy || incoming.cancelled) return previous ?? null;
  return incoming;
}

/** Short status-chip phrase for a running sync, conversion, or index task. */
export function libraryActivityLabel(task: Pick<
  BackgroundTask,
  'kind' | 'label' | 'message' | 'operation' | 'phase' | 'completed' | 'total'
>): string {
  if (task.kind === 'index') {
    if (task.phase === 'finalizing') return 'Updating library index…';
    const action = task.operation === 'update' ? 'Updating index' : 'Building index';
    const total = task.total ?? 0;
    const completed = task.completed ?? 0;
    if (total > 0) return `${action} ${Math.min(completed, total)} of ${total}`;
    return `${action}…`;
  }
  const message = task.message?.trim();
  if (message) return message;
  return task.label;
}

export function libraryHealth(input: LibraryHealthInput): LibraryHealth {
  const index = input.index ?? null;
  const syncReport = input.syncReport && !input.syncReport.busy && !input.syncReport.cancelled
    ? input.syncReport
    : null;
  const indexing = input.indexing ?? null;
  const items: LibraryHealthItem[] = [];

  const errors = syncReport?.errors ?? [];
  const fileFailureCount = Math.max(syncReport?.failed ?? 0, errors.length);
  const shown = errors.slice(0, FAILURE_ROW_LIMIT);
  for (const entry of shown) {
    const path = joinLibraryPath(input.libraryPath, entry.input);
    if (isIndexFailure(entry.input)) {
      items.push({
        kind: 'syncError',
        text: 'Library index could not be updated',
        detail: entry.error,
        path,
        actions: ['tryAgain', 'openConvertLog'],
      });
      continue;
    }
    items.push({
      kind: 'failedFile',
      text: fileName(path),
      detail: entry.error,
      path,
      actions: ['retry', 'convertWithOptions', 'showInFolder'],
    });
  }
  const hiddenFailures = fileFailureCount - shown.length;
  if (hiddenFailures > 0) {
    items.push({ kind: 'moreFailures', text: `and ${hiddenFailures} more`, actions: [] });
  }
  if (shown.length === 0 && (fileFailureCount > 0 || (syncReport?.ok === false && Boolean(syncReport.error)))) {
    const summary = fileFailureCount > 0
      ? `${fileFailureCount} file${fileFailureCount === 1 ? '' : 's'} did not convert`
      : (syncReport?.error || 'Library sync failed');
    const detail = fileFailureCount > 0 ? syncReport?.error : undefined;
    items.push({
      kind: 'syncError',
      text: summary,
      detail: detail && detail !== summary ? detail : undefined,
      actions: ['tryAgain', 'openConvertLog'],
    });
  }
  if (syncReport?.needs_confirmation) {
    items.push({
      kind: 'needsConfirmation',
      text: 'A lot of documents disappeared from this folder. Confirm only if you deleted those files.',
      actions: ['review'],
    });
  }
  const skipped = input.indexReport?.skipped ?? 0;
  if (skipped > 0) {
    items.push({
      kind: 'skippedIndex',
      text: skipped === 1
        ? '1 archive was skipped while indexing'
        : `${skipped} archives were skipped while indexing`,
      actions: ['viewReport'],
    });
  }
  if (input.pendingCount > 0) {
    items.push({
      kind: 'pendingFiles',
      text: `${input.pendingCount} file${input.pendingCount === 1 ? '' : 's'} not searchable yet`,
      actions: ['convertNow'],
    });
  }
  const indexKnown = index != null || !input.indexChecking;
  if (!indexing && indexKnown) {
    if (!index?.exists) {
      items.push({ kind: 'index', text: 'Not built', actions: ['buildIndex'] });
    } else if (index.fresh) {
      items.push({ kind: 'index', text: 'Up to date', actions: ['updateIndex'] });
    } else {
      const reasons = reasonText(index.reasons);
      items.push({
        kind: 'index',
        text: reasons ? `Out of date: ${reasons}` : 'Out of date',
        actions: ['updateIndex'],
      });
    }
  }

  let attentionCount = 0;
  if (shown.length > 0 || fileFailureCount > 0) attentionCount += Math.max(fileFailureCount, shown.length);
  else if (syncReport?.ok === false && syncReport.error) attentionCount += 1;
  if (syncReport?.needs_confirmation) attentionCount += 1;
  if (skipped > 0) attentionCount += 1;

  const working = Boolean(indexing || input.syncing || input.converting);
  const stale = Boolean(index?.exists && !index.fresh);
  let state: LibraryHealthState;
  if (working) state = 'working';
  else if (attentionCount > 0) state = 'attention';
  else if (input.pendingCount > 0 || stale) state = 'pending';
  else if (!index?.exists && !(input.indexChecking && !index)) state = 'setup';
  else if (input.indexChecking && !index) state = 'checking';
  else state = 'ready';

  const label = state === 'working'
    ? workLabel(input)
    : state === 'attention'
      ? `Needs attention (${attentionCount})`
      : state === 'pending'
        ? (input.pendingCount > 0 ? `${input.pendingCount} new` : 'Out of date')
        : state === 'setup'
          ? 'Not indexed'
          : state === 'checking'
            ? 'Checking…'
            : 'Ready';

  let title = label;
  if (state === 'attention') {
    title = `Needs attention (${attentionCount}). Select for details.`;
  } else if (state === 'pending' && input.pendingCount > 0) {
    title = `${input.pendingCount} file${input.pendingCount === 1 ? '' : 's'} not searchable yet`;
    if (stale) {
      const reasons = reasonText(index?.reasons);
      title += reasons ? `. Index needs updating: ${reasons}` : '. Index needs updating';
    }
  } else if (state === 'pending') {
    const reasons = reasonText(index?.reasons);
    title = reasons ? `Index needs updating: ${reasons}` : 'Index needs updating';
  } else if (state === 'setup') {
    title = 'No index yet. Select to build one.';
  } else if (state === 'checking') {
    title = 'Checking index status…';
  } else if (state === 'ready') {
    title = 'Ready. Select for library health.';
  }
  if (input.indexChecking && index && state !== 'working') {
    title += ' Verifying current folder state…';
  }

  return { state, label, title, items };
}

function workLabel(input: LibraryHealthInput): string {
  const message = input.workMessage?.trim();
  if (message) return message;
  if (input.indexing === 'build') return 'Building index…';
  if (input.indexing === 'update') return 'Updating index…';
  if (input.converting) return 'Converting…';
  return 'Syncing…';
}

function reasonText(reasons: string[] | undefined): string {
  return (reasons ?? []).map((reason) => reason.trim()).filter(Boolean).join('; ');
}

function isIndexFailure(input: string): boolean {
  const relative = input.replace(/\\/g, '/').replace(/^\/+/, '').toLowerCase();
  return relative === '.vera/index' || relative.endsWith('/.vera/index');
}

function joinLibraryPath(libraryPath: string, input: string): string {
  const trimmed = input.trim();
  if (!trimmed) return libraryPath;
  if (/^[a-zA-Z]:[\\/]/.test(trimmed) || trimmed.startsWith('\\\\') || trimmed.startsWith('/')) {
    return trimmed;
  }
  const separator = libraryPath.includes('\\') ? '\\' : '/';
  const base = libraryPath.replace(/[\\/]+$/, '');
  const relative = trimmed.replace(/\\/g, '/').replace(/^\/+/, '');
  return `${base}${separator}${relative.split('/').join(separator)}`;
}
