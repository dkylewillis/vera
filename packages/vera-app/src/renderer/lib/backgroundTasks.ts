export type BackgroundTaskKind = 'conversion' | 'index' | 'inspection' | 'operation' | 'docling_prepare';
export type IndexTaskOperation = 'build' | 'update';

export interface BackgroundTask {
  id: string;
  kind: BackgroundTaskKind;
  label: string;
  path?: string;
  operation?: IndexTaskOperation;
  phase?: string;
  message?: string;
  completed?: number;
  total?: number;
  currentItem?: string;
  chunks?: number;
  skipped?: number;
}

export type BackgroundTaskAction =
  | { type: 'start'; task: BackgroundTask }
  | { type: 'update'; id: string; update: Partial<Omit<BackgroundTask, 'id' | 'kind'>> }
  | { type: 'finish'; id: string };

export function backgroundTasksReducer(
  tasks: BackgroundTask[],
  action: BackgroundTaskAction,
): BackgroundTask[] {
  if (action.type === 'start') {
    return [...tasks.filter((task) => task.id !== action.task.id), action.task];
  }
  if (action.type === 'update') {
    return tasks.map((task) => (
      task.id === action.id ? { ...task, ...action.update } : task
    ));
  }
  return tasks.filter((task) => task.id !== action.id);
}

export function taskIsDeterminate(task: BackgroundTask): boolean {
  return typeof task.total === 'number' && task.total > 0
    && typeof task.completed === 'number';
}

function itemName(value: string): string {
  return value.split(/[\\/]/).pop() || value;
}

export function formatBackgroundTask(task: BackgroundTask): string {
  const details: string[] = [];
  if (task.kind === 'index') {
    if (task.phase === 'discovering') {
      details.push('Discovering index files');
    } else if (task.phase === 'finalizing') {
      details.push('Finalizing index');
    } else {
      const action = task.operation === 'update' ? 'Updating index' : 'Building index';
      const count = taskIsDeterminate(task) ? ` ${task.completed} of ${task.total}` : '';
      details.push(`${action}${count}`);
    }
  } else if (task.kind === 'inspection') {
    const count = taskIsDeterminate(task) ? ` ${task.completed} of ${task.total}` : '';
    details.push(`Inspecting library${count}`);
  } else if (task.kind === 'docling_prepare') {
    details.push(task.message || task.label);
  } else {
    details.push(task.label);
    if (task.message) details.push(task.message);
  }

  if (task.currentItem) details.push(itemName(task.currentItem));
  if ((task.kind === 'index' || task.kind === 'inspection') && typeof task.chunks === 'number') {
    details.push(`${task.chunks.toLocaleString()} chunks`);
  }
  if ((task.kind === 'index' || task.kind === 'inspection') && task.skipped) {
    details.push(`${task.skipped} skipped`);
  }
  return details.join(' · ');
}
