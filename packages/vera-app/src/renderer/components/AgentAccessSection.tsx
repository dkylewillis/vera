import { useEffect, useRef, useState } from 'react';
import { Cloud, Folder, FolderPlus, Laptop } from 'lucide-react';
import { AGENT_SERVICE_NOTE } from '../../shared/agent-snippets';
import { fallbackLibraryName, libraryNameError } from '../../shared/library-names';
import { subscriptionActive } from '../../shared/pro';
import { publishProAccount, useProAccount } from '../lib/proAccount';
import type { AgentServiceStatus } from '../types';
import { CopyField, SettingsCard, StatusPill, ToggleRow } from './SettingsWidgets';

export type AgentDestination = 'cloud' | 'local';
type ConnectApp = 'claude' | 'cursor' | 'vscode' | 'other';
type SnippetKind = 'http' | 'stdio';

const CONNECT_APPS: { id: ConnectApp; label: string; kind: SnippetKind | 'ask'; where: string }[] = [
  {
    id: 'claude',
    label: 'Claude Desktop',
    kind: 'stdio',
    where: 'Paste this into Claude Desktop → Settings → Developer → Edit Config, then restart Claude. Leave VERA open.',
  },
  {
    id: 'cursor',
    label: 'Cursor',
    kind: 'http',
    where: 'In Cursor, open Settings → MCP and add a server, or paste this into .cursor/mcp.json. Leave VERA open.',
  },
  {
    id: 'vscode',
    label: 'VS Code',
    kind: 'http',
    where: 'In VS Code, open the Command Palette, run MCP: Open User Configuration, and paste this. Leave VERA open.',
  },
  {
    id: 'other',
    label: 'Other',
    kind: 'ask',
    where: '',
  },
];

const OTHER_WHERE: Record<SnippetKind, string> = {
  http: 'Use this when the app connects to a local web address. Leave VERA open.',
  stdio: 'Use this when the app starts a program. It needs VERA to stay open.',
};

/** Adding the first folder turns access on. Removing the last folder turns it off. */
export function localAccessAfterFolderChange(enabled: boolean, previousCount: number, nextCount: number): boolean {
  if (nextCount <= 0) return false;
  if (previousCount <= 0) return true;
  return enabled;
}

/** Cloud assistants are the default. A setup that only uses local apps opens on that tab. */
export function initialDestination(enabled: boolean, cloudEnabled: boolean): AgentDestination {
  return enabled && !cloudEnabled ? 'local' : 'cloud';
}

/** The relay forwards to the local service, so cloud only works while that service runs. */
export function accessSummary(enabled: boolean, cloudOn: boolean, folderCount: number): string {
  if (folderCount === 0) return 'Off. Add a folder to get started.';
  const folders = folderCount === 1 ? '1 folder' : `${folderCount} folders`;
  if (!enabled) return `Off. ${folders} ready. Choose where your AI runs below.`;
  if (cloudOn) return `Ready. ${folders} shared with cloud assistants and apps on this computer while VERA is open.`;
  return `Ready. ${folders} shared with apps on this computer while VERA is open.`;
}

function folderLabel(root: string): string {
  const parts = root.split(/[\\/]/).filter((part) => part.length > 0);
  return parts[parts.length - 1] || root;
}

