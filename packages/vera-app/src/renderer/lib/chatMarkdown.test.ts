import { describe, expect, it } from 'vitest';

import { prepareChatMarkdown } from './chatMarkdown';

describe('prepareChatMarkdown', () => {
  it('converts inline and display TeX delimiters to dollars', () => {
    expect(prepareChatMarkdown('Use \\(C_L\\) and\n\\[E = mc^2\\]')).toBe(
      'Use $C_L$ and\n$$\nE = mc^2\n$$',
    );
  });

  it('expands one-line dollar display math into a block', () => {
    expect(prepareChatMarkdown('$$E = mc^2$$')).toBe('$$\nE = mc^2\n$$');
  });

  it('leaves already-blocked display math alone', () => {
    expect(prepareChatMarkdown('$$\nE = mc^2\n$$')).toBe('$$\nE = mc^2\n$$');
  });

  it('leaves fenced and inline code untouched', () => {
    const source = 'See `\\(x\\)` and:\n```\n\\[E = mc^2\\]\n```\nthen \\(y\\)';
    expect(prepareChatMarkdown(source)).toBe(
      'See `\\(x\\)` and:\n```\n\\[E = mc^2\\]\n```\nthen $y$',
    );
  });

  it('escapes a dollar pair whose closer is followed by a digit', () => {
    expect(prepareChatMarkdown('Budget is $20,000 and $30,000.')).toBe(
      'Budget is \\$20,000 and $30,000.',
    );
  });

  it('leaves unmatched delimiters and real dollar math alone', () => {
    expect(prepareChatMarkdown('Partial \\(C_L and $a + b$')).toBe(
      'Partial \\(C_L and $a + b$',
    );
  });
});
