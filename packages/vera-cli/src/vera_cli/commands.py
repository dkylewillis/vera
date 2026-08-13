from __future__ import annotations

import json
import sys
from pathlib import Path

from vera.collection import build_library_index, library_index_status, update_library_index
from vera.corpus import VeraCorpus
from vera.document import VeraDocument
from vera import UnknownEmbeddingModelError
from vera_ingest import (
    UnknownIngestPipelineError,
    batch_convert,
    convert,
)
from vera_ingest.viewer import (
    export_source_document,
    figures_for,
    get_source_document,
    regions_for,
    result_payload,
)
from vera_ingest_pymupdf import (
    OCRLanguageDownloadError,
    UnknownOCRLanguageError,
    describe_ocr_languages,
    download_ocr_language_data,
)


_TRUE_TOKENS = {"1", "true", "yes", "y", "on"}
_FALSE_TOKENS = {"0", "false", "no", "n", "off", ""}


def str_to_bool(value: str) -> bool:
    lowered = str(value).strip().lower()
    if lowered in _TRUE_TOKENS:
        return True
    if lowered in _FALSE_TOKENS:
        return False
    raise ValueError(f"invalid boolean value: {value!r}")


def _document_for(target, result) -> VeraDocument:
    if isinstance(target, VeraCorpus):
        return target.document(result.file)
    return target


def _archive_locator(requested: str, document: VeraDocument) -> dict[str, str]:
    return {"file": requested, "path": str(Path(document.path).resolve())}


def _pipeline_options_from_args(args) -> dict[str, object]:
    return _key_value_options_from_args(getattr(args, "pipeline_options", []) or [])


def _embedder_options_from_args(args) -> dict[str, object]:
    return _key_value_options_from_args(getattr(args, "embedder_options", []) or [])


def _key_value_options_from_args(pairs) -> dict[str, object]:
    """Coerce KEY=VALUE tokens without ``float()``.

    Dotted tokens such as ``3.10`` or ``ocr_language=1.0`` stay strings.
    Whole-digit tokens become ints; ``true``/``false``/``yes``/``no``/``on``/
    ``off`` become bools. ``from_mapping`` then validates each typed field
    (so ``ocr_download=1`` is int ``1``, accepted by ``require_bool``).
    """
    options: dict[str, object] = {}
    for key, raw in pairs:
        text = str(raw).strip()
        lowered = text.lower()
        if lowered in {"true", "yes", "y", "on"}:
            options[key] = True
        elif lowered in {"false", "no", "n", "off"}:
            options[key] = False
        elif text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
            options[key] = int(text)
        else:
            options[key] = text
    return options


def cmd_convert(args) -> int:
    input_path = Path(args.input)
    pipeline_options = _pipeline_options_from_args(args)
    embedder_options = _embedder_options_from_args(args)
    try:
        if input_path.is_dir():
            if args.output:
                message = (
                    "Directory conversion creates each .vera beside its PDF; "
                    "do not provide an output path."
                )
                if args.json:
                    print(json.dumps({"ok": False, "error": message}))
                else:
                    print(message, file=sys.stderr)
                return 2
            report = batch_convert(
                args.input,
                recursive=args.recursive,
                overwrite=args.overwrite,
                model=args.model,
                parser=args.parser,
                chunk_size=args.chunk_size,
                overlap=args.overlap,
                store_original=args.store_original,
                ocr_mode=args.ocr_mode,
                ocr_language=args.ocr_language,
                ocr_dpi=args.ocr_dpi,
                ocr_download=args.ocr_allow_download,
                pipeline_options=pipeline_options or None,
                embedder_options=embedder_options or None,
            )
            unsuccessful = report["failed"] + report["malformed"]
            if args.json:
                print(json.dumps({"ok": unsuccessful == 0, **report}))
            else:
                print(
                    f"Found {report['discovered']} PDFs: {report['converted']} converted, "
                    f"{report['skipped']} skipped, {report['malformed']} malformed, "
                    f"{report['failed']} failed"
                )
                for entry in report["malformed_existing"]:
                    issues = "; ".join(entry["issues"])
                    print(f"Malformed {entry['output']}: {issues}", file=sys.stderr)
                for entry in report["errors"]:
                    print(f"Failed {entry['input']}: {entry['error']}", file=sys.stderr)
            return 1 if unsuccessful else 0

        output = args.output or str(input_path.with_suffix(".vera"))
        path = convert(
            args.input,
            output,
            model=args.model,
            parser=args.parser,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
            store_original=args.store_original,
            ocr_mode=args.ocr_mode,
            ocr_language=args.ocr_language,
            ocr_dpi=args.ocr_dpi,
            ocr_download=args.ocr_allow_download,
            pipeline_options=pipeline_options or None,
            embedder_options=embedder_options or None,
        )
    except (UnknownIngestPipelineError, UnknownEmbeddingModelError) as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}))
        else:
            print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"ok": True, "output": str(path)}))
    else:
        print(f"Created {path}")
    return 0


