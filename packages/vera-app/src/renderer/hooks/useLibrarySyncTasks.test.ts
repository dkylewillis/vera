import { describe, expect, it } from 'vitest';
import type { BackgroundTask } from '../lib/backgroundTasks';
import {
  librarySyncHydrationTask,
  librarySyncProgressAction,
  librarySyncReportAction,
} from './useLibrarySyncTasks';

const folder = 'C:\\library';

describe('library sync task', () => {
  it('stays quiet until a sync has files to check or convert', () => {
    expect(librarySyncProgressAction(
      { phase: 'indexing', completed: 0, total: 0, input: '' },
      'bg',
      folder,
      undefined,
    )).toBeNull();
    expect(librarySyncProgressAction(
      { phase: 'scanning', completed: 0, total: 0, input: '' },
      'bg',
      folder,
      undefined,
    )).toBeNull();
  });

  it('creates a task on the first scanning event and finishes it when the report arrives', () => {
    const started = librarySyncProgressAction(
      { phase: 'scanning', completed: 0, total: 106, input: 'a.pdf' },
      'bg',
      folder,
      undefined,
    );
    expect(started).toEqual({
      type: 'start',
      task: expect.objectContaining({
        id: 'bg',
        kind: 'librarySync',
        label: 'Syncing library',
        path: folder,
        message: 'Checking library 1 of 106',
        currentItem: 'a.pdf',
      }),
    });
    const task = (started && started.type === 'start' ? started.task : null) as BackgroundTask;
    const tasks = [task];
    expect(librarySyncReportAction(tasks, 'bg')).toEqual({ type: 'finish', id: 'bg' });
    expect(librarySyncReportAction(tasks, undefined)).toBeNull();
  });

  it('leaves a conversion task that owns the same request alone', () => {
    const conversion: BackgroundTask = {
      id: 'req',
      kind: 'conversion',
      label: 'Converting new files',
      path: folder,
    };
    expect(librarySyncReportAction([conversion], 'req')).toBeNull();
  });

  it('hydrates a task a window can stop while a sync is already running', () => {
    expect(librarySyncHydrationTask(folder, 'bg')).toMatchObject({
      id: 'bg',
      kind: 'librarySync',
      path: folder,
      message: 'Checking library…',
    });
  });

  it('keeps Stopping… in place while later progress arrives', () => {
    const stopping: BackgroundTask = {
      id: 'bg',
      kind: 'librarySync',
      label: 'Syncing library',
      path: folder,
      message: 'Stopping…',
    };
    expect(librarySyncProgressAction(
      { phase: 'convert', completed: 1, total: 4, input: 'b.pdf' },
      'bg',
      folder,
      stopping,
    )).toBeNull();
  });
});
