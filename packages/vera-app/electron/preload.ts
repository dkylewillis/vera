import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('vera', {
  request: (payload: Record<string, unknown>) => ipcRenderer.invoke('vera:request', payload),
});
