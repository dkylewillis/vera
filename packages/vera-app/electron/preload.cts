import type { AppSettings, Session, StreamEvent } from '../src/shared/contracts.js';
import { IPC_CHANNELS } from '../src/shared/protocol.js';

const { contextBridge, ipcRenderer } = require('electron');

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
