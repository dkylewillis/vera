import { createRequire } from 'node:module';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const { applyEnvText, loadRepoEnv } = createRequire(import.meta.url)(
  join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'scripts', 'load-dotenv.cjs'),
) as {
  applyEnvText: (env: NodeJS.ProcessEnv, text: string) => NodeJS.ProcessEnv;
  loadRepoEnv: (env: NodeJS.ProcessEnv, root: string) => NodeJS.ProcessEnv;
};

describe('repo dotenv', () => {
  it('fills empty keys and keeps a shell value', () => {
    const env: NodeJS.ProcessEnv = { VERA_PRO_SITE_URL: 'https://shell.example' };
    applyEnvText(env, `
      # comment
      VERA_PRO_SITE_URL=https://file.example
      export VERA_PRO_SUPABASE_URL="https://project.supabase.co"
      VERA_PRO_SUPABASE_ANON_KEY=
      VERA_PRO_RELAY_URL='https://relay.example'
    `);
    expect(env.VERA_PRO_SITE_URL).toBe('https://shell.example');
    expect(env.VERA_PRO_SUPABASE_URL).toBe('https://project.supabase.co');
    expect(env.VERA_PRO_SUPABASE_ANON_KEY).toBeUndefined();
    expect(env.VERA_PRO_RELAY_URL).toBe('https://relay.example');
  });

  it('reads .env from a directory', () => {
    const root = mkdtempSync(join(tmpdir(), 'vera-dotenv-'));
    writeFileSync(join(root, '.env'), 'VERA_PRO_SITE_URL=https://veradoc.si\n');
    const env: NodeJS.ProcessEnv = {};
    loadRepoEnv(env, root);
    expect(env.VERA_PRO_SITE_URL).toBe('https://veradoc.si');
  });
});
