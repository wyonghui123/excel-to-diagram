#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_viewer.py - staging 部署动作结构化审计日志 + viewer

设计原则 (无开发假设):
  - JSONL 格式: 每行一条记录, 方便追加 + 解析
  - 不假设具体部署工具 (deploy_upload / staging_round / 手动 scp 都记)
  - viewer 支持: 最近 N 条 / 按 target 过滤 / 按 action 过滤 / 按时间范围 / 失败统计

用途:
  - 解决"部署动作不可追溯"问题 (本次根因之一)
  - 每次部署: 写一条记录 (who/when/what/result/duration/error)
  - 失败时: 一眼看到最近 50 条, 谁改了啥, 哪些失败
  - 审计: 看任意 staging 在 2026-09 期间被谁碰过

JSONL 格式 (一行一记录):
  {"ts": "2026-09-16T12:34:56Z", "action": "upload", "target": "staging",
   "files": ["meta/scripts/init_auth.py"], "ok": true, "duration_sec": 1.23,
   "actor": "deploy-upload", "drift_count": 0, "stale_count": 0,
   "note": "staging round 15 v087/v088/v089 redo"}

用法:
  # append 一条记录
  python audit_viewer.py append --action upload --target staging \\
      --files meta/scripts/init_auth.py --ok --duration-sec 1.5 --note "..."

  # 查看最近 20 条
  python audit_viewer.py tail -n 20

  # 按 target 过滤
  python audit_viewer.py tail --target staging -n 10

  # 按 action 过滤
  python audit_viewer.py tail --action upload -n 10

  # 失败统计
  python audit_viewer.py stats --since 2026-09-01

  # 查看所有 actions
  python audit_viewer.py list-actions

[2026-09-16] P2 通用化基础设施
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


# 默认 audit 文件路径
DEFAULT_AUDIT_FILE = Path(__file__).parent.parent / ".staging_deploy_audit.jsonl"


