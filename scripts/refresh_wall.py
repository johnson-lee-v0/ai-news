"""Refresh the local personal wall; publication is a separate explicit export."""
from argparse import ArgumentParser
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from pulse import wall


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--data-file", type=Path, default=ROOT / "data" / "wall.json")
    parser.add_argument("--public-output", type=Path, help="Explicit sanitized export to public/wall.json; never reads the market database")
    parser.add_argument("--export-only", action="store_true", help="Export the existing validated wall without fetching again")
    args = parser.parse_args()
    if args.export_only and not args.public_output:
        parser.error("--export-only requires --public-output")
    try:
        if args.export_only and not args.data_file.exists():
            raise ValueError("No collected wall exists to export")
        result = {"refresh_skipped": True} if args.export_only else wall.refresh_file(args.data_file)
        if args.public_output:
            result["public_export"] = wall.write_public(args.public_output, wall.load_file(args.data_file, strict=True))
            result["public_written"] = True
        print(json.dumps(result, indent=2))
        return 2 if result.get("error_count") or result.get("skipped_count") else 0
    except (ValueError, OSError, RuntimeError) as exc:
        print("Wall update failed: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
