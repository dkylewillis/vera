import { CheckCircle2, RefreshCw } from 'lucide-react';
import {
  formatBackgroundTask,
  taskIsDeterminate,
  type BackgroundTask,
} from '../lib/backgroundTasks';

interface AppStatusBarProps {
  tasks: BackgroundTask[];
  busyFolderPath?: string;
}

const MAX_VISIBLE_TASKS = 2;

function itemName(value: string): string {
  return value.split(/[\\/]/).pop() || value;
}

export function AppStatusBar({
  tasks,
  busyFolderPath = '',
}: AppStatusBarProps) {
  // User-initiated work should be visible immediately instead of appearing
  // only after older background jobs leave the limited footer.
  const visibleTasks = tasks.slice(-MAX_VISIBLE_TASKS).reverse();
  const hiddenTaskCount = Math.max(0, tasks.length - visibleTasks.length);
  const hasActivity = tasks.length > 0 || Boolean(busyFolderPath);

  return (
    <footer className="appStatusBar" role="status" aria-live="polite" aria-atomic="false">
      {visibleTasks.map((task) => {
        const determinate = taskIsDeterminate(task);
        const description = formatBackgroundTask(task);
        const completed = Math.min(task.total ?? 0, Math.max(0, task.completed ?? 0));
        return (
          <span
            className="appStatusItem"
            key={task.id}
            title={task.currentItem || task.path}
            {...(determinate
              ? {
                  role: 'progressbar',
                  'aria-label': description,
                  'aria-valuemin': 0,
                  'aria-valuemax': task.total,
                  'aria-valuenow': completed,
                }
              : {})}
          >
            <RefreshCw size={12} className="spinning" aria-hidden="true" />
            {determinate ? (
              <progress
                className="appStatusProgress"
                max={task.total}
                value={completed}
                aria-hidden="true"
              />
            ) : null}
            <span className="appStatusText">{description}</span>
          </span>
        );
      })}
      {hiddenTaskCount ? (
        <span className="appStatusItem appStatusItem--overflow" title={`${hiddenTaskCount} additional background task${hiddenTaskCount === 1 ? '' : 's'}`}>
          +{hiddenTaskCount} more
        </span>
      ) : null}
      {busyFolderPath ? (
        <span className="appStatusItem" title={busyFolderPath}>
          <RefreshCw size={12} className="spinning" aria-hidden="true" />
          <span className="appStatusText">Refreshing folder · {itemName(busyFolderPath)}</span>
        </span>
      ) : null}
      {!hasActivity ? (
        <span className="appStatusItem appStatusItem--idle">
          <CheckCircle2 size={12} aria-hidden="true" />
          <span>Ready</span>
        </span>
      ) : null}
    </footer>
  );
}
