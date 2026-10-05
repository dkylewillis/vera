# Desktop ChatGPT bridge (developer-mode PoC)

Status: **implemented locally**. Live ChatGPT developer-mode validation is
still **blocked** pending a tester-provisioned OpenAI tunnel. This is a private
developer-mode experiment, not public plugin distribution. See the
[setup runbook](desktop-bridge-poc-setup-runbook.md),
[validation report](desktop-bridge-poc-validation.md), and
[production proposal](desktop-bridge-production.md).

## Outcome and scope

A Windows user can install a development build of VERA Desktop, approve one
local library, start **File > Settings → ChatGPT Bridge**, and (once a tunnel
exists) ask ChatGPT a question that searches that library and opens a
highlighted citation. Desktop manages the local runtime and connection
lifecycle. The archives, indexes, and retrieval engine remain on the computer.

Use one computer, one trusted tester/workspace, one explicitly selected local
folder, and read-only retrieval tools. Start with generated PDF and Markdown
fixtures using hashing embeddings; then verify MiniLM hybrid retrieval with the
bundled ONNX runtime. No external embedding credentials are required for these
fixtures. Public relay hosting, VERA accounts, multiple devices, background
startup, remote conversion/export, and arbitrary embedding-provider support
remain out of scope.

Product disclosure: **Your library stays on your computer. Requested excerpts
and source previews are shared with ChatGPT.** Preview pages can include text
beyond the cited passage. Absolute archive paths are visible to the host in
this PoC. Content already returned cannot be recalled by disconnecting.

## What shipped

| Area | Implementation |
| --- | --- |
| Restricted MCP | `vera_mcp.access_policy.AccessPolicy`, `build_server(policy=…)`, `vera-mcp-bridge` / `main_bridge` |
| Citation viewer | Same `vera_show_sources` / `vera_source_page` tools, gated by the policy |
| Desktop supervisor | `packages/vera-app/electron/bridge-manager.ts`, Settings → ChatGPT Bridge |
| Frozen runtime | `vera-sidecar mcp-bridge` argv dispatch; `scripts/verify-packaged-bridge.cjs` |
| Fixtures | `scripts/build_bridge_poc_fixtures.py` and `dev/fixtures/bridge-poc/` |

Ordinary `vera mcp` is unchanged: no policy file, no library grant, and
`vera_validate` remains registered. Wrapping that unrestricted command in a
tunnel is not the bridge.

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

Desktop owns the `tunnel-client` process. The client launches the MCP child
using its stdio profile. Do not attach two clients to the same stdin/stdout
stream. Stopping the bridge stops the child process tree (`taskkill /T` on
Windows). The existing JSON-lines sidecar stays independently usable for
Search/Ask.

This policy is not an OS sandbox against a malicious process running as the
same local user.

## Fail-closed policy

Bridge mode requires `VERA_BRIDGE_POLICY_PATH` pointing at a JSON file.
Desktop writes that file under `userData/bridge/policy.json` before spawn and
deletes it on disconnect. Missing, empty, or invalid policy fails closed
(`vera-mcp-bridge` prints the error on stderr and exits 2). MCP arguments and
document metadata cannot change the grant.

Desktop writes:

```json
{
  "library_root": "C:/approved/library",
  "max_top_k": 20,
  "max_context_chunks": 2,
  "max_sources": 12
}
```

`library_root` must be an existing directory. Optional `allowed_tools` must be
a non-empty subset of the bridge tool set; unknown names fail closed.

Registered tools: `vera_library_info`, `vera_search`, `vera_corpus_search`,
`vera_inspect`, `vera_figures`, `vera_get_figure`, `vera_get_page`,
`vera_get_chunk`, `vera_get_chunk_regions`, `vera_show_sources`, and
`vera_source_page`. **`vera_validate` is omitted.** Conversion, index mutation,
and export are not registered.

Bounds: `top_k` is clamped to 20, `context_chunks` to 2, and
`vera_show_sources` to 12 citations. `vera_library_info` returns the approved
root, those bounds, supported modes, and the product disclosure. Unrestricted
local MCP returns `unrestricted: true` and `library_root: null` instead.

Path rules, checked before every archive open, corpus root, indexed locator,
figure read, and viewer navigation:

- Canonicalize with `resolve` + `realpath`; reject UNC, device, and
  reparse/junction escapes.
- Require an absolute path under the approved root (actual containment, not a
  string prefix).
- Restrict files to `.vera` archives. Use originals stored in the archive, not
  arbitrary external paths from metadata.
- Stale or escaped corpus/index members are dropped and reported on
  `skipped_files` as `category: "denied"` with a generic reason (denied paths
  are not leaked).

`main_bridge` unsets `VERA_AUTO_INSTALL_SEMANTIC_DEPS`. Desktop also forces
that variable to `0` in the child environment so the packaged runtime cannot
pip-install Sentence Transformers. Unsupported models error or require an
explicit keyword search; the bridge does not substitute another embedder.

## Desktop supervisor

**File > Settings → ChatGPT Bridge** collects the approved library, a
`tunnel_…` ID, a securely stored runtime key, and a detected or selected
`tunnel-client` executable. **Save & Connect** stays disabled until those
paths exist and the tunnel ID matches `tunnel_[A-Za-z0-9_-]+`.
`VERA_TUNNEL_CLIENT` or `PATH` can supply the client; the renderer cannot
inject an arbitrary command string.

States: `disabled`, `needs_setup`, `starting`, `connected`, `reconnecting`,
and `error`. Connected requires the client loopback health URL to answer
`/readyz` or `/healthz`, not merely a running PID. Startup waits up to 45
seconds. Unexpected exits retry up to 3 times with bounded backoff. Disconnect
and app exit kill the process tree and delete the policy file. Library, client,
or tunnel changes stop the bridge and require reconnecting so the policy is
rewritten. App restart leaves the bridge disabled until you Connect again;
there is no tray or autostart.

The supervisor passes `--health.listen-addr 127.0.0.1:0` and a private
`--health.url-file`, then reads the reported loopback URL. Do not assume a
fixed health port. Only `http://127.0.0.1` or `http://[::1]` with a port and
no extra path is accepted. Redacted `tunnel-client` stdout/stderr is appended
to the local sidecar log; runtime keys, `sk-…` tokens, and Bearer headers are
stripped first.

## Remaining ChatGPT validation

Local policy, packaging, and supervisor tests exist. The live ChatGPT
round-trip in the [demo checklist](desktop-bridge-poc-demo-checklist.md) is
still **blocked** until a tester records tunnel-client identity and a real
developer-mode session. A local viewer simulator does not satisfy that
milestone.

Until those boxes are checked, treat the ChatGPT demo as blocked even when
local tests pass. Use the measured setup friction from that demo to decide
whether to proceed to the production relay.
