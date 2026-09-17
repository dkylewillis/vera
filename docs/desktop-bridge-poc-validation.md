# Desktop bridge PoC validation report

Date: 2026-09-17

## Scope delivered

| Milestone | Status |
| --- | --- |
| 0 Tunnel runbook | Written (`docs/desktop-bridge-poc-setup-runbook.md`); live ChatGPT round-trip **blocked** pending tester credentials |
| 1 Restricted MCP | `vera_mcp.access_policy`, `build_server(policy=…)`, `main_bridge`, viewer gating, tests |
| 2 Packaged MCP mode | `vera-sidecar mcp-bridge` argv dispatch; PyInstaller collects `vera_mcp` / viewer UI; `scripts/verify-packaged-bridge.cjs` |
| 3 Desktop supervision | `electron/bridge-manager.ts`, IPC, encrypted tunnel key, Settings → ChatGPT Bridge |
| 4 Fixtures / demo | `scripts/build_bridge_poc_fixtures.py`, demo checklist (ChatGPT evidence blocked) |
| 5 Docs / checks | This report; runbook; desktop/plugin notes |

## Commands

```text
# Policy / MCP tests (passed on 2026-09-17 with local .venv)
.\.venv\Scripts\python.exe -m pytest packages/vera-mcp/tests/test_access_policy.py -q

# Broader MCP suite
.\.venv\Scripts\python.exe -m pytest packages/vera-mcp/tests -q

# App unit tests / typecheck (requires Node.js on PATH)
npm --prefix packages/vera-app run test:unit
npm --prefix packages/vera-app run typecheck

# Packaged bridge smoke (after npm run build:sidecar)
node packages/vera-app/scripts/verify-packaged-bridge.cjs

# Fixture library for ChatGPT demo
.\.venv\Scripts\python.exe scripts\build_bridge_poc_fixtures.py
```

Recorded this environment: Python MCP policy tests **passed**. Node.js/npm were
not available on PATH, so Electron unit tests and packaged verify were not
executed here. ChatGPT live evidence remains **blocked** pending tunnel access.

## Remaining production questions

See [desktop-bridge-production.md](desktop-bridge-production.md): public relay,
account linking, multi-device grants, and automatic distribution are out of scope
for this PoC.
