/** Web pages Settings can open in the browser. Main opens only these URLs. */
export const HELP_LINKS = {
  openai_api_keys: 'https://platform.openai.com/api-keys',
  openrouter_keys: 'https://openrouter.ai/settings/keys',
  huggingface_tokens: 'https://huggingface.co/settings/tokens',
  ollama_download: 'https://ollama.com/download',
  lmstudio_download: 'https://lmstudio.ai/',
} as const;

export type HelpLinkId = keyof typeof HELP_LINKS;

export function helpLinkUrl(id: unknown): string | null {
  if (typeof id !== 'string' || !Object.prototype.hasOwnProperty.call(HELP_LINKS, id)) return null;
  return HELP_LINKS[id as HelpLinkId];
}
