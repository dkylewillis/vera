import { useEffect, useSyncExternalStore } from 'react';
import type { ProAccount } from '../../shared/pro';

let current: ProAccount | null = null;
const listeners = new Set<() => void>();
let listeningForBroadcasts = false;

function veraApi() {
  return typeof window !== 'undefined' ? window.vera : undefined;
}

export function readProAccount(): ProAccount | null {
  return current;
}

export function publishProAccount(next: ProAccount): void {
  current = next;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  if (!listeningForBroadcasts) {
    const api = veraApi();
    if (api?.onProAccountChanged) {
      api.onProAccountChanged(publishProAccount);
      listeningForBroadcasts = true;
    }
  }
  return () => {
    listeners.delete(listener);
  };
}

/**
 * The account every view shares: the last known value renders immediately
 * (null until the first answer), and each mount asks the main process again.
 */
export function useProAccount(): ProAccount | null {
  const account = useSyncExternalStore(subscribe, () => current, () => null);
  useEffect(() => {
    void veraApi()?.proGetAccount?.().then(publishProAccount).catch(() => undefined);
  }, []);
  return account;
}

export function canLoadProAccount(): boolean {
  return Boolean(veraApi()?.proGetAccount);
}
