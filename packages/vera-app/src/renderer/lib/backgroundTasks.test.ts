import { describe, expect, it } from 'vitest';
import {
  backgroundTasksReducer,
  formatBackgroundTask,
  taskIsDeterminate,
  type BackgroundTask,
} from './backgroundTasks';

const indexTask: BackgroundTask = {
  id: 'index-1',
  kind: 'index',
  label: 'Building index',
  operation: 'build',
  path: 'C:\\library',
  phase: 'indexing',
  completed: 3,
  total: 10,
  currentItem: 'C:\\library\\manual.vera',
  chunks: 842,
  skipped: 1,
};

describe('backgroundTasksReducer', () => {
  it('tracks independent request-scoped tasks', () => {
    const conversion: BackgroundTask = {
      id: 'conversion-1',
      kind: 'conversion',
      label: 'Conversion',
      message: 'Starting…',
    };

    const started = backgroundTasksReducer([], { type: 'start', task: indexTask });
    const concurrent = backgroundTasksReducer(started, { type: 'start', task: conversion });
    const updated = backgroundTasksReducer(concurrent, {
      type: 'update',
      id: 'index-1',
      update: { completed: 4, chunks: 1_024 },
    });
    const finished = backgroundTasksReducer(updated, { type: 'finish', id: 'conversion-1' });

    expect(updated).toHaveLength(2);
    expect(updated[0]).toMatchObject({ id: 'index-1', completed: 4, chunks: 1_024 });
    expect(finished.map((task) => task.id)).toEqual(['index-1']);
  });
});

describe('background task status', () => {
  it('formats determinate indexing progress with useful details', () => {
    expect(taskIsDeterminate(indexTask)).toBe(true);
    expect(formatBackgroundTask(indexTask)).toBe(
      'Building index 3 of 10 · manual.vera · 842 chunks · 1 skipped',
    );
  });

  it('uses phase labels while totals are unavailable or work is publishing', () => {
    expect(formatBackgroundTask({ ...indexTask, phase: 'discovering', total: 0 }))
      .toBe('Discovering index files · manual.vera · 842 chunks · 1 skipped');
    expect(formatBackgroundTask({ ...indexTask, phase: 'finalizing', currentItem: undefined }))
      .toBe('Finalizing index · 842 chunks · 1 skipped');
  });

  it('formats Docling model prefetch as its own task', () => {
    expect(formatBackgroundTask({
      id: 'docling-1',
      kind: 'docling_prepare',
      label: 'Docling models',
      phase: 'preparing',
      message: 'Downloading Docling models (first run can take several minutes)…',
    })).toBe('Downloading Docling models (first run can take several minutes)…');
  });

  it('formats library inspection as its own determinate task', () => {
    expect(formatBackgroundTask({
      id: 'inspection-1',
      kind: 'inspection',
      label: 'Inspecting library',
      completed: 2,
      total: 5,
      currentItem: 'C:\\library\\water.vera',
      chunks: 320,
    })).toBe('Inspecting library 2 of 5 · water.vera · 320 chunks');
  });
});
