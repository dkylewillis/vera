const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('vera', {
  request: (payload: Record<string, unknown>) => ipcRenderer.invoke('vera:request', payload),
  pickArchive: () => ipcRenderer.invoke('vera:pickArchive'),
  pickFolder: () => ipcRenderer.invoke('vera:pickFolder'),
  pickPdf: () => ipcRenderer.invoke('vera:pickPdf'),
  saveVera: (defaultPath?: string) => ipcRenderer.invoke('vera:saveVera', defaultPath),
  saveAny: () => ipcRenderer.invoke('vera:saveAny'),
});
