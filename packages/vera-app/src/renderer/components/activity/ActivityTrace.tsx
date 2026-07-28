import { FileText, Image as ImageIcon, Search } from 'lucide-react';
import type { ChatCitationResult, FigureResult } from '../../types';

export type ActivitySearchItem = { query: string; mode?: string; hits?: number; pending?: boolean };

type ActivityStep =
  | { kind: 'search'; item: ActivitySearchItem }
  | { kind: 'source'; citation: ChatCitationResult }
  | { kind: 'image'; citation: ChatCitationResult; figure: FigureResult };

function ActivityStepRow({
  step,
  onSelectCitation,
  selected,
}: {
  step: ActivityStep;
  onSelectCitation?: (citation: ChatCitationResult) => void;
  selected?: boolean;
}) {
  if (step.kind === 'search') {
    const { item } = step;
    return (
      <li className={item.pending ? 'activityItem activityItem--pending' : 'activityItem'}>
        <Search size={12} className="activityIcon" />
        <span className="activityText">
          Searched for <code className="activityPill">{item.query}</code>
          {item.pending ? (
            <span className="activityMeta"> …</span>
          ) : (
            <span className="activityMeta"> · {item.mode}, {item.hits} {item.hits === 1 ? 'hit' : 'hits'}</span>
          )}
        </span>
      </li>
    );
  }
  if (step.kind === 'image') {
    const { citation, figure } = step;
    const label = figure.caption?.trim() || citation.result.heading_path || citation.result.source_filename || citation.result.chunk_id;
    return (
      <li className="activityItem">
        <button
          type="button"
          className={selected ? 'activityRowButton activityRowButton--selected' : 'activityRowButton'}
          onClick={() => onSelectCitation?.(citation)}
        >
          <ImageIcon size={12} className="activityIcon" />
          <span className="activityText">
            Viewed image <code className="activityPill">{label}</code>
            {figure.page_number != null ? <span className="activityMeta"> · p. {figure.page_number}</span> : null}
          </span>
        </button>
      </li>
    );
  }
  const { citation } = step;
  const label = citation.result.heading_path || citation.result.source_filename || citation.result.chunk_id;
  const pages =
    citation.result.page_start != null
      ? citation.result.page_end != null && citation.result.page_end !== citation.result.page_start
        ? `p. ${citation.result.page_start}\u2013${citation.result.page_end}`
        : `p. ${citation.result.page_start}`
      : null;
  return (
    <li className="activityItem">
      <button
        type="button"
        className={selected ? 'activityRowButton activityRowButton--selected' : 'activityRowButton'}
        onClick={() => onSelectCitation?.(citation)}
      >
        <FileText size={12} className="activityIcon" />
        <span className="activityText">
          Read <code className="activityPill">{label}</code>
          {pages ? <span className="activityMeta"> · {pages}</span> : null}
        </span>
      </button>
    </li>
  );
}

export function ActivityTrace({
  searches,
  citations,
  selectCitation,
  selectedChunkId,
  live,
}: {
  searches?: ActivitySearchItem[];
  citations?: ChatCitationResult[];
  selectCitation?: (citation: ChatCitationResult) => void;
  selectedChunkId?: string;
  live?: boolean;
}) {
  const steps: ActivityStep[] = [
    ...(searches || []).map((item): ActivityStep => ({ kind: 'search', item })),
    ...(citations || []).map((citation): ActivityStep => ({ kind: 'source', citation })),
    ...(citations || []).flatMap((citation): ActivityStep[] =>
      (citation.result.figures || [])
        .filter((figure) => figure.data_url && figure.included_in_context)
        .map((figure): ActivityStep => ({ kind: 'image', citation, figure })),
    ),
  ];
  if (!steps.length) return null;

  const list = (
    <ul className="activityList">
      {steps.map((step, i) => (
        <ActivityStepRow
          key={i}
          step={step}
          onSelectCitation={selectCitation}
          selected={step.kind !== 'search' && step.citation.result.chunk_id === selectedChunkId}
        />
      ))}
    </ul>
  );

  if (live) {
    return <div className="activityTrace activityTrace--live">{list}</div>;
  }

  const searchCount = searches?.length || 0;
  const sourceCount = citations?.length || 0;
  const imageCount = steps.filter((step) => step.kind === 'image').length;
  const summaryParts: string[] = [];
  if (searchCount) summaryParts.push(`Searched ${searchCount} ${searchCount === 1 ? 'query' : 'queries'}`);
  if (sourceCount) summaryParts.push(`reviewed ${sourceCount} ${sourceCount === 1 ? 'source' : 'sources'}`);
  if (imageCount) summaryParts.push(`viewed ${imageCount} ${imageCount === 1 ? 'image' : 'images'}`);

  return (
    <details className="activityDisclosure">
      <summary>{summaryParts.join(' and ') || 'Activity'}</summary>
      {list}
    </details>
  );
}