def cmd_inspect(args) -> int:
    doc = VeraDocument.open(args.file)
    try:
        info = doc.inspect()
        if args.json:
            print(json.dumps({**info, **_archive_locator(args.file, doc)}))
            return 0
        print(f"File: {args.file}")
        print(f"Format: {info.get('format_name', 'VERA')} v{info.get('format_version')}")
        print(f"Source: {info.get('source_file_name') or info.get('source')}")
        print(f"Pages: {info.get('pages')}")
        print(f"Chunks: {info.get('chunks')}")
        print(f"Embedding model: {info.get('default_embedding_model')}")
        print(f"Embedding dimensions: {info.get('default_embedding_dimension')}")
        print(f"Embedding normalization: {info.get('default_embedding_normalization', 'unknown')}")
        print(f"Parser: {info.get('parser_name')}")
        print(f"Created: {info.get('created_at')}")
    finally:
        doc.close()
    return 0


def cmd_search(args) -> int:
    target = (
        VeraCorpus.open(
            args.file,
            recursive=True if getattr(args, "recursive", False) else None,
            excludes=getattr(args, "exclude", None),
        )
        if Path(args.file).is_dir()
        else VeraDocument.open(args.file)
    )
    try:
        results = target.search(
            text=args.query,
            mode=args.mode,
            top_k=args.top_k,
            context_chunks=args.context_chunks,
        )
        if args.json:
            payload = []
            for result in results:
                entry = result_payload(result)
                document = _document_for(target, result)
                if args.figures:
                    entry["figures"] = figures_for(document, result)
                if args.regions:
                    entry["regions"] = regions_for(document, result)
                payload.append(entry)
            response = {"query": args.query, "mode": args.mode, "results": payload}
            if isinstance(target, VeraCorpus):
                response["index"] = {"used": target.uses_index, **target.index_status}
                response["skipped_files"] = target.invalid_files
                response["skipped_semantic_model_groups"] = target.skipped_semantic_model_groups
            print(json.dumps(response))
            return 0
        if isinstance(target, VeraCorpus):
            if target.uses_index:
                print(f"Index: {target.index_status.get('index')} (active)")
            elif target.index_status.get("exists"):
                reasons = "; ".join(target.index_status.get("reasons", []))
                print(f"Index: fallback ({reasons})")
            for group in target.skipped_semantic_model_groups:
                print(
                    "Warning: skipped semantic model group "
                    f"{group['model_name']} ({group['dimension']} dimensions): "
                    f"{group['error']}"
                )
        for result in results:
            metadata = result.record.metadata
            print(f"Score: {result.score:.4f}")
            file = getattr(result, "file", None)
            if file:
                print(f"File: {file}")
            print(f"Source: {metadata.get('source_filename')}")
            page_start = metadata.get("page_start")
            page_end = metadata.get("page_end")
            page = page_start if page_start == page_end else f"{page_start}-{page_end}"
            print(f"Page: {page}")
            print(f"Heading: {metadata.get('heading_path') or ''}")
            print()
            print(result.record.text)
            print("-" * 72)
    finally:
        target.close()
    return 0


def _print_index_report(report: dict) -> None:
    print(f"Index: {report['index']}")
    print(f"Directory: {report['directory']}")
    if "fresh" in report:
        print(f"Status: {'fresh' if report['fresh'] else 'stale'}")
        for reason in report.get("reasons", []):
            print(f"- {reason}")
        return
    print(f"Files: {report['indexed']}/{report['discovered']}")
    print(f"Chunks: {report['chunks']}")
    print(
        "Changes: "
        f"{report['added']} added, {report['changed']} changed, "
        f"{report['moved']} moved, {report['removed']} removed"
    )
    for category in ("invalid", "incompatible"):
        for item in report.get(category, []):
            print(f"{category.title()}: {item['file']}: {item['reason']}")


def cmd_index_build(args) -> int:
    report = build_library_index(
        args.directory,
        recursive=args.recursive,
        excludes=args.exclude or (),
    )
    if args.json:
        print(json.dumps(report))
    else:
        _print_index_report(report)
    return 0


def cmd_index_update(args) -> int:
    report = update_library_index(args.directory)
    if args.json:
        print(json.dumps(report))
    else:
        _print_index_report(report)
    return 0


