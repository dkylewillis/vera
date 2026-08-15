import type { CSSProperties, KeyboardEvent, MouseEvent, ReactNode, RefObject } from 'react';
import {
  FileInput,
  Folder,
  MessageSquareText,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Settings,
} from 'lucide-react';

export type SideView = 'explorer' | 'chats' | 'convert';
export type CenterView = 'chat' | 'search';

export function AppShell({
  workspaceRef,
  sidebarCollapsed,
  viewerCollapsed,
  viewerExpanded,
  sourcePaneWidth,
  sidePanelWidth,
  sideView,
  centerView,
  isResizingSide,
  isResizingSource,
  headerActions,
  sidebarBody,
  onToggleSidebar,
  onSideViewChange,
  onOpenSettings,
  onExplorerBlankPointer,
  onResizeSide,
  onResetSideWidth,
  onNudgeSideWidth,
  onCenterViewChange,
  onNewChat,
  errorBanner,
  centerBody,
  onResizeSource,
  onResetSourceWidth,
  onNudgeSourceWidth,
  viewer,
}: {
  workspaceRef: RefObject<HTMLDivElement | null>;
  sidebarCollapsed: boolean;
  viewerCollapsed: boolean;
  viewerExpanded: boolean;
  sourcePaneWidth: number;
  sidePanelWidth: number;
  sideView: SideView;
  centerView: CenterView;
  isResizingSide: boolean;
  isResizingSource: boolean;
  headerActions: ReactNode;
  sidebarBody: ReactNode;
  onToggleSidebar: () => void;
  onSideViewChange: (view: SideView) => void;
  onOpenSettings: () => void;
  onExplorerBlankPointer: (event: MouseEvent<HTMLDivElement>) => void;
  onResizeSide: (clientX: number) => void;
  onResetSideWidth: () => void;
  onNudgeSideWidth: (delta: number, edge?: 'min' | 'max') => void;
  onCenterViewChange: (view: CenterView) => void;
  onNewChat: () => void;
  errorBanner: ReactNode;
  centerBody: ReactNode;
  onResizeSource: (clientX: number) => void;
  onResetSourceWidth: () => void;
  onNudgeSourceWidth: (delta: number, edge?: 'min' | 'max') => void;
  viewer: ReactNode;
}) {
  return (
    <div
      className={[
        'appBody',
        sidebarCollapsed ? 'appBody--sidebarCollapsed' : '',
        viewerCollapsed ? 'appBody--viewerCollapsed' : '',
        viewerExpanded && !viewerCollapsed ? 'appBody--viewerExpanded' : '',
      ].filter(Boolean).join(' ')}
      ref={workspaceRef}
      style={{ '--source-pane-width': `${sourcePaneWidth}%`, '--side-panel-width': `${sidePanelWidth}px` } as CSSProperties}
    >
      <aside className={sidebarCollapsed ? 'sidePanel sidePanel--collapsed' : 'sidePanel'}>
        <div className="sidePanelHeader">
          <button
            type="button"
            className="ghostIcon"
            onClick={onToggleSidebar}
            title={sidebarCollapsed ? 'Show sidebar' : 'Hide sidebar'}
            aria-label={sidebarCollapsed ? 'Show sidebar' : 'Hide sidebar'}
            aria-pressed={!sidebarCollapsed}
          >
            {sidebarCollapsed ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />}
          </button>
          {!sidebarCollapsed ? (
            <>
              <nav className="sideViewNav" aria-label="Sidebar views">
                {([
                  ['explorer', 'Explorer', Folder],
                  ['chats', 'Chats', MessageSquareText],
                  ['convert', 'Convert PDF', FileInput],
                ] as const).map(([view, label, Icon]) => (
                  <button
                    className={`ghostIcon sideViewButton${sideView === view ? ' active' : ''}`}
                    key={view}
                    onClick={() => onSideViewChange(view)}
                    title={label}
                    aria-label={label}
                    aria-pressed={sideView === view}
                  >
                    <Icon size={15} />
                  </button>
                ))}
              </nav>
              <div className="sidePanelActions">
                {headerActions}
                <button className="ghostIcon" onClick={onOpenSettings} title="Settings" aria-label="Settings"><Settings size={15} /></button>
              </div>
            </>
          ) : null}
        </div>
        {!sidebarCollapsed ? (
          <div
            className={`sidePanelBody${sideView === 'explorer' ? ' sidePanelBody--explorer' : ''}${sideView === 'chats' ? ' sidePanelBody--chats' : ''}`}
            tabIndex={sideView === 'explorer' ? -1 : undefined}
            onMouseDown={sideView === 'explorer' ? onExplorerBlankPointer : undefined}
          >
            {sidebarBody}
          </div>
        ) : null}
      </aside>

      {!sidebarCollapsed ? (
        <div
          className={isResizingSide ? 'paneDivider sideDivider resizing' : 'paneDivider sideDivider'}
          role="separator"
          aria-label="Resize side panel"
          aria-orientation="vertical"
          tabIndex={0}
          onDoubleClick={onResetSideWidth}
          onKeyDown={(event: KeyboardEvent<HTMLDivElement>) => {
            if (event.key === 'ArrowLeft') onNudgeSideWidth(-16);
            if (event.key === 'ArrowRight') onNudgeSideWidth(16);
            if (event.key === 'Home') onNudgeSideWidth(0, 'min');
            if (event.key === 'End') onNudgeSideWidth(0, 'max');
          }}
          onPointerDown={(event) => {
            event.preventDefault();
            onResizeSide(event.clientX);
          }}
        />
      ) : null}

      {!(viewerExpanded && !viewerCollapsed) ? (
        <main className="centerPane">
          <header className="centerHeader">
            <div className="centerViewToggle" role="group" aria-label="Center workspace">
              <button
                type="button"
                className={centerView === 'chat' ? 'active' : ''}
                onClick={() => onCenterViewChange('chat')}
                aria-pressed={centerView === 'chat'}
              >
                Chat
              </button>
              <button
                type="button"
                className={centerView === 'search' ? 'active' : ''}
                onClick={() => onCenterViewChange('search')}
                aria-pressed={centerView === 'search'}
              >
                Search
              </button>
            </div>
            {centerView === 'chat' ? (
              <button className="centerNewChat" onClick={onNewChat} title="Start a new chat"><Plus size={14} />New chat</button>
            ) : null}
          </header>
          {errorBanner}
          {centerBody}
        </main>
      ) : null}

      {!viewerCollapsed && !viewerExpanded ? (
        <div
          className={isResizingSource ? 'paneDivider resizing' : 'paneDivider'}
          role="separator"
          aria-label="Resize Source Document pane"
          aria-orientation="vertical"
          tabIndex={0}
          onDoubleClick={onResetSourceWidth}
          onKeyDown={(event: KeyboardEvent<HTMLDivElement>) => {
            if (event.key === 'ArrowLeft') onNudgeSourceWidth(4);
            if (event.key === 'ArrowRight') onNudgeSourceWidth(-4);
            if (event.key === 'Home') onNudgeSourceWidth(0, 'min');
            if (event.key === 'End') onNudgeSourceWidth(0, 'max');
          }}
          onPointerDown={(event) => {
            event.preventDefault();
            onResizeSource(event.clientX);
          }}
        />
      ) : null}

      {viewer}
    </div>
  );
}
