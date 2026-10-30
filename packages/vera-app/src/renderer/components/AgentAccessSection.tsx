import { useEffect, useState } from 'react';
import { AGENT_SERVICE_NOTE } from '../../shared/agent-snippets';
import type { ProAccount } from '../../shared/pro';
import type { AgentServiceStatus } from '../types';

function subscriptionActive(account: ProAccount | null): boolean {
  return account?.subscriptionStatus === 'active' || account?.subscriptionStatus === 'trialing';
}

async function copyText(value: string): Promise<boolean> {
  if (!value || typeof navigator === 'undefined' || !navigator.clipboard?.writeText) return false;
  try {
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    return false;
  }
}

export function AgentAccessSection() {
  const [status, setStatus] = useState<AgentServiceStatus | null>(null);
  const [roots, setRoots] = useState<string[]>([]);
  const [enabled, setEnabled] = useState(false);
  const [cloudEnabled, setCloudEnabled] = useState(false);
  const [isPro, setIsPro] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');

  useEffect(() => {
    const api = window.vera;
    if (!api?.serviceGetStatus) return undefined;
    let cancelled = false;
    void api.serviceGetStatus().then((next) => {
      if (cancelled) return;
      setStatus(next);
      setRoots(next.libraryRoots);
      setEnabled(next.enabled);
      setCloudEnabled(Boolean(next.cloudEnabled));
    }).catch(() => undefined);
    const unsubscribe = api.onServiceEvent?.((next) => {
      setStatus(next);
      setRoots(next.libraryRoots);
      setEnabled(next.enabled);
      setCloudEnabled(Boolean(next.cloudEnabled));
    });
    const unsubscribePro = api.onProAccountChanged?.((account) => setIsPro(subscriptionActive(account)));
    void api.proGetAccount?.().then((account) => setIsPro(subscriptionActive(account))).catch(() => undefined);
    return () => {
      cancelled = true;
      unsubscribe?.();
      unsubscribePro?.();
    };
  }, []);

  async function save(nextEnabled: boolean, nextRoots: string[], nextCloud = cloudEnabled) {
    setBusy(true);
    try {
      const next = await window.vera.serviceSave({
        enabled: nextEnabled,
        libraryRoots: nextRoots,
        port: status?.port,
        cloudEnabled: nextCloud,
      });
      setStatus(next);
      setRoots(next.libraryRoots);
      setEnabled(next.enabled);
      setCloudEnabled(Boolean(next.cloudEnabled));
      setNotice(next.message);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to update agent access.');
    } finally {
      setBusy(false);
    }
  }

  async function addLibrary() {
    const picked = await window.vera.pickFolder();
    if (!picked) return;
    if (roots.some((root) => root.toLowerCase() === picked.toLowerCase())) return;
    await save(enabled, [...roots, picked]);
  }

  return (
    <div className="settingsForm">
      <h3>Agent access</h3>
      <p>{AGENT_SERVICE_NOTE}</p>
      <label className="settingsCheck">
        <input
          type="checkbox"
          checked={enabled}
          disabled={busy}
          onChange={(event) => void save(event.target.checked, roots)}
        />
        Share libraries with local agents
      </label>
      <label className="settingsCheck">
        <input
          type="checkbox"
          checked={cloudEnabled}
          disabled={busy || !isPro}
          onChange={(event) => void save(enabled, roots, event.target.checked)}
        />
        Allow cloud agents (VERA Pro)
      </label>
      <p>Cloud assistants reach your library through VERA's relay while this app is open.</p>
      {!isPro ? (
        <button type="button" className="secondaryAction" disabled={busy} onClick={() => void window.vera.proOpenPage('pricing')}>
          Get Pro
        </button>
      ) : null}
      {status?.cloud?.message ? <p role="status">{status.cloud.message}</p> : null}
      {status?.cloud?.connectorUrl ? (
        <>
          <h4>Connector URL</h4>
          <pre>{status.cloud.connectorUrl}</pre>
          <button
            type="button"
            className="secondaryAction"
            onClick={() => void copyText(status.cloud.connectorUrl).then((ok) => setNotice(ok ? 'Connector URL copied.' : 'Unable to copy the connector URL.'))}
          >
            Copy connector URL
          </button>
        </>
      ) : null}
      <h4>Shared libraries</h4>
      {roots.length === 0 ? <p>No libraries shared yet.</p> : null}
      <ul className="agentLibraryList">
        {roots.map((root) => (
          <li key={root}>
            <span>{root}</span>
            <button
              type="button"
              className="secondaryAction"
              disabled={busy}
              onClick={() => void save(enabled, roots.filter((item) => item !== root))}
            >
              Remove
            </button>
          </li>
        ))}
      </ul>
      <button type="button" className="secondaryAction" disabled={busy} onClick={() => void addLibrary()}>
        Add library
      </button>
      <p role="status">{notice || status?.message || 'Agent access is off.'}</p>
      <button
        type="button"
        className="secondaryAction"
        disabled={busy}
        onClick={() => {
          void window.vera.serviceRotateToken().then((next) => {
            setStatus(next);
            setNotice(next.message);
          });
        }}
      >
        Rotate token
      </button>
      <h4>HTTP snippet</h4>
      <pre>{status?.snippets.http || 'Turn on agent access to copy a config snippet.'}</pre>
      <button
        type="button"
        className="secondaryAction"
        disabled={!status?.snippets.http}
        onClick={() => void copyText(status?.snippets.http || '').then((ok) => setNotice(ok ? 'HTTP snippet copied.' : 'Unable to copy the HTTP snippet.'))}
      >
        Copy HTTP snippet
      </button>
      <h4>Stdio snippet</h4>
      <pre>{status?.snippets.stdio || 'Turn on agent access to copy a config snippet.'}</pre>
      <button
        type="button"
        className="secondaryAction"
        disabled={!status?.snippets.stdio}
        onClick={() => void copyText(status?.snippets.stdio || '').then((ok) => setNotice(ok ? 'Stdio snippet copied.' : 'Unable to copy the stdio snippet.'))}
      >
        Copy stdio snippet
      </button>
    </div>
  );
}
