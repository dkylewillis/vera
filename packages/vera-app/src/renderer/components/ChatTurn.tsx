import React, { type ReactNode } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { ChatCitationResult, SessionTurn } from '../types';
import { ActivityTrace } from './activity/ActivityTrace';
import { TraceView } from './activity/TraceView';

function renderAnswerWithCitations(
  answerText: string,
  citations: ChatCitationResult[],
  selectCitation: (citation: ChatCitationResult) => void,
) {
  const citationById = new Map(citations.map((citation) => [citation.id, citation]));

  // Replace any string child containing `[C#]` markers with clickable citation buttons,
  // leaving the surrounding markdown-rendered elements intact.
  const injectCitations = (children: ReactNode): ReactNode =>
    React.Children.map(children, (child, index) => {
      if (typeof child !== 'string') return child;
      if (!child.includes('[C')) return child;
      return child.split(/(\[C\d+\])/g).map((part, partIndex) => {
        const id = part.match(/^\[(C\d+)\]$/)?.[1];
        const citation = id ? citationById.get(id) : null;
        if (!citation) return <React.Fragment key={`t-${index}-${partIndex}`}>{part}</React.Fragment>;
        return (
          <button className="inlineCitation" key={`c-${index}-${partIndex}`} onClick={() => selectCitation(citation)}>
            {part}
          </button>
        );
      });
    });

  const withCitations =
    (Tag: keyof React.JSX.IntrinsicElements) =>
    ({ children, ...props }: { children?: ReactNode }) =>
      React.createElement(Tag, props, injectCitations(children));

  return (
    <div className="markdownBody">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: withCitations('p'),
          li: withCitations('li'),
          td: withCitations('td'),
          th: withCitations('th'),
          h1: withCitations('h1'),
          h2: withCitations('h2'),
          h3: withCitations('h3'),
          h4: withCitations('h4'),
          h5: withCitations('h5'),
          h6: withCitations('h6'),
          strong: withCitations('strong'),
          em: withCitations('em'),
          blockquote: withCitations('blockquote'),
          a: ({ children, ...props }) => (
            <a {...props} target="_blank" rel="noreferrer">{injectCitations(children)}</a>
          ),
        }}
      >
        {answerText}
      </Markdown>
    </div>
  );
}

// Memoized per-turn chat bubble. Historical turns keep a stable `turn` object
// reference (new turns are only ever appended), so as long as the callback/selection
// props stay stable too, React can skip re-rendering (and re-parsing Markdown for)
// every past turn whenever unrelated App state changes, e.g. each composer keystroke.
export const ChatTurn = React.memo(function ChatTurn({
  turn,
  selectCitation,
  selectedChunkId,
  showTrace,
}: {
  turn: SessionTurn;
  selectCitation: (citation: ChatCitationResult) => void;
  selectedChunkId?: string;
  showTrace: boolean;
}) {
  if (turn.role === 'user') {
    return (
      <article className="chatMessage userMessage">
        {turn.attachments && turn.attachments.length ? (
          <div className="userAttachments">
            {turn.attachments.map((att) => (
              <img key={att.id} className="userAttachmentThumb" src={att.data_url} alt={att.name} title={att.name} />
            ))}
          </div>
        ) : null}
        <p>{turn.content}</p>
      </article>
    );
  }
  return (
    <article className="chatMessage assistantMessage">
      <span>
        VERA{turn.mode_label ? ` · ${turn.mode_label}` : ''}{turn.llm ? ` · ${turn.llm.model}` : ''}
      </span>
      <ActivityTrace
        searches={turn.searches}
        citations={turn.citations}
        selectedPaths={turn.selected_paths}
        selectCitation={selectCitation}
        selectedChunkId={selectedChunkId}
      />
      {turn.answer_mode === 'retrieval' ? <div className="noteBanner">The active API route rejected tool calling, so VERA used a single retrieval pass instead of agentic search.</div> : null}
      {turn.vision_fallback ? <div className="noteBanner">This model does not support image input. VERA omitted the images and retried with text only.</div> : null}
      {turn.citations && turn.citations.length ? (
        renderAnswerWithCitations(turn.content, turn.citations, selectCitation)
      ) : (
        <div className="markdownBody"><Markdown remarkPlugins={[remarkGfm]}>{turn.content}</Markdown></div>
      )}
      {showTrace && turn.trace?.length ? <TraceView events={turn.trace} /> : null}
    </article>
  );
});
