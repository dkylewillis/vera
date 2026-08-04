import { Image as ImageIcon, Maximize2, Minimize2, Terminal } from 'lucide-react';
import { useState } from 'react';
import type { StreamEvent } from '../../types';

export function TraceView({ events }: { events: StreamEvent[] }) {
  const [expanded, setExpanded] = useState(false);
  if (!events.length) return null;
  return (
    <div className={expanded ? 'llmTrace llmTrace--expanded' : 'llmTrace'}>
      <div className="llmTraceHeader">
        <Terminal size={12} />LLM trace
        <button
          type="button"
          className="traceExpandButton"
          onClick={() => setExpanded((value) => !value)}
          title={expanded ? 'Collapse content blocks' : 'Expand to see full contents'}
        >
          {expanded ? <><Minimize2 size={12} />Collapse</> : <><Maximize2 size={12} />Expand full</>}
        </button>
      </div>
      {events.map((ev, index) => {
        if (ev.event === 'llm_request') {
          return (
            <details className="traceEntry traceRequest" key={index} open={expanded}>
              <summary>
                <span className="traceBadge req">Request</span>
                <span className="traceMeta">turn {ev.turn ?? 0} · {ev.model || 'model'} · {ev.tools && ev.tools.length ? `tools: ${ev.tools.join(', ')}` : 'no tools'}</span>
              </summary>
              <div className="traceMessages">
                {(ev.messages || []).map((message, mi) => {
                  const calls = message.tool_calls
                    ?.map((tc) => `${tc.function?.name || 'tool'}(${tc.function?.arguments || ''})`)
                    .join('\n');
                  return (
                    <div className={`traceMsg traceRole--${message.role}`} key={mi}>
                      <span className="traceRole">{message.role}{message.name ? ` · ${message.name}` : ''}</span>
                      {Array.isArray(message.content) ? (
                        message.content.map((part, pi) =>
                          part.type === 'image_url' ? (
                            <span className="traceContent traceImagePart" key={pi}>
                              <ImageIcon size={12} />
                              {part.image_url.url}
                            </span>
                          ) : (
                            <pre className="traceContent" key={pi}>{part.text}</pre>
                          ),
                        )
                      ) : message.content ? (
                        <pre className="traceContent">{message.content}</pre>
                      ) : null}
                      {calls ? <pre className="traceContent traceToolCalls">{calls}</pre> : null}
                    </div>
                  );
                })}
              </div>
            </details>
          );
        }
        if (ev.event === 'llm_response') {
          const tokens = ev.usage && typeof ev.usage.total_tokens === 'number' ? ev.usage.total_tokens : null;
          const calls = ev.tool_calls?.map((tc) => `${tc.name || 'tool'}(${JSON.stringify(tc.arguments ?? {})})`).join('\n');
          return (
            <details className="traceEntry traceResponse" key={index} open={expanded || !ev.tool_calls?.length}>
              <summary>
                <span className="traceBadge res">Response</span>
                <span className="traceMeta">turn {ev.turn ?? 0} · {ev.model || 'model'}{ev.tool_calls?.length ? ` · ${ev.tool_calls.length} tool call(s)` : ''}{tokens != null ? ` · ${tokens} tok` : ''}</span>
              </summary>
              {ev.content ? <pre className="traceContent">{ev.content}</pre> : null}
              {calls ? <pre className="traceContent traceToolCalls">{calls}</pre> : null}
            </details>
          );
        }
        if (ev.event === 'tool_call') {
          return (
            <details className="traceEntry traceTool" key={index} open={expanded}>
              <summary>
                <span className="traceBadge tool">Tool · {ev.name || 'tool'}</span>
                <span className="traceMeta">{JSON.stringify(ev.arguments ?? {})}</span>
              </summary>
              <pre className="traceContent">{JSON.stringify(ev.output, null, 2)}</pre>
            </details>
          );
        }
        if (ev.event === 'search_start' || ev.event === 'search_done') {
          return (
            <div className="traceEntry traceSearch" key={index}>
              <span className={ev.event === 'search_done' ? 'traceBadge search done' : 'traceBadge search'}>{ev.event === 'search_done' ? 'search done' : 'searching'}</span>
              <span className="traceMeta">{ev.query}{ev.event === 'search_done' ? ` · ${ev.mode}, ${ev.hits} hits` : ' …'}</span>
            </div>
          );
        }
        // Streaming answer/reset and unrelated progress events update other UI;
        // they are not diagnostic search operations.
        return null;
      })}
    </div>
  );
}
