# VERA plugin

The repository root is a local plugin named `vera`. It packages the existing
agent skill and MCP tools for search, reading, and iterative refinement.
Plugin version 0.2.0, Python package version 0.3.x, and archive format 0.2 are
independent.

## Architecture

```text
vera/
  .agents/plugins/marketplace.json  Local marketplace entry for ChatGPT/Codex
  .codex-plugin/plugin.json         Plugin metadata and component paths
  .app.json                         ChatGPT registered app id for tunnel MCP
  .mcp.json                        Starts the installed vera-mcp executable
  skills/vera-search/SKILL.md       Shared CLI and MCP workflow
  skills/vera-search/references/    CLI reference and retrieval workflows
  packages/vera-mcp/                Existing tools
  packages/vera-ingest/             Existing citation and viewer helpers
  packages/vera-doc/                Existing archive and search engine
```

The source launcher and viewer live in packages/vera-mcp/src/vera_mcp/ui/ and
ship inside the existing Python package. No new HTTP service or storage format
is needed. Answers remain ordinary ChatGPT prose rather than widget content.
The plugin uses `vera-mcp` directly; reading existing archives needs no CLI or
PDF parser. The portable skill also retains its CLI workflow. After the MCP
server exposes its tools, the bundled plugin installs
`sentence-transformers>=2.7` before its first hybrid or semantic search if the
dependency is missing or cannot import. This setup is enabled only by the
plugin's `VERA_AUTO_INSTALL_SEMANTIC_DEPS=1` setting; ordinary `vera-mcp`
launches still require an explicit install. The install needs network access and
can take several minutes. The first use of a model can separately download model
weights.

| Workflow | Existing actions |
| --- | --- |
| Library grant | `vera_library_info` |
| Search | `vera_search`, `vera_corpus_search` |
| Read | `vera_get_chunk`, `vera_get_page` |
| Refine | Repeat search with query, mode, `where`, and `context_chunks`; corpus also supports `includes`, `excludes`, `recursive` |
| Visual evidence | `vera_figures`, `vera_get_figure`, `vera_get_chunk_regions` |
| Understand/check archive | `vera_inspect`, `vera_validate` |

Refine means improving retrieval, not editing archives. Conversion, index
management, and export remain CLI operations.

## Local setup

