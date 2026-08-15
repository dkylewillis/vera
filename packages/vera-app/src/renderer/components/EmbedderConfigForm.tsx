import { PipelineConfigForm } from './PipelineConfigForm';
import type { EmbedderDescriptor, PipelineDescriptor, PipelineOptions } from '../../shared/contracts';

export function embedderAsPipelineDescriptor(
  descriptor: EmbedderDescriptor | null | undefined,
): PipelineDescriptor | null {
  if (!descriptor) return null;
  return {
    provider: descriptor.provider,
    variant: '',
    spec: descriptor.provider,
    label: descriptor.label,
    description: descriptor.description,
    installed: descriptor.installed,
    capabilities: {},
    fields: descriptor.fields || [],
    notes: descriptor.notes,
    source: descriptor.source,
  };
}

export function EmbedderConfigForm({
  descriptor,
  values,
  disabled = false,
  onChange,
}: {
  descriptor: EmbedderDescriptor | null;
  values: PipelineOptions;
  disabled?: boolean;
  onChange: (next: PipelineOptions) => void;
}) {
  return (
    <PipelineConfigForm
      descriptor={embedderAsPipelineDescriptor(descriptor)}
      values={values}
      disabled={disabled}
      onChange={onChange}
    />
  );
}
