import { useEffect, useRef, type Dispatch } from 'react';
import type { BackgroundTask, BackgroundTaskAction } from '../lib/backgroundTasks';
import { librarySyncTaskUpdate } from '../lib/managedLibrary';
import type { StreamEvent } from '../types';

const LIBRARY_SYNC_WORK_PHASES = new Set(['convert', 'move', 'trash']);

/** Turn one progress event into a task start or update. Quiet until there is work. */
export function librarySyncProgressAction(
  event: Pick<StreamEvent, 'phase' | 'total' | 'completed' | 'input'>,
  requestId: string,
  folderPath: string,
  existing: BackgroundTask | undefined,
): BackgroundTaskAction | null {
  if (existing?.message === 'Stopping…') return null;
  const phase = event.phase || '';
  const total = event.total ?? 0;
  const startsWork = (phase === 'scanning' && total > 0) || LIBRARY_SYNC_WORK_PHASES.has(phase);
  if (!existing && !startsWork) return null;
  const update = librarySyncTaskUpdate(event);
  if (!existing) {
    return {
      type: 'start',
      task: {
        id: requestId,
        kind: 'librarySync',
        label: 'Syncing library',
        path: folderPath,
        ...update,
      },
    };
  }
  return { type: 'update', id: requestId, update };
}

export function librarySyncHydrationTask(folderPath: string, requestId: string): BackgroundTask {
  return {
    id: requestId,
    kind: 'librarySync',
    label: 'Syncing library',
    path: folderPath,
    message: 'Checking library…',
  };
}

/** Finish the sync task when its report arrives. A conversion task with the same id keeps itself. */
export function librarySyncReportAction(
  tasks: BackgroundTask[],
  requestId: string | undefined,
): BackgroundTaskAction | null {
  if (!requestId) return null;
  const task = tasks.find((item) => item.id === requestId);
  if (!task || task.kind !== 'librarySync') return null;
  return { type: 'finish', id: requestId };
}

/**
 * Show background library syncs in the status bar. A sync with nothing to do
 * stays quiet. A conversion the user started owns its own task and is ignored here.
 */
export function useLibrarySyncTasks(
  tasks: BackgroundTask[],
  dispatch: Dispatch<BackgroundTaskAction>,
): void {
  const tasksRef = useRef(tasks);
  tasksRef.current = tasks;

  useEffect(() => {
    const ownedByConversion = (requestId: string) => tasksRef.current.some((task) => (
      task.id === requestId && task.kind === 'conversion'
    ));
    const offProgress = window.vera.onLibrarySyncProgress((folderPath, requestId, event) => {
      if (ownedByConversion(requestId)) return;
      const existing = tasksRef.current.find((task) => task.id === requestId && task.kind === 'librarySync');
      const action = librarySyncProgressAction(event, requestId, folderPath, existing);
      if (action) dispatch(action);
    });
    const offReport = window.vera.onLibrarySync((_folderPath, _report, requestId) => {
      const action = librarySyncReportAction(tasksRef.current, requestId);
      if (action) dispatch(action);
    });
    let canceled = false;
    void window.vera.librarySyncStatus().then((running) => {
      if (canceled) return;
      for (const item of running) {
        if (tasksRef.current.some((task) => task.id === item.requestId)) continue;
        dispatch({ type: 'start', task: librarySyncHydrationTask(item.folderPath, item.requestId) });
      }
    }).catch(() => undefined);
    return () => {
      canceled = true;
      offProgress();
      offReport();
    };
  }, [dispatch]);
}
