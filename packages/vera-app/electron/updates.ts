import { app, dialog } from 'electron';
import electronUpdater from 'electron-updater';

const { autoUpdater } = electronUpdater;

let configured = false;

/** Check GitHub Releases for a signed installer. No-op in an unpackaged checkout. */
export function configureAutoUpdate(): void {
  if (configured || !app.isPackaged) return;
  configured = true;
  autoUpdater.autoDownload = true;
  autoUpdater.on('error', (error) => {
    console.error('[vera-update]', error instanceof Error ? error.message : error);
  });
  void autoUpdater.checkForUpdatesAndNotify().catch((error) => {
    console.error('[vera-update]', error instanceof Error ? error.message : error);
  });
}

export async function checkForUpdatesManually(): Promise<void> {
  if (!app.isPackaged) {
    await dialog.showMessageBox({
      type: 'info',
      title: 'Updates',
      message: 'Update checks run in the installed Windows app.',
      detail: 'Development checkouts stay on the version you are running.',
    });
    return;
  }
  configureAutoUpdate();
  try {
    const result = await autoUpdater.checkForUpdates();
    const current = app.getVersion();
    const next = result?.updateInfo?.version;
    if (!next || next === current) {
      await dialog.showMessageBox({
        type: 'info',
        title: 'Updates',
        message: `VERA ${current} is up to date.`,
      });
      return;
    }
    await dialog.showMessageBox({
      type: 'info',
      title: 'Updates',
      message: `VERA ${next} is downloading.`,
      detail: 'Restart VERA when the download finishes to install it.',
    });
  } catch (error) {
    await dialog.showMessageBox({
      type: 'error',
      title: 'Updates',
      message: 'Unable to check for updates.',
      detail: error instanceof Error ? error.message : 'Unknown update error',
    });
  }
}
