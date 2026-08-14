import re
from pathlib import Path
from urllib.parse import unquote

import vera_doc
from helpers.cli import leaf_commands as _leaf_commands
from vera_cli.main import build_parser

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
PACKAGES = ROOT / "packages"
CLI_REFERENCE = DOCS / "cli-reference.md"


def _documentation_files() -> list[Path]:
    return [
        ROOT / "README.md",
        ROOT / "AGENTS.md",
        *DOCS.rglob("*.md"),
        *(ROOT / "skills" / "vera").rglob("*.md"),
    ]


def _prose_files() -> list[Path]:
    """Documentation plus the prose that ships inside the packages.

    Package READMEs become PyPI long descriptions and docstrings become the
    published API reference, so both carry the same accuracy obligation as
    ``docs/``.
    """
    return [
        *_documentation_files(),
        ROOT / "CONTRIBUTING.md",
        PACKAGES / "README.md",
        *PACKAGES.glob("*/README.md"),
        *PACKAGES.glob("*/src/**/*.py"),
    ]


def test_local_documentation_links_resolve():
    link_pattern = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
    for document in _documentation_files():
        text = document.read_text(encoding="utf-8")
        for raw_target in link_pattern.findall(text):
            target = raw_target.split("#", 1)[0].strip()
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            path = (document.parent / unquote(target)).resolve()
            assert path.exists(), f"{document.relative_to(ROOT)} links to missing {raw_target}"


def test_site_pages_only_link_relatively_within_the_docs_tree():
    """MkDocs resolves relative links against the pages it builds, not the repo.

    A link such as ``../CHANGELOG.md`` exists on disk, so
    ``test_local_documentation_links_resolve`` accepts it, but
    ``mkdocs build --strict`` fails it. Repo files outside ``docs/`` have to be
    linked by URL.
    """
    link_pattern = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
    for document in DOCS.rglob("*.md"):
        text = document.read_text(encoding="utf-8")
        for raw_target in link_pattern.findall(text):
            target = raw_target.split("#", 1)[0].strip()
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            path = (document.parent / unquote(target)).resolve()
            assert path.is_relative_to(DOCS), (
                f"{document.relative_to(ROOT)} links to {raw_target}, which is outside "
                "docs/; mkdocs --strict cannot resolve it, so use a full URL"
            )


def test_prose_refers_to_the_storage_package_as_vera_doc():
    """0.3 renamed the storage import from ``vera`` to ``vera_doc``.

    Only names the package actually exports are matched, so the ``vera``
    console script, the ``.vera`` extension, the ``vera.embedders`` and
    ``vera.ingest_pipelines`` entry-point groups, and the
    ``application/vnd.vera.*`` media types are all left alone.
    """
    exports = "|".join(sorted(vera_doc.__all__))
    stale = re.compile(rf"\bvera\.({exports})\b")
    violations = []
    for document in _prose_files():
        for number, line in enumerate(document.read_text(encoding="utf-8").splitlines(), 1):
            violations.extend(
                f"{document.relative_to(ROOT)}:{number} refers to {match.group(0)}"
                for match in stale.finditer(line)
            )
    assert violations == [], "use vera_doc.<name>: " + "; ".join(violations)


def test_documentation_index_lists_user_guides():
    index = (DOCS / "user-documentation.md").read_text(encoding="utf-8")
    guides = {
        "getting-started.md",
        "desktop-app-getting-started.md",
        "examples.md",
        "troubleshooting.md",
        "conversion.md",
        "searching.md",
        "document-libraries.md",
        "figures-and-regions.md",
        "validation-and-export.md",
        "evaluation.md",
        "python-api.md",
        "mcp.md",
        "cli-reference.md",
        "library-index-structure.md",
    }
    for guide in guides:
        assert f"]({guide})" in index
        assert (DOCS / guide).is_file()


def test_human_cli_reference_covers_parser_commands_and_options():
    reference = CLI_REFERENCE.read_text(encoding="utf-8")
    options: set[str] = set()
    for path, parser in _leaf_commands(build_parser()):
        command = " ".join(path)
        assert f"## `vera {command}" in reference, f"undocumented command: vera {command}"
        for action in parser._actions:
            options.update(
                option
                for option in action.option_strings
                if option.startswith("--") and option != "--help"
            )
    for option in sorted(options):
        assert f"`{option}" in reference, f"undocumented option: {option}"


