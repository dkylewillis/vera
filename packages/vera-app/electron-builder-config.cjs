/**
 * electron-builder configuration helpers.
 * Azure Trusted Signing is applied only when the release environment supplies
 * every required variable, so local and CI builds without a certificate still pack.
 */

function buildConfig(env = process.env) {
  const pkg = require('./package.json');
  const config = structuredClone(pkg.build);
  const ready = Boolean(
    env.AZURE_TENANT_ID
    && env.AZURE_CLIENT_ID
    && env.AZURE_CLIENT_SECRET
    && env.AZURE_SIGN_ENDPOINT
    && env.AZURE_SIGN_PROFILE
    && env.AZURE_SIGN_ACCOUNT,
  );
  if (!config.win) config.win = {};
  if (ready) {
    config.win.azureSignOptions = {
      publisherName: env.AZURE_SIGN_PUBLISHER || 'VERA',
      endpoint: env.AZURE_SIGN_ENDPOINT,
      certificateProfileName: env.AZURE_SIGN_PROFILE,
      codeSigningAccountName: env.AZURE_SIGN_ACCOUNT,
    };
    // Sign the app executable and PyInstaller sidecar binaries under extraResources.
    config.win.signExts = ['.exe', '.dll'];
  } else {
    delete config.win.azureSignOptions;
  }
  return config;
}

module.exports = { buildConfig };