def cmd_index_status(args) -> int:
    report = library_index_status(args.directory)
    if args.json:
        print(json.dumps(report))
    else:
        _print_index_report(report)
    return 0 if report.get("fresh") else 1


def cmd_validate(args) -> int:
    doc = VeraDocument.open(args.file)
    try:
        report = doc.validate()
    finally:
        doc.close()
    if args.json:
        print(json.dumps({**report, **_archive_locator(args.file, doc)}))
        return 0 if report["ok"] else 1
    print(f"VERA validation: {'PASS' if report['ok'] else 'FAIL'}")
    print(f"File: {args.file}")
    counts = report["counts"]
    print(f"Chunks: {counts['chunks']}")
    print(f"Embeddings: {counts['embeddings']}")
    print(f"Attachments: {counts['attachments']}")
    print(f"FTS rows: {counts['fts_rows']}")
    print(
        f"Original document: {'present' if report['checks']['original_document_present'] else 'missing'}"
    )
    print(f"Issues: {len(report['issues'])}")
    for issue in report["issues"]:
        print(f"- {issue}")
    return 0 if report["ok"] else 1


def cmd_export(args) -> int:
    doc = VeraDocument.open(args.file)
    try:
        try:
            path = export_source_document(doc, args.output)
        except ValueError as exc:
            if args.json:
                print(json.dumps({"ok": False, "error": str(exc)}))
            else:
                print(f"Error: {exc}", file=sys.stderr)
            return 1
        source = get_source_document(doc)
    finally:
        doc.close()
    if args.json:
        print(
            json.dumps(
                {
                    "ok": True,
                    "output": path,
                    "filename": source.filename,
                    "mime_type": source.media_type,
                    "hash": source.checksum,
                }
            )
        )
    else:
        print(f"Exported {path}")
    return 0


def cmd_mcp(args) -> int:
    from vera_mcp import main as mcp_main

    return mcp_main()


def cmd_ocr_languages_list(args) -> int:
    entries = describe_ocr_languages(args.language)
    if args.json:
        print(json.dumps({"ok": True, "languages": entries}))
        return 0
    for entry in entries:
        state = "bundled" if entry["bundled"] else ("cached" if entry["cached"] else "not cached")
        size = entry.get("size_bytes")
        size_note = f", {size / (1024 * 1024):.1f} MB" if isinstance(size, int) else ""
        downloadable = "" if entry["downloadable"] else " (manual TESSDATA_PREFIX install required)"
        print(f"{entry['code']:<8} {entry['name']:<24} {state}{size_note}{downloadable}")
    return 0


def cmd_ocr_languages_download(args) -> int:
    downloaded: list[str] = []

    def report_progress(code: str, downloaded_bytes: int, total_bytes: int) -> None:
        if args.json or total_bytes <= 0:
            return
        percent = min(100, int(downloaded_bytes * 100 / total_bytes))
        print(f"\r{code}: {percent}%", end="", file=sys.stderr, flush=True)

    try:
        cache_dir = download_ocr_language_data(args.language, progress=report_progress)
    except (UnknownOCRLanguageError, OCRLanguageDownloadError) as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}))
        else:
            print(str(exc), file=sys.stderr)
        return 2
    if not args.json:
        print(file=sys.stderr)  # newline after the last progress line
    downloaded = [part.strip() for part in args.language.split("+") if part.strip()]
    if args.json:
        print(
            json.dumps(
                {
                    "ok": True,
                    "language": args.language,
                    "downloaded": downloaded,
                    "cache_dir": cache_dir,
                }
            )
        )
    else:
        print(f"Downloaded {', '.join(downloaded)} into {cache_dir}")
    return 0


def cmd_eval(args) -> int:
    from vera_cli.evaluate import evaluate

    summary = evaluate(args.file, args.queries, mode=args.mode, top_k=args.top_k)
    all_ok = all(report["hits"] == report["total"] for report in summary["reports"])
    if args.json:
        print(json.dumps(summary))
        return 0 if all_ok else 1
    print(f"File: {summary['file']}")
    print(f"Queries: {summary['queries_file']}")
    for report in summary["reports"]:
        print()
        print(f"Mode: {report['mode']}  (top_k={report['top_k']})")
        for entry in report["queries"]:
            status = f"HIT rank={entry['rank']}" if entry["hit"] else "MISS"
            note = f"  # {entry['note']}" if entry["note"] else ""
            print(f"  [{status:>10}] {entry['query']}{note}")
        print(
            f"  Hits: {report['hits']}/{report['total']} ({report['hit_rate']:.0%})  MRR: {report['mrr']:.3f}"
        )
    return 0 if all_ok else 1
