#!/usr/bin/env python3
# MANIFEST //sha256  [V007.50 2026-09-01 rebuilt]
# [L17 delta CLI - rebuilt after A3 corruption incident]
"""
_build_delta.py - delta deploy CLI.

Usage:
  python _build_delta.py build --prev-manifest baseline.yaml --version v20260901 --out delta.zip
  python _build_delta.py build --version v20260901 --out full.zip --type full
  python _build_delta.py verify --zip delta.zip --deploy-dir /opt/app/staging/deploy/current
  python _build_delta.py plan --prev-manifest baseline.yaml --version v20260901
"""
import argparse
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from manifest_utils import (
    generate_manifest,
    parse_manifest,
    compute_delta,
    build_delta_zip,
    verify_delta_manifest,
)


def cmd_build(args):
    src = Path(args.root).resolve()
    out = Path(args.out).resolve()

    prev = None
    if args.prev_manifest:
        prev_path = Path(args.prev_manifest)
        if not prev_path.exists():
            print(f"[ERROR] prev manifest not found: {prev_path}")
            return 1
        prev = parse_manifest(prev_path.read_text(encoding="utf-8"))

    print(f"[1/4] scanning {src}")
    new_m = generate_manifest(src, version=args.version, deployment_type=args.type)
    print(f"  files: {len(new_m.files)}")
    print(f"  size:  {sum(f.size for f in new_m.files)/1024/1024:.1f} MB")

    # [P1-10 2026-09-01] DB fingerprint embed: capture DB state and attach to manifest
    db_fingerprint_data = None
    if args.db_path:
        print(f"[2/4] capturing DB fingerprint: {args.db_path}")
        try:
            import db_fingerprint
            db_fingerprint_data = db_fingerprint.capture(args.db_path)
            # Embed as manifest.extra dict (manifest_utils may need a setter)
            new_m.extra = new_m.extra or {}
            new_m.extra['db_fingerprint'] = {
                'tables_count': db_fingerprint_data.get('tables_count'),
                'tables_sha': db_fingerprint_data.get('tables_sha'),
                'row_counts_sha': db_fingerprint_data.get('row_counts_sha'),
                'migrations': db_fingerprint_data.get('migrations', []),
                'captured_at': db_fingerprint_data.get('captured_at'),
                'db_path': args.db_path,
            }
            print(f"  embedded: tables={db_fingerprint_data.get('tables_count')}, "
                  f"migrations={len(db_fingerprint_data.get('migrations', []))}")
        except Exception as e:
            print(f"  [WARN] DB fingerprint failed: {e}")

    print(f"[3/4] building delta -> {out}")
    result = build_delta_zip(src, prev, new_m, out)
    print(f"  modified: {len(result['modified'])}")
    print(f"  added:    {len(result['added'])}")
    print(f"  deleted:  {len(result['deleted'])}")
    print(f"  zip_size: {result['zip_size']/1024:.1f} KB")

    print(f"[4/4] changed/* entries:")
    for f in result['modified']:
        print(f"  M  {f}")
    for f in result['added']:
        print(f"  A  {f}")
    for f in result['deleted']:
        print(f"  D  {f}")

    return 0


