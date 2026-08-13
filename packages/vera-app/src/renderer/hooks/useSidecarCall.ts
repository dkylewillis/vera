import { useRef, type Dispatch } from 'react';
import type { BackgroundTaskAction } from '../lib/backgroundTasks';
import {
  DEFAULT_ACTION_TIMEOUT_MS,
  sidecarCallScope,
  sidecarCallWasCancelled,
  sidecarTimeoutMessage,
  type ActionCallOptions,
  type SidecarCall,
} from '../lib/sidecarCall';

export type { ActionCallOptions, SidecarCall } from '../lib/sidecarCall';
export { DEFAULT_ACTION_TIMEOUT_MS } from '../lib/sidecarCall';

export type SidecarCallHost = {
  dispatchBackgroundTask: Dispatch<BackgroundTaskAction>;
  setErrorMessage: (message: string | null) => void;
  setProviderErrorDetail: (detail: string | null) => void;
};

export function createSidecarCaller(
  actionScopes: Map<string, string>,
  getHost: () => SidecarCallHost,
): {
  call: SidecarCall;
  cancelActionScope: (scope: string) => void;
} {
  function cancelActionScope(scope: string) {
    const requestId = actionScopes.get(scope);
    if (!requestId) return;
    actionScopes.delete(scope);
    getHost().dispatchBackgroundTask({ type: 'finish', id: requestId });
    void window.vera.cancelRequest(requestId);
  }

  async function call<T>(
    payload: Record<string, unknown>,
    label: string,
    requestId?: string,
    callOptions: ActionCallOptions = {},
  ): Promise<T | null> {
    const { dispatchBackgroundTask, setErrorMessage, setProviderErrorDetail } = getHost();
    const activityId = requestId || crypto.randomUUID();
    const scope = sidecarCallScope(payload, label, callOptions);
    const timeoutMs = callOptions.timeoutMs ?? DEFAULT_ACTION_TIMEOUT_MS;
    const previousRequestId = actionScopes.get(scope);
    if (previousRequestId && previousRequestId !== activityId) {
      dispatchBackgroundTask({ type: 'finish', id: previousRequestId });
      void window.vera.cancelRequest(previousRequestId);
    }
    actionScopes.set(scope, activityId);
    dispatchBackgroundTask({
      type: 'start',
      task: {
        id: activityId,
        kind: 'operation',
        label,
      },
    });
    setErrorMessage(null);
    setProviderErrorDetail(null);
    let timeout: ReturnType<typeof setTimeout> | null = null;
    try {
      const request = window.vera.request<T>(payload, activityId);
      const response = timeoutMs > 0
        ? await new Promise<Awaited<typeof request>>((resolve, reject) => {
            timeout = setTimeout(() => {
              void window.vera.cancelRequest(activityId);
              reject(new Error(sidecarTimeoutMessage(label, timeoutMs)));
            }, timeoutMs);
            request.then(resolve, reject);
          })
        : await request;
      if (actionScopes.get(scope) !== activityId) {
        return null;
      }
      if (!response.ok) {
        if (sidecarCallWasCancelled(response.error, response.cancelled)) {
          return null;
        }
        setErrorMessage(response.error || 'Request failed');
        setProviderErrorDetail(response.provider_error_detail || null);
        return null;
      }
      return (response.result || null) as T | null;
    } catch (error) {
      if (actionScopes.get(scope) !== activityId) {
        return null;
      }
      const message = error instanceof Error ? error.message : 'Request failed';
      if (sidecarCallWasCancelled(message)) {
        return null;
      }
      setErrorMessage(message);
      setProviderErrorDetail(null);
      return null;
    } finally {
      if (timeout) clearTimeout(timeout);
      if (actionScopes.get(scope) === activityId) {
        actionScopes.delete(scope);
      }
      dispatchBackgroundTask({ type: 'finish', id: activityId });
    }
  }

  return { call, cancelActionScope };
}

export function useSidecarCall(options: SidecarCallHost): {
  call: SidecarCall;
  cancelActionScope: (scope: string) => void;
} {
  const actionScopesRef = useRef(new Map<string, string>());
  const optionsRef = useRef(options);
  optionsRef.current = options;
  const callerRef = useRef<ReturnType<typeof createSidecarCaller> | null>(null);
  if (!callerRef.current) {
    callerRef.current = createSidecarCaller(actionScopesRef.current, () => optionsRef.current);
  }
  return callerRef.current;
}
