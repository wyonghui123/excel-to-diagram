"""scratch_dir.py - unified temp dir for agent helper files.

[P1-9 2026-09-01] Replaces ad-hoc '_test_*.py' / '_verify_*.py' files left in tools/
after each session. Provides:
  - Standard location: <repo>/_scratch/<ISO_TS>_<agent_id>/
  - Context manager: auto-cleanup on exit (unless keep=True)
  - Subdirs per concern: tests/, debug/, snapshots/

Usage:
    from scratch_dir import scratch

    with scratch('db-assert-unit') as sd:
        sd.write('my_test.py', 'print(1)')
        sd.write_json('data.json', {'k': 'v'})
        # ... sd.path is absolute path, sd.dir is Path object

    # or manual
    sd = scratch('manual', keep=True)
    sd.write('foo.txt', 'bar')
    print(sd.path)
    sd.cleanup()

    # CLI
    python scratch_dir.py --id my-task --list        # list files in current scratch
    python scratch_dir.py --list-all                # list all scratch dirs
    python scratch_dir.py --prune --older-than 7d   # clean up old dirs
"""
import os
import sys
import json
import shutil
import argparse
import tempfile
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRATCH_ROOT = REPO_ROOT / '_scratch'


class ScratchDir:
    """One scratch directory under _scratch/<ISO_TS>_<id>/."""

    def __init__(self, scratch_id, base=SCRATCH_ROOT, keep=False):
        self.id = self._safe_id(scratch_id)
        self.iso_ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        self.dir_name = f'{self.iso_ts}_{self.id}'
        self.dir = Path(base) / self.dir_name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.keep = keep
        self.created_files = []

    @staticmethod
    def _safe_id(s):
        # Allow only alnum, dash, underscore
        return re.sub(r'[^a-zA-Z0-9_-]', '_', s)[:64]

    @property
    def path(self):
        return str(self.dir)

    def write(self, filename, content, encoding='utf-8'):
        """Write a file into this scratch dir."""
        p = self.dir / filename
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            p.write_text(content, encoding=encoding)
        else:
            p.write_bytes(content)
        self.created_files.append(str(p))
        return p

    def write_json(self, filename, obj, indent=2):
        return self.write(filename, json.dumps(obj, indent=indent, ensure_ascii=False))

    def subdir(self, name):
        p = self.dir / name
        p.mkdir(parents=True, exist_ok=True)
        return p

    def cleanup(self):
        """Remove the scratch dir unless keep=True."""
        if self.keep:
            return
        if self.dir.exists():
            shutil.rmtree(self.dir, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.cleanup()


def scratch(scratch_id, keep=False):
    """Create a ScratchDir context manager.

    Usage:
        with scratch('my-task') as sd:
            sd.write('foo.txt', 'bar')
    """
    return ScratchDir(scratch_id, keep=keep)


def list_all(base=SCRATCH_ROOT):
    """List all scratch dirs, sorted newest first."""
    base = Path(base)
    if not base.exists():
        return []
    return sorted(
        [d for d in base.iterdir() if d.is_dir()],
        key=lambda d: d.name,
        reverse=True,
    )


def prune_older_than(days, base=SCRATCH_ROOT, dry_run=False):
    """Remove scratch dirs older than `days`."""
    base = Path(base)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    removed = 0
    kept = 0
    for d in list_all(base):
        # Parse ISO timestamp from name prefix (20260901T150843Z)
        m = re.match(r'(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z', d.name)
        if not m:
            kept += 1
            continue
        ts = datetime(
            int(m.group(1)), int(m.group(2)), int(m.group(3)),
            int(m.group(4)), int(m.group(5)), int(m.group(6)),
            tzinfo=timezone.utc,
        )
        if ts < cutoff:
            if dry_run:
                print(f'[DRY-RUN] would remove: {d}')
            else:
                shutil.rmtree(d, ignore_errors=True)
                print(f'[PRUNED] {d}')
            removed += 1
        else:
            kept += 1
    return removed, kept


def main():
    p = argparse.ArgumentParser(description='scratch_dir CLI')
    p.add_argument('--id', help='scratch id (creates _scratch/<ts>_<id>)')
    p.add_argument('--keep', action='store_true', help='do not auto-cleanup')
    p.add_argument('--list', action='store_true', help='list files in current/newest scratch')
    p.add_argument('--list-all', action='store_true', help='list all scratch dirs')
    p.add_argument('--prune', action='store_true', help='remove old scratch dirs')
    p.add_argument('--older-than', default='7d', help='age threshold (e.g. 7d, 24h, 30m)')
    p.add_argument('--dry-run', action='store_true')
    args = p.parse_args()

    if args.list_all:
        for d in list_all():
            idx = d / 'INDEX.json'
            label = ''
            if idx.exists():
                try:
                    label = json.loads(idx.read_text(encoding='utf-8')).get('label', '')
                except Exception:
                    pass
            print(f'{d.name}  {label}')
        return

    if args.prune:
        # Parse age
        m = re.match(r'^(\d+)([dhm])$', args.older_than)
        if not m:
            print(f'bad --older-than: {args.older_than}', file=sys.stderr)
            sys.exit(2)
        n = int(m.group(1))
        unit = m.group(2)
        if unit == 'd':
            days = n
        elif unit == 'h':
            days = n / 24
        else:  # m
            days = n / (24 * 60)
        removed, kept = prune_older_than(days, dry_run=args.dry_run)
        print(f'pruned {removed} dirs, kept {kept}')
        return

    if args.list:
        # List files in the most recent scratch
        all_dirs = list_all()
        if not all_dirs:
            print('(no scratch dirs)')
            return
        latest = all_dirs[0]
        print(f'=== {latest.name} ===')
        for f in sorted(latest.rglob('*')):
            if f.is_file():
                print(f'  {f.relative_to(latest)}')
        return

    if args.id:
        sd = scratch(args.id, keep=args.keep)
        print(sd.path)
        return

    p.print_help()


if __name__ == '__main__':
    main()
