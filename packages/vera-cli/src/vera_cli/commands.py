from __future__ import annotations

import json
import sys
from pathlib import Path

from vera import batch_convert, convert
from vera.collection import build_library_index, library_index_status, update_library_index
from vera.corpus import VeraCorpus
from vera.document import VeraDocument


def str_to_bool(value: str) -> bool:
    return str(value).lower() in {"1", "true", "yes", "y", "on"}


def cmd_convert(args) -> int:
    input_path = Path(args.input)
    if input_path.is_dir():
        if args.output:
            print("Directory conversion creates each .vera beside its PDF; do not provide an output path.", file=sys.stderr)
            return 2
        report = batch_convert(
            args.input,
            recursive=args.recursive,
            overwrite=args.overwrite,
            model=args.model,
            parser=args.parser,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
            store_original=str_to_bool(args.store_original),
        )
        if args.json:
            print(json.dumps({"ok": report["failed"] == 0, **report}))
        else:
            print(
                f"Found {report['discovered']} PDFs: {report['converted']} converted, "
                f"{report['skipped']} skipped, {report['failed']} failed"
            )
            for entry in report["errors"]:
                print(f"Failed {entry['input']}: {entry['error']}", file=sys.stderr)
        return 1 if report["failed"] else 0

    output = args.output or str(input_path.with_suffix(".vera"))
    path = convert(
        args.input,
        output,
        model=args.model,
        parser=args.parser,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
        store_original=str_to_bool(args.store_original),
    )
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
            print(json.dumps({"file": args.file, **info}))
            return 0
        print(f"File: {args.file}")
        print(f"Format: {info.get('format_name', 'VERA')} v{info.get('format_version')}")
        print(f"Source: {info.get('source_file_name') or info.get('source')}")
        print(f"Pages: {info.get('pages')}")
        print(f"Chunks: {info.get('chunks')}")
        print(f"Embedding model: {info.get('default_embedding_model')}")
        print(f"Embedding dimensions: {info.get('default_embedding_dimension')}")
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
        results = target.search(args.query, mode=args.mode, top_k=args.top_k, context_chunks=args.context_chunks)
        if args.json:
            payload = []
            for result in results:
                entry = result.as_dict()
                if args.figures:
                    entry["figures"] = target.figures_for(result)
                if args.regions:
                    entry["regions"] = target.regions_for(result)
                payload.append(entry)
            response = {"query": args.query, "mode": args.mode, "results": payload}
            if isinstance(target, VeraCorpus):
                response["index"] = {"used": target.uses_index, **target.index_status}
            print(json.dumps(response))
            return 0
        if isinstance(target, VeraCorpus):
            if target.uses_index:
                print(f"Index: {target.index_status.get('index')} (active)")
            elif target.index_status.get("exists"):
                reasons = "; ".join(target.index_status.get("reasons", []))
                print(f"Index: fallback ({reasons})")
        for result in results:
            print(f"Score: {result.score:.4f}")
            file = getattr(result, "file", None)
            if file:
                print(f"File: {file}")
            print(f"Source: {result.source_filename}")
            page = result.page_start if result.page_start == result.page_end else f"{result.page_start}-{result.page_end}"
            print(f"Page: {page}")
            print(f"Heading: {result.heading_path or ''}")
            print()
            print(result.text)
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
        print(json.dumps({"file": args.file, **report}))
        return 0 if report["ok"] else 1
    print(f"VERA validation: {'PASS' if report['ok'] else 'FAIL'}")
    print(f"File: {args.file}")
    counts = report["counts"]
    print(f"Documents: {counts['documents']}")
    print(f"Pages: {counts['pages']}")
    print(f"Chunks: {counts['chunks']}")
    print(f"Embeddings: {counts['embeddings']}")
    print(f"FTS rows: {counts['fts_rows']}")
    print(f"Original document: {'present' if report['checks']['original_document_present'] else 'missing'}")
    print(f"Issues: {len(report['issues'])}")
    for issue in report["issues"]:
        print(f"- {issue}")
    return 0 if report["ok"] else 1


def cmd_export(args) -> int:
    doc = VeraDocument.open(args.file)
    try:
        try:
            path = doc.export_source_document(args.output)
        except ValueError as exc:
            if args.json:
                print(json.dumps({"ok": False, "error": str(exc)}))
            else:
                print(f"Error: {exc}", file=sys.stderr)
            return 1
        source = doc.get_source_document()
    finally:
        doc.close()
    if args.json:
        print(json.dumps({"ok": True, "output": path, "filename": source.filename, "mime_type": source.mime_type, "hash": source.hash}))
    else:
        print(f"Exported {path}")
    return 0


def cmd_mcp(args) -> int:
    from vera.integrations.mcp_server import main as mcp_main

    return mcp_main()


def cmd_eval(args) -> int:
    from vera.evaluate import evaluate

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
        print(f"  Hits: {report['hits']}/{report['total']} ({report['hit_rate']:.0%})  MRR: {report['mrr']:.3f}")
    return 0 if all_ok else 1
