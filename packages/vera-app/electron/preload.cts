import type { AppSettings, Session, StreamEvent } from '../src/shared/contracts.js';
import type { IPC_CHANNELS as IpcChannels } from '../src/shared/protocol.js';

const { contextBridge, ipcRenderer } = require('electron');

/**
 * Duplicated from protocol.ts's IPC_CHANNELS (kept in sync by
 * protocol-contract.test.ts) rather than imported. Electron's sandboxed
 * preload uses its own restricted `require`, which cannot load protocol.ts's
 * compiled ES module output, or resolve a sibling JSON/CommonJS file by
 * relative path; only this preload script's own bundle is available.
 */
const IPC_CHANNELS: typeof IpcChannels = {
  showMenu: 'vera:showMenu',
  request: 'vera:request',
  cancelAnswer: 'vera:cancelAnswer',
  cancelRequest: 'vera:cancelRequest',
  skipConversion: 'vera:skipConversion',
  getSettings: 'vera:getSettings',
  saveSettings: 'vera:saveSettings',
  saveApiKey: 'vera:saveApiKey',
  clearApiKey: 'vera:clearApiKey',
  saveHfToken: 'vera:saveHfToken',
  clearHfToken: 'vera:clearHfToken',
  getSessions: 'vera:getSessions',
  saveSession: 'vera:saveSession',
  deleteSession: 'vera:deleteSession',
  listModes: 'vera:listModes',
  openModesFolder: 'vera:openModesFolder',
  pickArchive: 'vera:pickArchive',
  pickFolder: 'vera:pickFolder',
  listFolder: 'vera:listFolder',
  pathExists: 'vera:pathExists',
  showInFolder: 'vera:showInFolder',
  trashWorkspaceFile: 'vera:trashWorkspaceFile',
  setWatchedFolders: 'vera:setWatchedFolders',
  pickPdf: 'vera:pickPdf',
  saveAny: 'vera:saveAny',
  openTarget: 'vera:openTarget',
  openSettings: 'vera:openSettings',
  folderChanged: 'vera:folderChanged',
  answerEvent: 'vera:answerEvent',
};

contextBridge.exposeInMainWorld('vera', {
  platform: process.platform,
  showMenu: (menuId: string, x: number, y: number) => ipcRenderer.invoke(IPC_CHANNELS.showMenu, menuId, x, y),
  request: (payload: Record<string, unknown>, requestId?: string) => ipcRenderer.invoke(IPC_CHANNELS.request, payload, requestId),
  cancelAnswer: (requestId: string) => ipcRenderer.invoke(IPC_CHANNELS.cancelAnswer, requestId),
  cancelRequest: (requestId: string) => ipcRenderer.invoke(IPC_CHANNELS.cancelRequest, requestId),
  skipConversion: (requestId: string) => ipcRenderer.invoke(IPC_CHANNELS.skipConversion, requestId),
  getSettings: () => ipcRenderer.invoke(IPC_CHANNELS.getSettings),
  saveSettings: (settings: AppSettings) => ipcRenderer.invoke(IPC_CHANNELS.saveSettings, settings),
  saveApiKey: (providerId: string, apiKey: string) => ipcRenderer.invoke(IPC_CHANNELS.saveApiKey, providerId, apiKey),
  clearApiKey: (providerId: string) => ipcRenderer.invoke(IPC_CHANNELS.clearApiKey, providerId),
  saveHfToken: (token: string) => ipcRenderer.invoke(IPC_CHANNELS.saveHfToken, token),
  clearHfToken: () => ipcRenderer.invoke(IPC_CHANNELS.clearHfToken),
  getSessions: () => ipcRenderer.invoke(IPC_CHANNELS.getSessions),
  saveSession: (session: Session) => ipcRenderer.invoke(IPC_CHANNELS.saveSession, session),
  deleteSession: (id: string) => ipcRenderer.invoke(IPC_CHANNELS.deleteSession, id),
  listModes: () => ipcRenderer.invoke(IPC_CHANNELS.listModes),
  openModesFolder: () => ipcRenderer.invoke(IPC_CHANNELS.openModesFolder),
  pickArchive: () => ipcRenderer.invoke(IPC_CHANNELS.pickArchive),
  pickFolder: () => ipcRenderer.invoke(IPC_CHANNELS.pickFolder),
  listFolder: (dir: string) => ipcRenderer.invoke(IPC_CHANNELS.listFolder, dir),
  pathExists: (targetPath: string) => ipcRenderer.invoke(IPC_CHANNELS.pathExists, targetPath),
  showInFolder: (targetPath: string) => ipcRenderer.invoke(IPC_CHANNELS.showInFolder, targetPath),
  trashWorkspaceFile: (filePath: string, folderPath: string) => ipcRenderer.invoke(IPC_CHANNELS.trashWorkspaceFile, filePath, folderPath),
  setWatchedFolders: (paths: string[]) => ipcRenderer.invoke(IPC_CHANNELS.setWatchedFolders, paths),
  pickPdf: () => ipcRenderer.invoke(IPC_CHANNELS.pickPdf),
  saveAny: () => ipcRenderer.invoke(IPC_CHANNELS.saveAny),
  onOpenTarget: (callback: (path: string) => void) => {
    const listener = (_event: unknown, path: string) => callback(path);
    ipcRenderer.on(IPC_CHANNELS.openTarget, listener);
    return () => ipcRenderer.removeListener(IPC_CHANNELS.openTarget, listener);
  },
  onOpenSettings: (callback: () => void) => {
    const listener = () => callback();
    ipcRenderer.on(IPC_CHANNELS.openSettings, listener);
    return () => ipcRenderer.removeListener(IPC_CHANNELS.openSettings, listener);
  },
  onFolderChanged: (callback: (path: string) => void) => {
    const listener = (_event: unknown, path: string) => callback(path);
    ipcRenderer.on(IPC_CHANNELS.folderChanged, listener);
    return () => ipcRenderer.removeListener(IPC_CHANNELS.folderChanged, listener);
  },
  onAnswerEvent: (callback: (data: StreamEvent) => void) => {
    const listener = (_event: unknown, data: StreamEvent) => callback(data);
    ipcRenderer.on(IPC_CHANNELS.answerEvent, listener);
    return () => ipcRenderer.removeListener(IPC_CHANNELS.answerEvent, listener);
  },
});
