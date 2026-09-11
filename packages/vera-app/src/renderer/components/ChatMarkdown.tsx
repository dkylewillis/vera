import Markdown from 'react-markdown';
import type { Components, Options } from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import { prepareChatMarkdown } from '../lib/chatMarkdown';

const REMARK_PLUGINS: Options['remarkPlugins'] = [remarkGfm, remarkMath];
const REHYPE_PLUGINS: Options['rehypePlugins'] = [
  [rehypeKatex, { throwOnError: false, strict: 'ignore' }],
];

export function ChatMarkdown({
  children,
  components,
}: {
  children: string;
  components?: Components;
}) {
  return (
    <div className="markdownBody">
      <Markdown
        remarkPlugins={REMARK_PLUGINS}
        rehypePlugins={REHYPE_PLUGINS}
        components={components}
      >
        {prepareChatMarkdown(children)}
      </Markdown>
    </div>
  );
}
