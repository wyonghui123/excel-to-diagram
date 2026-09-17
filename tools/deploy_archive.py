#!/usr/bin/env python3
"""deploy_archive.py - versioned archive of deployed delta zips + DB snapshots.

[P1-7 2026-09-01] Provides traceability: every deploy produces an immutable archive
of (zip + manifest + DB snapshot + sha256), retained for N versions.

Without this, when staging breaks 3 days later, we cannot answer:
  - "what was deployed?"
  - "what did the DB look like right before?"
  - "can I roll back to yesterday's version?"
  - "did anyone deploy between 14:00 and 16:00?"

Usage:
    # Archive after deploy (called by deploy_with_safety.py or manually)
    python deploy_archive.py archive \\
        --zip ./deltas/spec17.zip \\
        --manifest ./deltas/spec17.MANIFEST.yaml \\
        --db-local /tmp/staging_pre.db \\
        --label "spec17-plan-d" \\
        --archive-dir /opt/app/backups/deploy_archives

    # List archives
    python deploy_archive.py list --archive-dir /opt/app/backups/deploy_archives

    # Restore archive (extract zip to a temp dir for inspection)
    python deploy_archive.py restore \\
        --archive-dir /opt/app/backups/deploy_archives \\
        --label "spec17-plan-d" \\
        --output /tmp/restored

    # Prune old archives (keep N most recent)
    python deploy_archive.py prune --keep 10

    # Diff two archives (what changed between deploys)
    python deploy_archive.py diff \\
        --archive-dir /opt/app/backups/deploy_archives \\
        --label-a "spec17-plan-d" --label-b "spec17-plan-e"
"""
import sys
import shutil
import json
import hashlib
import argparse
from pathlib import Path
from datetime import datetime, timezone


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def _archive_one(zip_path, manifest_path, db_local_path, archive_dir, label):
    """Create one archive directory: <archive_dir>/<ISO_TS>_<label>/."""
    if not Path(zip_path).exists():
        raise FileNotFoundError(f'zip not found: {zip_path}')
    iso_ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    safe_label = ''.join(c if c.isalnum() or c in '-_.' else '_' for c in label)
    archive_name = f'{iso_ts}_{safe_label}'
    target_dir = Path(archive_dir) / archive_name
    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. Copy zip + compute sha256
    target_zip = target_dir / Path(zip_path).name
    shutil.copy2(zip_path, target_zip)
    zip_sha = _sha256_file(target_zip)

    # 2. Copy manifest if provided
    manifest_sha = None
    if manifest_path and Path(manifest_path).exists():
        target_manifest = target_dir / Path(manifest_path).name
        shutil.copy2(manifest_path, target_manifest)
        manifest_sha = _sha256_file(target_manifest)

    # 3. Snapshot DB if provided (copy, do not move)
    db_sha = None
    if db_local_path and Path(db_local_path).exists():
        target_db = target_dir / f'db_pre_{archive_name}.sqlite'
        shutil.copy2(db_local_path, target_db)
        db_sha = _sha256_file(target_db)

    # 4. Write INDEX.yaml with metadata
    index = {
        'archived_at': iso_ts,
        'label': label,
        'zip': {
            'name': target_zip.name,
            'sha256': zip_sha,
            'size_bytes': target_zip.stat().st_size,
        },
        'manifest': {
            'name': Path(manifest_path).name if manifest_path else None,
            'sha256': manifest_sha,
        },
        'db_snapshot': {
            'name': target_db.name if db_local_path and Path(db_local_path).exists() else None,
            'sha256': db_sha,
        },
    }
    (target_dir / 'INDEX.json').write_text(
        json.dumps(index, indent=2, ensure_ascii=False),
        encoding='utf-8',
    )

    return target_dir, index


def cmd_archive(args):
    target_dir, index = _archive_one(
        zip_path=args.zip,
        manifest_path=args.manifest,
        db_local_path=args.db_local,
        archive_dir=args.archive_dir,
        label=args.label,
    )
    print(f'ARCHIVED: {target_dir}')
    print(json.dumps(index, indent=2, ensure_ascii=False))


