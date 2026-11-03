import { useEffect, useState } from 'react';
import { ListChecks, Plus, RefreshCw, Search, X } from 'lucide-react';
import { PRO_PRESET_KEY } from '../../shared/pro';
import { formatTimeAgo } from '../lib/formatting';
import { canListModels, isModelListStale, MODEL_LIST_MAX_AGE_MS, providerDisplayName } from '../lib/providers';
import type { ProviderProfile } from '../types';

/** Providers whose model list is old enough to re-check when a model list opens. */
export function staleModelProviderIds(providers: ProviderProfile[], now = Date.now()): string[] {
  return providers
    .filter((profile) => profile.preset_key !== PRO_PRESET_KEY)
    .filter((profile) => canListModels(profile) && isModelListStale(profile, MODEL_LIST_MAX_AGE_MS, now))
    .map((profile) => profile.id);
}

export function ModelManager({
  providers,
  busyProviderIds,
  message,
  onToggle,
  onRefresh,
  onAddProvider,
  onClose,
}: {
  providers: ProviderProfile[];
  busyProviderIds: string[];
  message: string;
  onToggle: (providerId: string, model: string) => void;
  onRefresh: (providerIds: string[]) => void;
  onAddProvider: () => void;
  onClose: () => void;
}) {
  const [filter, setFilter] = useState('');
  const normalizedFilter = filter.trim().toLowerCase();

  useEffect(() => {
    const stale = staleModelProviderIds(providers);
    if (stale.length) onRefresh(stale);
  }, []);

  return (
    <div className="modalBackdrop" onClick={onClose}>
      <div className="modal modelManagerModal" onClick={(event) => event.stopPropagation()}>
        <header className="modalHeader">
          <h2><ListChecks size={18} />Models</h2>
          <button className="iconAction" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </header>
        <div className="modelManagerSearch">
          <Search size={14} />
          <input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Search models" autoFocus />
        </div>
        <div className="modelManagerBody">
          {providers.length === 0 ? <p className="mutedText">Add a provider to discover models.</p> : null}
          {providers.map((profile) => {
            const busy = busyProviderIds.includes(profile.id);
            const models = Array.from(new Set([...(profile.available_models ?? []), ...profile.models]))
              .filter((model) => !normalizedFilter || model.toLowerCase().includes(normalizedFilter))
              .sort((a, b) => a.localeCompare(b));
            let updated = '';
            if (busy) updated = 'Checking…';
            else if (profile.models_refreshed_at) updated = `Updated ${formatTimeAgo(profile.models_refreshed_at)}`;
            return (
              <section className="modelManagerGroup" key={profile.id}>
                <div className="modelManagerGroupHead">
                  <span>{providerDisplayName(profile)}</span>
                  <span className="modelManagerGroupMeta">
                    {updated ? <small>{updated}</small> : null}
                    <button
                      type="button"
                      className="ghostIcon tiny visible"
                      onClick={() => onRefresh([profile.id])}
                      disabled={busyProviderIds.length > 0}
                      title="Check for new models"
                      aria-label={`Check ${providerDisplayName(profile)} for new models`}
                    >
                      <RefreshCw size={13} className={busy ? 'spinning' : ''} />
                    </button>
                  </span>
                </div>
                {models.length ? models.map((model) => (
                  <label className="modelManagerRow" key={`${profile.id}:${model}`}>
                    <span>{model}</span>
                    <input
                      type="checkbox"
                      checked={profile.models.includes(model)}
                      onChange={() => onToggle(profile.id, model)}
                      aria-label={`Enable ${model}`}
                    />
                  </label>
                )) : (
                  <p className="modelManagerEmpty">
                    {normalizedFilter
                      ? 'No matching models.'
                      : busy ? 'Loading models…' : 'No models yet. Add a key or check the server in Settings.'}
                  </p>
                )}
              </section>
            );
          })}
        </div>
        <footer className="modalFooter">
          <button className="modelManagerAdd" onClick={onAddProvider}><Plus size={14} />Add provider…</button>
          <span className="modalMessage">{message}</span>
        </footer>
      </div>
    </div>
  );
}
