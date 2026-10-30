import { useEffect, useState } from 'react';
import { Settings, User } from 'lucide-react';
import type { ProAccount } from '../../shared/pro';

const EMPTY_ACCOUNT: ProAccount = {
  configured: false,
  siteUrl: '',
  signedIn: false,
  email: '',
  subscriptionStatus: '',
  hasProKey: false,
  usageUsd: null,
  limitUsd: null,
  remainingUsd: null,
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
  const [account, setAccount] = useState<ProAccount>(EMPTY_ACCOUNT);

  useEffect(() => {
    const api = typeof window !== 'undefined' ? window.vera : undefined;
    if (!api?.proGetAccount) return undefined;
    let cancelled = false;
    void api.proGetAccount().then((next) => {
      if (!cancelled) setAccount(next);
    });
    const unsubscribe = api.onProAccountChanged?.((next) => setAccount(next));
    return () => {
      cancelled = true;
      unsubscribe?.();
    };
  }, []);

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