def test_documented_cli_examples_parse():
    parser = build_parser()
    examples = [
        ["convert", "input.pdf", "output.vera", "--model", "hashing", "--json"],
        [
            "convert",
            "input.pdf",
            "output.vera",
            "--pipeline-option",
            "chunk_size=700",
            "--pipeline-option",
            "ocr_mode=auto",
            "--json",
        ],
        [
            "convert",
            "input.pdf",
            "output.vera",
            "--model",
            "hashing",
            "--embedder-option",
            "dimension=256",
            "--json",
        ],
        ["inspect", "output.vera", "--json"],
        [
            "search",
            "output.vera",
            "parking requirements",
            "--mode",
            "hybrid",
            "--top-k",
            "5",
            "--context-chunks",
            "1",
            "--figures",
            "--regions",
            "--json",
        ],
        ["index", "build", "library", "--recursive", "--exclude", "archive/**", "--json"],
        ["index", "update", "library", "--json"],
        ["index", "status", "library", "--json"],
        ["validate", "output.vera", "--json"],
        ["export", "output.vera", "exports", "--json"],
        ["eval", "output.vera", "queries.json", "--mode", "all", "--top-k", "5", "--json"],
        ["mcp"],
    ]
    for argv in examples:
        args = parser.parse_args(argv)
        assert callable(args.func)


def test_agents_rule_requires_human_documentation_updates():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "Keep human and agent documentation current" in agents
    assert "Any user-visible feature change" in agents
    assert "Do not merge a feature whose" in agents


