import { app, BrowserWindow, dialog, ipcMain } from 'electron';
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { delimiter, join } from 'node:path';
import { fileURLToPath } from 'node:url';

interface SidecarRequest {
  id?: string;
  action: string;
  [key: string]: unknown;
}

interface SidecarPayload {
  action: string;
  [key: string]: unknown;
}

interface SidecarResponse {
  id?: string;
  ok: boolean;
  result?: unknown;
  error?: string;
  traceback?: string;
}

class PythonSidecar {
  private child: ChildProcessWithoutNullStreams | null = null;
  private pending = new Map<string, { resolve: (value: SidecarResponse) => void; reject: (reason?: unknown) => void }>();
  private nextId = 1;
  private stdoutBuffer = '';

  request(payload: SidecarPayload): Promise<SidecarResponse> {
    const child = this.ensureStarted();
    const id = String(this.nextId++);
    const message: SidecarRequest = { ...payload, id };
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      child.stdin.write(`${JSON.stringify(message)}\n`, (error) => {
        if (error) {
          this.pending.delete(id);
          reject(error);
        }
      });
    });
  }

  stop(): void {
    if (this.child) {
      this.child.kill();
      this.child = null;
    }
    for (const entry of this.pending.values()) {
      entry.reject(new Error('VERA sidecar stopped'));
    }
    this.pending.clear();
  }

  private ensureStarted(): ChildProcessWithoutNullStreams {
    if (this.child) {
      return this.child;
    }

    const python = process.env.VERA_APP_PYTHON || 'python';
    const env = { ...process.env };
    const sourcePaths = [join(process.cwd(), 'src'), join(process.cwd(), '..', 'vera-doc', 'src')];
    env.PYTHONPATH = [sourcePaths.join(delimiter), env.PYTHONPATH || ''].filter(Boolean).join(delimiter);

    this.child = spawn(python, ['-m', 'vera_app.sidecar'], {
      cwd: process.cwd(),
      env,
    });

    this.child.stdout.on('data', (chunk: Buffer) => this.handleStdout(chunk.toString('utf8')));
    this.child.stderr.on('data', (chunk: Buffer) => console.error(`[vera-sidecar] ${chunk.toString('utf8')}`));
    this.child.on('exit', () => {
      this.child = null;
      for (const entry of this.pending.values()) {
        entry.reject(new Error('VERA sidecar exited'));
      }
      this.pending.clear();
    });

    return this.child;
  }

  private handleStdout(data: string): void {
    this.stdoutBuffer += data;
    const lines = this.stdoutBuffer.split('\n');
    this.stdoutBuffer = lines.pop() || '';
    for (const line of lines) {
      if (!line.trim()) {
        continue;
      }
      const response = JSON.parse(line) as SidecarResponse;
      if (!response.id) {
        continue;
      }
      const pending = this.pending.get(response.id);
      if (!pending) {
        continue;
      }
      this.pending.delete(response.id);
      pending.resolve(response);
    }
  }
}

const sidecar = new PythonSidecar();

function createWindow(): void {
  const preload = fileURLToPath(new URL('./preload.js', import.meta.url));
  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 980,
    minHeight: 660,
    title: 'VERA',
    backgroundColor: '#f3f1ec',
    webPreferences: {
      preload,
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (app.isPackaged) {
    win.loadFile(join(process.cwd(), 'dist', 'index.html'));
  } else {
    win.loadURL('http://127.0.0.1:5173');
  }
}

app.whenReady().then(() => {
  ipcMain.handle('vera:request', async (_event, payload: SidecarPayload) => sidecar.request(payload));
  ipcMain.handle('vera:pickArchive', async () => {
    const result = await dialog.showOpenDialog({
      title: 'Open VERA archive',
      properties: ['openFile'],
      filters: [{ name: 'VERA Archives', extensions: ['vera'] }],
    });
    return result.canceled ? null : result.filePaths[0];
  });
  ipcMain.handle('vera:pickFolder', async () => {
    const result = await dialog.showOpenDialog({
      title: 'Open VERA library folder',
      properties: ['openDirectory'],
    });
    return result.canceled ? null : result.filePaths[0];
  });
  ipcMain.handle('vera:pickPdf', async () => {
    const result = await dialog.showOpenDialog({
      title: 'Open PDF',
      properties: ['openFile'],
      filters: [{ name: 'PDF Documents', extensions: ['pdf'] }],
    });
    return result.canceled ? null : result.filePaths[0];
  });
  ipcMain.handle('vera:saveVera', async (_event, defaultPath?: string) => {
    const result = await dialog.showSaveDialog({
      title: 'Save VERA archive',
      defaultPath,
      filters: [{ name: 'VERA Archives', extensions: ['vera'] }],
    });
    return result.canceled ? null : result.filePath;
  });
  ipcMain.handle('vera:saveAny', async () => {
    const result = await dialog.showSaveDialog({ title: 'Save file' });
    return result.canceled ? null : result.filePath;
  });
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('before-quit', () => sidecar.stop());

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
