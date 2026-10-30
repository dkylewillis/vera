/** Disclosure stored in the agent-service policy and returned by vera_library_info. */
export const AGENT_SERVICE_DISCLOSURE =
  "Your library stays on your computer. Requested excerpts and source previews are returned to the local agent that asked for them, and that agent's model provider receives them.";

export const AGENT_SERVICE_CLOUD_DISCLOSURE =
  "Your library stays on your computer. Requested excerpts and source previews are returned to the agent that asked for them. Cloud assistants reach this computer through the VERA relay, and that assistant's model provider receives the excerpts.";

export const AGENT_SERVICE_NOTE =
  "Excerpts returned to an agent are sent to that agent's model provider. Your library stays on this computer.";

export const DEFAULT_AGENT_SERVICE_PORT = 47821;

export interface AgentSnippetInput {
  url: string;
  token: string;
  command: string;
  args: string[];
}

export interface AgentSnippets {
  http: string;
  stdio: string;
  note: string;
}

/** Copyable MCP client config. The token is included because the client must send it. */
export function agentServiceSnippets(input: AgentSnippetInput): AgentSnippets {
  const http = JSON.stringify(
    {
      mcpServers: {
        vera: {
          url: input.url,
          headers: { Authorization: `Bearer ${input.token}` },
        },
      },
    },
    null,
    2,
  );
  const stdio = JSON.stringify(
    {
      mcpServers: {
        vera: {
          command: input.command,
          args: input.args,
        },
      },
    },
    null,
    2,
  );
  return { http, stdio, note: AGENT_SERVICE_NOTE };
}