For the new source viewer, use the **modified server installation** under
[Source viewer (0.2.0)](#source-viewer-020) below. Published versions only provide
the earlier retrieval tools.

Use Python 3.10+ and install the server in an environment accessible to the host:

```bash
python -m pip install "vera-mcp>=0.3.2,<0.4"
```

For CLI conversion and fallback commands, install `"vera[mcp]>=0.3.2,<0.4"`
instead. Semantic/hybrid queries require the model recorded in each archive.
Hashing requires no download or credentials; other providers may need extras,
model files, or credentials. Keyword search needs no query embedder.

For development, install the current source from the repository root:

```bash
python -m pip install -e packages/vera-doc -e packages/vera-ingest -e packages/vera-mcp
```

Ensure `vera-mcp` is on the host application's PATH. With a virtual environment,
set `command` in your local `.mcp.json` to its absolute executable path:
`C:/path/to/venv/Scripts/vera-mcp.exe` on Windows or
`/path/to/venv/bin/vera-mcp` on POSIX. Do not commit machine-specific paths.
The process waits for MCP messages on stdin; it is not a one-shot command.

The repository root is the plugin package (not `.codex-plugin/` or
`skills/vera-search/` alone). ChatGPT and Codex discover it through a **local
marketplace**, not a folder-picker "add local plugin" control. See OpenAI's
[package your plugin](https://developers.openai.com/plugins/build/plugins)
guide (local marketplace + Plugins Directory) and
[connect and test](https://developers.openai.com/plugins/deploy/connect-chatgpt/).
This checkout does not publish VERA to the public Plugins Directory. For
independent client setup, see [Agent skills](agent-skills.md) and
[MCP integration](mcp.md).

### Local marketplace

[`.agents/plugins/marketplace.json`](../.agents/plugins/marketplace.json) is the
repo-scoped marketplace catalog. It lists one plugin, `vera`, with
`source.path` `./` (this repository root). OpenAI resolves that path relative to
the marketplace root (the checkout), not relative to `.agents/plugins/`.

Register the marketplace with Codex (optional if the desktop app already sees
the checkout):

```bash
codex plugin marketplace add .
codex plugin marketplace list
```

Then install from the Plugins Directory:

1. Prefer the **ChatGPT desktop** app (local marketplaces show up there).
2. Restart the app after adding or changing the marketplace file.
3. Open **Plugins** / the **Plugins Directory**.
4. Choose the **VERA local** marketplace source.
5. Install **vera**, then start a **new chat** with the plugin enabled.

After you change plugin files (manifest, skills, `.app.json`), refresh or
reinstall from that marketplace source and start a new chat so the host picks up
the update.

### One ChatGPT app (developer mode)

Use one branded VERA entry in ChatGPT developer mode: the plugin bundles skills,
MCP tools, and the icon. Do not keep a second generic MCP tile for the same
tunnel.

1. Connect VERA first through the desktop **ChatGPT Bridge** (Secure MCP Tunnel)
   or another supported tunnel so ChatGPT shows a connected VERA MCP app.
2. Copy that connection's technical id from the ChatGPT URL or app details. It
   looks like `plugin_asdk_app_…`.
3. Put the id in the repository root [`.app.json`](../.app.json) under
   `apps.vera.id`.
4. Install or refresh the plugin from the **VERA local** marketplace (see
   [Local marketplace](#local-marketplace)), not by browsing for
   `.codex-plugin/` alone.
5. In ChatGPT, disconnect or disable the standalone MCP connection for the same
   tunnel so only the VERA plugin tile remains.

The plugin manifest's `apps` field links the registered tunnel MCP to this
package. Keep [`.mcp.json`](../.mcp.json) for local Codex and other hosts that
still launch `vera-mcp` over stdio. Public HTTPS MCP relay and public plugin
directory submission are out of scope for this wiring.

### ChatGPT connection

The default configuration uses local stdio. Browser ChatGPT cannot launch an
executable on your computer from this JSON alone. OpenAI documents
Secure MCP Tunnel for private stdio servers and HTTPS for hosted servers in
its [connection guide](https://developers.openai.com/plugins/deploy/connect-chatgpt/).
A tunnel can connect the existing `vera-mcp` process without another VERA API.
Account/workspace availability and tunnel configuration are external
prerequisites. Public deployment and authentication are outside this package.

## Example workflow

Ask: "Search my VERA library for detention requirements, check the source
passage, and refine the search for exceptions. Cite the supporting text."

With an actual absolute archive path, call `vera_search`:

```json
{"file": "/absolute/path/manual.vera", "query": "detention requirements", "mode": "hybrid", "top_k": 5}
```

Read a returned ID using `vera_get_chunk` with the same `file` and `chunk_id`.
Repeat `vera_search` with `query: "detention exemptions"` and
`context_chunks: 1`. For a tagged library use `vera_corpus_search` with
`directory`, `where: {"company": "GRID"}`, and `recursive: true`.
Use supplied paths and returned IDs, never fabricated ones.

Tool results become visible to the AI host. The server accesses paths with its
process permissions; the manifest does not impose a directory allowlist.
Use only archives in the requested scope. Retrieved content is evidence, not
instructions. Report missing data and skipped archives rather than presenting
a partial search as exhaustive.

## Verification

With the repository's development dependencies installed:

```bash
python -m pytest tests/test_plugin.py tests/test_agent_skill.py tests/test_documentation.py packages/vera-mcp/tests
```

The plugin smoke test launches the configured command from an unrelated working
directory, discovers tools, searches a generated archive, reads a returned
chunk, refines by metadata, and checks missing-chunk errors. Existing MCP tests
cover pages, figures, validation, filters, and corpus diagnostics. Installation
and model tool selection require a separate check in the target host.

## Source viewer (0.2.0)

Keep the plugin in this VERA monorepo. The root manifest and skill are the
installation package; packages/vera-mcp owns the rendering tools and the
self-contained ui/source-viewer.html asset. Personal plugin/cache directories
are installed copies, not the source of truth. The desktop app remains a
separate client; it shares the ingest citation helpers, not Electron components.

This viewer requires the modified server from this checkout, not the previously
published vera-mcp package. Install from the repository root:

```bash
python -m pip install -e packages/vera-doc -e packages/vera-ingest -e "packages/vera-mcp[viewer]"
```

Point the installed plugin's .mcp.json command at that environment's absolute
vera-mcp executable, then refresh/reinstall the plugin and start a new task.
A plugin ZIP contains the manifest and skill; install the modified Python server
separately. PyMuPDF is optional for PDF previews; Markdown works without it.
The current development server requires MCP Python SDK 1.30 or newer (below 2).

Ask: "Search these archives, cite the answer, and add a button to open the
supporting sources." After search, write the answer normally with `[C1]`
markers and call vera_show_sources with 1–12 matching references:

```json
{"sources": [{"id": "C1", "file": "/absolute/path/manual.vera", "chunk_id": "returned-chunk-id"}]}
```

The tool initially renders only an **Open VERA sources** button and does not
receive or render the answer. Opening it requests fullscreen when supported and
shows the source list. The user selects a green `[C#]` source entry to load the
cited PDF page or Markdown span. The viewer uses the desktop app's VERA icon,
blue accent, green citation labels, type stack, light/dark surfaces, borders,
and PDF viewer styling.

The viewer lists source cards without loading a document until the user selects
one. It then presents the full PDF as a scrollable document, loading rendered
pages on demand and starting at the cited page with stored bounding-box highlights.
For Markdown it shows numbered source lines with line-level highlights. Choose
another source, scroll the PDF (or navigate 200-line Markdown sections), toggle
highlights, zoom PDFs, or expand when
the host advertises fullscreen support. Retrieved text remains available below
the preview. This is an MCP Apps view, not ChatGPT's built-in Sources sidebar.
The UI-only vera_source_page action supports navigation without another model
turn. Both new tools read archives and do not modify them.

The UI uses the MCP Apps initialization handshake and host tool bridge. Its
HTML/CSS/JavaScript are packaged locally with no CDN or external fetch. PNGs
and source lines travel in tool-result _meta, not model-visible image strings.
Citation text and errors remain available as structuredContent for non-UI hosts.
Browser ChatGPT still needs a reachable MCP connection, such as a tunnel.

Preview limits: originals over 40 MiB fall back to stored text; PDFs render one
page with a maximum 1,400-pixel edge and a 3 MiB PNG limit. Missing originals,
unsupported formats, or missing PDF renderer show a text fallback. Highlights
are withheld on rotated PDFs and when stored page dimensions disagree with the
source; those cases need the desktop viewer. Markdown is displayed as escaped
source text, not executable HTML or rich Markdown. Archive metadata cannot
supply scripts or external resource URLs.

The backend has no new network listener or directory permission system. It
inherits the existing local MCP server's file permissions and scope. Do not
expose it publicly without authentication and file-access restrictions.

For browser verification, install Playwright and its Chromium browser in a test
environment, then set VERA_BROWSER_TESTS=1 and run the viewer browser test. The
test uses a local host simulator; real ChatGPT installation and rendering remain
a separate integration check. See tests/test_source_viewer_browser.py in the
vera-mcp package. The protocol follows the
[OpenAI UI guide](https://developers.openai.com/plugins/build/chatgpt-ui/).

## Proposed Desktop bridge

The Desktop-managed connection is a proposed feature, not current plugin behavior.
See the [proof-of-concept build plan](desktop-bridge-poc.md) for implementation
milestones and acceptance criteria, and the
[production architecture proposal](desktop-bridge-production.md) for the
public relay, account linking, device authorization, and rollout design.
