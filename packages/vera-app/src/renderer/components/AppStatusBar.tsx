import { CheckCircle2, Cloud, RefreshCw, Square } from 'lucide-react';
import {
  formatBackgroundTask,
  taskIsDeterminate,
  type BackgroundTask,
} from '../lib/backgroundTasks';
import type { AgentServiceStatus } from '../types';

interface AppStatusBarProps {
  tasks: BackgroundTask[];
  busyFolderPath?: string;
  /** Conversions can start from Explorer, so Stop must not require the Convert view. */
  onStopConversion?: () => void;
  /** Stop the library sync shown in the status bar. */
  onStopLibrarySync?: (requestId: string) => void;
  /** Live agent-service status. Cloud routing is shown only while cloud agents are on. */
  agentStatus?: AgentServiceStatus | null;
  onOpenCloudAgents?: () => void;
}

export type CloudComputerTone = 'here' | 'away' | 'pending' | 'error';

export type CloudComputerIndicator = {
  /** The computer cloud agents are using, or a short state when that is unknown. */
  label: string;
  title: string;
  tone: CloudComputerTone;
};

/** Which computer answers cloud agents, for the status bar. Hidden while cloud agents are off. */
export function cloudComputerIndicator(status: AgentServiceStatus | null | undefined): CloudComputerIndicator | null {
  if (!status?.cloudEnabled) return null;
  const cloud = status.cloud;
  if (!cloud || cloud.state === 'off') return null;
  if (cloud.state === 'connecting') {
    return { label: 'Connecting…', title: cloud.message || 'Connecting to the VERA relay…', tone: 'pending' };
  }
  if (cloud.state === 'error' || cloud.state === 'not_pro') {
    return { label: 'Not connected', title: cloud.message || 'Cloud agents are not connected.', tone: 'error' };
  }
  const selfName = cloud.device.name.trim() || 'This computer';
  if (cloud.state === 'connected') {
    return {
      label: selfName,
      title: `Cloud agents are using this computer (${selfName}).`,
      tone: 'here',
    };
  }
  const activeId = cloud.routing.mode === 'pinned' && cloud.routing.pinned ? cloud.routing.pinned : cloud.current || '';
  const active = cloud.devices.find((device) => device.id === activeId);
  if (activeId && activeId !== cloud.device.id) {
    const name = active?.name.trim() || 'another computer';
    return {
      label: name,
      title: `Cloud agents are using ${name}. This computer is standing by.`,
      tone: 'away',
    };
  }
  return { label: 'Standing by', title: cloud.message || 'This computer is standing by.', tone: 'pending' };
}

const MAX_VISIBLE_TASKS = 2;

function itemName(value: string): string {
  return value.split(/[\\/]/).pop() || value;
}

export function AppStatusBar({
  tasks,
  busyFolderPath = '',
  onStopConversion,
  onStopLibrarySync,
  agentStatus = null,
  onOpenCloudAgents,
}: AppStatusBarProps) {
  // User-initiated work should be visible immediately instead of appearing
  // only after older background jobs leave the limited footer.
  const visibleTasks = tasks.slice(-MAX_VISIBLE_TASKS).reverse();
  const hiddenTaskCount = Math.max(0, tasks.length - visibleTasks.length);
  const hasActivity = tasks.length > 0 || Boolean(busyFolderPath);
  const cloudComputer = cloudComputerIndicator(agentStatus);

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
            {task.kind === 'conversion' && onStopConversion ? (
              <button
                type="button"
                className="appStatusAction"
                onClick={onStopConversion}
                disabled={task.message === 'Stopping…'}
                title="Stop conversion"
                aria-label="Stop conversion"
              >
                <Square size={9} fill="currentColor" aria-hidden="true" />
              </button>
            ) : null}
            {task.kind === 'librarySync' && onStopLibrarySync ? (
              <button
                type="button"
                className="appStatusAction"
                onClick={() => onStopLibrarySync(task.id)}
                disabled={task.message === 'Stopping…'}
                title="Stop library sync"
                aria-label="Stop library sync"
              >
                <Square size={9} fill="currentColor" aria-hidden="true" />
              </button>
            ) : null}
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
      {cloudComputer ? (
        <button
          type="button"
          className={`appStatusCloud appStatusCloud--${cloudComputer.tone}`}
          title={cloudComputer.title}
          aria-label={cloudComputer.title}
          onClick={onOpenCloudAgents}
        >
          <Cloud size={12} aria-hidden="true" />
          <span className="appStatusText">{cloudComputer.label}</span>
        </button>
      ) : null}
    </footer>
  );
}
