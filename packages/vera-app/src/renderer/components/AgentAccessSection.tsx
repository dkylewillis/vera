import { useEffect, useState } from 'react';
import { Cloud, Folder, FolderPlus, Laptop, Plug } from 'lucide-react';
import { AGENT_SERVICE_NOTE } from '../../shared/agent-snippets';
import { subscriptionActive } from '../../shared/pro';
import { useProAccount } from '../lib/proAccount';
import type { AgentServiceStatus } from '../types';
import { Callout, CopyField, SettingsCard, StatusPill, ToggleRow } from './SettingsWidgets';

export function AgentAccessSection() {
  const [status, setStatus] = useState<AgentServiceStatus | null>(null);
  const [roots, setRoots] = useState<string[]>([]);
  const [enabled, setEnabled] = useState(false);
  const [cloudEnabled, setCloudEnabled] = useState(false);
  const hasAgentAccess = subscriptionActive(useProAccount()?.agentAccessStatus || '');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [nameDraft, setNameDraft] = useState('');

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
    return () => {
      cancelled = true;
      unsubscribe?.();
    };
  }, []);

  useEffect(() => {
    if (!cloudEnabled || !window.vera?.relayRefreshDevices) return undefined;
    let cancelled = false;
    void window.vera.relayRefreshDevices().then((next) => {
      if (!cancelled) setStatus(next);
    }).catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [cloudEnabled]);

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

  async function runCloudAction(action: () => Promise<AgentServiceStatus>, success: string) {
    setBusy(true);
    try {
      const next = await action();
      setStatus(next);
      setNotice(success || next.cloud?.message || next.message);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to update cloud agents.');
    } finally {
      setBusy(false);
    }
  }

  async function addLibrary() {
    const picked = await window.vera.pickFolder('agent-library');
    if (!picked) return;
    if (roots.some((root) => root.toLowerCase() === picked.toLowerCase())) return;
    await save(enabled, [...roots, picked]);
  }

  const snippetHint = 'Turn on agent access to copy a config snippet.';

  return (
    <div className="settingsStack">
      <Callout>
        <p>{AGENT_SERVICE_NOTE}</p>
      </Callout>

      <SettingsCard
        icon={<Laptop size={16} />}
        title="Agents on this computer"
        badge={enabled ? <StatusPill tone="good">On</StatusPill> : <StatusPill>Off</StatusPill>}
      >
        <ToggleRow
          title="Share libraries with local agents"
          description="Claude Desktop, Cursor, and other MCP apps on this computer can search the shared libraries while VERA is open."
          checked={enabled}
          disabled={busy}
          onChange={(next) => void save(next, roots)}
        />
        <p className="providerHint" role="status">{notice || status?.message || 'Agent access is off.'}</p>
      </SettingsCard>

      <SettingsCard
        icon={<Folder size={16} />}
        title="Shared libraries"
        description="Agents can search only these folders."
        actions={(
          <button type="button" className="secondaryAction compactAction" disabled={busy} onClick={() => void addLibrary()}>
            <FolderPlus size={14} />Add library
          </button>
        )}
      >
        {roots.length === 0 ? (
          <p className="mutedText">No libraries shared yet.</p>
        ) : (
          <ul className="agentLibraryList">
            {roots.map((root) => (
              <li key={root}>
                <Folder size={14} aria-hidden="true" />
                <span title={root}>{root}</span>
                <button
                  type="button"
                  className="secondaryAction compactAction"
                  disabled={busy}
                  onClick={() => void save(enabled, roots.filter((item) => item !== root))}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </SettingsCard>

      <SettingsCard
        icon={<Plug size={16} />}
        title="Connect an agent"
        description="Paste one snippet into the agent's MCP settings. The stdio snippet runs mcp-connect, which needs VERA Desktop open."
      >
        <CopyField label="HTTP snippet" value={status?.snippets.http || ''} emptyText={snippetHint} multiline />
        <CopyField label="Stdio snippet" value={status?.snippets.stdio || ''} emptyText={snippetHint} multiline />
        <div className="settingRow">
          <span className="settingRowText">
            <span className="settingRowTitle">Rotate token</span>
            <span className="settingRowDescription">Issues a new token. Snippets you already copied stop working.</span>
          </span>
          <button
            type="button"
            className="secondaryAction compactAction"
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
        </div>
      </SettingsCard>

      <SettingsCard
        icon={<Cloud size={16} />}
        title="Cloud agents"
        badge={cloudEnabled ? <StatusPill tone="good">On</StatusPill> : <StatusPill>Off</StatusPill>}
        description="Cloud assistants reach your library through VERA's relay while this app is open. This needs an Agent Access subscription. VERA Pro does not include it. Each signed-in computer stays connected. Cloud agents use one of them."
      >
        <ToggleRow
          title="Allow cloud agents (Agent Access)"
          description={hasAgentAccess ? 'Uses your VERA account to sign the assistant in.' : 'Requires an Agent Access subscription.'}
          checked={cloudEnabled}
          disabled={busy || !hasAgentAccess}
          onChange={(next) => void save(enabled, roots, next)}
        />
        {!hasAgentAccess ? (
          <div className="editorActions">
            <button type="button" className="secondaryAction compactAction" disabled={busy} onClick={() => void window.vera.proOpenPage('pricing')}>
              Get Agent Access
            </button>
          </div>
        ) : null}
        {status?.cloud?.message ? <p className="providerHint" role="status">{status.cloud.message}</p> : null}
        {status?.cloud?.connectorUrl ? <CopyField label="Connector URL" value={status.cloud.connectorUrl} /> : null}
        <div className="agentComputer">
          <span className="settingRowTitle">This computer: {status?.cloud.device.name || 'This computer'}</span>
          <form
            className="agentComputerRename"
            onSubmit={(event) => {
              event.preventDefault();
              const name = nameDraft.trim();
              if (!name || !window.vera?.relayRenameDevice) return;
              void runCloudAction(() => window.vera.relayRenameDevice(name), 'Computer renamed.');
            }}
          >
            <input
              type="text"
              aria-label="Computer name"
              placeholder="New name for this computer"
              value={nameDraft}
              disabled={busy}
              onChange={(event) => setNameDraft(event.target.value)}
            />
            <button type="submit" className="secondaryAction compactAction" disabled={busy || !nameDraft.trim()}>
              Rename
            </button>
          </form>
        </div>
        {cloudEnabled ? (
          <CloudComputers
            status={status}
            busy={busy}
            onRouting={(mode, deviceId) => void runCloudAction(
              () => window.vera.relaySetRouting({ mode, deviceId }),
              mode === 'auto' ? 'Cloud agents will stay on the current computer.' : 'Cloud agents will use that computer.',
            )}
            onForget={(deviceId) => void runCloudAction(
              () => window.vera.relayForgetDevice(deviceId),
              'Computer removed.',
            )}
            onUseThis={() => {
              const id = status?.cloud.device.id;
              if (!id) return;
              void runCloudAction(
                () => window.vera.relaySetRouting({ mode: 'pinned', deviceId: id }),
                'Cloud agents will use this computer.',
              );
            }}
          />
        ) : null}
      </SettingsCard>
    </div>
  );
}

function CloudComputers({
  status,
  busy,
  onRouting,
  onForget,
  onUseThis,
}: {
  status: AgentServiceStatus | null;
  busy: boolean;
  onRouting: (mode: 'auto' | 'pinned', deviceId?: string) => void;
  onForget: (deviceId: string) => void;
  onUseThis: () => void;
}) {
  const cloud = status?.cloud;
  const devices = cloud?.devices || [];
  const self = cloud?.device.id || '';
  const current = devices.find((device) => device.id === cloud?.current);
  const routingValue = cloud?.routing.mode === 'pinned' && cloud.routing.pinned ? cloud.routing.pinned : 'auto';
  const automatic = current ? `Automatic (currently ${current.name})` : 'Automatic';
  return (
    <div className="agentComputer">
      <label className="agentComputerRouting">
        Cloud agents use
        <select
          aria-label="Cloud agents use"
          value={routingValue}
          disabled={busy}
          onChange={(event) => {
            const value = event.target.value;
            if (value === 'auto') onRouting('auto');
            else onRouting('pinned', value);
          }}
        >
          <option value="auto">{automatic}</option>
          {devices.map((device) => (
            <option key={device.id} value={device.id}>{device.name}</option>
          ))}
        </select>
      </label>
      {devices.length === 0 ? <p className="mutedText">No other computers have connected yet.</p> : null}
      <ul className="agentLibraryList">
        {devices.map((device) => (
          <li key={device.id}>
            <Laptop size={14} aria-hidden="true" />
            <span>
              {device.name}
              {device.id === self ? <span className="agentComputerBadge"> · this computer</span> : null}
              {device.online || !device.lastSeen ? null : (
                <span className="agentComputerBadge"> · last seen {new Date(device.lastSeen).toLocaleString()}</span>
              )}
            </span>
            {device.online ? <StatusPill tone="good">Online</StatusPill> : <StatusPill>Offline</StatusPill>}
            {!device.online ? (
              <button type="button" className="secondaryAction compactAction" disabled={busy} onClick={() => onForget(device.id)}>
                Forget
              </button>
            ) : null}
          </li>
        ))}
      </ul>
      <div className="editorActions">
        <button
          type="button"
          className="secondaryAction compactAction"
          disabled={busy || !self || (cloud?.routing.mode === 'pinned' && cloud.routing.pinned === self)}
          onClick={onUseThis}
        >
          Use this computer
        </button>
      </div>
    </div>
  );
}
