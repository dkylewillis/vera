import { useEffect, useState, type ReactNode } from 'react';
import {
  CheckCircle2,
  Copy,
  ExternalLink,
  Eye,
  EyeOff,
  Info,
  KeyRound,
  Trash2,
  TriangleAlert,
} from 'lucide-react';
import type { HelpLinkId } from '../../shared/help-links';

export type PillTone = 'good' | 'warn' | 'neutral' | 'accent' | 'danger';

export async function copyText(value: string): Promise<boolean> {
  if (!value || typeof navigator === 'undefined' || !navigator.clipboard?.writeText) return false;
  try {
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    return false;
  }
}

export function StatusPill({ tone = 'neutral', children }: { tone?: PillTone; children: ReactNode }) {
  return <span className={`statusPill statusPill--${tone}`}>{children}</span>;
}

export function ToggleSwitch({
  checked,
  onChange,
  label,
  disabled = false,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <input
      type="checkbox"
      role="switch"
      className="toggleSwitch"
      checked={checked}
      disabled={disabled}
      aria-label={label}
      onChange={(event) => onChange(event.target.checked)}
    />
  );
}

/** A labelled on/off setting. Clicking the text flips the switch too. */
export function ToggleRow({
  title,
  description,
  checked,
  onChange,
  disabled = false,
}: {
  title: string;
  description?: ReactNode;
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className={disabled ? 'settingRow disabled' : 'settingRow'}>
      <span className="settingRowText">
        <span className="settingRowTitle">{title}</span>
        {description ? <span className="settingRowDescription">{description}</span> : null}
      </span>
      <ToggleSwitch checked={checked} onChange={onChange} label={title} disabled={disabled} />
    </label>
  );
}

export function SettingsCard({
  title,
  description,
  icon,
  badge,
  actions,
  children,
  className = '',
}: {
  title?: ReactNode;
  description?: ReactNode;
  icon?: ReactNode;
  badge?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <section className={className ? `settingsCard ${className}` : 'settingsCard'}>
      {title ? (
        <header className="settingsCardHead">
          {icon ? <span className="settingsCardIcon" aria-hidden="true">{icon}</span> : null}
          <div className="settingsCardTitle">
            <h4>{title}{badge ? <> {badge}</> : null}</h4>
            {description ? <p>{description}</p> : null}
          </div>
          {actions ? <div className="settingsCardActions">{actions}</div> : null}
        </header>
      ) : null}
      {children ? <div className="settingsCardBody">{children}</div> : null}
    </section>
  );
}

export function Callout({
  tone = 'info',
  title,
  children,
}: {
  tone?: 'info' | 'good' | 'warn';
  title?: ReactNode;
  children?: ReactNode;
}) {
  const Icon = tone === 'warn' ? TriangleAlert : tone === 'good' ? CheckCircle2 : Info;
  return (
    <div className={`settingsCallout settingsCallout--${tone}`} role="note">
      <Icon size={16} aria-hidden="true" />
      <div>
        {title ? <strong>{title}</strong> : null}
        {children}
      </div>
    </div>
  );
}

export function HelpLinkButton({ link, children }: { link: HelpLinkId; children: ReactNode }) {
  return (
    <button type="button" className="settingsLink" onClick={() => void window.vera.openHelpLink(link)}>
      {children}
      <ExternalLink size={12} aria-hidden="true" />
    </button>
  );
}

/** Destructive button that asks for a second click before acting. */
export function ConfirmButton({
  label,
  confirmLabel,
  onConfirm,
  disabled = false,
}: {
  label: string;
  confirmLabel: string;
  onConfirm: () => void;
  disabled?: boolean;
}) {
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    if (!armed) return undefined;
    const timer = window.setTimeout(() => setArmed(false), 4000);
    return () => window.clearTimeout(timer);
  }, [armed]);
  return (
    <button
      type="button"
      className={armed ? 'secondaryAction compactAction danger armed' : 'secondaryAction compactAction danger'}
      disabled={disabled}
      onClick={() => {
        if (!armed) {
          setArmed(true);
          return;
        }
        setArmed(false);
        onConfirm();
      }}
    >
      <Trash2 size={13} />
      {armed ? confirmLabel : label}
    </button>
  );
}

/**
 * Password-style field for API keys and tokens. A saved secret is never shown;
 * the field offers Replace and Remove instead.
 */
