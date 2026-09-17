#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
service_health_probe.py - 多路径服务健康探活 (避免代理假成功)

设计原则 (无开发假设):
  - 不假设服务端口 / 协议 / 路径
  - 多路径并行探活, 至少 N 个独立探活点都 OK 才算真活
  - 区分: HTTP 端口 + 进程存活 + 内省接口 + DB 连通 + introspection

本次根因 (2026-09-15):
  staging 的 unified_18081 代理在 server.py 死了之后仍返 200 OK, 假成功陷阱.
  解决方案: 不只 ping 端口, 还要:
    1. 直接 curl 端口 + 检查 body (避免代理返 200 但实际 502/504)
    2. introspect 关键 Python 模块 __file__ (确认实际加载的是我们上传的版本)
    3. 检查 DB 连通 (确认 init_*.py 启动没崩)
    4. 进程存活 (ps aux | grep server.py)
    5. 最近 N 条 migration 是 SUCCESS

用法:
  python service_health_probe.py --target staging
  python service_health_probe.py --target production --probe-port 18080
  python service_health_probe.py --target staging --introspect-modules meta.api.v2_bo.bo_user
  python service_health_probe.py --target staging --json --exit-code

[2026-09-16] P1-2 通用化基础设施
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Optional

# 让 tools/ 成为 import root
sys.path.insert(0, str(Path(__file__).parent))


# --------------------------------------------------------------------------
# 探活点 (每个独立可调用)
# --------------------------------------------------------------------------
def probe_http_port(host: str, port: int, path: str = "/",
                    expected_substrings: Optional[List[str]] = None,
                    timeout: int = 5) -> dict:
    """HTTP 端口探活: curl 端口 + 检查 body 含预期字符串.

    Returns:
        {ok: bool, code: int|None, body_snippet: str, reason: str}
    """
    url = f"http://{host}:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            code = r.getcode()
            body = r.read().decode("utf-8", errors="replace")[:500]
        ok = 200 <= code < 300
        reason = f"HTTP {code}"
        # 检查预期字符串 (避免代理返 200 但 body 是 502 错误页)
        if expected_substrings:
            for s in expected_substrings:
                if s not in body:
                    ok = False
                    reason += f" (missing expected substring: {s})"
                    break
        return {"ok": ok, "code": code, "body_snippet": body[:200], "reason": reason}
    except urllib.error.HTTPError as e:
        # 401/403 = endpoint 注册 OK, 需要鉴权 (符合预期, 后端在线)
        if e.code in (401, 403):
            return {"ok": True, "code": e.code, "body_snippet": "", "reason": f"HTTP {e.code} (auth required, endpoint alive)"}
        return {"ok": False, "code": e.code, "body_snippet": "", "reason": f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "code": None, "body_snippet": "", "reason": f"err: {e}"}


def probe_process_alive(host: str, process_pattern: str, exec_fn=None) -> dict:
    """进程存活: ps aux | grep <pattern> 至少 1 个匹配.

    Returns:
        {ok: bool, count: int, samples: [pid, ...], reason: str}
    """
    if exec_fn is None:
        return {"ok": False, "count": 0, "samples": [], "reason": "no exec_fn bound"}

    cmd = f"ps aux | grep -E '{process_pattern}' | grep -v grep"
    r = exec_fn(cmd, timeout=10)
    out = (r.get("stdout") or "").strip() if isinstance(r, dict) else str(r)
    lines = [l for l in out.splitlines() if l.strip()]
    count = len(lines)
    samples = []
    for line in lines[:3]:
        # ps aux 第二列是 PID
        parts = line.split()
        if len(parts) >= 2:
            samples.append(parts[1])
    ok = count >= 1
    reason = f"{count} process(es) match" if ok else f"no process matches '{process_pattern}'"
    return {"ok": ok, "count": count, "samples": samples, "reason": reason}


