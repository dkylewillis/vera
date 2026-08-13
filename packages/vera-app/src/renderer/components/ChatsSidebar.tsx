import { MessageSquareText, Plus, Trash2 } from 'lucide-react';
import type { Session } from '../types';

export function ChatsSidebar({
  sessions,
  activeSessionId,
  onNewSession,
  onLoadSession,
  onRemoveSession,
}: {
  sessions: Session[];
  activeSessionId: string | null;
  onNewSession: () => void;
  onLoadSession: (session: Session) => void;
  onRemoveSession: (id: string) => void;
}) {
  return (
    <div className="chatsView">
      <button className="sidePrimary" onClick={onNewSession}><Plus size={15} />New chat</button>
      {sessions.length === 0 ? (
        <p className="sideMuted">No conversations yet.</p>
      ) : (
        sessions.map((s) => (
          <div key={s.id} className={s.id === activeSessionId ? 'chatRow active' : 'chatRow'}>
            <button className="chatRowTitle" onClick={() => onLoadSession(s)} title={s.title}>
              <MessageSquareText size={14} />
              <span>{s.title}</span>
            </button>
            <button className="ghostIcon tiny" onClick={() => onRemoveSession(s.id)} title="Delete chat"><Trash2 size={12} /></button>
          </div>
        ))
      )}
    </div>
  );
}
