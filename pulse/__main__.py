from argparse import ArgumentParser
import json
from pathlib import Path
import sys
from .server import ROOT, dashboard, refresh, serve
from .research import import_records


def main():
    parser = ArgumentParser(description="AI Stock Pulse — local public-source evidence feed")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data", help="Separate data directory (fixtures/tests must not use live data)")
    sub = parser.add_subparsers(dest="command", required=True)
    server_parser = sub.add_parser("serve", help="Serve on loopback, choosing an unused port")
    server_parser.add_argument("--port", type=int, default=8765)
    sub.add_parser("refresh", help="Fetch configured public sources once and save a daily snapshot")
    sub.add_parser("export", help="Export current dashboard JSON")
    importer = sub.add_parser("import-curation", help="Import dated, source-backed notes, financing or earnings JSON")
    importer.add_argument("file", type=Path)
    args = parser.parse_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    db_path = args.data_dir.resolve() / "pulse.sqlite3"
    try:
        if args.command == "serve":
            if args.port < 1024 or args.port > 65535:
                parser.error("Use a port from 1024 to 65535")
            serve(db_path, args.port)
        elif args.command == "refresh":
            result = refresh(db_path)
            print(json.dumps(result, indent=2))
            if result.get("error_count", 0) or result.get("skipped_count", 0):
                return 2
        elif args.command == "export":
            print(json.dumps(dashboard(db_path), indent=2, ensure_ascii=False))
        else:
            payload = json.loads(args.file.read_text(encoding="utf-8"))
            print(json.dumps(import_records(db_path, payload), indent=2))
    except (ValueError, RuntimeError, OSError) as exc:
        print("Error: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
