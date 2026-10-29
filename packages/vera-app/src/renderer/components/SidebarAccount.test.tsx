import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { SidebarAccount, sidebarAccountInitial, sidebarAccountLabel } from './SidebarAccount';

describe('SidebarAccount', () => {
  it('shows Sign in and Settings before an account is loaded', () => {
    const html = renderToStaticMarkup(
      <SidebarAccount collapsed={false} onOpenAccount={() => undefined} onOpenSettings={() => undefined} />,
    );
    expect(html).toContain('Sign in');
    expect(html).toContain('Settings');
    expect(html).not.toContain('sideAccountPro');
  });

  it('keeps the identity button when the sidebar is collapsed', () => {
    const html = renderToStaticMarkup(
      <SidebarAccount collapsed onOpenAccount={() => undefined} onOpenSettings={() => undefined} />,
    );
    expect(html).toContain('sideAccount--collapsed');
    expect(html).toContain('Sign in to VERA Pro');
    expect(html).toContain('Settings');
    expect(html).not.toContain('sideAccountLabel');
  });

  it('uses the email as the signed-in label and its first letter as the mark', () => {
    expect(sidebarAccountLabel({ signedIn: true, email: 'kyle@example.com' })).toBe('kyle@example.com');
    expect(sidebarAccountLabel({ signedIn: false, email: 'kyle@example.com' })).toBe('Sign in');
    expect(sidebarAccountInitial('kyle@example.com')).toBe('K');
  });
});
