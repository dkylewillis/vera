/** Shared with the relay worker. Kept local so the desktop does not import the private relay package. */

export const RELAY_PROTOCOL = '2';
export const HEADER_PROTOCOL = 'x-vera-relay-protocol';
export const HEADER_DEVICE_ID = 'x-vera-device-id';
export const HEADER_DEVICE_NAME = 'x-vera-device-name';
export const HEADER_INSTANCE = 'x-vera-instance';
export const HEADER_APP_VERSION = 'x-vera-app-version';
export const PING = '{"type":"ping"}';
export const PONG = '{"type":"pong"}';
export const CLOSE_EXPIRED = 4001;
export const CLOSE_DUPLICATE = 4002;
export const CLOSE_FORGOTTEN = 4004;
export const CHUNK_BYTES = 32 * 1024;
