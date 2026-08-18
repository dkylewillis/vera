import { existsSync, mkdirSync, unlinkSync, writeFileSync } from 'node:fs';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import {
  BUNDLED_DOCLING_FILES,
  applyDoclingArtifactsEnv,
  bundledDoclingArtifactsPath,
  userDataDoclingArtifactsPath,
} from './docling-artifacts-env.js';

function writeDoclingSnapshot(directory: string): void {
  mkdirSync(directory, { recursive: true });
  for (const name of BUNDLED_DOCLING_FILES) {
    const target = join(directory, name);
    mkdirSync(join(target, '..'), { recursive: true });
    writeFileSync(target, 'stub');
  }
}

describe('applyDoclingArtifactsEnv', () => {
  it('uses the userData cache when unpackaged', () => {
    const root = mkdtempSync(join(tmpdir(), 'vera-docling-env-dev-'));
    const userDataPath = join(root, 'userData');
    const sidecarDir = join(root, 'sidecar');
    writeDoclingSnapshot(join(sidecarDir, 'docling-artifacts'));
    mkdirSync(userDataPath, { recursive: true });

    const env: NodeJS.ProcessEnv = {};
    applyDoclingArtifactsEnv(env, { isPackaged: false, userDataPath, sidecarDir });

    expect(bundledDoclingArtifactsPath({ isPackaged: false, sidecarDir })).toBeUndefined();
    expect(env.DOCLING_ARTIFACTS_PATH).toBe(userDataDoclingArtifactsPath(userDataPath));
    expect(env.HF_HOME).toBe(userDataDoclingArtifactsPath(userDataPath));
    expect(existsSync(userDataDoclingArtifactsPath(userDataPath))).toBe(true);
  });

  it('points packaged Convert at a complete onedir freeze and Hub writes at userData', () => {
    const root = mkdtempSync(join(tmpdir(), 'vera-docling-env-onedir-'));
    const userDataPath = join(root, 'userData');
    const sidecarDir = join(root, 'sidecar');
    const bundled = join(sidecarDir, 'docling-artifacts');
    writeDoclingSnapshot(bundled);
    mkdirSync(userDataPath, { recursive: true });

    const env: NodeJS.ProcessEnv = {};
    applyDoclingArtifactsEnv(env, { isPackaged: true, userDataPath, sidecarDir });

    expect(env.DOCLING_ARTIFACTS_PATH).toBe(bundled);
    expect(env.HF_HOME).toBe(userDataDoclingArtifactsPath(userDataPath));
    expect(existsSync(userDataDoclingArtifactsPath(userDataPath))).toBe(true);
  });

  it('accepts a complete PyInstaller _internal freeze', () => {
    const root = mkdtempSync(join(tmpdir(), 'vera-docling-env-internal-'));
    const userDataPath = join(root, 'userData');
    const sidecarDir = join(root, 'sidecar');
    const bundled = join(sidecarDir, '_internal', 'docling-artifacts');
    writeDoclingSnapshot(bundled);
    mkdirSync(userDataPath, { recursive: true });

    const env: NodeJS.ProcessEnv = {};
    applyDoclingArtifactsEnv(env, { isPackaged: true, userDataPath, sidecarDir });

    expect(env.DOCLING_ARTIFACTS_PATH).toBe(bundled);
    expect(env.HF_HOME).toBe(userDataDoclingArtifactsPath(userDataPath));
  });

  it('falls back to userData when the packaged freeze is incomplete', () => {
    const root = mkdtempSync(join(tmpdir(), 'vera-docling-env-incomplete-'));
    const userDataPath = join(root, 'userData');
    const sidecarDir = join(root, 'sidecar');
    const bundled = join(sidecarDir, 'docling-artifacts');
    writeDoclingSnapshot(bundled);
    const missing = BUNDLED_DOCLING_FILES.find((name) =>
      name.endsWith('tableformer_accurate.safetensors'),
    );
    expect(missing).toBeTruthy();
    unlinkSync(join(bundled, missing!));
    mkdirSync(userDataPath, { recursive: true });

    const env: NodeJS.ProcessEnv = {};
    applyDoclingArtifactsEnv(env, { isPackaged: true, userDataPath, sidecarDir });

    expect(env.DOCLING_ARTIFACTS_PATH).toBe(userDataDoclingArtifactsPath(userDataPath));
    expect(env.HF_HOME).toBe(userDataDoclingArtifactsPath(userDataPath));
  });

  it('lets an explicit artifacts path win over a complete freeze', () => {
    const root = mkdtempSync(join(tmpdir(), 'vera-docling-env-override-'));
    const userDataPath = join(root, 'userData');
    const sidecarDir = join(root, 'sidecar');
    const override = join(root, 'custom-cache');
    writeDoclingSnapshot(join(sidecarDir, 'docling-artifacts'));
    mkdirSync(userDataPath, { recursive: true });

    const env: NodeJS.ProcessEnv = { DOCLING_ARTIFACTS_PATH: override };
    applyDoclingArtifactsEnv(env, { isPackaged: true, userDataPath, sidecarDir });

    expect(env.DOCLING_ARTIFACTS_PATH).toBe(override);
    expect(env.HF_HOME).toBe(override);
    expect(existsSync(override)).toBe(true);
  });

  it('preserves an existing HF_HOME so Hub writes stay writable', () => {
    const root = mkdtempSync(join(tmpdir(), 'vera-docling-env-hf-'));
    const userDataPath = join(root, 'userData');
    const sidecarDir = join(root, 'sidecar');
    const hub = join(root, 'hub');
    const bundled = join(sidecarDir, 'docling-artifacts');
    writeDoclingSnapshot(bundled);
    mkdirSync(userDataPath, { recursive: true });

    const env: NodeJS.ProcessEnv = { HF_HOME: hub };
    applyDoclingArtifactsEnv(env, { isPackaged: true, userDataPath, sidecarDir });

    expect(env.DOCLING_ARTIFACTS_PATH).toBe(bundled);
    expect(env.HF_HOME).toBe(hub);
    expect(existsSync(hub)).toBe(false);
  });

  it('treats a blank artifacts path as unset', () => {
    const root = mkdtempSync(join(tmpdir(), 'vera-docling-env-blank-'));
    const userDataPath = join(root, 'userData');
    mkdirSync(userDataPath, { recursive: true });

    const env: NodeJS.ProcessEnv = { DOCLING_ARTIFACTS_PATH: '   ' };
    applyDoclingArtifactsEnv(env, {
      isPackaged: false,
      userDataPath,
      sidecarDir: join(root, 'sidecar'),
    });

    expect(env.DOCLING_ARTIFACTS_PATH).toBe(userDataDoclingArtifactsPath(userDataPath));
  });
});