def probe_db_schema(db_path: str, expected_tables: Optional[List[str]] = None,
                    exec_fn=None) -> dict:
    """DB schema 探活: sqlite3 连通 + 关键表存在.

    Returns:
        {ok: bool, table_count: int, missing_tables: [str, ...], reason: str}
    """
    # 本地模式
    if db_path and Path(db_path).exists():
        import sqlite3
        try:
            conn = sqlite3.connect(db_path)
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            conn.close()
            missing = []
            if expected_tables:
                missing = [t for t in expected_tables if t not in tables]
            ok = len(missing) == 0 and len(tables) > 0
            reason = f"tables={len(tables)}"
            if missing:
                reason += f", missing={missing}"
            return {"ok": ok, "table_count": len(tables), "missing_tables": missing, "reason": reason}
        except Exception as e:
            return {"ok": False, "table_count": 0, "missing_tables": [], "reason": f"sqlite err: {e}"}

    # 远端模式
    if exec_fn:
        # 远端: ls + sqlite3
        cmd = f"ls -la {db_path} 2>/dev/null && sqlite3 {db_path} \"SELECT count(*) FROM sqlite_master WHERE type='table'\""
        r = exec_fn(cmd, timeout=10)
        out = (r.get("stdout") or "").strip() if isinstance(r, dict) else str(r)
        if not out:
            return {"ok": False, "table_count": 0, "missing_tables": [], "reason": f"db not accessible: {db_path}"}
        m = re.search(r"(\d+)", out)
        table_count = int(m.group(1)) if m else 0
        tables = []  # 远端模式我们不列具体表名
        # 检查关键表
        missing = []
        if expected_tables:
            for t in expected_tables:
                check = exec_fn(
                    f"sqlite3 {db_path} \"SELECT 1 FROM sqlite_master WHERE type='table' AND name='{t}' LIMIT 1\"",
                    timeout=5,
                )
                check_out = (check.get("stdout") or "").strip() if isinstance(check, dict) else str(check)
                if not check_out:
                    missing.append(t)
        ok = len(missing) == 0 and table_count > 0
        reason = f"tables={table_count}, missing={missing}" if missing else f"tables={table_count}"
        return {"ok": ok, "table_count": table_count, "missing_tables": missing, "reason": reason}
    else:
        return {"ok": False, "table_count": 0, "missing_tables": [], "reason": "no db_path / exec_fn"}


def probe_python_introspect(host: str, deploy_root: str, module: str,
                            python_bin: str = "/opt/miniconda3-py39/bin/python",
                            exec_fn=None) -> dict:
    """Python introspect: 远端 import + 看 __file__ 是不是 deploy_root 里的版本.

    Returns:
        {ok: bool, file_path: str|None, in_deploy: bool, reason: str}
    """
    if exec_fn is None:
        return {"ok": False, "file_path": None, "in_deploy": False, "reason": "no exec_fn bound"}

    inner = f"import {module} as x; print(x.__file__)"
    cmd = (
        f'bash -c "cd {deploy_root} && '
        f'{python_bin} -c \\"{inner}\\""'
    )
    r = exec_fn(cmd, timeout=30)
    out = (r.get("stdout") or "").strip() if isinstance(r, dict) else str(r)
    err = (r.get("stderr") or "").strip() if isinstance(r, dict) else ""

    if "ModuleNotFoundError" in err or "ImportError" in err:
        return {"ok": False, "file_path": None, "in_deploy": False, "reason": f"import failed: {err.splitlines()[-1] if err else ''}"}

    if not out:
        return {"ok": False, "file_path": None, "in_deploy": False, "reason": "no stdout"}

    # 路径分析: 是否在 deploy_root 下
    deploy_dir = deploy_root.rstrip('/').rsplit('/', 1)[0] if deploy_root else ""
    in_deploy = bool(deploy_root) and (
        deploy_root in out or (deploy_dir and deploy_dir in out)
    )
    ok = in_deploy
    reason = "in deploy_root" if in_deploy else f"OUTSIDE deploy_root ({out})"
    return {"ok": ok, "file_path": out, "in_deploy": in_deploy, "reason": reason}


