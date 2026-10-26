import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { DESKTOP_DEFAULT_EMBEDDING_MODEL } from '../src/shared/desktop-defaults.js';

import {
  createPkcePair,
  exchangeDesktopCode,
  mergeProCloudConfig,
  proCloudConfigFromEnv,
  proCloudConfigFromFile,
  proSignInUrl,
} from './pro-account.js';

describe('desktop embedding default', () => {
  it('matches the sidecar fallback', () => {
    const convertPy = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), '../src/vera_app/convert.py'),
      'utf8',
    );
    expect(convertPy).toContain(
      `DEFAULT_DESKTOP_EMBEDDING_MODEL = "${DESKTOP_DEFAULT_EMBEDDING_MODEL}"`,
    );
  });
});

describe('pro cloud config', () => {
  it('lets environment values override a packaged file', () => {
    const merged = mergeProCloudConfig(
      proCloudConfigFromFile({
        siteUrl: 'https://files.example/app/',
        supabaseUrl: 'https://files.supabase.co',
        supabaseAnonKey: 'file-key',
      }),
      proCloudConfigFromEnv({
        VERA_PRO_SITE_URL: 'https://env.example',
        VERA_PRO_SUPABASE_URL: '',
        VERA_PRO_SUPABASE_ANON_KEY: 'env-key',
      }),
    );
    expect(merged).toEqual({
      siteUrl: 'https://env.example',
      supabaseUrl: 'https://files.supabase.co',
      supabaseAnonKey: 'env-key',
    });
  });

  it('builds a PKCE sign-in URL whose challenge matches the verifier', () => {
    const pair = createPkcePair();
    const challenge = createHash('sha256').update(pair.verifier).digest('base64url');
    expect(pair.challenge).toBe(challenge);
    const url = new URL(proSignInUrl({
      siteUrl: 'https://pro.example',
      supabaseUrl: 'https://project.supabase.co',
      supabaseAnonKey: 'anon',
    }, pair.challenge, pair.state));
    expect(url.pathname).toBe('/login.html');
    expect(url.searchParams.get('code_challenge')).toBe(pair.challenge);
    expect(url.searchParams.get('state')).toBe(pair.state);
  });
});

describe('desktop code exchange', () => {
  it('stores the session returned by desktop-exchange', async () => {
    const session = await exchangeDesktopCode({
      siteUrl: 'https://pro.example',
      supabaseUrl: 'https://project.supabase.co',
      supabaseAnonKey: 'anon',
    }, { code: 'code', code_verifier: 'verifier', state: 'state' }, (async () => new Response(JSON.stringify({
      access_token: 'access',
      refresh_token: 'refresh',
      expires_in: 3600,
      user: { id: 'user-1', email: 'a@example.com' },
    }), { status: 200 })) as typeof fetch);
    expect(session.email).toBe('a@example.com');
    expect(session.user_id).toBe('user-1');
    expect(session.access_token).toBe('access');
    expect(session.expires_at).toBeGreaterThan(Date.now());
  });

  it('surfaces the function error message', async () => {
    await expect(exchangeDesktopCode({
      siteUrl: 'https://pro.example',
      supabaseUrl: 'https://project.supabase.co',
      supabaseAnonKey: 'anon',
    }, { code: 'code', code_verifier: 'verifier', state: 'state' }, (async () => new Response(JSON.stringify({
      error: 'Sign-in link expired.',
    }), { status: 400 })) as typeof fetch)).rejects.toThrow('Sign-in link expired.');
  });
});
