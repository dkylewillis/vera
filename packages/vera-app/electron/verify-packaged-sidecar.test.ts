import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const require = createRequire(import.meta.url);
const {
  REQUIRED_MINILM_FILES,
  findBundledMinilm,
  findForbiddenRuntime,
  minilmCandidates,
} = require('../scripts/verify-packaged-sidecar.cjs') as {
  REQUIRED_MINILM_FILES: string[];
  findBundledMinilm: (sidecarExe: string) => string | null;
  findForbiddenRuntime: (sidecarExe: string) => string | null;
  minilmCandidates: (sidecarExe: string) => string[];
};

function writeMinilmSnapshot(directory: string): void {
  mkdirSync(directory, { recursive: true });
  for (const name of REQUIRED_MINILM_FILES) {
    writeFileSync(join(directory, name), 'stub');
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

  it('rejects a freeze that still contains Torch', () => {
    const root = mkdtempSync(join(tmpdir(), 'vera-minilm-torch-'));
    const sidecarExe = join(root, 'vera-sidecar');
    writeFileSync(sidecarExe, '');
    mkdirSync(join(root, '_internal', 'torch'), { recursive: true });
    expect(findForbiddenRuntime(sidecarExe)).toBe(join(root, '_internal', 'torch'));
  });

  it('accepts an ONNX-only freeze', () => {
    const root = mkdtempSync(join(tmpdir(), 'vera-minilm-onnx-only-'));
    const sidecarExe = join(root, 'vera-sidecar');
    writeFileSync(sidecarExe, '');
    writeMinilmSnapshot(join(root, 'sentence_transformers_models', 'all-MiniLM-L6-v2'));
    expect(findForbiddenRuntime(sidecarExe)).toBeNull();
  });
});
