import type { RefObject } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  CheckCircle2,
  ChevronDown,
  FolderOpen,
  ListChecks,
  RefreshCw,
  Search,
  Settings,
  Terminal,
} from 'lucide-react';
import { ActivityTrace } from './activity/ActivityTrace';
import { TraceView } from './activity/TraceView';
import { ChatComposer } from './ChatComposer';
import { ChatTurn } from './ChatTurn';
import { fileName } from '../lib/formatting';
import { providerDisplayName, REASONING_EFFORTS, reasoningEffortLabel } from '../lib/providers';
import type {
  ChatAttachment,
  ChatCitationResult,
  Mode,
  ProviderProfile,
  SearchResult,
  SessionTurn,
  StreamEvent,
} from '../types';

export function CenterChatView({
  sessionTurns,
  linkableCitations,
  selectCitation,
  selected,
  showTrace,
  chatBusy,
  responseStatus,
  streamEvents,
  streamingAnswer,
  traceEvents,
  threadRef,
  showJumpToLatest,
  onThreadScroll,
  onJumpToLatest,
  conversionInProgress,
  selectedFiles,
  activeLibraryIsEmpty,
  activeLibraryPath,
  path,
  attachments,
  busyAction,
  hasSearchableScope,
  composerResetVersion,
  composerRestoredDraft,
  onAddAttachments,
  onRemoveAttachment,
  onAsk,
  onStopAnswer,
  modePickerOpen,
  onModePickerOpenChange,
  modes,
  activeMode,
  onSelectActiveMode,
  onOpenModesFolder,
  onReloadModes,
  modelPickerOpen,
  onModelPickerOpenChange,
  activeProvider,
  activeProviderId,
  activeModel,
  activeModelOptions,
  modelFilter,
  onModelFilterChange,
  providers,
  hoveredModelOptions,
  onHoveredModelOptionsChange,
  onSelectActiveModel,
  onRefreshProviderModels,
  modelRefreshBusyId,
  onOpenSettings,
  onOpenModelManager,
  onUpdateModelOptions,
  onShowTraceChange,
}: {
  sessionTurns: SessionTurn[];
  linkableCitations: ChatCitationResult[];
  selectCitation: (citation: ChatCitationResult) => void;
  selected: SearchResult | null;
  showTrace: boolean;
  chatBusy: boolean;
  responseStatus: string;
  streamEvents: StreamEvent[];
  streamingAnswer: string;
  traceEvents: StreamEvent[];
  threadRef: RefObject<HTMLDivElement | null>;
  showJumpToLatest: boolean;
  onThreadScroll: () => void;
  onJumpToLatest: () => void;
  conversionInProgress: boolean;
  selectedFiles: string[];
  activeLibraryIsEmpty: boolean;
  activeLibraryPath: string;
  path: string;
  attachments: ChatAttachment[];
  busyAction: string | null;
  hasSearchableScope: boolean;
  composerResetVersion: number;
  composerRestoredDraft: { version: number; text: string };
  onAddAttachments: (files: FileList | File[]) => Promise<void>;
  onRemoveAttachment: (id: string) => void;
  onAsk: (prompt: string, onAccepted: () => void) => Promise<void>;
  onStopAnswer: () => void;
  modePickerOpen: boolean;
  onModePickerOpenChange: (open: boolean | ((value: boolean) => boolean)) => void;
  modes: Mode[];
  activeMode: Mode | null;
  onSelectActiveMode: (id: string) => void;
  onOpenModesFolder: () => void;
  onReloadModes: () => void;
  modelPickerOpen: boolean;
  onModelPickerOpenChange: (open: boolean) => void;
  activeProvider: ProviderProfile | null;
  activeProviderId: string | null;
  activeModel: string;
  activeModelOptions: { reasoning_effort?: string; fast?: boolean };
  modelFilter: string;
  onModelFilterChange: (value: string) => void;
  providers: ProviderProfile[];
  hoveredModelOptions: { providerId: string; model: string } | null;
  onHoveredModelOptionsChange: (value: { providerId: string; model: string } | null) => void;
  onSelectActiveModel: (providerId: string, model: string) => void;
  onRefreshProviderModels: (providerId: string) => void;
  modelRefreshBusyId: string | null;
  onOpenSettings: () => void;
  onOpenModelManager: () => void;
  onUpdateModelOptions: (
    providerId: string,
    model: string,
    options: { reasoning_effort?: string; fast?: boolean },
  ) => void;
  onShowTraceChange: (value: boolean | ((current: boolean) => boolean)) => void;
}) {
  const scopeLabel = conversionInProgress
    ? 'Chat unavailable while the conversion completes.'
    : selectedFiles.length > 0
      ? null
      : activeLibraryIsEmpty ? `“${fileName(activeLibraryPath)}” is empty`
        : activeLibraryPath ? `All documents in “${fileName(activeLibraryPath)}”` : path ? `Current document: “${fileName(path)}”` : 'No search scope';

  return (
    <div className={sessionTurns.length > 0 ? 'chatPanel chatPanel--active' : 'chatPanel chatPanel--empty'}>
      {sessionTurns.length > 0 ? (
        <div className="chatThreadWrap">
          <div className="chatThread" ref={threadRef} onScroll={onThreadScroll}>
            {sessionTurns.map((turn, idx) => (
              <ChatTurn
                key={idx}
                turn={turn}
                linkableCitations={linkableCitations}
                selectCitation={selectCitation}
                selectedChunkId={selected?.chunk_id}
                showTrace={showTrace}
              />
            ))}
            {chatBusy ? (
              <article className="chatMessage assistantMessage streamingMessage">
                <ActivityTrace
                  live
                  status={responseStatus}
                  searches={streamEvents.map((ev) => ({
                    query: ev.query || '',
                    mode: ev.mode,
                    hits: ev.hits,
                    pending: ev.event !== 'search_done',
                  }))}
                />
                {streamingAnswer ? (
                  <div className="markdownBody"><Markdown remarkPlugins={[remarkGfm]}>{streamingAnswer}</Markdown></div>
                ) : null}
                {showTrace && traceEvents.length > 0 ? <TraceView events={traceEvents} /> : null}
              </article>
            ) : null}
          </div>
          {showJumpToLatest ? (
            <button
              type="button"
              className="jumpToLatest"
              onClick={onJumpToLatest}
              aria-label="Jump to the latest chat response"
            >
              <ChevronDown size={15} />
              Jump to latest
            </button>
          ) : null}
        </div>
      ) : null}
      <div className="askComposerWrap">
        <div className="composerScope">
          {selectedFiles.length > 0 && !conversionInProgress ? (
            <details className="composerScopeDocuments">
              <summary>{selectedFiles.length} selected document{selectedFiles.length === 1 ? '' : 's'}</summary>
              <ul>
                {selectedFiles.map((filePath) => (
                  <li key={filePath} title={filePath}>{fileName(filePath)}</li>
                ))}
              </ul>
            </details>
          ) : scopeLabel}
        </div>
        <ChatComposer
          attachments={attachments}
          busy={chatBusy || conversionInProgress}
          busyAction={busyAction}
          hasSearchableScope={hasSearchableScope}
          hasPreviousTurns={sessionTurns.length > 0}
          resetVersion={composerResetVersion}
          restoredDraft={composerRestoredDraft}
          onAddAttachments={onAddAttachments}
          onRemoveAttachment={onRemoveAttachment}
          onAsk={onAsk}
          onStopAnswer={onStopAnswer}
        />
        <div className="composerBar">
          <div className="modelPicker">
            <button
              type="button"
              className="modelPickerButton"
              onClick={() => onModePickerOpenChange((open) => !open)}
            >
              <ListChecks size={14} />
              <span>{activeMode ? activeMode.label : 'Mode'}</span>
              <ChevronDown size={14} />
            </button>
            {modePickerOpen ? (
              <>
                <div className="modelPickerBackdrop" onClick={() => onModePickerOpenChange(false)} />
                <div className="modelPickerMenu" role="menu">
                  <div className="modelPickerGroupLabel">Answer mode</div>
                  {modes.map((entry) => (
                    <button
                      type="button"
                      key={entry.id}
                      className={entry.id === (activeMode?.id ?? '') ? 'modelOption active' : 'modelOption'}
                      onClick={() => onSelectActiveMode(entry.id)}
                    >
                      <span>{entry.label}{entry.builtin ? '' : ' · custom'}</span>
                      {entry.description ? <small>{entry.description}</small> : null}
                    </button>
                  ))}
                  <div className="modelPickerSep" />
                  <button
                    type="button"
                    className="modelOption manageOption"
                    onClick={() => {
                      onModePickerOpenChange(false);
                      onOpenModesFolder();
                    }}
                  >
                    <FolderOpen size={14} />
                    <span>Open modes folder…</span>
                  </button>
                  <button
                    type="button"
                    className="modelOption manageOption"
                    onClick={() => {
                      onModePickerOpenChange(false);
                      onReloadModes();
                    }}
                  >
                    <RefreshCw size={14} />
                    <span>Reload modes</span>
                  </button>
                </div>
              </>
            ) : null}
          </div>
          <div className="modelPicker">
            <button
              type="button"
              className="modelPickerButton"
              title="Select model · Ctrl+Alt+/ cycles reasoning effort"
              onClick={() => {
                const opening = !modelPickerOpen;
                onModelPickerOpenChange(opening);
                if (!opening) return;
                onModelFilterChange('');
                const refreshedAt = activeProvider?.models_refreshed_at ?? 0;
                if (activeProvider && Date.now() - refreshedAt > 60 * 60 * 1000) {
                  onRefreshProviderModels(activeProvider.id);
                }
              }}
            >
              <span>
                {activeProvider && activeModel
                  ? `${activeModel}${activeModelOptions.reasoning_effort ? ` · ${reasoningEffortLabel(activeModelOptions.reasoning_effort)}` : ''}${activeModelOptions.fast ? ' · Fast' : ''}`
                  : 'Select model'}
              </span>
              <ChevronDown size={14} />
            </button>
            {modelPickerOpen ? (
              <>
                <div className="modelPickerBackdrop" onClick={() => onModelPickerOpenChange(false)} />
                <div className="modelPickerMenu" role="menu" onMouseLeave={() => onHoveredModelOptionsChange(null)}>
                  <div className="modelPickerMenuScroll">
                    <div className="modelPickerSearch">
                      <Search size={13} />
                      <input value={modelFilter} onChange={(event) => onModelFilterChange(event.target.value)} placeholder="Search models" autoFocus />
                    </div>
                    {providers.length === 0 ? (
                      <div className="modelPickerEmpty">No providers yet — add one below.</div>
                    ) : null}
                    {providers.map((profile) => (
                      <div className="modelPickerGroup" key={profile.id}>
                        <div className="modelPickerGroupLabel">{providerDisplayName(profile)}</div>
                        {profile.models.length === 0 ? (
                          <div className="modelPickerEmpty">No models enabled</div>
                        ) : (
                          profile.models
                            .filter((model) => !modelFilter.trim() || model.toLowerCase().includes(modelFilter.trim().toLowerCase()))
                            .map((model) => (
                            <button
                              type="button"
                              key={`${profile.id}-${model}`}
                              className={profile.id === activeProviderId && model === activeModel ? 'modelOption active' : 'modelOption'}
                              onClick={() => onSelectActiveModel(profile.id, model)}
                              onMouseEnter={() => {
                                onHoveredModelOptionsChange({
                                  providerId: profile.id,
                                  model,
                                });
                              }}
                            >
                              <span>{model}</span>
                            </button>
                          ))
                        )}
                      </div>
                    ))}
                  </div>
                  <div className="modelPickerSep" />
                  <button
                    type="button"
                    className="modelOption manageOption"
                    onClick={() => {
                      if (activeProviderId) onRefreshProviderModels(activeProviderId);
                      else {
                        onModelPickerOpenChange(false);
                        onOpenSettings();
                      }
                    }}
                    disabled={Boolean(modelRefreshBusyId)}
                  >
                    <RefreshCw size={14} className={modelRefreshBusyId ? 'spinning' : ''} />
                    <span>{modelRefreshBusyId ? 'Refreshing models…' : 'Refresh models'}</span>
                  </button>
                  <button
                    type="button"
                    className="modelOption manageOption"
                    onClick={() => {
                      onModelPickerOpenChange(false);
                      onOpenModelManager();
                    }}
                  >
                    <Settings size={14} />
                    <span>Edit models…</span>
                  </button>
                  {hoveredModelOptions ? (() => {
                    const profile = providers.find((entry) => entry.id === hoveredModelOptions.providerId);
                    if (!profile) return null;
                    const options: { reasoning_effort?: string; fast?: boolean } = profile.model_options?.[hoveredModelOptions.model] ?? {};
                    const thinkingEnabled = options.reasoning_effort !== 'none';
                    const selectedEffort = options.reasoning_effort && options.reasoning_effort !== 'none'
                      ? options.reasoning_effort
                      : 'medium';
                    return (
                      <div className="modelOptionsFlyout">
                        <span className="modelOptionsHeading">Options</span>
                        <label className="modelFlyoutToggle">
                          <span>Thinking</span>
                          <input
                            type="checkbox"
                            checked={thinkingEnabled}
                            onChange={() => onUpdateModelOptions(profile.id, hoveredModelOptions.model, {
                              ...options,
                              reasoning_effort: thinkingEnabled ? 'none' : 'medium',
                            })}
                          />
                        </label>
                        <label className="modelFlyoutToggle">
                          <span>Fast</span>
                          <input
                            type="checkbox"
                            checked={Boolean(options.fast)}
                            onChange={() => onUpdateModelOptions(profile.id, hoveredModelOptions.model, {
                              ...options,
                              fast: !options.fast,
                            })}
                          />
                        </label>
                        <span className="modelOptionsHeading effortHeading">Effort</span>
                        <div className="modelEffortMenu">
                          {REASONING_EFFORTS.map((effort) => (
                            <button
                              type="button"
                              key={effort}
                              className={thinkingEnabled && selectedEffort === effort ? 'active' : ''}
                              disabled={!thinkingEnabled}
                              onClick={() => onUpdateModelOptions(profile.id, hoveredModelOptions.model, {
                                ...options,
                                reasoning_effort: effort,
                              })}
                            >
                              <span>{reasoningEffortLabel(effort)}</span>
                              {thinkingEnabled && selectedEffort === effort ? <CheckCircle2 size={13} /> : null}
                            </button>
                          ))}
                        </div>
                      </div>
                    );
                  })() : null}
                </div>
              </>
            ) : null}
          </div>
          <button
            type="button"
            className={showTrace ? 'composerToggle active' : 'composerToggle'}
            onClick={() => onShowTraceChange((value) => {
              const next = !value;
              try { localStorage.setItem('vera.showTrace', next ? '1' : '0'); } catch { /* ignore persistence errors */ }
              return next;
            })}
            title="Show the prompts, tool calls, and responses exchanged with the LLM"
          >
            <Terminal size={14} />
            <span>Trace</span>
          </button>
        </div>
      </div>
    </div>
  );
}