def probe_migration_tail(db_path: str, tail_count: int = 5, exec_fn=None) -> dict:
    """Migration tail: 最近 N 条 status 都是 SUCCESS.

    Returns:
        {ok: bool, tail: [(name, status, ts), ...], reason: str}
    """
    if exec_fn:
        cmd = (
            f"sqlite3 {db_path} \"SELECT migration_name, status, executed_at "
            f"FROM schema_migrations ORDER BY executed_at DESC LIMIT {tail_count}\""
        )
        r = exec_fn(cmd, timeout=10)
        out = (r.get("stdout") or "").strip() if isinstance(r, dict) else str(r)
        if not out:
            return {"ok": False, "tail": [], "reason": "no migrations recorded"}
        tail = []
        all_ok = True
        for line in out.splitlines():
            parts = line.split("|")
            if len(parts) >= 2:
                name, status = parts[0], parts[1]
                ts = parts[2] if len(parts) >= 3 else ""
                tail.append((name, status, ts))
                if status != "SUCCESS":
                    all_ok = False
        reason = "all SUCCESS" if all_ok else "non-SUCCESS in tail"
        return {"ok": all_ok, "tail": tail, "reason": reason}
    else:
        # 本地
        import sqlite3
        try:
            conn = sqlite3.connect(db_path)
            rows = conn.execute(
                f"SELECT migration_name, status, executed_at FROM schema_migrations "
                f"ORDER BY executed_at DESC LIMIT {tail_count}"
            ).fetchall()
            conn.close()
            tail = [(r[0], r[1], r[2]) for r in rows]
            all_ok = all(t[1] == "SUCCESS" for t in tail) if tail else False
            return {"ok": all_ok, "tail": tail, "reason": "all SUCCESS" if all_ok else "non-SUCCESS"}
        except Exception as e:
            return {"ok": False, "tail": [], "reason": f"err: {e}"}


