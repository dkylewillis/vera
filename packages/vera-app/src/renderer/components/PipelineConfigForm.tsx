import type { PipelineDescriptor, PipelineFieldDescriptor, PipelineOptions, JsonValue } from '../../shared/contracts';

function fieldHelp(field: PipelineFieldDescriptor): string {
  const parts = [field.description?.trim() || '', field.unit ? `Unit: ${field.unit}` : '']
    .filter(Boolean);
  return parts.join(' ');
}

function coerceNumber(value: string, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function defaultFor(field: PipelineFieldDescriptor): JsonValue {
  if (field.default === undefined) {
    if (field.type === 'boolean') return false;
    if (field.type === 'integer' || field.type === 'number') return 0;
    return '';
  }
  return field.default;
}

export function mergePipelineFieldValues(
  descriptor: PipelineDescriptor | null | undefined,
  saved: PipelineOptions | null | undefined,
): PipelineOptions {
  if (!descriptor) return { ...(saved || {}) };
  const merged: PipelineOptions = {};
  for (const field of descriptor.fields) {
    const savedValue = saved?.[field.key];
    merged[field.key] = savedValue === undefined ? defaultFor(field) : savedValue;
  }
  return merged;
}

export function PipelineConfigForm({
  descriptor,
  values,
  disabled = false,
  onChange,
}: {
  descriptor: PipelineDescriptor | null;
  values: PipelineOptions;
  disabled?: boolean;
  onChange: (next: PipelineOptions) => void;
}) {
  if (!descriptor) {
    return <p className="sideMuted">Pipeline settings will appear once descriptors load.</p>;
  }

  if (!descriptor.fields.length) {
    return (
      <p className="sideMuted">
        {descriptor.notes?.length
          ? descriptor.notes.join(' ')
          : 'This pipeline does not advertise Convert settings.'}
      </p>
    );
  }

  function updateField(key: string, value: JsonValue) {
    onChange({ ...values, [key]: value });
  }

  return (
    <div className="pipelineConfigForm">
      <div className="convertGrid">
        {descriptor.fields.map((field) => {
          const help = fieldHelp(field);
          const current = values[field.key] ?? defaultFor(field);
          if (field.type === 'boolean') {
            return (
              <label className="miniCheck" key={field.key} title={help || undefined}>
                <input
                  type="checkbox"
                  checked={Boolean(current)}
                  disabled={disabled}
                  onChange={(event) => updateField(field.key, event.target.checked)}
                />
                <span>{field.label}{field.unit ? ` (${field.unit})` : ''}</span>
              </label>
            );
          }
          if (field.type === 'enum') {
            return (
              <label className="miniField" key={field.key} title={help || undefined}>
                <span>{field.label}{field.unit ? ` (${field.unit})` : ''}</span>
                <select
                  value={String(current ?? '')}
                  disabled={disabled}
                  onChange={(event) => updateField(field.key, event.target.value)}
                >
                  {(field.choices || []).map((choice) => (
                    <option key={choice.value} value={choice.value}>{choice.label}</option>
                  ))}
                </select>
              </label>
            );
          }
          if (field.type === 'integer' || field.type === 'number') {
            const fallback = typeof defaultFor(field) === 'number' ? Number(defaultFor(field)) : 0;
            return (
              <label className="miniField" key={field.key} title={help || undefined}>
                <span>{field.label}{field.unit ? ` (${field.unit})` : ''}</span>
                <input
                  className="numberInput"
                  type="number"
                  min={field.minimum ?? undefined}
                  max={field.maximum ?? undefined}
                  step={field.step ?? (field.type === 'integer' ? 1 : 0.1)}
                  value={typeof current === 'number' ? current : fallback}
                  disabled={disabled}
                  onChange={(event) => updateField(
                    field.key,
                    field.type === 'integer'
                      ? Math.trunc(coerceNumber(event.target.value, fallback))
                      : coerceNumber(event.target.value, fallback),
                  )}
                />
              </label>
            );
          }
          return (
            <label className="miniField" key={field.key} title={help || undefined}>
              <span>{field.label}{field.unit ? ` (${field.unit})` : ''}</span>
              <input
                type="text"
                value={String(current ?? '')}
                placeholder={field.placeholder || undefined}
                disabled={disabled}
                onChange={(event) => updateField(field.key, event.target.value)}
              />
            </label>
          );
        })}
      </div>
      {descriptor.notes?.length ? (
        <p className="sideMuted">{descriptor.notes.join(' ')}</p>
      ) : null}
    </div>
  );
}
