import { Settings, User } from 'lucide-react';
import type { ProAccount } from '../../shared/pro';
import { useProAccount } from '../lib/proAccount';

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

export function sidebarAccountLabel(account: Pick<ProAccount, 'signedIn' | 'email'>): string {
  return account.signedIn && account.email.trim() ? account.email.trim() : 'Sign in';
}

export function sidebarAccountInitial(email: string): string {
  const letter = email.trim().charAt(0).toUpperCase();
  return letter || '?';
}

export function SidebarAccount({
  collapsed,
  onOpenAccount,
  onOpenSettings,
}: {
  collapsed: boolean;
  onOpenAccount: () => void;
  onOpenSettings: () => void;
}) {
  const account = useProAccount() ?? EMPTY_ACCOUNT;

  const label = sidebarAccountLabel(account);
  const pro = account.subscriptionStatus === 'active' || account.subscriptionStatus === 'trialing';
  const title = account.signedIn
    ? `${account.email}${pro ? ' · Pro' : ''}`
    : 'Sign in to VERA Pro';

  async function openIdentity() {
    if (account.signedIn || !account.configured) {
      onOpenAccount();
      return;
    }
    const result = await window.vera.proSignIn();
    if (!result.ok) onOpenAccount();
  }

  return (
    <div className={collapsed ? 'sideAccount sideAccount--collapsed' : 'sideAccount'}>
      <button
        type="button"
        className="sideAccountIdentity"
        title={title}
        aria-label={title}
        onClick={() => { void openIdentity(); }}
      >
        <span className="sideAccountAvatar" aria-hidden="true">
          {account.signedIn ? sidebarAccountInitial(account.email) : <User size={13} />}
        </span>
        {collapsed ? null : <span className="sideAccountLabel">{label}</span>}
      </button>
      {collapsed || !pro ? null : <span className="sideAccountPro">Pro</span>}
      <button
        type="button"
        className="ghostIcon sideAccountSettings"
        title="Settings"
        aria-label="Settings"
        onClick={onOpenSettings}
      >
        <Settings size={15} />
      </button>
    </div>
  );
}
