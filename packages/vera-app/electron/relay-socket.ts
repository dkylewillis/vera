import { createHash, randomBytes } from 'node:crypto';
import { connect as netConnect, type Socket } from 'node:net';
import { connect as tlsConnect } from 'node:tls';

/** Text WebSocket used by the desktop relay. The token travels in the upgrade header. */
export interface RelaySocket {
  send(data: string): void;
  close(code?: number, reason?: string): void;
  onMessage(handler: (data: string) => void): void;
  onClose(handler: (code: number) => void): void;
  onOpen(handler: () => void): void;
}

const GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11';

export interface RelayConnectError extends Error {
  status?: number;
}

export function openRelaySocket(url: string, token: string): Promise<RelaySocket> {
  const target = new URL(url);
  const secure = target.protocol === 'wss:';
  if (target.protocol !== 'wss:' && target.protocol !== 'ws:') {
    return Promise.reject(new Error('Relay URL must be ws or wss.'));
  }
  const port = Number(target.port || (secure ? 443 : 80));
  const key = randomBytes(16).toString('base64');
  const expected = createHash('sha1').update(`${key}${GUID}`).digest('base64');
  const socket = secure
    ? tlsConnect({ host: target.hostname, port, servername: target.hostname })
    : netConnect({ host: target.hostname, port });
  const path = `${target.pathname || '/'}${target.search}`;
  const host = target.host;

  return new Promise((resolve, reject) => {
    const fail = (error: Error) => {
      socket.destroy();
      reject(error);
    };
    socket.once('error', fail);
    socket.once('connect', () => {
      socket.write([
        `GET ${path} HTTP/1.1`,
        `Host: ${host}`,
        'Upgrade: websocket',
        'Connection: Upgrade',
        `Sec-WebSocket-Key: ${key}`,
        'Sec-WebSocket-Version: 13',
        `Authorization: Bearer ${token}`,
        '',
        '',
      ].join('\r\n'));
    });
    let header = Buffer.alloc(0);
    const onData = (chunk: Buffer) => {
      header = Buffer.concat([header, chunk]);
      const split = header.indexOf('\r\n\r\n');
      if (split < 0) return;
      socket.off('data', onData);
      const text = header.subarray(0, split).toString('utf8');
      const status = Number(/^HTTP\/1\.[01] (\d+)/.exec(text)?.[1] || 0);
      const accept = /^sec-websocket-accept:\s*(.+)$/im.exec(text)?.[1]?.trim();
      if (status !== 101 || accept !== expected) {
        const error = new Error(`Relay refused the desktop connection (${status || 'no status'}).`) as RelayConnectError;
        error.status = status;
        fail(error);
        return;
      }
      socket.off('error', fail);
      resolve(new NodeRelaySocket(socket, header.subarray(split + 4)));
    };
    socket.on('data', onData);
  });
}

class NodeRelaySocket implements RelaySocket {
  private readonly pending: Buffer[] = [];
  private fragments: Buffer[] = [];
  private messageHandler: ((data: string) => void) | null = null;
  private closeHandler: ((code: number) => void) | null = null;
  private openHandler: (() => void) | null = null;
  private opened = false;

  constructor(private readonly socket: Socket, initial: Buffer) {
    if (initial.byteLength) this.pending.push(initial);
    this.socket.on('data', (chunk: Buffer | string) => {
      this.pending.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
      this.drain();
    });
    this.socket.on('close', () => this.closeHandler?.(1006));
    this.socket.on('error', () => this.closeHandler?.(1006));
    queueMicrotask(() => {
      this.opened = true;
      this.openHandler?.();
      this.drain();
    });
  }

  send(data: string): void {
    this.socket.write(encodeFrame(0x1, Buffer.from(data), true));
  }

  close(code = 1000, reason = ''): void {
    const payload = Buffer.alloc(2 + Buffer.byteLength(reason));
    payload.writeUInt16BE(code);
    payload.write(reason, 2);
    try {
      this.socket.write(encodeFrame(0x8, payload, true));
    } catch {
      /* already closed */
    }
    this.socket.end();
  }

  onMessage(handler: (data: string) => void): void {
    this.messageHandler = handler;
  }

  onClose(handler: (code: number) => void): void {
    this.closeHandler = handler;
  }

  onOpen(handler: () => void): void {
    this.openHandler = handler;
    if (this.opened) handler();
  }

  private drain(): void {
    let pending = Buffer.concat(this.pending);
    this.pending.length = 0;
    while (pending.byteLength >= 2) {
      const first = pending[0] ?? 0;
      const second = pending[1] ?? 0;
      let length = second & 0x7f;
      let offset = 2;
      if (length === 126) {
        if (pending.byteLength < 4) break;
        length = pending.readUInt16BE(2);
        offset = 4;
      } else if (length === 127) {
        if (pending.byteLength < 10) break;
        length = pending.readUInt32BE(6);
        offset = 10;
      }
      const masked = (second & 0x80) !== 0;
      const maskLength = masked ? 4 : 0;
      if (pending.byteLength < offset + maskLength + length) break;
      let payload = pending.subarray(offset + maskLength, offset + maskLength + length);
      if (masked) {
        const mask = pending.subarray(offset, offset + 4);
        const copy = Buffer.from(payload);
        for (let index = 0; index < copy.byteLength; index += 1) {
          copy[index] = (copy[index] ?? 0) ^ (mask[index % 4] ?? 0);
        }
        payload = copy;
      }
      const opcode = first & 0x0f;
      const fin = (first & 0x80) !== 0;
      pending = pending.subarray(offset + maskLength + length);
      this.dispatch(opcode, payload, fin);
    }
    if (pending.byteLength) this.pending.push(pending);
  }

  private dispatch(opcode: number, payload: Buffer, fin: boolean): void {
    if (opcode === 0x9) {
      this.socket.write(encodeFrame(0xA, payload, true));
      return;
    }
    if (opcode === 0x8) {
      const code = payload.byteLength >= 2 ? payload.readUInt16BE(0) : 1005;
      this.closeHandler?.(code);
      this.socket.end();
      return;
    }
    if (opcode !== 0x1 && opcode !== 0x0) return;
    if (opcode === 0x1) this.fragments = [];
    this.fragments.push(payload);
    if (!fin) return;
    const text = Buffer.concat(this.fragments).toString('utf8');
    this.fragments = [];
    this.messageHandler?.(text);
  }
}

function encodeFrame(opcode: number, payload: Buffer, mask: boolean): Buffer {
  const length = payload.byteLength;
  const head = [0x80 | opcode];
  if (length < 126) head.push((mask ? 0x80 : 0) | length);
  else if (length < 65536) head.push((mask ? 0x80 : 0) | 126, length >> 8, length & 0xff);
  else throw new Error('Relay frame is too large.');
  const maskKey = mask ? randomBytes(4) : Buffer.alloc(0);
  const body = Buffer.from(payload);
  if (mask) {
    for (let index = 0; index < body.byteLength; index += 1) {
      body[index] = (body[index] ?? 0) ^ (maskKey[index % 4] ?? 0);
    }
  }
  return Buffer.concat([Buffer.from(head), maskKey, body]);
}
