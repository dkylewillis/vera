const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('vera', {
  request: (payload: Record<string, unknown>) => ipcRenderer.invoke('vera:request', payload),
  pickArchive: () => ipcRenderer.invoke('vera:pickArchive'),
  pickFolder: () => ipcRenderer.invoke('vera:pickFolder'),
  pickPdf: () => ipcRenderer.invoke('vera:pickPdf'),
  saveVera: (defaultPath?: string) => ipcRenderer.invoke('vera:saveVera', defaultPath),
  saveAny: () => ipcRenderer.invoke('vera:saveAny'),
  onOpenTarget: (callback: (path: string) => void) => {
    const listener = (_event: unknown, path: string) => callback(path);
    ipcRenderer.on('vera:openTarget', listener);
    return () => ipcRenderer.removeListener('vera:openTarget', listener);
  },
});
