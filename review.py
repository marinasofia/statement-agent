"""Offline review CLI. Never sends data to a model."""

import argparse
import json
import sqlite3
from pathlib import Path

from core.review import ReviewQueue


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="outputs/review.sqlite")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    imp = sub.add_parser("import-result")
    imp.add_argument(
        "result", help="Full extraction state JSON, including validated_data"
    )
    imp.add_argument("source", help="Original PDF used for content-based deduplication")
    for command in ("show", "correct", "approve", "export", "preview"):
        item = sub.add_parser(command)
        item.add_argument("id")
        if command in ("correct", "approve"):
            item.add_argument("--revision", type=int, required=True)
            item.add_argument("--reviewer", required=True)
            item.add_argument("--reason", required=True)
        if command == "correct":
            item.add_argument(
                "--data", required=True, help="Corrected StatementData JSON file"
            )
        if command == "approve":
            item.add_argument("--acknowledge-skipped", action="store_true")
        if command == "preview":
            item.add_argument("--output", default="outputs/review.html")
        if command == "export":
            item.add_argument("--directory", default="outputs/approved")
    args = parser.parse_args(argv)
    queue = ReviewQueue(args.db)
    try:
        if args.command == "list":
            result = queue.list()
        elif args.command == "import-result":
            result = queue.add(
                json.loads(Path(args.result).read_text()),
                Path(args.source).read_bytes(),
            )
        elif args.command == "show":
            result = queue.get(args.id)
        elif args.command == "preview":
            result = str(queue.preview(args.id, args.output))
        elif args.command == "export":
            result = str(queue.export(args.id, args.directory))
        else:
            queue.change(
                args.id,
                args.revision,
                args.reviewer,
                args.reason,
                data=json.loads(Path(args.data).read_text())
                if args.command == "correct"
                else None,
                approve=args.command == "approve",
                acknowledge_skipped=getattr(args, "acknowledge_skipped", False),
            )
            result = queue.get(args.id)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f"Review action failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
