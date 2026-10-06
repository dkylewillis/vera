# Optional remote VERA bridge

VERA Local uses local MCP by default. Keep this remote connector separate from
the local plugin. The desktop application's ChatGPT Bridge continues to work
with its configured tunnel and approved library; no bridge code was removed.

`connector.app.json` preserves the existing developer connector registration.
It is an example, not an automatically discovered root `.app.json`. A separate
remote-only plugin can explicitly reference a copy as its `apps` component and
omit `mcpServers`. Label it VERA Remote and identify the intended computer when
setting up the connection. Use your own registered app ID for other deployments.

For local Codex tasks, select VERA Local and pass a folder, for example:
"Search F:\Manuals for time of concentration."
Check `vera_library_info`: local stdio reports `unrestricted: true` and
`library_root: null`. Do not treat a remote bridge's library path as local.