# --------------------------------------------------------------------------
# 1. 追加记录
# --------------------------------------------------------------------------
def append_record(
    audit_file: Path,
    action: str,
    target: str,
    files: Optional[List[str]] = None,
    ok: bool = True,
    duration_sec: float = 0.0,
    actor: str = "unknown",
    drift_count: int = 0,
    stale_count: int = 0,
    error: str = "",
    note: str = "",
    extra: Optional[dict] = None,
) -> dict:
    """追加一条记录到 JSONL 文件. 返回写入的 record dict."""
    record = {
        'ts': datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        'action': action,
        'target': target,
        'files': files or [],
        'ok': ok,
        'duration_sec': round(duration_sec, 3),
        'actor': actor,
        'drift_count': drift_count,
        'stale_count': stale_count,
        'error': error[:500] if error else "",
        'note': note[:500] if note else "",
    }
    if extra:
        record['extra'] = extra

    # 确保父目录存在
    audit_file.parent.mkdir(parents=True, exist_ok=True)
    # append 一行 JSON
    with open(audit_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record


# --------------------------------------------------------------------------
# 2. 读取 + 过滤
# --------------------------------------------------------------------------
def read_records(
    audit_file: Path,
    target: Optional[str] = None,
    action: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    only_failures: bool = False,
) -> List[dict]:
    """读所有记录, 按条件过滤."""
    if not audit_file.exists():
        return []

    records = []
    with open(audit_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue

            if target and r.get('target') != target:
                continue
            if action and r.get('action') != action:
                continue
            if only_failures and r.get('ok') is not False:
                continue
            if since and r.get('ts', '') < since:
                continue
            if until and r.get('ts', '') > until:
                continue
            records.append(r)
    return records


# --------------------------------------------------------------------------
# 3. Viewer
# --------------------------------------------------------------------------
def tail_records(
    audit_file: Path,
    n: int = 20,
    target: Optional[str] = None,
    action: Optional[str] = None,
    only_failures: bool = False,
) -> List[dict]:
    """返回最后 N 条 (按文件顺序倒序)."""
    all_records = read_records(
        audit_file, target=target, action=action, only_failures=only_failures,
    )
    return all_records[-n:][::-1]  # 倒序


def stats_records(
    audit_file: Path,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> dict:
    """统计: 总数 / 成功 / 失败 / 按 action 分组 / 按 target 分组."""
    records = read_records(audit_file, since=since, until=until)

    total = len(records)
    ok_count = sum(1 for r in records if r.get('ok'))
    fail_count = total - ok_count
    by_action = Counter(r.get('action', '?') for r in records)
    by_target = Counter(r.get('target', '?') for r in records)
    by_actor = Counter(r.get('actor', '?') for r in records)
    total_duration = sum(r.get('duration_sec', 0) for r in records)

    return {
        'total': total,
        'ok': ok_count,
        'fail': fail_count,
        'ok_pct': round(ok_count / total * 100, 1) if total > 0 else 0,
        'total_duration_sec': round(total_duration, 2),
        'by_action': dict(by_action),
        'by_target': dict(by_target),
        'by_actor': dict(by_actor),
        'since': since,
        'until': until,
    }


def list_actions(audit_file: Path) -> List[str]:
    """列出所有用过的 action 名."""
    records = read_records(audit_file)
    return sorted({r.get('action', '?') for r in records})


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _print_record(r: dict) -> None:
    status = "OK" if r.get('ok') else "FAIL"
    files = ','.join(r.get('files', [])[:3])
    if len(r.get('files', [])) > 3:
        files += f"...(+{len(r['files']) - 3})"
    print(f"  [{status}] {r.get('ts')} {r.get('action')} target={r.get('target')} actor={r.get('actor')}")
    print(f"      files: {files}")
    if r.get('drift_count') or r.get('stale_count'):
        print(f"      drift={r.get('drift_count')}, stale={r.get('stale_count')}")
    if r.get('error'):
        print(f"      error: {r['error'][:100]}")
    if r.get('note'):
        print(f"      note: {r['note'][:100]}")
    if r.get('duration_sec'):
        print(f"      duration: {r['duration_sec']}s")


def main():
    parser = argparse.ArgumentParser(
        description='[P2] staging 部署动作审计日志 + viewer (JSONL, 无开发假设)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--audit-file', default=str(DEFAULT_AUDIT_FILE),
                        help=f'audit JSONL 文件路径 (默认 {DEFAULT_AUDIT_FILE})')

    sub = parser.add_subparsers(dest='cmd', required=True)

    # append
    sp = sub.add_parser('append', help='追加一条记录')
    sp.add_argument('--action', required=True, help='动作 (upload/rollback/migrate/healthcheck/...)')
    sp.add_argument('--target', required=True, help='目标 (staging/production/...)')
    sp.add_argument('--file', dest='files', action='append', default=None,
                    help='涉及的文件 (可多次)')
    sp.add_argument('--ok', action='store_true', help='动作成功 (默认 True)')
    sp.add_argument('--fail', action='store_true', help='动作失败')
    sp.add_argument('--duration-sec', type=float, default=0.0)
    sp.add_argument('--actor', default='unknown', help='执行者 (deploy-upload/staging-round/...)')
    sp.add_argument('--drift-count', type=int, default=0)
    sp.add_argument('--stale-count', type=int, default=0)
    sp.add_argument('--error', default='', help='错误信息')
    sp.add_argument('--note', default='', help='备注')

    # tail
    sp = sub.add_parser('tail', help='查看最近 N 条')
    sp.add_argument('-n', type=int, default=20)
    sp.add_argument('--target', default=None)
    sp.add_argument('--action', default=None)
    sp.add_argument('--only-failures', action='store_true')

    # stats
    sp = sub.add_parser('stats', help='统计')
    sp.add_argument('--since', default=None, help='起始时间 (e.g. 2026-09-01)')
    sp.add_argument('--until', default=None, help='结束时间')

    # list-actions
    sub.add_parser('list-actions', help='列出所有用过的 action')

    args = parser.parse_args()
    audit_file = Path(args.audit_file)

    if args.cmd == 'append':
        # 默认 ok=True, 只有 --fail 才设为 False
        ok = not args.fail if args.fail else args.ok
        r = append_record(
            audit_file=audit_file,
            action=args.action,
            target=args.target,
            files=args.files,
            ok=ok,
            duration_sec=args.duration_sec,
            actor=args.actor,
            drift_count=args.drift_count,
            stale_count=args.stale_count,
            error=args.error,
            note=args.note,
        )
        print(f"[OK] appended: {json.dumps(r, ensure_ascii=False)}")

    elif args.cmd == 'tail':
        records = tail_records(
            audit_file, n=args.n,
            target=args.target, action=args.action, only_failures=args.only_failures,
        )
        print(f"[tail] {len(records)} record(s)")
        for r in records:
            _print_record(r)
            print()

    elif args.cmd == 'stats':
        s = stats_records(audit_file, since=args.since, until=args.until)
        print(f"[stats] total={s['total']}, ok={s['ok']}, fail={s['fail']}, ok_pct={s['ok_pct']}%")
        print(f"[stats] total_duration={s['total_duration_sec']}s")
        print(f"[stats] by_action: {s['by_action']}")
        print(f"[stats] by_target: {s['by_target']}")
        print(f"[stats] by_actor: {s['by_actor']}")

    elif args.cmd == 'list-actions':
        actions = list_actions(audit_file)
        print(f"[actions] {actions}")


if __name__ == '__main__':
    main()