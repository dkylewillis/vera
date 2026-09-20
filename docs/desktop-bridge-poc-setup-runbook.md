# Desktop bridge PoC: Secure MCP Tunnel setup runbook

Status: **blocked** until a tester provisions an OpenAI Platform tunnel and
ChatGPT developer-mode access. Prepared for the private developer-mode
experiment described in [desktop-bridge-poc.md](desktop-bridge-poc.md).

Product disclosure (share with testers): **Your library stays on your computer.
Requested excerpts and source previews are shared with ChatGPT.** Preview pages
can include text beyond the cited passage. Content already returned cannot be
recalled by disconnecting.

## Prerequisites

| Item | Notes |
| --- | --- |
| Windows client | Record the tested OS build (Settings → System → About). |
| `tunnel-client` | Download from Platform tunnel settings or the latest public release of `openai/tunnel-client`. Prefer the Platform download link for redistribution terms. |
| Version / checksum | Record `tunnel-client --version` (or equivalent) and a SHA-256 of the Windows binary before first use. |
| Platform permissions | Tunnels Read + Manage to create; Read + Use to run the client and select the tunnel in ChatGPT. |
| ChatGPT workspace | Developer mode enabled (separate from Platform tunnel roles). Enterprise/Edu: workspace admin grant, then Settings → Security and login. |
| Network | Outbound HTTPS to `api.openai.com:443` on `/v1/tunnel/*` (or `mtls.api.openai.com:443` when control-plane mTLS is configured). No inbound ports. |

Keep the tunnel runtime API key outside the repository, command-line screenshots,
and committed logs. Desktop stores it only in the encrypted credential blob when
the Bridge settings panel is used.

Official guide: [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).

## Recorded client identity (fill in during the first successful setup)

| Field | Value |
| --- | --- |
| Date | _YYYY-MM-DD_ |
| Windows build | _e.g. 10.0.26200_ |
| `tunnel-client` version | _fill after download_ |
| SHA-256 | _fill after download_ |
| Tunnel ID | `tunnel_…` (redact in shared copies if needed) |
| Associated Platform org | _name / id_ |
| Associated ChatGPT workspace | _name / id_ |
| Status | **blocked** — no validated ChatGPT round-trip yet |

## Fixture-only validation (before VERA)

Use a harmless local stdio MCP server first so tunnel transport issues are not
confused with VERA policy bugs.

```powershell
# From a directory that is not the VERA repo (optional but recommended)
$env:CONTROL_PLANE_API_KEY = "<runtime-api-key-not-committed>"

# Exact flags come from the tested client's help — confirm on Windows:
tunnel-client help quickstart
tunnel-client help init
tunnel-client help doctor
tunnel-client help run

tunnel-client init `
  --sample sample_mcp_stdio_local `
  --profile vera-fixture `
  --tunnel-id tunnel_<id> `
  --mcp-command "python -c `"print('replace with fixture mcp')`""

tunnel-client doctor --profile vera-fixture --explain
tunnel-client run --profile vera-fixture
```

While `run` is healthy, open the loopback admin UI (default `/ui`) and confirm
ready/connected before ChatGPT tests. Admin endpoints must remain loopback-only.

Exit evidence for this step: redacted `doctor --explain` output and a note that
ChatGPT listed the tunnel under developer-mode app creation.

## Connect ChatGPT (developer mode)

1. Enable ChatGPT developer mode for the tester account/workspace.
2. Create a developer-mode app; choose **Tunnel** under Connection.
3. Select the associated tunnel or paste the `tunnel_id`.
4. Run a trivial tool call against the fixture MCP.
5. Disconnect and confirm the local client stops receiving work.

Connection guide: [Connect ChatGPT](https://developers.openai.com/plugins/deploy/connect-chatgpt/).

## VERA Desktop bridge profile (after milestones 1–3)

Desktop owns `tunnel-client` and writes a fail-closed policy file. Manual
equivalent for debugging (do not put secrets in shell history if avoidable):

```powershell
$env:CONTROL_PLANE_API_KEY = "<runtime-api-key-not-committed>"
$env:VERA_BRIDGE_POLICY_PATH = "C:\path\to\bridge-policy.json"
$env:VERA_AUTO_INSTALL_SEMANTIC_DEPS = "0"

# Packaged binary (preferred for the PoC installer):
#   <resources>\python\sidecar\vera-sidecar.exe mcp-bridge
# Dev:
#   <python> -m vera_app.sidecar mcp-bridge

tunnel-client init `
  --profile vera-desktop-bridge `
  --tunnel-id tunnel_<id> `
  --mcp-command "`"<absolute-vera-sidecar>`" mcp-bridge"

tunnel-client doctor --profile vera-desktop-bridge --explain
tunnel-client run --profile vera-desktop-bridge
```

Prefer the Desktop **Settings → ChatGPT Bridge** setup wizard once milestone 3
lands. It selects the approved library and `tunnel-client` executable, stores
the runtime key in encrypted storage, validates the local paths and `tunnel_…`
ID, then enables **Save & Connect**. Library, client, or tunnel changes require
Disconnect then Connect so the policy file is rewritten.
The Desktop supervisor passes `--health.listen-addr 127.0.0.1:0` and a private
`--health.url-file`, then polls the reported loopback `/readyz` endpoint. Do
not assume a fixed health/admin port. Its redacted tunnel-client stdout/stderr
is appended to VERA's local sidecar log; credentials are removed before logging.

## Shutdown and revocation

- Desktop Disconnect / app exit must terminate `tunnel-client` and its MCP child
  tree. Confirm with Task Manager that no orphan `tunnel-client` or
  `vera-sidecar … mcp-bridge` processes remain.
- Previously delivered excerpts cannot be recalled by disconnecting.
- Rotate or revoke the runtime API key in Platform if the tester machine is
  compromised.

## Troubleshooting (from OpenAI docs + PoC notes)

| Symptom | Check |
| --- | --- |
| Tunnels access required | Org-level role (not project). Wait up to ~30 minutes after role change. |
| Tunnel missing in ChatGPT | Associate the ChatGPT workspace with the tunnel, not only a Platform org; need Tunnels Use. |
| Tool calls fail | `tunnel-client run` still healthy; re-run `doctor --profile … --explain`. |
| VERA path denied | Approved library only; absolute `.vera` under the policy root; no sibling-prefix escapes. |

## Evidence checklist

- [ ] Client version + SHA-256 recorded
- [ ] Fixture MCP round-trip from ChatGPT
- [ ] VERA hybrid search + `vera_show_sources` highlight (PDF and Markdown)
- [ ] Sibling sentinel library denied
- [ ] Disconnect mid-request stops further data
- [ ] App exit leaves no orphan processes
- [ ] Redacted screenshots/recording attached outside git (or linked privately)

Until the boxes above are checked with a real tunnel, treat the ChatGPT demo as
**blocked** even if local policy and packaging tests pass.
