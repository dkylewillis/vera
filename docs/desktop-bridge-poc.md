# VERA Desktop bridge: proof-of-concept build plan

Status: proposed, not implemented. Prepared September 17, 2026.

## Outcome and scope

Demonstrate that a Windows user can install a development build of VERA Desktop,
approve one local library, connect it to ChatGPT, ask a question, and open a
highlighted citation. Desktop manages the local runtime and connection lifecycle.
The archives, indexes, and retrieval engine remain on the computer.

This is a private developer-mode experiment. Manual tunnel provisioning and
ChatGPT connection setup are acceptable. A successful demo does not establish
public plugin distribution or automatic account linking. See the separate
[production proposal](desktop-bridge-production.md).

Use one computer, one trusted tester/workspace, one explicitly selected local
folder, and read-only retrieval tools. Start with generated PDF and Markdown
fixtures using hashing embeddings; then verify MiniLM hybrid retrieval with the
bundled ONNX runtime. No external embedding credentials are required for these
fixtures. Defer public relay hosting, VERA accounts, multiple devices, background
startup, remote conversion/export, and arbitrary embedding-provider support.

Product disclosure: **Your library stays on your computer. Requested excerpts
and source previews are shared with ChatGPT.** Preview pages can include text
beyond the cited passage. Content already returned cannot be recalled by
disconnecting.

## Current implementation to reuse

| Area | Existing source | Planned change |
| --- | --- | --- |
| MCP tools and stdio entry point | `packages/vera-mcp/src/vera_mcp/server.py` | Inject an optional access policy; retain ordinary local CLI behavior |
| Citation viewer | `packages/vera-mcp/src/vera_mcp/source_viewer.py` and `ui/source-viewer.html` | Apply the same policy to every preview and navigation request |
| Desktop process management and secrets | `packages/vera-app/electron/main.ts` | Add a dedicated bridge supervisor and encrypted tunnel credential storage |
| Desktop Python protocol | `packages/vera-app/src/vera_app/sidecar.py` | Keep existing JSON-lines protocol separate from MCP |
| Frozen runtime | `packages/vera-app/scripts/build-sidecar.cjs` and `verify-packaged-sidecar.cjs` | Package and smoke-test an MCP launch mode with viewer assets |
| Retrieval implementation | `packages/vera-doc/src/vera_doc` | Reuse unchanged; keep transport and authorization out of the storage engine |

The current MCP server accepts filesystem paths, and the desktop sidecar is not
an MCP server. Wrapping the existing unrestricted command in a tunnel is not the
finished bridge. The current plugin can install semantic dependencies at runtime;
the packaged bridge must disable that behavior and use its tested bundled models.
Reconcile any in-progress plugin/viewer changes before implementation.

## Process and trust boundaries

```text
ChatGPT developer-mode connection
          | authenticated OpenAI tunnel transport
OpenAI tunnel service
          | outbound HTTPS initiated by local tunnel-client
VERA Desktop supervisor -> tunnel-client -> restricted VERA MCP process (stdio)
                                               |
                                       approved local library
```

Desktop owns the tunnel-client process; the client launches the MCP child using
its stdio profile. Do not attach two clients to the same stdin/stdout stream.
Stopping the bridge must stop the whole child process tree. Keep the existing
desktop sidecar independently usable.

OpenAI documents outbound tunnel access, a tunnel ID and runtime API key, and
separate Platform/workspace permissions. Validate these for the tester before
building the UI. Use the official client setup and diagnostics documented in
[Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).

## Ordered implementation milestones

### 0. Validate the external connection prerequisite

- Confirm target Windows client availability, supported version, redistribution
  terms, and a reproducible download/checksum policy. Record the tested version.
- Provision a dedicated test tunnel with appropriate organization/workspace
  associations and permissions; enable ChatGPT developer mode.
- Test the official client's initialization, diagnostics, stdio launch, and
  shutdown using a harmless fixture-only MCP server. Keep a restricted test key
  outside the repo, command arguments, screenshots, and logs.
- Record exact Windows commands from the tested client's help. Do not assume
  Unix command quoting or undocumented login/automation APIs work on Windows.
- Verify tool discovery and a simple round trip from browser ChatGPT.

Exit evidence: a dated setup runbook with client version, redacted diagnostics,
and successful ChatGPT call. If access or client distribution is unavailable,
continue local policy/runtime work but mark the real ChatGPT demo blocked. Do not
substitute an unauthenticated public tunnel.

### 1. Implement a restricted MCP launch mode

Introduce a shared access-policy object in `vera-mcp`, passed to tool and viewer
registration. A bridge-specific entry point requires an explicit policy; missing,
empty, or invalid policy fails closed. Ordinary local MCP startup can retain its
existing behavior. Neither MCP arguments nor document metadata may change policy.

For the POC, retain existing tool names and path-shaped arguments for viewer
compatibility. Add a small discovery tool that returns only the approved library
root and supported search capabilities, so ChatGPT does not guess paths. Absolute
paths will be visible to the host in this version; disclose this to testers.

Enforce policy before any archive open, corpus/index access, figure read, source
render, or navigation call. Checking only `server._open` is insufficient: corpus
search and viewer code have independent paths. Resolve canonical paths and check
actual containment, never string prefixes. Reject UNC/network/device paths and
symlink/junction/reparse-point escapes in the POC. Restrict files to approved
`.vera` archives; use originals embedded in archives, not arbitrary external paths
from metadata. Check discovered corpus members and indexed archive locators too.
If safe indexed discovery cannot be enforced, use the existing fallback search
path and preserve its diagnostics. This policy is not an OS sandbox against a
malicious process running as the same local user; document that boundary.