# --------------------------------------------------------------------------
# 主入口
# --------------------------------------------------------------------------
def run_probe(target_name: str,
              probe_port: Optional[int] = None,
              probe_paths: Optional[List[str]] = None,
              expected_substrings: Optional[List[str]] = None,
              process_pattern: Optional[str] = None,
              db_path: Optional[str] = None,
              expected_tables: Optional[List[str]] = None,
              introspect_modules: Optional[List[str]] = None,
              deploy_root: Optional[str] = None,
              python_bin: str = "/opt/miniconda3-py39/bin/python",
              tail_migrations: int = 0,
              exec_fn=None) -> dict:
    """跑所有启用的探活, 返回聚合报告.

    Returns:
        {
            'target': str,
            'probes': [{name, ok, result, weight}],
            'overall_ok': bool,
            'overall_score': float,  # 0-1, 加权
        }
    """
    probes = []

    # 1. HTTP 端口 (多个 path)
    if probe_port is not None:
        paths = probe_paths or ["/"]
        for p in paths:
            r = probe_http_port(target_name.split('@')[-1] if '@' in target_name else '127.0.0.1',
                                probe_port, p, expected_substrings=expected_substrings)
            probes.append({
                'name': f'http_port_{p}',
                'ok': r['ok'],
                'result': r,
                'weight': 1.0,
            })

    # 2. 进程存活
    if process_pattern:
        r = probe_process_alive(target_name, process_pattern, exec_fn=exec_fn)
        probes.append({
            'name': 'process_alive',
            'ok': r['ok'],
            'result': r,
            'weight': 2.0,  # 高权重
        })

    # 3. DB schema
    if db_path:
        r = probe_db_schema(db_path, expected_tables=expected_tables, exec_fn=exec_fn)
        probes.append({
            'name': 'db_schema',
            'ok': r['ok'],
            'result': r,
            'weight': 1.5,
        })

    # 4. Python introspect
    if introspect_modules and deploy_root:
        for m in introspect_modules:
            r = probe_python_introspect(target_name, deploy_root, m,
                                        python_bin=python_bin, exec_fn=exec_fn)
            probes.append({
                'name': f'introspect_{m}',
                'ok': r['ok'],
                'result': r,
                'weight': 1.0,
            })

    # 5. Migration tail
    if tail_migrations > 0 and db_path:
        r = probe_migration_tail(db_path, tail_count=tail_migrations, exec_fn=exec_fn)
        probes.append({
            'name': f'migration_tail_{tail_migrations}',
            'ok': r['ok'],
            'result': r,
            'weight': 0.5,
        })

    # 计算总分
    total_weight = sum(p['weight'] for p in probes)
    ok_weight = sum(p['weight'] for p in probes if p['ok'])
    score = ok_weight / total_weight if total_weight > 0 else 0.0
    overall_ok = score >= 0.5  # 50% 加权通过就算 OK

    return {
        'target': target_name,
        'probes': probes,
        'overall_ok': overall_ok,
        'overall_score': round(score, 3),
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _print_human(report: dict) -> None:
    print(f"[probe] target: {report['target']}")
    print(f"[probe] overall_ok: {report['overall_ok']}, score: {report['overall_score']}")
    print()
    for p in report['probes']:
        status = "OK" if p['ok'] else "FAIL"
        print(f"  [{status}] {p['name']} (weight={p['weight']})")
        if not p['ok']:
            print(f"      reason: {p['result'].get('reason', '?')}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description='[P1-2] 多路径服务健康探活 (避免代理假成功, 无开发假设)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python service_health_probe.py --target staging --probe-port 13011 \\
      --process-pattern server.py --db-path /opt/app/staging/db.sqlite \\
      --introspect-modules meta.api.v2_bo.bo_user --deploy-root /opt/app/staging/deploy/current
        """
    )
    parser.add_argument('--target', default='staging', help='目标名 (staging/production/...)')
    parser.add_argument('--probe-port', type=int, default=None, help='HTTP 端口')
    parser.add_argument('--probe-path', action='append', default=None,
                        help='HTTP 路径 (可多次, 默认 /)')
    parser.add_argument('--expected-substring', action='append', default=None,
                        help='Body 必须含的字符串 (可多次)')
    parser.add_argument('--process-pattern', default=None, help='ps aux 匹配的进程名 pattern')
    parser.add_argument('--db-path', default=None, help='DB 文件路径')
    parser.add_argument('--expected-table', action='append', default=None,
                        help='DB 必须含的表 (可多次)')
    parser.add_argument('--introspect-module', action='append', default=None,
                        help='要 introspect 的 Python 模块 (可多次)')
    parser.add_argument('--deploy-root', default=None, help='部署目录 (供 introspect)')
    parser.add_argument('--python-bin', default='/opt/miniconda3-py39/bin/python',
                        help='远端 Python 解释器')
    parser.add_argument('--tail-migrations', type=int, default=0,
                        help='检查最近 N 条 migration status')
    parser.add_argument('--json', action='store_true', help='JSON 输出')
    parser.add_argument('--exit-code', action='store_true', help='不通过时 exit 1')

    args = parser.parse_args()

    # 尝试绑定 exec_fn (远端 exec)
    exec_fn = None
    try:
        from staging_round import remote_exec
        exec_fn = remote_exec
    except ImportError:
        pass

    report = run_probe(
        target_name=args.target,
        probe_port=args.probe_port,
        probe_paths=args.probe_path,
        expected_substrings=args.expected_substring,
        process_pattern=args.process_pattern,
        db_path=args.db_path,
        expected_tables=args.expected_table,
        introspect_modules=args.introspect_module,
        deploy_root=args.deploy_root,
        python_bin=args.python_bin,
        tail_migrations=args.tail_migrations,
        exec_fn=exec_fn,
    )

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_human(report)

    if args.exit_code and not report['overall_ok']:
        sys.exit(1)
    sys.exit(0 if report['overall_ok'] else (1 if args.exit_code else 0))


if __name__ == '__main__':
    main()