def cmd_verify(args):
    import zipfile
    zp = Path(args.zip).resolve()
    if not zp.exists():
        print(f"[ERROR] zip not found: {zp}")
        return 1

    print(f"[1/3] extracting manifest from {zp}")
    with zipfile.ZipFile(zp, 'r') as zf:
        if 'MANIFEST' not in zf.namelist():
            print("[ERROR] zip missing MANIFEST entry")
            return 1
        manifest = parse_manifest(zf.read('MANIFEST').decode('utf-8'))

    print(f"[2/3] verifying {len(manifest.files)} files against {args.deploy_dir}")
    result = verify_delta_manifest(Path(args.deploy_dir), manifest)
    print(f"  ok:        {result['ok']}")
    print(f"  checked:   {result['checked']}")
    print(f"  mismatched: {len(result['mismatched'])}")
    print(f"  missing:    {len(result['missing'])}")
    if result['mismatched']:
        print("\nMISMATCHED:")
        for p in result['mismatched']:
            print(f"  !  {p}")
    if result['missing']:
        print("\nMISSING:")
        for p in result['missing']:
            print(f"  ?  {p}")

    # [P1-10 2026-09-01] DB fingerprint diff: compare embedded vs current DB
    db_diff_ok = True
    if args.db_path and hasattr(manifest, 'extra') and manifest.extra and 'db_fingerprint' in (manifest.extra or {}):
        print(f"[3/3] DB fingerprint diff (embedded vs current: {args.db_path})")
        try:
            import db_fingerprint
            embedded = manifest.extra['db_fingerprint']
            current = db_fingerprint.capture(args.db_path)

            diffs = []
            for key in ('tables_count', 'tables_sha', 'row_counts_sha'):
                if embedded.get(key) != current.get(key):
                    diffs.append(f'{key}: embedded={embedded.get(key)} current={current.get(key)}')
            emb_migs = set(embedded.get('migrations', []))
            cur_migs = set(current.get('migrations', []))
            if emb_migs != cur_migs:
                added = cur_migs - emb_migs
                removed = emb_migs - cur_migs
                if added:
                    diffs.append(f'migrations added: {sorted(added)}')
                if removed:
                    diffs.append(f'migrations removed: {sorted(removed)}')

            if diffs:
                db_diff_ok = False
                print('  DB DIFF:')
                for d in diffs:
                    print(f'    !  {d}')
            else:
                print('  DB MATCH: tables_sha + row_counts_sha + migrations identical')
        except Exception as e:
            db_diff_ok = False
            print(f'  [WARN] DB fingerprint diff failed: {e}')
    elif args.db_path:
        print(f"[3/3] skip DB diff (no embedded fingerprint in MANIFEST)")

    overall_ok = result['ok'] and db_diff_ok
    return 0 if overall_ok else 1


def cmd_plan(args):
    src = Path(args.root).resolve()
    prev_path = Path(args.prev_manifest)
    if not prev_path.exists():
        print(f"[ERROR] prev manifest not found: {prev_path}")
        return 1

    prev = parse_manifest(prev_path.read_text(encoding="utf-8"))
    new_m = generate_manifest(src, version=args.version)
    delta = compute_delta(prev, new_m)

    summary = {
        "modified_count": len(delta["modified"]),
        "added_count": len(delta["added"]),
        "deleted_count": len(delta["deleted"]),
        "modified": delta["modified"],
        "added": delta["added"],
        "deleted": delta["deleted"],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def main():
    parser = argparse.ArgumentParser(description="delta deploy builder/verifier")
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_build = sub.add_parser('build', help='build delta zip')
    p_build.add_argument('--root', default='.', help='source root (default: cwd)')
    p_build.add_argument('--prev-manifest', help='prev MANIFEST yaml for delta mode')
    p_build.add_argument('--version', required=True, help='version string e.g. v20260901')
    p_build.add_argument('--type', default='delta', choices=['delta', 'full', 'hotfix'])
    p_build.add_argument('--out', required=True, help='output zip path')
    p_build.add_argument('--db-path', default=None, help='[P1-10] capture DB fingerprint and embed in MANIFEST')
    p_build.set_defaults(func=cmd_build)

    p_verify = sub.add_parser('verify', help='verify deployed files match manifest sha256')
    p_verify.add_argument('--zip', required=True)
    p_verify.add_argument('--deploy-dir', required=True)
    p_verify.add_argument('--db-path', default=None, help='[P1-10] diff current DB fingerprint vs embedded')
    p_verify.set_defaults(func=cmd_verify)

    p_plan = sub.add_parser('plan', help='dry-run: show what would change (no zip)')
    p_plan.add_argument('--root', default='.')
    p_plan.add_argument('--prev-manifest', required=True)
    p_plan.add_argument('--version', required=True)
    p_plan.set_defaults(func=cmd_plan)

    args = parser.parse_args()
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
