/**
 * Prepare assistant Markdown so remark-math can typeset it:
 * convert TeX `\\(...\\)` / `\\[...\\]` to dollars, turn one-line `$$...$$`
 * into a display block, and apply Pandoc's currency rule (a closing `$`
 * followed by a digit is not math). Fenced and inline code stay literal.
 */
export function prepareChatMarkdown(source: string): string {
  let out = '';
  let i = 0;
  const n = source.length;

  while (i < n) {
    if (source.startsWith('```', i) || source.startsWith('~~~', i)) {
      const fence = source.slice(i, i + 3);
      const close = source.indexOf(`\n${fence}`, i + 3);
      if (close === -1) {
        out += source.slice(i);
        break;
      }
      let end = close + 1 + fence.length;
      while (end < n && source[end] !== '\n') end += 1;
      out += source.slice(i, end);
      i = end;
      continue;
    }

    if (source[i] === '`') {
      let ticks = 1;
      while (i + ticks < n && source[i + ticks] === '`') ticks += 1;
      const close = source.indexOf('`'.repeat(ticks), i + ticks);
      if (close === -1) {
        out += source.slice(i);
        break;
      }
      const end = close + ticks;
      out += source.slice(i, end);
      i = end;
      continue;
    }

    if (source.startsWith('$$', i)) {
      const close = source.indexOf('$$', i + 2);
      if (close !== -1) {
        const body = source.slice(i + 2, close);
        out += body.includes('\n') ? source.slice(i, close + 2) : `$$\n${body}\n$$`;
        i = close + 2;
        continue;
      }
    }

    if (source.startsWith('\\[', i)) {
      const close = source.indexOf('\\]', i + 2);
      if (close !== -1) {
        out += `$$\n${source.slice(i + 2, close)}\n$$`;
        i = close + 2;
        continue;
      }
    }

    if (source.startsWith('\\(', i)) {
      const close = source.indexOf('\\)', i + 2);
      if (close !== -1) {
        out += `$${source.slice(i + 2, close)}$`;
        i = close + 2;
        continue;
      }
    }

    if (source[i] === '$') {
      const close = source.indexOf('$', i + 1);
      if (close > i + 1) {
        const after = source[close + 1];
        if (after && after >= '0' && after <= '9') {
          out += `\\${source.slice(i, close)}`;
          i = close;
          continue;
        }
        out += source.slice(i, close + 1);
        i = close + 1;
        continue;
      }
    }

    out += source[i];
    i += 1;
  }

  return out;
}
