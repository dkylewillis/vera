import { SIDECAR_ACTIONS } from '../../shared/protocol';
import type { LibrarySyncReport, LibraryTrashEntry, StreamEvent, VeraResponse } from '../types';
import type { BackgroundTask } from './backgroundTasks';

/** Archive written for this source during the sync that just finished. */
export function convertedArchivePath(
  sourcePath: string,
  report: LibrarySyncReport | null | undefined,
): string {
  const wanted = sourcePath.replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase();
  if (!wanted) return '';
  for (const action of report?.actions ?? []) {
    if (action.action !== 'convert' || !action.output) continue;
    const source = (action.source ?? '').replace(/\\/g, '/').replace(/^\/+/, '').toLowerCase();
    if (!source) continue;
    if (wanted === source || wanted.endsWith(`/${source}`)) return action.output;
  }
  return '';
}

type Request = <T>(payload: Record<string, unknown>) => Promise<VeraResponse<T>>;

export function librarySyncSummary(report: LibrarySyncReport | null | undefined): string {
  if (!report || report.managed === false) return '';
  if (report.busy) return '';
  if (report.needs_confirmation) return 'Confirm before removing archives';
  if (report.failed) return 'Library sync had errors';
  const parts: string[] = [];
  if (report.converted) parts.push(`${report.converted} converted`);
  if (report.moved) parts.push(`${report.moved} moved`);
  if (report.trashed) parts.push(`${report.trashed} trashed`);
  return parts.join(', ');
}

/** Status-bar text for one `library_progress` event (sync steps, then the index refresh). */
export function librarySyncTaskUpdate(
  event: Pick<StreamEvent, 'phase' | 'total' | 'completed' | 'input'>,
): Partial<Omit<BackgroundTask, 'id' | 'kind'>> {
  const total = event.total ?? 0;
  const completed = event.completed ?? 0;
  const currentItem = event.input?.trim() || undefined;
  const base = { phase: event.phase, completed, total, currentItem };
  const step = total ? ` ${Math.min(completed + 1, total)} of ${total}` : '';
  switch (event.phase) {
    case 'convert':
      return { ...base, message: `Converting${step}` };
    case 'move':
      return { ...base, message: `Moving archives${step}` };
    case 'trash':
      return { ...base, message: `Moving to library trash${step}` };
    case 'discovering':
    case 'indexing':
    case 'finalizing':
      return { ...base, total: 0, currentItem: undefined, message: 'Updating library index…' };
    default:
      return { ...base, message: 'Checking library…' };
  }
}

/** Why a sync started from Convert needs the user's attention, or `null` when it finished cleanly. */
export function librarySyncProblem(report: LibrarySyncReport | null | undefined): string | null {
  if (!report) return 'Library sync failed. Try again, or open the convert log from File > Open convert log….';
  if (report.busy) return 'Another VERA process is updating this library. Convert again when it finishes.';
  if (report.error) return report.error;
  const errors = report.errors ?? [];
  if (errors.length) {
    const lines = errors.slice(0, 3).map((item) => `${item.input}: ${item.error}`);
    if (errors.length > 3) lines.push(`…and ${errors.length - 3} more`);
    return `Some files did not convert:\n${lines.join('\n')}`;
  }
  return null;
}

/** Create `.vera/` for a folder that is not already inside a managed library. */
export async function prepareManagedLibrary(
  folderPath: string,
  request: Request,
  options: { model?: string; askAdopt?: (count: number) => Promise<boolean> } = {},
): Promise<LibrarySyncReport | null> {
  const status = await request<LibrarySyncReport>({
    action: SIDECAR_ACTIONS.libraryStatus,
    path: folderPath,
  });
  const report = status.ok ? status.result ?? null : null;
  if (!report || report.managed || report.inside_library) return report;
  let adopt = false;
  const adoptable = report.adoptable?.length ?? 0;
  if (adoptable > 0 && options.askAdopt) adopt = await options.askAdopt(adoptable);
  const created = await request<{ library_id?: string }>({
    action: SIDECAR_ACTIONS.libraryInit,
    path: folderPath,
    adopt,
    model: options.model,
  });
  if (!created.ok) return null;
  return report;
}

export async function loadLibraryTrash(folderPath: string, request: Request): Promise<LibraryTrashEntry[]> {
  const response = await request<{ entries?: LibraryTrashEntry[] }>({
    action: SIDECAR_ACTIONS.libraryTrashList,
    path: folderPath,
  });
  return response.ok ? response.result?.entries ?? [] : [];
}

export async function restoreLibraryEntry(folderPath: string, entry: string, request: Request): Promise<boolean> {
  const response = await request<{ ok?: boolean }>({
    action: SIDECAR_ACTIONS.libraryRestore,
    path: folderPath,
    entry,
  });
  return Boolean(response.ok && response.result?.ok !== false);
}