Initially permit search, corpus search, inspect, chunk/page/region reads, figures,
and the source viewer. Omit unnecessary tools from bridge registration. Mark
retrieval tools read-only, but rely on backend checks, not annotations, for access
control. Bound result counts, context, preview size, concurrency, and request time.
Return useful errors without leaking denied paths or raw tracebacks.

Exit evidence: tests deny outside files, sibling-prefix paths, traversal,
junctions, stale indexed paths, and forged viewer requests while valid search and
citation navigation still work. No archive/source mutations; any existing index
cache writes must be identified and explicitly scoped to approved storage.

### 2. Package the MCP runtime

Add a distinct MCP entry mode to the frozen executable, dispatched before the
desktop sidecar protocol starts. Include MCP SDK dependencies, source-viewer HTML,
renderer support, and required package metadata. Never send logs to MCP stdout.
Keep Torch/Sentence Transformers excluded and reuse the verified ONNX model.
Explicitly unset `VERA_AUTO_INSTALL_SEMANTIC_DEPS` in the bridge child environment.

Verify hashing and MiniLM archives against the exact recorded model identities;
do not silently substitute an embedding model. Unsupported models produce an
actionable error or offer an explicit keyword search. Pass only required child
environment variables; do not inherit unrelated provider secrets.

Exit evidence: the packaged runtime can list tools, search, read a chunk, and
render a citation from an unrelated working directory on a clean Windows machine
without Python, uv, pip, or model downloads. Test paths with spaces and Unicode.

### 3. Add Desktop supervision and controls

Implement a dedicated module, for example `electron/bridge-manager.ts`, integrated
through narrowly scoped IPC methods and renderer types. The renderer may request
start/stop/status; it cannot supply executable paths or arbitrary command strings.
Build a bridge settings panel with library selection, tunnel ID, credential entry,
Connect, Disconnect, and setup instructions for ChatGPT.

Persist nonsecret configuration separately from credentials. Store credentials
using the existing encrypted secret mechanism; fail clearly if secure storage is
unavailable. Supply the client key through its supported secret mechanism without
logging it. Use an absolute trusted binary path, argument arrays, and hidden child
windows. Any local client admin endpoint must remain loopback-only.

States: disabled, needs setup, starting, connected, reconnecting, and error.
Connected requires actual client readiness, not merely a running PID. Use bounded
restart backoff and a startup timeout. Show permission, credential, offline, and
runtime errors distinctly. Disconnect cancels work, drops pending replies, and
terminates children. Library changes stop the bridge and require reconnecting
with the new policy. For the POC, app exit stops the bridge; do not add tray or
autostart behavior. App restart leaves it disabled until explicitly enabled.

Exit evidence: unit tests cover process failure, timeout, duplicate starts,
disconnect during work, and cleanup. A manual sleep/wake and network-loss test
confirms a recoverable state with no orphan processes.

### 4. Prove the ChatGPT citation workflow

Prepare a small fixture library containing a PDF with known page/region evidence
and Markdown with known line evidence, plus an unapproved sibling library with a
distinctive sentinel phrase. Freeze expected source passages and chunk IDs after
conversion. Include one metadata-filtered question and a paraphrased query.

Connect through ChatGPT developer mode following the
[official connection guide](https://developers.openai.com/plugins/deploy/connect-chatgpt/).
Test the complete installed private plugin as well as raw tool calls; document
which setup steps remain manual.

Demo script:

1. Discover the approved library and run a hybrid question against it.
2. Reload the returned chunk, answer with `[C1]`, and call `vera_show_sources`.
3. Open the viewer, select the citation, and verify PDF highlights; repeat with
   Markdown and verify line highlights and navigation.
4. Attempt the sibling sentinel search and direct denied-file/viewer access.
5. Disconnect while a request is in progress; confirm no further data is returned.
6. Reconnect, repeat the query, then exit Desktop and verify child cleanup.

Exit evidence: a redacted recording or screenshots from real ChatGPT, matching
source evidence, denial results, and observed cold/warm latency and preview sizes.
A local viewer simulator alone cannot satisfy this milestone. Preserve current
viewer fallbacks for missing originals, render failures, and unsupported geometry.

### 5. Verification and handoff

Add policy tests under `packages/vera-mcp/tests`, process tests under
`packages/vera-app/electron`, and packaged bridge checks alongside the existing
sidecar verification script. Extend viewer tests to cover authorization on every
navigation call. Test malformed archives and unsupported models too.

Run the repository's required checks from [CONTRIBUTING.md](../CONTRIBUTING.md):
Ruff, mypy, Python tests, app typecheck, and app unit tests, plus the Windows
packaged-runtime check and actual ChatGPT demo. Record commands/results, including
any existing unrelated failures, in a POC validation report.

When implementing public behavior, update README, desktop/plugin guides, examples,
portable skill, relevant skill references, and documentation-contract tests in
the same change. Include setup, data disclosure, supported models, shutdown,
revocation, troubleshooting, and the distinction between private testing and
published distribution. This planning document introduces no current behavior.

## Completion criteria and next decision

The POC is complete only when a packaged Windows build performs the approved
library search and highlighted-citation flow in real ChatGPT, access denials pass,
and disconnect/exit stop data access. Installation requires no Python setup;
external tunnel provisioning may still be manual and must be enumerated.

Use the measured setup friction, reliability, latency, and payload sizes to decide
whether to proceed to the production relay. If only local tests pass, report a
partial POC, not a validated ChatGPT bridge. Deliver the development installer,
setup runbook, validation report, and remaining production questions together.
