import { mkdirSync, mkdtempSync, unlinkSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const require = createRequire(import.meta.url);
const {
  REQUIRED_MINILM_FILES,
  REQUIRED_DOCLING_FILES,
  findBundledMinilm,
  findBundledDocling,
  minilmCandidates,
  doclingCandidates,
} = require('../scripts/verify-packaged-sidecar.cjs') as {
  REQUIRED_MINILM_FILES: string[];
  REQUIRED_DOCLING_FILES: string[];
  findBundledMinilm: (sidecarExe: string) => string | null;
  findBundledDocling: (sidecarExe: string) => string | null;
  minilmCandidates: (sidecarExe: string) => string[];
  doclingCandidates: (sidecarExe: string) => string[];
};

function writeMinilmSnapshot(directory: string): void {
  mkdirSync(directory, { recursive: true });
  for (const name of REQUIRED_MINILM_FILES) {
    writeFileSync(join(directory, name), 'stub');
  }
}

function writeDoclingSnapshot(directory: string): void {
  mkdirSync(directory, { recursive: true });
  for (const name of REQUIRED_DOCLING_FILES) {
    const target = join(directory, name);
    mkdirSync(join(target, '..'), { recursive: true });
    writeFileSync(target, 'stub');
  }
}

describe('packaged sidecar MiniLM layout', () => {
  it('looks next to the sidecar and under _internal', () => {
    const sidecarExe = join('build', 'sidecar', 'vera-sidecar', 'vera-sidecar.exe');
    expect(minilmCandidates(sidecarExe)).toEqual([
      join('build', 'sidecar', 'vera-sidecar', 'sentence_transformers_models', 'all-MiniLM-L6-v2'),
      join(
        'build',
        'sidecar',
        'vera-sidecar',
        '_internal',
        'sentence_transformers_models',
        'all-MiniLM-L6-v2',
      ),
    ]);
  });

  it('accepts a complete onedir snapshot beside the executable', () => {
    const root = mkdtempSync(join(tmpdir(), 'vera-minilm-onedir-'));
    const sidecarExe = join(root, 'vera-sidecar');
    writeFileSync(sidecarExe, '');
    const snapshot = join(root, 'sentence_transformers_models', 'all-MiniLM-L6-v2');
    writeMinilmSnapshot(snapshot);
    expect(findBundledMinilm(sidecarExe)).toBe(snapshot);
  });

  it('accepts a PyInstaller _internal snapshot', () => {
    const root = mkdtempSync(join(tmpdir(), 'vera-minilm-internal-'));
    const sidecarExe = join(root, 'vera-sidecar');
    writeFileSync(sidecarExe, '');
    const snapshot = join(root, '_internal', 'sentence_transformers_models', 'all-MiniLM-L6-v2');
    writeMinilmSnapshot(snapshot);
    expect(findBundledMinilm(sidecarExe)).toBe(snapshot);
  });

  it('rejects a snapshot missing tokenizer.json', () => {
    const root = mkdtempSync(join(tmpdir(), 'vera-minilm-incomplete-'));
    const sidecarExe = join(root, 'vera-sidecar');
    writeFileSync(sidecarExe, '');
    const snapshot = join(root, 'sentence_transformers_models', 'all-MiniLM-L6-v2');
    mkdirSync(snapshot, { recursive: true });
    for (const name of REQUIRED_MINILM_FILES.filter((item) => item !== 'tokenizer.json')) {
      writeFileSync(join(snapshot, name), 'stub');
    }
    expect(findBundledMinilm(sidecarExe)).toBeNull();
  });
});

describe('packaged sidecar Docling layout', () => {
  it('looks next to the sidecar and under _internal', () => {
    const sidecarExe = join('build', 'sidecar', 'vera-sidecar', 'vera-sidecar.exe');
    expect(doclingCandidates(sidecarExe)).toEqual([
      join('build', 'sidecar', 'vera-sidecar', 'docling-artifacts'),
      join('build', 'sidecar', 'vera-sidecar', '_internal', 'docling-artifacts'),
    ]);
  });

  it('accepts a complete onedir snapshot beside the executable', () => {
    const root = mkdtempSync(join(tmpdir(), 'vera-docling-onedir-'));
    const sidecarExe = join(root, 'vera-sidecar');
    writeFileSync(sidecarExe, '');
    const snapshot = join(root, 'docling-artifacts');
    writeDoclingSnapshot(snapshot);
    expect(findBundledDocling(sidecarExe)).toBe(snapshot);
  });

  it('accepts a PyInstaller _internal snapshot', () => {
    const root = mkdtempSync(join(tmpdir(), 'vera-docling-internal-'));
    const sidecarExe = join(root, 'vera-sidecar');
    writeFileSync(sidecarExe, '');
    const snapshot = join(root, '_internal', 'docling-artifacts');
    writeDoclingSnapshot(snapshot);
    expect(findBundledDocling(sidecarExe)).toBe(snapshot);
  });

  it('rejects a snapshot missing tableformer weights', () => {
    const root = mkdtempSync(join(tmpdir(), 'vera-docling-incomplete-'));
    const sidecarExe = join(root, 'vera-sidecar');
    writeFileSync(sidecarExe, '');
    const snapshot = join(root, 'docling-artifacts');
    writeDoclingSnapshot(snapshot);
    const missing = REQUIRED_DOCLING_FILES.find((name) => name.endsWith('tableformer_accurate.safetensors'));
    expect(missing).toBeTruthy();
    unlinkSync(join(snapshot, missing!));
    expect(findBundledDocling(sidecarExe)).toBeNull();
  });
});
