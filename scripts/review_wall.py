"""Queue, import and check source-grounded reviews; no model API is called."""
from argparse import ArgumentParser
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from pulse import wall, wall_review


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    queue = commands.add_parser("queue", help="Write sanitized public candidates for the existing research agent")
    queue.add_argument("--data-file", required=True, type=Path)
    queue.add_argument("--output", type=Path, help="Keep review work outside the public source checkout")
    queue.add_argument("--include-reviewed", action="store_true", help="Also revisit current reviews, including metadata-only triage")
    ingest = commands.add_parser("import", help="Atomically import an externally authored review packet")
    ingest.add_argument("--data-file", required=True, type=Path)
    ingest.add_argument("--packet", required=True, type=Path)
    check = commands.add_parser("check", help="Report public review coverage before publication")
    check.add_argument("--data-file", required=True, type=Path)
    check.add_argument("--require-complete", action="store_true", help="Fail if any public item lacks a current takeaway/access judgment")
    args = parser.parse_args(argv)
    try:
        if not args.data_file.is_file():
            raise ValueError("The wall store does not exist")
        if args.command == "import":
            result = wall_review.import_file(args.data_file, wall_review.read_packet(args.packet))
        else:
            payload = wall.load_file(args.data_file, strict=True)
            result = wall_review.review_queue(payload, args.include_reviewed) if args.command == "queue" else wall_review.coverage(payload)
        encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.command == "queue" and args.output:
            if args.output.resolve() == args.data_file.resolve():
                raise ValueError("Review queue output cannot replace its wall store")
            if args.output.is_symlink():
                raise ValueError("Review queue output must not be a symlink")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded, encoding="utf-8")
            print(json.dumps({"queued_items": len(result["items"]), "coverage": result["coverage"]}, indent=2))
        else:
            print(encoded, end="")
        return 2 if args.command == "check" and args.require_complete and not result["complete"] else 0
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
        print("Wall review failed: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
