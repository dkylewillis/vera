import { createRequire } from 'node:module';
import { describe, expect, it } from 'vitest';

const require = createRequire(import.meta.url);
const { buildConfig } = require('../electron-builder-config.cjs') as {
  buildConfig: (env: NodeJS.ProcessEnv) => {
    win?: { azureSignOptions?: { endpoint?: string }; signExts?: string[] };
    protocols?: { schemes: string[] }[];
    publish?: { provider: string; owner: string; repo: string }[];
  };
};

describe('electron-builder config', () => {
  it('drops placeholder Azure signing unless release credentials are present', () => {
    const config = buildConfig({});
    expect(config.win?.azureSignOptions).toBeUndefined();
    expect(config.protocols?.[0]?.schemes).toContain('vera');
    expect(config.publish?.[0]).toMatchObject({ provider: 'github', owner: 'dkylewillis', repo: 'vera' });
  });

  it('signs exe and dll sidecar binaries when Azure credentials are set', () => {
    const config = buildConfig({
      AZURE_TENANT_ID: 'tenant',
      AZURE_CLIENT_ID: 'client',
      AZURE_CLIENT_SECRET: 'secret',
      AZURE_SIGN_ENDPOINT: 'https://eus.codesigning.azure.net/',
      AZURE_SIGN_PROFILE: 'VERADesktop',
      AZURE_SIGN_ACCOUNT: 'vera-signing',
      AZURE_SIGN_PUBLISHER: 'VERA',
    });
    expect(config.win?.azureSignOptions).toMatchObject({
      publisherName: 'VERA',
      endpoint: 'https://eus.codesigning.azure.net/',
      certificateProfileName: 'VERADesktop',
      codeSigningAccountName: 'vera-signing',
    });
    expect(config.win?.signExts).toEqual(['.exe', '.dll']);
  });
});
