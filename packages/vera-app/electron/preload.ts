const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('vera', {
  request: (payload: Record<string, unknown>) => ipcRenderer.invoke('vera:request', payload),
  getSettings: () => ipcRenderer.invoke('vera:getSettings'),
  saveSettings: (settings: Record<string, unknown>) => ipcRenderer.invoke('vera:saveSettings', settings),
  saveApiKey: (providerId: string, apiKey: string) => ipcRenderer.invoke('vera:saveApiKey', providerId, apiKey),
  clearApiKey: (providerId: string) => ipcRenderer.invoke('vera:clearApiKey', providerId),
  getSessions: () => ipcRenderer.invoke('vera:getSessions'),
  saveSession: (session: Record<string, unknown>) => ipcRenderer.invoke('vera:saveSession', session),
  deleteSession: (id: string) => ipcRenderer.invoke('vera:deleteSession', id),
  listModes: () => ipcRenderer.invoke('vera:listModes'),
  openModesFolder: () => ipcRenderer.invoke('vera:openModesFolder'),
  pickArchive: () => ipcRenderer.invoke('vera:pickArchive'),
  pickFolder: () => ipcRenderer.invoke('vera:pickFolder'),
  listFolder: (dir: string) => ipcRenderer.invoke('vera:listFolder', dir),
  setWatchedFolders: (paths: string[]) => ipcRenderer.invoke('vera:setWatchedFolders', paths),
  pickPdf: () => ipcRenderer.invoke('vera:pickPdf'),
  saveVera: (defaultPath?: string) => ipcRenderer.invoke('vera:saveVera', defaultPath),
  saveAny: () => ipcRenderer.invoke('vera:saveAny'),
  onOpenTarget: (callback: (path: string) => void) => {
    const listener = (_event: unknown, path: string) => callback(path);
    ipcRenderer.on('vera:openTarget', listener);
    return () => ipcRenderer.removeListener('vera:openTarget', listener);
  },
  onOpenSettings: (callback: () => void) => {
    const listener = () => callback();
    ipcRenderer.on('vera:openSettings', listener);
    return () => ipcRenderer.removeListener('vera:openSettings', listener);
  },
  onFolderChanged: (callback: (path: string) => void) => {
    const listener = (_event: unknown, path: string) => callback(path);
    ipcRenderer.on('vera:folderChanged', listener);
    return () => ipcRenderer.removeListener('vera:folderChanged', listener);
  },
  onAnswerEvent: (callback: (data: Record<string, unknown>) => void) => {
    const listener = (_event: unknown, data: Record<string, unknown>) => callback(data);
    ipcRenderer.on('vera:answerEvent', listener);
    return () => ipcRenderer.removeListener('vera:answerEvent', listener);
  },
});
