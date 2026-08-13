import { useEffect, useRef, type Dispatch, type SetStateAction } from 'react';
import type { AppSettings, PipelineDescriptor, Session } from '../types';

export function fallbackPipelineDescriptors(pipelines: string[]): PipelineDescriptor[] {
  return pipelines.map((spec) => ({
    provider: spec,
    variant: '',
    spec,
    label: spec,
    description: '',
    installed: true,
    capabilities: {},
    fields: [],
    notes: [],
  }));
}

export function useAppBootstrap(options: {
  applySettings: (saved: AppSettings) => void;
  setEmbeddingProviders: Dispatch<SetStateAction<string[]>>;
  setIngestPipelineDescriptors: Dispatch<SetStateAction<PipelineDescriptor[]>>;
  setSessions: Dispatch<SetStateAction<Session[]>>;
  loadFolders: (isCanceled: () => boolean) => Promise<void>;
}): void {
  const optionsRef = useRef(options);
  optionsRef.current = options;

  useEffect(() => {
    let canceled = false;
    async function loadSettings() {
      const saved = await window.vera.getSettings();
      if (canceled) return;
      optionsRef.current.applySettings(saved);
    }
    async function loadEmbeddingProviders() {
      const response = await window.vera.request<{ providers: string[] }>({
        action: 'list_embedding_providers',
      });
      if (!canceled && response.ok) {
        optionsRef.current.setEmbeddingProviders(response.result?.providers ?? []);
      }
    }
    async function loadIngestPipelines() {
      const response = await window.vera.request<{ pipelines: PipelineDescriptor[] }>({
        action: 'describe_ingest_pipelines',
      });
      if (canceled) return;
      if (response.ok && response.result?.pipelines?.length) {
        optionsRef.current.setIngestPipelineDescriptors(response.result.pipelines);
        return;
      }
      const fallback = await window.vera.request<{ pipelines: string[] }>({
        action: 'list_ingest_pipelines',
      });
      if (!canceled && fallback.ok) {
        const pipelines = fallback.result?.pipelines?.length
          ? fallback.result.pipelines
          : ['pymupdf'];
        optionsRef.current.setIngestPipelineDescriptors(fallbackPipelineDescriptors(pipelines));
      }
    }
    async function loadSessions() {
      const saved = await window.vera.getSessions();
      if (canceled) return;
      optionsRef.current.setSessions(saved);
    }
    void loadSettings();
    void loadEmbeddingProviders();
    void loadIngestPipelines();
    void loadSessions();
    void optionsRef.current.loadFolders(() => canceled);
    return () => {
      canceled = true;
    };
  }, []);
}
