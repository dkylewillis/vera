import { useState } from 'react';
import { includedUsagePercent, onDemandLabel, type ProAccount } from '../../shared/pro';
import { canLoadProAccount, publishProAccount, useProAccount } from '../lib/proAccount';

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

  const status = account.subscriptionStatus || (account.signedIn ? 'signed in' : 'signed out');
  const subscribed = ['active', 'trialing', 'past_due', 'paused'].includes(account.subscriptionStatus);
  const included = includedUsagePercent(account);
  const usage = included === null ? '' : `Included usage ${included}% · On demand ${onDemandLabel(account)}`;

  return (
    <div className="settingsForm">
      <p className="providerItemDescription">
        VERA Pro sends Ask questions and retrieved passages to OpenRouter and the model provider you pick.
        Search stays on this computer. Signing out leaves a saved Pro key in place until you clear it.
      </p>
      {loaded ? (
        <>
          {!account.configured ? (
            <p className="mutedText">
              This build is not connected to VERA Pro. Set VERA_PRO_SITE_URL, VERA_PRO_SUPABASE_URL, and VERA_PRO_SUPABASE_ANON_KEY, or package pro-cloud.json.
            </p>
          ) : (
            <p className="mutedText">
              {account.email ? `${account.email} · ` : ''}
              {status}
              {account.hasProKey ? ' · key saved' : ''}
              {usage ? ` · ${usage}` : ''}
            </p>
          )}
          <div className="editorActions">
            {account.signedIn ? (
              <button type="button" className="secondaryAction" disabled={busy} onClick={() => void run(() => window.vera.proSignOut())}>
                Sign out
              </button>
            ) : (
              <button type="button" className="secondaryAction" disabled={busy} onClick={() => void run(() => window.vera.proSignIn())}>
                Sign in
              </button>
            )}
            {subscribed ? (
              <button type="button" className="secondaryAction" disabled={busy} onClick={() => void run(() => window.vera.proOpenPage('account'))}>
                Manage subscription
              </button>
            ) : (
              <button type="button" className="secondaryAction" disabled={busy} onClick={() => void run(() => window.vera.proOpenPage('pricing'))}>
                Get VERA Pro
              </button>
            )}
          </div>
        </>
      ) : null}
      {message ? <p className="modalMessage">{message}</p> : null}
    </div>
  );
}
