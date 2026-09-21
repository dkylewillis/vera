# Desktop bridge PoC: ChatGPT demo checklist

Use with fixtures from `python scripts/build_bridge_poc_fixtures.py` and the
[setup runbook](desktop-bridge-poc-setup-runbook.md).

**ChatGPT live evidence status: blocked** until Secure MCP Tunnel access is
validated. Local policy and packaging checks can still pass.

## Demo script

1. In Desktop **Settings → ChatGPT Bridge**, select `dev/fixtures/bridge-poc/approved`,
   enter tunnel ID + runtime key, Connect.
2. In ChatGPT developer mode, call `vera_library_info`, then hybrid search
   “how big should the detention pond be”.
3. Reload the returned chunk, answer with `[C1]`, call `vera_show_sources`, open
   the PDF highlight.
4. Search for pipe sizing / section 4.2 (keyword) and open Markdown line highlights.
5. Ask a metadata-filtered question with `where.company=GRID`.
6. Attempt `UNIQUE_SENTINEL_PHRASE_XYZ` against the sibling library / forged path;
   confirm denial without leaking the path.
7. Disconnect while a request is in progress; confirm no further data.
8. Reconnect, repeat one query, exit Desktop; confirm no orphan
   `tunnel-client` / `mcp-bridge` processes.

## Evidence to attach privately

- Redacted screenshots or recording from real ChatGPT
- Observed cold/warm latency and preview sizes
- Denial payload (no absolute denied paths)
- Process cleanup confirmation after exit
