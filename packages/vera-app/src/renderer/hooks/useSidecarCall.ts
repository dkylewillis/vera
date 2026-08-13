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

export function useSidecarCall(options: {
  dispatchBackgroundTask: Dispatch<BackgroundTaskAction>;
  setErrorMessage: (message: string | null) => void;
  setProviderErrorDetail: (detail: string | null) => void;
}): {
  call: SidecarCall;
  cancelActionScope: (scope: string) => void;
} {
  const actionScopesRef = useRef(new Map<string, string>());
  const optionsRef = useRef(options);
  optionsRef.current = options;

  function cancelActionScope(scope: string) {
    const requestId = actionScopesRef.current.get(scope);
    if (!requestId) return;
    actionScopesRef.current.delete(scope);
    optionsRef.current.dispatchBackgroundTask({ type: 'finish', id: requestId });
    void window.vera.cancelRequest(requestId);
  }

  async function call<T>(
    payload: Record<string, unknown>,
    label: string,
    requestId?: string,
    callOptions: ActionCallOptions = {},
  ): Promise<T | null> {
    const { dispatchBackgroundTask, setErrorMessage, setProviderErrorDetail } = optionsRef.current;
    const activityId = requestId || crypto.randomUUID();
    const scope = sidecarCallScope(payload, label, callOptions);
    const timeoutMs = callOptions.timeoutMs ?? DEFAULT_ACTION_TIMEOUT_MS;
    const previousRequestId = actionScopesRef.current.get(scope);
    if (previousRequestId && previousRequestId !== activityId) {
      dispatchBackgroundTask({ type: 'finish', id: previousRequestId });
      void window.vera.cancelRequest(previousRequestId);
    }
    actionScopesRef.current.set(scope, activityId);
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
      const message = error instanceof Error ? error.message : 'Request failed';
      if (sidecarCallWasCancelled(message)) {
        return null;
      }
      setErrorMessage(message);
      setProviderErrorDetail(null);
      return null;
    } finally {
      if (timeout) clearTimeout(timeout);
      if (actionScopesRef.current.get(scope) === activityId) {
        actionScopesRef.current.delete(scope);
      }
      dispatchBackgroundTask({ type: 'finish', id: activityId });
    }
  }

  return { call, cancelActionScope };
}