def test_hardening_json_contracts_are_documented():
    conversion = (DOCS / "conversion.md").read_text(encoding="utf-8")
    libraries = (DOCS / "document-libraries.md").read_text(encoding="utf-8")
    desktop = (DOCS / "desktop-app-getting-started.md").read_text(encoding="utf-8")
    desktop_architecture = (DOCS / "desktop-app-architecture.md").read_text(encoding="utf-8")
    mcp = (DOCS / "mcp.md").read_text(encoding="utf-8")
    python_api = (DOCS / "python-api.md").read_text(encoding="utf-8")
    cli_reference = CLI_REFERENCE.read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")

    assert "malformed_existing" in conversion
    assert "source_file_hash" in conversion
    assert "skipped_existing" in conversion
    assert "source_file_hash" in cli_reference
    assert "requires OCR" in conversion
    assert "## Pipeline options" in conversion
    assert "--pipeline-option" in conversion
    assert "pipeline_options" in conversion
    assert "100–3000" in conversion
    assert "8–4096" in conversion
    assert "IngestRequest" in conversion
    assert "describe_ingest_pipelines" in conversion
    assert "PipelineConfigForm" in conversion
    assert "Advanced pipeline options" in conversion
    assert "compatibility alias" in conversion.lower() or "Compatibility aliases" in conversion
    assert "ocr_language=en" in conversion
    assert "whitespace-split words" in conversion
    assert "Sliding-window character chunks" not in conversion
    assert "overlap" in conversion and "ocr_dpi" in conversion
    assert "**not** forwarded to" in conversion
    assert "Tesseract `--ocr-language`" in conversion
    assert "--embedder-option" in conversion
    assert "embedder_options" in conversion
    assert (
        "describe_embedding_providers" in conversion
        or "creating-an-embedding-provider.md" in conversion
    )
    assert "`--pipeline-option KEY=VALUE`" in cli_reference
    assert "`--embedder-option KEY=VALUE`" in cli_reference
    assert "compatibility alias" in cli_reference.lower() or "Compatibility alias" in cli_reference
    assert "pipeline-owned typed options" in roadmap
    assert "`vera convert --pipeline-option KEY=VALUE`" in roadmap
    assert "describe_ingest_pipelines" in roadmap
    assert "PipelineConfigForm" in roadmap
    assert "EmbedderOptions" in roadmap
    assert "describe_embedding_providers" in roadmap
    assert "--embedder-option" in roadmap
    assert "preflight_embedder" in roadmap
    assert "list_embedding_models" in roadmap
    assert "credential_env" in roadmap
    assert (DOCS / "creating-an-embedding-provider.md").is_file()
    guide = (DOCS / "creating-an-embedding-provider.md").read_text(encoding="utf-8")
    assert "EmbedderOptions" in guide
    assert "vera.embedder_descriptors" in guide
    assert "credential_env" in guide
    assert "Do not put API keys in Options" in guide or "do not put secrets" in guide.lower()
    assert (
        'scope": "convert"' in guide or "scope: convert" in guide or '"scope": "convert"' in guide
    )
    assert "vera.embedder_models" in guide
    assert 'metadata["minimum"]' in guide
    assert 'metadata["maximum"]' in guide
    ingest_guide = (DOCS / "creating-an-ingest-pipeline.md").read_text(encoding="utf-8")
    assert "must be between 100 and 3000" in ingest_guide
    assert "preflight_embedder" in conversion
    assert "credential_env" in conversion
    assert "list_embedding_models" in desktop_architecture
    assert "preflight_embedder" in desktop_architecture
    assert "credential_env" in desktop_architecture
    assert "skipped_files" in libraries
    assert "skipped_semantic_model_groups" in libraries
    assert "does not reopen archives" in libraries
    assert "does not rebuild" in libraries
    assert "summary_complete" in libraries
    assert "Collection indexes are persistent" in desktop
    assert "Use **Inspect** in the Info view" in desktop
    assert "corpus opens on the first" in desktop
    assert "indexing runs in the background" in desktop
    assert "completed archives" in desktop
    assert "finalizing phase" in desktop
    assert "Inspection runs on a sidecar worker" in desktop
    assert "independently of simultaneous indexing or conversion" in desktop
    assert "Selecting another citation supersedes" in desktop
    assert "within five minutes" in desktop
    assert "matching" in desktop and "sibling" in desktop
    assert "`write_attachment()`" in python_api
    assert "`size`" in python_api
    assert "Answer prose appears incrementally" in desktop
    assert "withholds inline tool-call markup" in desktop
    assert "initially returns only figure metadata" in desktop
    assert "loads image previews" in desktop
    assert "describe_ingest_pipelines" in desktop
    assert "PipelineConfigForm" in desktop
    assert "Advanced pipeline options" in desktop
    assert "only explicit `search_start` and `search_done`" in desktop_architecture
    assert "Token-level `answer_delta`" in desktop_architecture
    assert "describe_ingest_pipelines" in desktop_architecture
    assert "describe_embedding_providers" in desktop_architecture
    assert "embedder_options" in desktop_architecture
    assert "pipeline_options" in desktop_architecture
    assert "PipelineConfigForm" in desktop_architecture
    assert "Advanced pipeline options" in desktop_architecture
    assert "**Reconvert…**" in desktop_architecture
    assert "opens Convert immediately" in desktop_architecture
    assert "the folder badge spins" in desktop_architecture
    assert "**Convert PDFs…**" in desktop_architecture
    assert "not for an explicit menu action" in desktop_architecture
    assert "Shift+click" in desktop_architecture
    assert "## Reconvert with a different parser or embedding" in conversion
    assert "**Reconvert…**" in conversion
    assert "registers the default" in desktop_architecture and "pymupdf" in desktop_architecture
    assert "copy-metadata" in (
        ROOT / "packages" / "vera-app" / "scripts" / "build-sidecar.cjs"
    ).read_text(encoding="utf-8")
    assert "ensure_registered" in (
        ROOT / "packages" / "vera-ingest-pymupdf" / "src" / "vera_ingest_pymupdf" / "__init__.py"
    ).read_text(encoding="utf-8")
    assert "PyMuPDF ingest pipeline" in desktop
    assert "ingest_pipeline" in desktop
    assert "vera-ingest-docling" in conversion or "docling:hybrid" in conversion
    assert "provider:model-id" in desktop
    assert "Hugging Face" in desktop
    assert "HF_TOKEN" in desktop
    assert "Hugging Face" in (DOCS / "packages" / "vera-app.md").read_text(encoding="utf-8")
    assert "Advanced pipeline options" in (DOCS / "packages" / "vera-app.md").read_text(
        encoding="utf-8"
    )
    assert "`attachment_metadata()`" in python_api
    assert "do not contain a `data` field" in python_api
    assert "pipeline_options" in python_api
    assert "embedder_options" in python_api
    assert "New callers should pass" in python_api
    assert "IngestRequest" in python_api
    assert "may change before 1.0" in python_api
    assert "not bundled" in python_api
    assert "register_ingest_pipeline" in python_api
    assert "register_embedder" in python_api
    assert "may change before 1.0" in ingest_guide
    assert "may change before 1.0" in guide
    assert "not bundled" in guide
    ingest_pkg = (DOCS / "packages" / "vera-ingest.md").read_text(encoding="utf-8")
    assert "register_ingest_pipeline" in ingest_pkg
    assert "may change before 1.0" in ingest_pkg
    assert "app-private" in desktop_architecture
    assert "until" in desktop_architecture and "versioned" in desktop_architecture
    assert "allow_empty=True" in libraries
    assert "`skipped_files`" in mcp
    assert "`skipped_semantic_model_groups`" in mcp
    assert "top_k: int = 10" in mcp
    assert "matching the CLI" in mcp


