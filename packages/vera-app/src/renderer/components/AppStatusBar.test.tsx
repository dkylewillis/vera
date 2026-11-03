import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { AgentServiceStatus } from '../types';
import { AppStatusBar, cloudComputerIndicator } from './AppStatusBar';

function status(overrides: Partial<AgentServiceStatus> = {}, cloud: Partial<AgentServiceStatus['cloud']> = {}): AgentServiceStatus {
  return {
    state: 'running',
    enabled: true,
    libraryRoots: [],
    port: 7428,
    url: 'http://127.0.0.1:7428/mcp',
    connectFile: '',
    command: '',
    args: [],
    token: '',
    message: '',
    portChanged: false,
    cloudEnabled: true,
    snippets: { http: '', stdio: '', note: '' },
    cloud: {
      state: 'connected',
      message: 'Cloud agents can reach this computer.',
      connectorUrl: 'https://relay.example/mcp',
      device: { id: 'desk', name: 'Desk PC' },
      routing: { mode: 'auto' },
      current: 'desk',
      devices: [
        { id: 'desk', name: 'Desk PC', online: true, lastSeen: 0, appVersion: '' },
        { id: 'laptop', name: 'Office laptop', online: true, lastSeen: 0, appVersion: '' },
      ],
      ...cloud,
    },
    ...overrides,
  };
}

describe('cloudComputerIndicator', () => {
  it('stays hidden until cloud agents are on', () => {
    expect(cloudComputerIndicator(null)).toBeNull();
    expect(cloudComputerIndicator(status({ cloudEnabled: false }))).toBeNull();
    expect(cloudComputerIndicator(status({}, { state: 'off', message: '' }))).toBeNull();
  });

  it('names this computer while it is the one cloud agents use', () => {
    expect(cloudComputerIndicator(status())).toEqual({
      label: 'Desk PC',
      title: 'Cloud agents are using this computer (Desk PC).',
      tone: 'here',
    });
  });

  it('names the other computer while this one stands by', () => {
    const indicator = cloudComputerIndicator(status({}, {
      state: 'standby',
      current: 'laptop',
      message: 'Connected. Cloud agents are using Office laptop.',
    }));
    expect(indicator).toMatchObject({ label: 'Office laptop', tone: 'away' });
    expect(indicator?.title).toContain('Office laptop');
    expect(indicator?.title).toContain('standing by');
  });

  it('follows a pinned computer', () => {
    const indicator = cloudComputerIndicator(status({}, {
      state: 'standby',
      routing: { mode: 'pinned', pinned: 'laptop' },
      current: 'desk',
    }));
    expect(indicator?.label).toBe('Office laptop');
  });

  it('says standing by when this computer is asleep', () => {
    const indicator = cloudComputerIndicator(status({}, {
      state: 'standby',
      current: 'desk',
      message: 'This computer is asleep. Cloud agents will reconnect when it wakes.',
    }));
    expect(indicator).toMatchObject({
      label: 'Standing by',
      tone: 'pending',
      title: 'This computer is asleep. Cloud agents will reconnect when it wakes.',
    });
  });

  it('reports connecting and failures', () => {
    expect(cloudComputerIndicator(status({}, { state: 'connecting', message: 'Connecting to the VERA relay…' }))?.tone).toBe('pending');
    expect(cloudComputerIndicator(status({}, { state: 'error', message: 'Unable to reach the VERA relay.' }))).toMatchObject({
      label: 'Not connected',
      tone: 'error',
    });
  });
});

describe('AppStatusBar', () => {
  it('shows the connected computer on the right and keeps Ready', () => {
    const html = renderToStaticMarkup(
      <AppStatusBar tasks={[]} agentStatus={status()} onOpenCloudAgents={() => undefined} />,
    );
    expect(html).toContain('Ready');
    expect(html).toContain('Desk PC');
    expect(html).toContain('Cloud agents are using this computer (Desk PC).');
    expect(html).toContain('appStatusCloud--here');
  });

  it('omits the computer when cloud agents are off', () => {
    const html = renderToStaticMarkup(<AppStatusBar tasks={[]} agentStatus={status({ cloudEnabled: false })} />);
    expect(html).toContain('Ready');
    expect(html).not.toContain('appStatusCloud');
  });
});
