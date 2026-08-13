import { describe, expect, it } from 'vitest';
import {
  sidecarCallScope,
  sidecarCallWasCancelled,
  sidecarTimeoutMessage,
} from './sidecarCall';

describe('sidecarCallWasCancelled', () => {
  it('treats cancelled flags and messages as cancelled', () => {
    expect(sidecarCallWasCancelled(undefined, true)).toBe(true);
    expect(sidecarCallWasCancelled('Request cancelled by user')).toBe(true);
    expect(sidecarCallWasCancelled('Request failed')).toBe(false);
  });
});

describe('sidecarTimeoutMessage', () => {
  it('rounds the timeout to seconds', () => {
    expect(sidecarTimeoutMessage('Opening', 120000)).toBe('Opening timed out after 120 seconds');
  });
});

describe('sidecarCallScope', () => {
  it('prefers an explicit scope, then the action, then the label', () => {
    expect(sidecarCallScope({ action: 'inspect' }, 'Opening', { scope: 'source' })).toBe('source');
    expect(sidecarCallScope({ action: 'inspect' }, 'Opening')).toBe('inspect');
    expect(sidecarCallScope({}, 'Opening')).toBe('Opening');
  });
});