def test_figures_storage_map_is_documented():
    figures = (DOCS / "figures-and-regions.md").read_text(encoding="utf-8")
    spec = (DOCS / "vera-spec-v0.2.md").read_text(encoding="utf-8")

    assert "## Storage map (VERA 0.2 schema)" in figures
    for marker in (
        "`chunks`",
        "`metadata_json`",
        '`"regions"`',
        "`attachments`",
        "`chunk_attachments`",
        "`viewer_pages`",
        "`viewer_blocks`",
        "`vera_metadata`",
        "`archive_metadata`",
    ):
        assert marker in figures, f"storage map missing {marker}"
    assert "figures-and-regions.md#storage-map-vera-02-schema" in spec


def test_release_0_3_versioning_and_install_pins():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    getting_started = (DOCS / "getting-started.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    mkdocs = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    index = (DOCS / "user-documentation.md").read_text(encoding="utf-8")
    skill = (ROOT / "skills" / "vera" / "SKILL.md").read_text(encoding="utf-8")

    assert (ROOT / "CHANGELOG.md").is_file()
    assert "### What 0.3 means" in readme
    assert "archive format remains **0.2**" in readme
    assert "archive format remains **0.2**" in getting_started
    assert "vera-cli>=0.3.0" in readme
    assert "vera-cli>=0.3.0" in getting_started
    assert ">=0.2.4" not in readme
    assert ">=0.2.4" not in getting_started
    assert "UnknownEmbeddingModelError" in changelog
    assert "falling back to PyMuPDF" in changelog
    assert "format remains **0.2**" in changelog
    assert "### Desktop" in changelog
    assert "Open Folder" in changelog
    assert "saveVera" in changelog
    assert "defaultVeraPath" in changelog
    assert "follow-ups after the 0.3.0 tag" in roadmap
    assert "not blockers for 0.3.0" in roadmap
    assert "HANDOFF.md" not in mkdocs
    assert "HANDOFF.md" not in index
    assert not (DOCS / "HANDOFF.md").exists()
    assert not (ROOT / "TODO.md").exists()
    assert not (ROOT / "vera_project_brief.md").exists()
    assert "format_version` remains" in skill or "format_version remains" in skill
    assert "may not yet be published to PyPI" not in getting_started
    assert "may not yet be published to PyPI" not in (DOCS / "index.md").read_text(encoding="utf-8")
    assert "may not yet be published to PyPI" not in (DOCS / "python-api.md").read_text(
        encoding="utf-8"
    )

    skip = {".venv", "node_modules", ".git", ".pytest_cache", "dist-electron", "__pycache__"}
    leftover_pins: list[str] = []
    leftover_caveats: list[str] = []
    for path in ROOT.rglob("*.md"):
        if any(part in skip for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        if ">=0.2.4" in text:
            leftover_pins.append(str(path.relative_to(ROOT)))
        if "may not yet be published to PyPI" in text:
            leftover_caveats.append(str(path.relative_to(ROOT)))
    assert leftover_pins == [], f"stale >=0.2.4 install pins in {leftover_pins}"
    assert leftover_caveats == [], f"stale PyPI caveats in {leftover_caveats}"


def test_architecture_vera_doc_reads_format_0_2_only():
    architecture = (DOCS / "architecture.md").read_text(encoding="utf-8")
    assert "read-only compatibility for 0.1" not in architecture
    assert "Format 0.1 is historical" in architecture
    assert "`vera-doc` reads 0.2 archives only" in architecture


def test_docs_index_library_install_includes_default_pdf_pipeline():
    index = (DOCS / "index.md").read_text(encoding="utf-8")
    marker = "Library-only"
    assert marker in index
    block = index.split(marker, 1)[1].split("```bash", 1)[1].split("```", 1)[0]
    assert "vera-doc>=0.3.0" in block
    assert "vera-ingest>=0.3.0" in block
    assert "vera-ingest-pymupdf>=0.3.0" in block


def test_skill_version_is_schema_not_product_or_format():
    skill = (ROOT / "skills" / "vera" / "SKILL.md").read_text(encoding="utf-8")
    assert 'version: "1.0.0"' in skill
    assert "skill's schema version" in skill
    assert "not the VERA" in skill
    assert "archive format (0.2)" in skill


def test_agents_and_skill_document_convert_json_on_failure():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    skill = (ROOT / "skills" / "vera" / "SKILL.md").read_text(encoding="utf-8")
    assert "failed `convert`" in agents
    assert "failed `convert`" in skill
