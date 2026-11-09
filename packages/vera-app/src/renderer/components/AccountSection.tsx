import { useState } from 'react';
import { UserRound } from 'lucide-react';
import { includedUsagePercent, onDemandLabel, subscriptionActive, type ProAccount } from '../../shared/pro';
import { canLoadProAccount, publishProAccount, useProAccount } from '../lib/proAccount';
import { Callout, SettingsCard, StatusPill, UsageMeter, type PillTone } from './SettingsWidgets';

const EMPTY_ACCOUNT: ProAccount = {
  configured: false,
  siteUrl: '',
  signedIn: false,
  email: '',
  subscriptionStatus: '',
  agentAccessStatus: '',
  hasProKey: false,
  usageUsd: null,
  limitUsd: null,
  remainingUsd: null,
  includedPercent: null,
  onDemandEnabled: false,
  onDemandUsedUsd: null,
  onDemandLimitUsd: null,
};

const SUBSCRIPTION_LABELS: Record<string, { label: string; tone: PillTone }> = {
  active: { label: 'Pro', tone: 'accent' },
  trialing: { label: 'Pro trial', tone: 'accent' },
  past_due: { label: 'Payment due', tone: 'warn' },
  paused: { label: 'Paused', tone: 'warn' },
  canceled: { label: 'Canceled', tone: 'neutral' },
};

export function AccountSection({ onChanged }: { onChanged: () => Promise<void> }) {
  const knownAccount = useProAccount();
  const loaded = knownAccount !== null || !canLoadProAccount();
  const account = knownAccount ?? EMPTY_ACCOUNT;
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<{ ok: boolean; error?: string; account?: ProAccount }>) {
    setBusy(true);
    setMessage('');
    try {
      const result = await action();
      if (result.account) publishProAccount(result.account);
      if (!result.ok) setMessage(result.error || 'VERA Pro request failed.');
      else if (result.account?.error) setMessage(result.account.error);
      await onChanged();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'VERA Pro request failed.');
    } finally {
      setBusy(false);
    }
  }

  const subscribed = ['active', 'trialing', 'past_due', 'paused'].includes(account.subscriptionStatus);
  const included = includedUsagePercent(account);
  let pill: { label: string; tone: PillTone } = { label: 'Signed out', tone: 'neutral' };
  if (!account.configured) pill = { label: 'Unavailable', tone: 'neutral' };
  else if (account.signedIn) pill = SUBSCRIPTION_LABELS[account.subscriptionStatus] ?? { label: 'No subscription', tone: 'neutral' };

  const details: string[] = [];
  if (account.signedIn && !subscriptionActive(account.subscriptionStatus)) {
    details.push('Subscribe to use VERA Pro models in Chat.');
  }
  if (account.hasProKey) details.push('The Pro key is saved on this computer.');
  if (!account.signedIn && account.configured) details.push('Sign in to use VERA Pro for Chat without your own API key.');

  return (
    <div className="settingsStack">
      {loaded ? (
        <SettingsCard
          className="accountCard"
          icon={account.signedIn && account.email
            ? <span className="accountAvatar">{account.email.trim().charAt(0).toUpperCase()}</span>
            : <UserRound size={18} />}
          title={account.signedIn ? account.email || 'Signed in' : 'Not signed in'}
          badge={<StatusPill tone={pill.tone}>{pill.label}</StatusPill>}
          description={details.join(' ') || undefined}
          actions={(
            <>
              {account.signedIn ? (
                <button type="button" className="secondaryAction compactAction" disabled={busy} onClick={() => void run(() => window.vera.proSignOut())}>
                  Sign out
                </button>
              ) : (
                <button type="button" className="primaryAction compactAction" disabled={busy} onClick={() => void run(() => window.vera.proSignIn())}>
                  Sign in
                </button>
              )}
              {subscribed ? (
                <button type="button" className="secondaryAction compactAction" disabled={busy} onClick={() => void run(() => window.vera.proOpenPage('account'))}>
                  Manage subscription
                </button>
              ) : (
                <button type="button" className="secondaryAction compactAction" disabled={busy} onClick={() => void run(() => window.vera.proOpenPage('pricing'))}>
                  Get VERA Pro
                </button>
              )}
            </>
          )}
        >
          {account.signedIn && included !== null ? (
            <UsageMeter
              label="Included usage this month"
              percent={included}
              detail={`On-demand usage: ${onDemandLabel(account)}`}
            />
          ) : null}
        </SettingsCard>
      ) : null}
      {loaded && !account.configured ? (
        <Callout tone="warn" title="This build is not connected to VERA Pro.">
          <p>Add VERA_PRO_SITE_URL, VERA_PRO_SUPABASE_URL, and VERA_PRO_SUPABASE_ANON_KEY to the repo .env, or package pro-cloud.json.</p>
        </Callout>
      ) : null}
      {message ? <Callout tone="warn">{message}</Callout> : null}
      <p className="settingsNote">
        VERA Pro sends chat questions and retrieved passages to OpenRouter and the model provider you pick.
        Search stays on this computer. Signing out leaves a saved Pro key in place until you clear it.
      </p>
    </div>
  );
}
