import { useEffect, useRef, type Dispatch, type SetStateAction } from 'react';
import { SIDECAR_ACTIONS } from '../../shared/protocol';
import type { AppSettings, EmbedderDescriptor, PipelineDescriptor, Session } from '../types';

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
    source: spec === 'pymupdf' || spec === 'docling' ? 'bundled' : 'external',
  }));
}

export async function loadEmbeddingDescriptors(): Promise<EmbedderDescriptor[]> {
  const described = await window.vera.request<{ providers: EmbedderDescriptor[] }>({
    action: SIDECAR_ACTIONS.describeEmbeddingProviders,
  });
  return described.ok ? described.result?.providers ?? [] : [];
}

export async function loadIngestPipelineDescriptors(): Promise<PipelineDescriptor[]> {
  const response = await window.vera.request<{ pipelines: PipelineDescriptor[] }>({
    action: SIDECAR_ACTIONS.describeIngestPipelines,
  });
  if (response.ok && response.result?.pipelines?.length) {
    return response.result.pipelines;
  }
  const fallback = await window.vera.request<{ pipelines: string[] }>({
    action: SIDECAR_ACTIONS.listIngestPipelines,
  });
  const pipelines = fallback.ok && fallback.result?.pipelines?.length
    ? fallback.result.pipelines
    : ['pymupdf'];
  return fallbackPipelineDescriptors(pipelines);
}

export function useAppBootstrap(options: {
  applySettings: (saved: AppSettings) => void;
  setEmbeddingProviders: Dispatch<SetStateAction<string[]>>;
  setEmbeddingDescriptors: Dispatch<SetStateAction<EmbedderDescriptor[]>>;
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
      const described = await window.vera.request<{ providers: EmbedderDescriptor[] }>({
        action: SIDECAR_ACTIONS.describeEmbeddingProviders,
      });
      if (!canceled && described.ok && described.result?.providers?.length) {
        optionsRef.current.setEmbeddingDescriptors(described.result.providers);
        optionsRef.current.setEmbeddingProviders(
          described.result.providers.map((item) => item.provider),
        );
        return;
      }
      const response = await window.vera.request<{ providers: string[] }>({
        action: SIDECAR_ACTIONS.listEmbeddingProviders,
      });
      if (!canceled && response.ok) {
        optionsRef.current.setEmbeddingProviders(response.result?.providers ?? []);
      }
    }
    async function loadIngestPipelines() {
      const descriptors = await loadIngestPipelineDescriptors();
      if (!canceled) {
        optionsRef.current.setIngestPipelineDescriptors(descriptors);
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
