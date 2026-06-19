import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('vera', {
  request: (payload: Record<string, unknown>) => ipcRenderer.invoke('vera:request', payload),
  pickArchive: () => ipcRenderer.invoke('vera:pickArchive'),
  pickFolder: () => ipcRenderer.invoke('vera:pickFolder'),
  pickPdf: () => ipcRenderer.invoke('vera:pickPdf'),
  saveVera: () => ipcRenderer.invoke('vera:saveVera'),
  saveAny: () => ipcRenderer.invoke('vera:saveAny'),
});
