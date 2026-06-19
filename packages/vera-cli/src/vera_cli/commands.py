from __future__ import annotations

import json
import sys
from pathlib import Path

from vera import convert
from vera.corpus import VeraCorpus
from vera.document import VeraDocument


def str_to_bool(value: str) -> bool:
    return str(value).lower() in {"1", "true", "yes", "y", "on"}


def cmd_convert(args) -> int:
    path = convert(
        args.input,
        args.output,
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
    target = VeraCorpus.open(args.file) if Path(args.file).is_dir() else VeraDocument.open(args.file)
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
            print(json.dumps({"query": args.query, "mode": args.mode, "results": payload}))
            return 0
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
