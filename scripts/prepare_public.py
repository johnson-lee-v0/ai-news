"""Archive reviewed inputs privately and prepare both bounded public snapshots."""
from argparse import ArgumentParser
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.build_site import prepare_snapshot, safe_text
from pulse import wall, wall_review


def _inside(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _archive(directory, name, data):
    digest = hashlib.sha256(data).hexdigest()
    target = directory / (name + '-' + digest + '.json')
    if target.exists():
        if target.is_symlink() or target.read_bytes() != data:
            raise ValueError('Existing archive does not match its content hash')
    else:
        with target.open('xb') as handle:
            handle.write(data)
    return str(target)


def prepare(source, wall_source, archive_dir, output_dir, dry_run=False):
    source, wall_source, archive_dir, output_dir = map(Path, (source, wall_source, archive_dir, output_dir))
    if archive_dir.is_symlink() or output_dir.is_symlink():
        raise ValueError('Publication and archive directories cannot be symlinks')
    if _inside(archive_dir.resolve(), ROOT.resolve()) or _inside(archive_dir.resolve(), output_dir.resolve()):
        raise ValueError('The full reviewed archive must stay outside the public checkout and output')
    for name in ('brief.json', 'wall.json'):
        if (output_dir / name).is_symlink():
            raise ValueError('Public snapshot cannot be a symlink')
    # No output, archive or existing input changes until BOTH review gates pass.
    original = source.read_bytes()
    selected, rotation = prepare_snapshot(json.loads(original))
    if wall_source.is_symlink() or wall_source.stat().st_size > 10_000_000:
        raise ValueError('Unexpected wall store type or size')
    original_wall = wall_source.read_bytes()
    safe_wall = wall.public_projection(wall.validate_public(json.loads(original_wall)))
    safe_text(safe_wall)
    coverage = wall_review.coverage(safe_wall)
    if not coverage['complete']:
        raise ValueError('Public wall publication blocked: '+str(coverage['missing_reviews'])+' displayed item(s) lack a current structured takeaway/access judgment')
    output_bytes = {
        'brief.json': (json.dumps(selected, ensure_ascii=False, indent=2)+'\n').encode(),
        'wall.json': (json.dumps(safe_wall, ensure_ascii=False, indent=2)+'\n').encode(),
    }
    report = {'dry_run':dry_run, 'rotation':rotation, 'wall_coverage':coverage,
              'candidate_sha256':hashlib.sha256(original).hexdigest(),
              'wall_input_sha256':hashlib.sha256(original_wall).hexdigest(),
              'output_sha256':{key:hashlib.sha256(data).hexdigest() for key,data in output_bytes.items()},
              'archive':{}, 'written':False}
    if dry_run:
        return report
    archive_dir.mkdir(parents=True, exist_ok=True)
    report['archive']['full_candidate'] = _archive(archive_dir, 'reviewed-candidate', original)
    # The local wall remains untouched. Its private archive is never in Git/Pages.
    report['archive']['full_wall'] = _archive(archive_dir, 'reviewed-wall', original_wall)
    previous_bytes = {}
    for name in ('brief.json', 'wall.json'):
        previous = output_dir / name
        previous_bytes[name] = previous.read_bytes() if previous.exists() else None
        if previous.exists():
            report['archive']['previous_'+name] = _archive(archive_dir, 'previous-'+name[:-5], previous_bytes[name])
    output_dir.mkdir(parents=True, exist_ok=True)
    temporary = {}
    replaced = []
    try:
        for name, data in output_bytes.items():
            with tempfile.NamedTemporaryFile(dir=output_dir, prefix='.'+name+'-', delete=False) as handle:
                temporary[name] = Path(handle.name)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        if source.read_bytes() != original or wall_source.read_bytes() != original_wall:
            raise ValueError('Reviewed input changed during preparation; review the current input first')
        for name, previous in previous_bytes.items():
            current = output_dir / name
            if (current.read_bytes() if current.exists() else None) != previous:
                raise ValueError('Public snapshot changed during preparation; refusing to overwrite it')
        for name, path in temporary.items():
            os.replace(path, output_dir / name)
            replaced.append(name)
    except Exception:
        # Each replace is atomic; restore earlier replacements if the second
        # write fails so a partial preparation cannot leave mismatched feeds.
        for name in reversed(replaced):
            previous = previous_bytes[name]
            if previous is None:
                (output_dir / name).unlink()
            else:
                with tempfile.NamedTemporaryFile(dir=output_dir, prefix='.restore-', delete=False) as handle:
                    restore = Path(handle.name)
                    handle.write(previous)
                    handle.flush()
                    os.fsync(handle.fileno())
                try:
                    os.replace(restore, output_dir / name)
                finally:
                    if restore.exists():
                        restore.unlink()
        raise
    finally:
        for path in temporary.values():
            if path.exists():
                path.unlink()
    report['written'] = True
    return report


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path, help='Complete reviewed candidate, including historical research')
    parser.add_argument('--wall-source', required=True, type=Path, help='Existing real local wall, after complete source-bound review')
    parser.add_argument('--archive-dir', required=True, type=Path, help='Private content-addressed archive outside this checkout')
    parser.add_argument('--output-dir', type=Path, default=ROOT/'public')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.wall_source, args.archive_dir, args.output_dir, args.dry_run), indent=2))
