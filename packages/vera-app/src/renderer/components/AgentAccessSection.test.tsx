import { describe, expect, it } from 'vitest';
import { accessSummary, initialDestination, localAccessAfterFolderChange } from './AgentAccessSection';

describe('localAccessAfterFolderChange', () => {
  it('turns access on when the first folder is added', () => {
    expect(localAccessAfterFolderChange(false, 0, 1)).toBe(true);
  });

  it('leaves an existing choice alone when another folder is added', () => {
    expect(localAccessAfterFolderChange(true, 1, 2)).toBe(true);
    expect(localAccessAfterFolderChange(false, 2, 3)).toBe(false);
  });

  it('turns access off when the last folder is removed', () => {
    expect(localAccessAfterFolderChange(true, 1, 0)).toBe(false);
    expect(localAccessAfterFolderChange(false, 3, 2)).toBe(false);
  });
});

describe('initialDestination', () => {
  it('opens on cloud assistants unless only local apps are set up', () => {
    expect(initialDestination(false, false)).toBe('cloud');
    expect(initialDestination(true, true)).toBe('cloud');
    expect(initialDestination(false, true)).toBe('cloud');
    expect(initialDestination(true, false)).toBe('local');
  });
});

describe('accessSummary', () => {
  it('says what is shared and with whom', () => {
    expect(accessSummary(false, false, 0)).toBe('Off. Add a folder to get started.');
    expect(accessSummary(false, false, 2)).toContain('Off. 2 folders ready.');
    expect(accessSummary(true, false, 1)).toContain('1 folder shared with apps on this computer');
    expect(accessSummary(true, true, 3)).toContain('3 folders shared with cloud assistants and apps on this computer');
  });
});
