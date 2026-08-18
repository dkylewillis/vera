/** Split sidecar stderr so tqdm `\r` updates become visible `app:dev` lines. */
export function sidecarStderrLines(chunk: string): string[] {
  return chunk
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .split('\n')
    .filter((line) => line.trim().length > 0);
}

export function logSidecarStderr(label: string, chunk: string): void {
  for (const line of sidecarStderrLines(chunk)) {
    console.error(`[${label}] ${line}`);
  }
}