export function SecretField({
  label,
  saved,
  placeholder,
  onSave,
  onClear,
  busy = false,
  savedLabel = 'Key saved',
  helpLink,
  helpLabel = 'Get a key',
  hint,
}: {
  label: string;
  saved: boolean;
  placeholder: string;
  onSave: (value: string) => Promise<boolean>;
  onClear?: () => void;
  busy?: boolean;
  savedLabel?: string;
  helpLink?: HelpLinkId;
  helpLabel?: string;
  hint?: ReactNode;
}) {
  const [value, setValue] = useState('');
  const [reveal, setReveal] = useState(false);
  const [replacing, setReplacing] = useState(false);
  const editing = !saved || replacing;

  async function save() {
    const trimmed = value.trim();
    if (!trimmed) return;
    if (await onSave(trimmed)) {
      setValue('');
      setReveal(false);
      setReplacing(false);
    }
  }

  return (
    <div className="secretField">
      <div className="secretFieldHead">
        <span className="secretFieldLabel">{label}</span>
        {helpLink ? <HelpLinkButton link={helpLink}>{helpLabel}</HelpLinkButton> : null}
      </div>
      {editing ? (
        <div className="secretFieldRow">
          <div className="pathInput secretFieldInput">
            <KeyRound size={14} aria-hidden="true" />
            <input
              type={reveal ? 'text' : 'password'}
              value={value}
              onChange={(event) => setValue(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  void save();
                }
              }}
              placeholder={placeholder}
              aria-label={label}
              autoComplete="off"
              spellCheck={false}
              disabled={busy}
            />
            <button
              type="button"
              className="secretFieldReveal"
              onClick={() => setReveal((current) => !current)}
              aria-label={reveal ? 'Hide' : 'Show'}
              title={reveal ? 'Hide' : 'Show'}
              disabled={!value}
            >
              {reveal ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </div>
          <button type="button" className="primaryAction compactAction" onClick={() => void save()} disabled={busy || !value.trim()}>
            Save
          </button>
          {replacing ? (
            <button
              type="button"
              className="secondaryAction compactAction"
              onClick={() => {
                setReplacing(false);
                setValue('');
              }}
              disabled={busy}
            >
              Cancel
            </button>
          ) : null}
        </div>
      ) : (
        <div className="secretFieldRow">
          <StatusPill tone="good"><CheckCircle2 size={12} />{savedLabel}</StatusPill>
          <span className="secretFieldMask" aria-hidden="true">••••••••••••</span>
          <span className="secretFieldSpacer" />
          <button type="button" className="secondaryAction compactAction" onClick={() => setReplacing(true)} disabled={busy}>
            Replace
          </button>
          {onClear ? (
            <button type="button" className="secondaryAction compactAction danger" onClick={onClear} disabled={busy}>
              <Trash2 size={13} />Remove
            </button>
          ) : null}
        </div>
      )}
      {hint ? <p className="secretFieldHint">{hint}</p> : null}
    </div>
  );
}

export function CopyField({
  label,
  value,
  emptyText = '',
  multiline = false,
}: {
  label?: string;
  value: string;
  emptyText?: string;
  multiline?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return undefined;
    const timer = window.setTimeout(() => setCopied(false), 1800);
    return () => window.clearTimeout(timer);
  }, [copied]);
  return (
    <div className="copyField">
      {label ? <span className="copyFieldLabel">{label}</span> : null}
      <div className={multiline ? 'copyFieldBox multiline' : 'copyFieldBox'}>
        {multiline ? <pre>{value || emptyText}</pre> : <code>{value || emptyText}</code>}
        <button
          type="button"
          className="secondaryAction compactAction"
          disabled={!value}
          onClick={() => void copyText(value).then(setCopied)}
          aria-label={label ? `Copy ${label}` : 'Copy'}
        >
          {copied ? <CheckCircle2 size={13} /> : <Copy size={13} />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
    </div>
  );
}

export function UsageMeter({ label, percent, detail }: { label: string; percent: number; detail?: ReactNode }) {
  const clamped = Math.max(0, Math.min(100, Math.round(percent)));
  const tone = clamped >= 90 ? 'danger' : clamped >= 75 ? 'warn' : 'good';
  return (
    <div className="usageMeter">
      <div className="usageMeterHead">
        <span>{label}</span>
        <strong>{clamped}% used</strong>
      </div>
      <div
        className="usageMeterTrack"
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={clamped}
      >
        <div className={`usageMeterFill usageMeterFill--${tone}`} style={{ width: `${clamped}%` }} />
      </div>
      {detail ? <span className="usageMeterDetail">{detail}</span> : null}
    </div>
  );
}
