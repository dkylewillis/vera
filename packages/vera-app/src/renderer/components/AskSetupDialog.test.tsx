import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { AskSetupDialog } from './AskSetupDialog';

describe('AskSetupDialog', () => {
  it('offers VERA Pro next to adding your own provider', () => {
    const html = renderToStaticMarkup(
      <AskSetupDialog onUseVeraPro={() => undefined} onAddOwnProvider={() => undefined} onClose={() => undefined} />,
    );
    expect(html).toContain('Ask needs a model');
    expect(html).toContain('Use VERA Pro');
    expect(html).toContain('Add your own provider');
    const pro = html.indexOf('Use VERA Pro');
    const own = html.indexOf('Add your own provider');
    expect(pro).toBeGreaterThan(-1);
    expect(own).toBeGreaterThan(pro);
  });
});
