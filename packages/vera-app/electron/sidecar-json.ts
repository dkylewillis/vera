export type SidecarJsonPayload = Record<string, unknown>;

export type SidecarJsonParseResult =
  | { ok: true; payload: SidecarJsonPayload }
  | { ok: false; error: string };

export function parseSidecarJsonLine(line: string): SidecarJsonParseResult {
  let parsed: unknown;
  try {
    parsed = JSON.parse(line);
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'invalid JSON',
    };
  }

  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return { ok: false, error: 'payload must be a non-null JSON object' };
  }

  return { ok: true, payload: parsed as SidecarJsonPayload };
}
