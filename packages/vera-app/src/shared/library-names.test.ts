import { describe, expect, it } from 'vitest';
import {
  assignLibraryNames,
  fallbackLibraryName,
  libraryNameError,
  librarySlug,
  namesForRoots,
} from './library-names';

describe('library names', () => {
  it('matches the Python slug and fallback rules', () => {
    expect(librarySlug('Stormwater Manuals')).toBe('stormwater-manuals');
    expect(librarySlug('---')).toBe('');
    expect(librarySlug('_hidden')).toBe('hidden');
    expect(librarySlug('codes_v2')).toBe('codes-v2');
    expect(librarySlug('a'.repeat(80))).toBe('a'.repeat(64));
    expect(librarySlug('9lives')).toBe('9lives');

    const work = 'C:/libraries/work/codes';
    const other = 'C:/libraries/other/codes';
    expect(assignLibraryNames([work, other], {})).toEqual({
      [work]: 'work-codes',
      [other]: 'other-codes',
    });
    expect(assignLibraryNames([work, other], { [work]: 'manuals' })).toEqual({
      [work]: 'manuals',
      [other]: 'codes',
    });
    expect(fallbackLibraryName([work, other], { [work]: 'manuals' }, other)).toBe('codes');
    expect(() => assignLibraryNames([work, other], { [work]: 'manuals', [other]: 'manuals' })).toThrow(
      /used more than once/,
    );
    expect(libraryNameError([work, other], { [work]: 'Stormwater' })).toMatch(/lowercase/);
    expect(libraryNameError([work, other], { [work]: 'manuals', [other]: 'manuals' })).toMatch(/already used/);
    expect(namesForRoots([work], { [work]: 'manuals', [other]: 'other' })).toEqual({ [work]: 'manuals' });
  });
});
