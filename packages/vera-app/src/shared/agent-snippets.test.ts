import { describe, expect, it } from 'vitest';
import { AGENT_SERVICE_NOTE, agentServiceSnippets } from './agent-snippets';

describe('agentServiceSnippets', () => {
  it('builds HTTP and stdio configs without dropping the connect file', () => {
    const snippets = agentServiceSnippets({
      url: 'http://127.0.0.1:47821/mcp',
      token: 'secret-token',
      command: 'vera-sidecar.exe',
      args: ['mcp-connect', '--connect-file', 'C:/Users/me/connect.json'],
    });
    const http = JSON.parse(snippets.http) as { mcpServers: { vera: { url: string; headers: { Authorization: string } } } };
    expect(http.mcpServers.vera.url).toBe('http://127.0.0.1:47821/mcp');
    expect(http.mcpServers.vera.headers.Authorization).toBe('Bearer secret-token');
    const stdio = JSON.parse(snippets.stdio) as { mcpServers: { vera: { command: string; args: string[] } } };
    expect(stdio.mcpServers.vera.command).toBe('vera-sidecar.exe');
    expect(stdio.mcpServers.vera.args).toEqual(['mcp-connect', '--connect-file', 'C:/Users/me/connect.json']);
    expect(snippets.note).toBe(AGENT_SERVICE_NOTE);
  });
});