def cmd_list(args):
    archive_dir = Path(args.archive_dir)
    if not archive_dir.exists():
        print(f'(empty: {archive_dir} does not exist)')
        return
    entries = []
    for d in sorted(archive_dir.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        idx_file = d / 'INDEX.json'
        idx = {}
        if idx_file.exists():
            try:
                idx = json.loads(idx_file.read_text(encoding='utf-8'))
            except Exception:
                pass
        entries.append({
            'name': d.name,
            'label': idx.get('label'),
            'archived_at': idx.get('archived_at'),
            'zip': idx.get('zip', {}).get('name'),
            'zip_sha256': idx.get('zip', {}).get('sha256'),
            'db_snapshot': idx.get('db_snapshot', {}).get('name'),
        })
    print(f'=== archives in {archive_dir} ({len(entries)} entries) ===')
    for e in entries:
        print(f"  {e['name']:50s}  label={e['label']}  zip={e['zip']}  db={e['db_snapshot']}")


def cmd_restore(args):
    archive_dir = Path(args.archive_dir)
    target = _resolve_archive_dir(archive_dir, args.label)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    # Copy everything except INDEX.json
    for f in target.iterdir():
        if f.name == 'INDEX.json':
            continue
        shutil.copy2(f, output / f.name)
    print(f'RESTORED: {target} -> {output}')


def cmd_prune(args):
    archive_dir = Path(args.archive_dir)
    if not archive_dir.exists():
        print(f'(empty: {archive_dir} does not exist)')
        return
    entries = sorted(
        [d for d in archive_dir.iterdir() if d.is_dir()],
        key=lambda d: d.name,
        reverse=True,  # newer first (ISO timestamp prefix)
    )
    if len(entries) <= args.keep:
        print(f'no prune needed: {len(entries)} <= keep={args.keep}')
        return
    to_delete = entries[args.keep:]
    for d in to_delete:
        if args.dry_run:
            print(f'[DRY-RUN] would delete: {d}')
        else:
            shutil.rmtree(d)
            print(f'[PRUNED] {d}')
    print(f'pruned {len(to_delete)} archives, kept {min(args.keep, len(entries))}')


def _resolve_archive_dir(archive_dir, label):
    """Resolve a label to archive directory. Accepts full archive name OR substring."""
    candidate = archive_dir / label
    if candidate.is_dir():
        return candidate
    matches = [d for d in archive_dir.iterdir() if d.is_dir() and label in d.name]
    if not matches:
        raise FileNotFoundError(f'no archive matching label: {label}')
    if len(matches) > 1:
        # Use most recent (last in sorted order due to ISO timestamp prefix)
        matches.sort(key=lambda d: d.name, reverse=True)
    return matches[0]


def cmd_diff(args):
    archive_dir = Path(args.archive_dir)
    a_dir = _resolve_archive_dir(archive_dir, args.label_a)
    b_dir = _resolve_archive_dir(archive_dir, args.label_b)
    a_idx = json.loads((a_dir / 'INDEX.json').read_text(encoding='utf-8'))
    b_idx = json.loads((b_dir / 'INDEX.json').read_text(encoding='utf-8'))

    print(f'=== diff {a_dir.name} vs {b_dir.name} ===')
    print(f"label:    {a_idx.get('label')} -> {b_idx.get('label')}")
    print(f"archived: {a_idx.get('archived_at')} -> {b_idx.get('archived_at')}")
    print(f"zip:      {a_idx['zip']['name']} ({a_idx['zip']['sha256'][:12]}...) "
          f"-> {b_idx['zip']['name']} ({b_idx['zip']['sha256'][:12]}...)")
    print(f"zip_changed: {a_idx['zip']['sha256'] != b_idx['zip']['sha256']}")
    db_a = a_idx.get('db_snapshot', {}).get('sha256') or 'none'
    db_b = b_idx.get('db_snapshot', {}).get('sha256') or 'none'
    print(f"db_changed:  {db_a != db_b}")


def main():
    p = argparse.ArgumentParser(description='deploy archive CLI')
    sub = p.add_subparsers(dest='cmd', required=True)

    p_arch = sub.add_parser('archive', help='archive a deploy')
    p_arch.add_argument('--zip', required=True)
    p_arch.add_argument('--manifest', default=None)
    p_arch.add_argument('--db-local', default=None)
    p_arch.add_argument('--label', required=True)
    p_arch.add_argument('--archive-dir', required=True)

    p_list = sub.add_parser('list', help='list archives')
    p_list.add_argument('--archive-dir', required=True)

    p_restore = sub.add_parser('restore', help='restore an archive to output dir')
    p_restore.add_argument('--label', required=True, help='archive name OR label substring')
    p_restore.add_argument('--archive-dir', required=True)
    p_restore.add_argument('--output', required=True)

    p_prune = sub.add_parser('prune', help='keep N most recent archives')
    p_prune.add_argument('--keep', type=int, default=10)
    p_prune.add_argument('--archive-dir', required=True)
    p_prune.add_argument('--dry-run', action='store_true')

    p_diff = sub.add_parser('diff', help='diff two archives')
    p_diff.add_argument('--archive-dir', required=True)
    p_diff.add_argument('--label-a', required=True)
    p_diff.add_argument('--label-b', required=True)

    args = p.parse_args()
    if args.cmd == 'archive':
        cmd_archive(args)
    elif args.cmd == 'list':
        cmd_list(args)
    elif args.cmd == 'restore':
        cmd_restore(args)
    elif args.cmd == 'prune':
        cmd_prune(args)
    elif args.cmd == 'diff':
        cmd_diff(args)


if __name__ == '__main__':
    main()
