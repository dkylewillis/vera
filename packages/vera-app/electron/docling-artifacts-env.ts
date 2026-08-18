import { existsSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';

/** Files that must exist before a freeze is treated as a complete offline cache. */
export const BUNDLED_DOCLING_FILES = [
  join('docling-project--docling-layout-heron-onnx', 'config.json'),
  join('docling-project--docling-layout-heron-onnx', 'model.onnx'),
  join('docling-project--docling-layout-heron-onnx', 'preprocessor_config.json'),
  join('docling-project--docling-models', 'model_artifacts', 'tableformer', 'accurate', 'tm_config.json'),
  join(
    'docling-project--docling-models',
    'model_artifacts',
    'tableformer',
    'accurate',
    'tableformer_accurate.safetensors',
  ),
];

export interface DoclingArtifactsEnvOptions {
  isPackaged: boolean;
  userDataPath: string;
  sidecarDir: string;
}

export function userDataDoclingArtifactsPath(userDataPath: string): string {
  return join(userDataPath, 'docling-artifacts');
}

export function doclingArtifactsComplete(root: string): boolean {
  return BUNDLED_DOCLING_FILES.every((relativePath) => existsSync(join(root, relativePath)));
}

export function bundledDoclingArtifactsPath(
  options: Pick<DoclingArtifactsEnvOptions, 'isPackaged' | 'sidecarDir'>,
): string | undefined {
  if (!options.isPackaged) return undefined;
  const candidates = [
    join(options.sidecarDir, 'docling-artifacts'),
    join(options.sidecarDir, '_internal', 'docling-artifacts'),
  ];
  return candidates.find((candidate) => doclingArtifactsComplete(candidate));
}

/**
 * Packaged builds read bundled snapshots (often read-only) and keep Hub writes
 * under Electron userData. Explicit DOCLING_ARTIFACTS_PATH always wins.
 */
export function applyDoclingArtifactsEnv(
  env: NodeJS.ProcessEnv,
  options: DoclingArtifactsEnvOptions,
): void {
  const fromEnv = (env.DOCLING_ARTIFACTS_PATH || '').trim();
  const writableCache = userDataDoclingArtifactsPath(options.userDataPath);
  if (fromEnv) {
    env.DOCLING_ARTIFACTS_PATH = fromEnv;
    mkdirSync(fromEnv, { recursive: true });
  } else {
    const bundled = bundledDoclingArtifactsPath(options);
    if (bundled) {
      env.DOCLING_ARTIFACTS_PATH = bundled;
    } else {
      env.DOCLING_ARTIFACTS_PATH = writableCache;
      mkdirSync(writableCache, { recursive: true });
    }
  }
  if (!(env.HF_HOME || '').trim()) {
    env.HF_HOME = fromEnv || writableCache;
    mkdirSync(env.HF_HOME, { recursive: true });
  }
}