export function AgentAccessSection() {
  const [status, setStatus] = useState<AgentServiceStatus | null>(null);
  const [roots, setRoots] = useState<string[]>([]);
  const [names, setNames] = useState<Record<string, string>>({});
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [nameErrors, setNameErrors] = useState<Record<string, string>>({});
  const [renaming, setRenaming] = useState<string | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [cloudEnabled, setCloudEnabled] = useState(false);
  const account = useProAccount();
  const hasAgentAccess = subscriptionActive(account?.agentAccessStatus || '');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [nameDraft, setNameDraft] = useState('');
  const [destination, setDestination] = useState<AgentDestination>('cloud');
  const [connectApp, setConnectApp] = useState<ConnectApp>('claude');
  const [otherKind, setOtherKind] = useState<SnippetKind>('http');
  const cancelRename = useRef(false);

  useEffect(() => {
    const api = window.vera;
    if (!api?.serviceGetStatus) return undefined;
    let cancelled = false;
    void api.serviceGetStatus().then((next) => {
      if (cancelled) return;
      setStatus(next);
      setRoots(next.libraryRoots);
      setNames(next.libraryNames || {});
      setEnabled(next.enabled);
      setCloudEnabled(Boolean(next.cloudEnabled));
      setDestination(initialDestination(next.enabled, Boolean(next.cloudEnabled)));
    }).catch(() => undefined);
    const unsubscribe = api.onServiceEvent?.((next) => {
      setStatus(next);
      setRoots(next.libraryRoots);
      setNames(next.libraryNames || {});
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

  async function save(
    nextEnabled: boolean,
    nextRoots: string[],
    nextCloud = cloudEnabled,
    nextNames = names,
  ) {
    setBusy(true);
    try {
      const next = await window.vera.serviceSave({
        enabled: nextEnabled,
        libraryRoots: nextRoots,
        libraryNames: nextNames,
        port: status?.port,
        cloudEnabled: nextCloud,
      });
      setStatus(next);
      setRoots(next.libraryRoots);
      setNames(next.libraryNames || {});
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

  async function signIn() {
    setBusy(true);
    try {
      const result = await window.vera.proSignIn();
      if (result.account) publishProAccount(result.account);
      if (!result.ok) setNotice(result.error || 'Unable to sign in.');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to sign in.');
    } finally {
      setBusy(false);
    }
  }

  async function addLibrary() {
    const picked = await window.vera.pickFolder('agent-library');
    if (!picked) return;
    if (roots.some((root) => root.toLowerCase() === picked.toLowerCase())) return;
    const nextRoots = [...roots, picked];
    await save(localAccessAfterFolderChange(enabled, roots.length, nextRoots.length), nextRoots, cloudEnabled, names);
  }

  function removeLibrary(root: string) {
    const nextNames = { ...names };
    delete nextNames[root];
    const nextRoots = roots.filter((item) => item !== root);
    if (renaming === root) setRenaming(null);
    void save(localAccessAfterFolderChange(enabled, roots.length, nextRoots.length), nextRoots, cloudEnabled, nextNames);
  }

  function commitName(root: string) {
    const draft = (drafts[root] ?? names[root] ?? '').trim();
    const next = { ...names };
    if (draft) next[root] = draft;
    else delete next[root];
    const problem = libraryNameError(roots, next);
    setNameErrors((current) => ({ ...current, [root]: problem }));
    if (problem) return;
    setRenaming(null);
    setDrafts((current) => {
      const copy = { ...current };
      delete copy[root];
      return copy;
    });
    if ((names[root] ?? '') === (next[root] ?? '')) return;
    void save(enabled, roots, cloudEnabled, next);
  }

  function fallbackName(root: string): string {
    try {
      return fallbackLibraryName(roots, names, root) || folderLabel(root);
    } catch {
      return folderLabel(root);
    }
  }

  function displayName(root: string): string {
    return names[root] || fallbackName(root);
  }

  const cloudOn = enabled && cloudEnabled;
  const noFolders = roots.length === 0;
  const selected = CONNECT_APPS.find((app) => app.id === connectApp) ?? CONNECT_APPS[0];
  const snippetKind: SnippetKind = selected.kind === 'ask' ? otherKind : selected.kind;
  const snippetWhere = selected.kind === 'ask' ? OTHER_WHERE[otherKind] : selected.where;
  const snippetValue = !enabled
    ? ''
    : (snippetKind === 'http' ? status?.snippets.http : status?.snippets.stdio) || '';
  const snippetEmpty = enabled ? 'Preparing the setup snippet…' : 'Turn this on to copy a setup snippet.';
  const detail = notice || (status?.message && status.message !== 'Agent access is off.' ? status.message : '');
  const devices = status?.cloud?.devices || [];

  function renderCloud() {
    if (account && !account.configured) {
      return <p className="mutedText">Cloud assistants are not available in this build of VERA.</p>;
    }
    if (!account?.signedIn || !hasAgentAccess) {
      return (
        <>
          <p className="agentStepHint">
            Cloud assistants reach this computer through VERA&apos;s secure relay. This needs a VERA account with an
            Agent Access subscription. VERA Pro does not include it.
          </p>
          <div className="editorActions">
            {account?.signedIn ? null : (
              <button type="button" className="primaryAction compactAction" disabled={busy} onClick={() => void signIn()}>
                Sign in
              </button>
            )}
            <button type="button" className="secondaryAction compactAction" disabled={busy} onClick={() => void window.vera.proOpenPage('pricing')}>
              Get Agent Access
            </button>
          </div>
          {detail ? <p className="providerHint" role="status">{detail}</p> : null}
        </>
      );
    }
    return (
      <>
        <ToggleRow
          title="Allow cloud agents"
          description={noFolders
            ? 'Add a folder first.'
            : 'ChatGPT, Claude, Grok, and other cloud assistants can search these folders while VERA is open.'}
          checked={cloudOn}
          disabled={busy || (!cloudOn && noFolders)}
          onChange={(next) => {
            if (next && noFolders) return;
            void save(next ? true : enabled, roots, next);
          }}
        />
        {status?.cloud?.message ? <p className="providerHint" role="status">{status.cloud.message}</p> : null}
        {cloudOn && status?.cloud?.connectorUrl ? (
          <>
            <p className="agentStepHint">
              Add this address as a custom connector in ChatGPT, Claude, or Grok. The assistant asks you to sign in
              with your VERA account. Keep VERA open while you use it.
            </p>
            <CopyField label="Connector URL" value={status.cloud.connectorUrl} />
          </>
        ) : null}
        {cloudOn ? (
          <p className="mutedText">This computer: {status?.cloud.device.name || 'This computer'}</p>
        ) : null}
        {cloudOn && devices.length > 1 ? (
          <details className="providerAdvanced">
            <summary>Manage computers</summary>
            <div className="agentComputer">
              <span className="settingRowTitle">Rename this computer</span>
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
          </details>
        ) : null}
      </>
    );
  }

  function renderLocal() {
    return (
      <>
        <ToggleRow
          title="Let apps on this computer search these folders"
          description={noFolders
            ? 'Add a folder first.'
            : cloudOn
              ? 'Turning this off also pauses cloud assistants.'
              : 'Claude Desktop, Cursor, and other apps on this computer can search these folders while VERA is open.'}
          checked={enabled}
          disabled={busy || (!enabled && noFolders)}
          onChange={(next) => {
            if (next && noFolders) return;
            void save(next, roots);
          }}
        />
        {detail ? <p className="providerHint" role="status">{detail}</p> : null}
        <p className="agentStepHint">Pick the app, copy the snippet, and paste it where that app keeps its connections.</p>
        <div className="agentAppPicker" role="group" aria-label="Which app are you connecting?">
          {CONNECT_APPS.map((app) => (
            <button
              key={app.id}
              type="button"
              className="secondaryAction compactAction"
              aria-pressed={connectApp === app.id}
              onClick={() => setConnectApp(app.id)}
            >
              {app.label}
            </button>
          ))}
        </div>
        {selected.kind === 'ask' ? (
          <div className="agentAppPicker" role="group" aria-label="How does that app connect?">
            <button
              type="button"
              className="secondaryAction compactAction"
              aria-pressed={otherKind === 'http'}
              onClick={() => setOtherKind('http')}
            >
              Web address
            </button>
            <button
              type="button"
              className="secondaryAction compactAction"
              aria-pressed={otherKind === 'stdio'}
              onClick={() => setOtherKind('stdio')}
            >
              Command
            </button>
          </div>
        ) : null}
        <p className="agentStepHint">{snippetWhere}</p>
        <CopyField label="Setup snippet" value={snippetValue} emptyText={snippetEmpty} multiline />
        <details className="providerAdvanced">
          <summary>Advanced</summary>
          <CopyField
            label="HTTP snippet"
            value={enabled ? (status?.snippets.http || '') : ''}
            emptyText={snippetEmpty}
            multiline
          />
          <CopyField
            label="Stdio snippet"
            value={enabled ? (status?.snippets.stdio || '') : ''}
            emptyText={snippetEmpty}
            multiline
          />
          {status ? <p className="mutedText">Listening on port {status.port}.</p> : null}
          <div className="settingRow">
            <span className="settingRowText">
              <span className="settingRowTitle">Reset connection key</span>
              <span className="settingRowDescription">Use this if a snippet was shared by mistake. Apps you already set up need the new snippet.</span>
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
              Reset connection key
            </button>
          </div>
        </details>
      </>
    );
  }

  return (
    <div className="settingsStack">
      <div className="agentIntro">
        <p className="agentStatusLine">{accessSummary(enabled, cloudOn, roots.length)}</p>
        <p className="mutedText">{AGENT_SERVICE_NOTE}</p>
      </div>

      <SettingsCard>
        <ol className="agentSteps">
          <li className="agentStep">
            <span className="agentStepNumber" aria-hidden="true">1</span>
            <div className="agentStepBody">
              <div className="agentStepHead">
                <h5 className="agentStepTitle">Choose folders</h5>
                <button type="button" className="secondaryAction compactAction" disabled={busy} onClick={() => void addLibrary()}>
                  <FolderPlus size={14} />Add folder
                </button>
              </div>
              <p className="agentStepHint">AI can search only these folders. A short name is optional, for when you ask for one library.</p>
              {noFolders ? (
                <p className="mutedText">No folders yet. Add the folder that holds the documents you want AI to search.</p>
              ) : (
                <ul className="agentLibraryList">
                  {roots.map((root) => {
                    const error = nameErrors[root];
                    const editing = renaming === root;
                    return (
                      <li key={root}>
                        <Folder size={14} aria-hidden="true" />
                        {editing ? (
                          <input
                            className="agentLibraryName"
                            type="text"
                            aria-label={`Library name for ${root}`}
                            placeholder={fallbackName(root)}
                            spellCheck={false}
                            disabled={busy}
                            autoFocus
                            value={drafts[root] ?? names[root] ?? ''}
                            onChange={(event) => {
                              const value = event.target.value;
                              setDrafts((current) => ({ ...current, [root]: value }));
                              setNameErrors((current) => ({ ...current, [root]: '' }));
                            }}
                            onBlur={() => {
                              if (cancelRename.current) {
                                cancelRename.current = false;
                                return;
                              }
                              commitName(root);
                            }}
                            onKeyDown={(event) => {
                              if (event.key === 'Enter') {
                                event.preventDefault();
                                (event.target as HTMLInputElement).blur();
                              }
                              if (event.key === 'Escape') {
                                event.preventDefault();
                                cancelRename.current = true;
                                setDrafts((current) => {
                                  const copy = { ...current };
                                  delete copy[root];
                                  return copy;
                                });
                                setNameErrors((current) => ({ ...current, [root]: '' }));
                                setRenaming(null);
                              }
                            }}
                          />
                        ) : (
                          <span className="agentLibraryNameText">{displayName(root)}</span>
                        )}
                        <span className="agentLibraryPath" title={root}>{root}</span>
                        {error ? <span className="agentLibraryNameError">{error}</span> : null}
                        {editing ? null : (
                          <button
                            type="button"
                            className="settingsLink"
                            disabled={busy}
                            onClick={() => {
                              setRenaming(root);
                              setNameErrors((current) => ({ ...current, [root]: '' }));
                            }}
                          >
                            Rename
                          </button>
                        )}
                        <button
                          type="button"
                          className="secondaryAction compactAction"
                          disabled={busy}
                          onMouseDown={(event) => event.preventDefault()}
                          onClick={() => removeLibrary(root)}
                        >
                          Remove
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </li>

          <li className="agentStep">
            <span className="agentStepNumber" aria-hidden="true">2</span>
            <div className="agentStepBody">
              <h5 className="agentStepTitle">Where does your AI run?</h5>
              <div className="agentDestinations" role="group" aria-label="Where does your AI run?">
                <button
                  type="button"
                  className="agentDestination"
                  aria-pressed={destination === 'cloud'}
                  onClick={() => setDestination('cloud')}
                >
                  <Cloud size={18} aria-hidden="true" />
                  <span className="agentDestinationText">
                    <span className="agentDestinationTitle">
                      In the cloud
                      {cloudOn ? <StatusPill tone="good">On</StatusPill> : null}
                    </span>
                    <span className="agentDestinationDescription">ChatGPT, Claude, Grok, and other assistants you sign in to, on the web, desktop, or phone</span>
                  </span>
                </button>
                <button
                  type="button"
                  className="agentDestination"
                  aria-pressed={destination === 'local'}
                  onClick={() => setDestination('local')}
                >
                  <Laptop size={18} aria-hidden="true" />
                  <span className="agentDestinationText">
                    <span className="agentDestinationTitle">
                      On this computer
                      {enabled ? <StatusPill tone="good">On</StatusPill> : null}
                    </span>
                    <span className="agentDestinationDescription">Cursor, VS Code, Claude Desktop, and other apps that connect to VERA directly</span>
                  </span>
                </button>
              </div>
            </div>
          </li>

          <li className="agentStep">
            <span className="agentStepNumber" aria-hidden="true">3</span>
            <div className="agentStepBody">
              <h5 className="agentStepTitle">
                {destination === 'cloud' ? 'Connect a cloud assistant' : 'Connect an app on this computer'}
              </h5>
              {destination === 'cloud' ? renderCloud() : renderLocal()}
            </div>
          </li>
        </ol>
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
