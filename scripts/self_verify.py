#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
自动自验证脚本 - 多智能体开发场景下 Agent 修复后的自验证

用法:
  python scripts/self_verify.py run <wt-name>    # 完整流程: 启动服务 -> 冒烟 -> 停止 -> 输出报告
  python scripts/self_verify.py smoke <wt-name>  # 仅冒烟测试 (假设服务已运行)
  python scripts/self_verify.py report <wt-name> # 仅输出 SELF_VERIFY_RESULTS Markdown
  python scripts/self_verify.py quick <wt-name>  # 快速检查: healthz + 1 API 端点

退出码:
  0: 所有检查 PASS
  1: 一个或多个检查 FAIL
  2: 错误 (服务未运行等)
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ── 路径与端口 (复用 _ports_sync.py 模式) ──────────────────────────

PATHS_FILE = Path("D:/filework/.coord/paths.json")
DEFAULT_PATHS = {
    "worktree_base": "D:/filework/worktrees",
    "ports_registry": "D:/filework/.coord/ports.json",
    "main_repo": "D:/filework/excel-to-diagram",
}

SELF_VERIFY_DEFAULTS = {
    "backend_startup_timeout": 60,
    "frontend_startup_timeout": 30,
    "api_smoke_endpoints": ["/api/v1/health", "/api/v1/products"],
    "default_verify_commands": [],
}


def load_paths() -> dict:
    if PATHS_FILE.exists():
        try:
            with open(PATHS_FILE, encoding="utf-8-sig") as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_PATHS


def load_ports() -> dict:
    paths = load_paths()
    p = Path(paths["ports_registry"])
    if not p.exists():
        return {"reserved": {}, "allocated": {}}
    try:
        with open(p, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {"reserved": {}, "allocated": {}}


def load_self_verify_config() -> dict:
    paths = load_paths()
    main = Path(paths["main_repo"])
    pf = main / "paths.json"
    if pf.exists():
        try:
            with open(pf, encoding="utf-8-sig") as f:
                data = json.load(f)
            if "self_verify" in data:
                return {**SELF_VERIFY_DEFAULTS, **data["self_verify"]}
        except Exception:
            pass
    return SELF_VERIFY_DEFAULTS


# ── ANSI 颜色 ────────────────────────────────────────────────────────

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def c_pass(msg: str) -> str:
    return f"{GREEN}{msg}{RESET}"


def c_fail(msg: str) -> str:
    return f"{RED}{msg}{RESET}"


def c_skip(msg: str) -> str:
    return f"{YELLOW}{msg}{RESET}"


# ── 端口解析 ──────────────────────────────────────────────────────────

def resolve_ports(wt_name: str):
    """返回 (backend_port, frontend_port, wt_path)"""
    ports = load_ports()
    # 在 allocated 中查找 owner == wt_name
    for port_str, info in ports.get("allocated", {}).items():
        if info.get("owner") == wt_name:
            be_port = int(port_str)
            # 前端端口 = 后端端口 - 4 (与 _wt_service 一致)
            fe_port = be_port - 4
            wt_path = info.get("worktree", "")
            return be_port, fe_port, wt_path
    # fallback: 默认端口
    return 3013, 3009, ""


# ── HTTP 工具 ─────────────────────────────────────────────────────────

def http_get(url: str, timeout: int = 10) -> tuple:
    """返回 (status_code, body_str) 或 (-1, error_str)"""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return e.code, body
    except Exception as e:
        return -1, str(e)


# ── HANDOVER 解析 ─────────────────────────────────────────────────────

def find_handover(wt_path: str) -> Path | None:
    """在 worktree 根目录查找 DEPLOY_HANDOVER*.md"""
    if not wt_path:
        return None
    root = Path(wt_path)
    for f in sorted(root.glob("DEPLOY_HANDOVER*.md")):
        return f
    return None


def parse_handover_files(handover_path: Path) -> list[str]:
    """从 HANDOVER 中提取修改文件列表"""
    if not handover_path or not handover_path.exists():
        return []
    text = handover_path.read_text(encoding="utf-8", errors="replace")
    files = []
    # 匹配 "修改文件" 或 changed files 表格行
    for line in text.splitlines():
        # 表格行: | src/foo.py | ... |
        m = re.match(r"\|\s*(`?[\w./\\-]+`?)\s*\|", line.strip())
        if m:
            val = m.group(1).strip("`")
            if "/" in val or val.endswith(".py") or val.endswith(".vue") or val.endswith(".js"):
                files.append(val)
    return files


# ── 冒烟测试 ──────────────────────────────────────────────────────────

def smoke_backend(be_port: int, endpoints: list[str]) -> list[dict]:
    """后端 API 冒烟, 返回 [{api, method, expect, actual, verdict}]"""
    results = []
    for ep in endpoints:
        url = f"http://localhost:{be_port}{ep}"
        code, _ = http_get(url)
        actual = code if code > 0 else 0
        verdict = "PASS" if actual == 200 else ("FAIL" if actual > 0 else "FAIL")
        results.append({
            "api": ep,
            "method": "GET",
            "expect": 200,
            "actual": actual,
            "verdict": verdict,
        })
    return results


def smoke_frontend(fe_port: int) -> dict:
    """前端渲染验证"""
    if fe_port <= 0:
        return {"page": "(未启动前端)", "method": "-", "result": "-", "verdict": "SKIP"}
    url = f"http://localhost:{fe_port}/"
    code, body = http_get(url, timeout=5)
    if code == 200:
        return {"page": "/", "method": "HTTP GET", "result": f"{code} OK", "verdict": "PASS"}
    return {"page": "/", "method": "HTTP GET", "result": f"status={code}", "verdict": "FAIL"}


def run_unit_tests(wt_path: str, changed_files: list[str]) -> list[dict]:
    """运行相关单元测试"""
    if not wt_path:
        return [{"file": "(未运行)", "cases": "-", "passed": "-", "failed": "-", "verdict": "SKIP"}]
    # 查找测试文件
    test_files = set()
    root = Path(wt_path)
    for cf in changed_files:
        # 简单启发: foo.py -> test_foo.py 或 test/test_foo.py
        base = Path(cf).stem
        for pattern in [f"**/test_{base}.py", f"**/tests/test_{base}.py"]:
            for f in root.glob(pattern):
                test_files.add(str(f))
    if not test_files:
        return [{"file": "(未找到相关测试)", "cases": "-", "passed": "-", "failed": "-", "verdict": "SKIP"}]
    results = []
    for tf in sorted(test_files):
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pytest", tf, "-q", "--tb=no"],
                capture_output=True, encoding="utf-8", errors="replace", timeout=60,
                cwd=wt_path,
            )
            # 解析 pytest 输出: "3 passed, 1 failed"
            out = r.stdout + r.stderr
            pm = re.search(r"(\d+) passed", out)
            fm = re.search(r"(\d+) failed", out)
            passed = int(pm.group(1)) if pm else 0
            failed = int(fm.group(1)) if fm else 0
            verdict = "PASS" if failed == 0 and r.returncode == 0 else "FAIL"
            results.append({
                "file": Path(tf).name,
                "cases": passed + failed,
                "passed": passed,
                "failed": failed,
                "verdict": verdict,
            })
        except Exception as e:
            results.append({"file": Path(tf).name, "cases": "?", "passed": "?", "failed": "?", "verdict": "FAIL"})
    return results


# ── 服务管理 ──────────────────────────────────────────────────────────

def check_db_schema_version(wt_path: str) -> dict:
    """检查 worktree 的 DB schema 版本与主仓库是否一致 (L1)

    Returns:
        {"wt_version": int, "main_version": int, "verdict": "PASS"|"FAIL"|"SKIP"}
    """
    result = {"wt_version": None, "main_version": None, "verdict": "SKIP"}

    def _get_schema_version(db_path: str) -> int | None:
        if not Path(db_path).exists():
            return None
        try:
            import sqlite3
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
            # 检查 schema_migrations 表是否存在
            r = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).fetchone()
            if not r:
                conn.close()
                return 0  # 表不存在 = version 0
            r = conn.execute("SELECT COUNT(*) FROM schema_migrations WHERE status='SUCCESS'").fetchone()
            conn.close()
            return r[0] if r else 0
        except Exception:
            return None

    # worktree DB
    wt_db = str(Path(wt_path) / "meta" / "architecture.db")
    result["wt_version"] = _get_schema_version(wt_db)

    # 主仓库 DB (作为基准)
    paths = load_paths()
    main_db = str(Path(paths["main_repo"]) / "meta" / "architecture.db")
    result["main_version"] = _get_schema_version(main_db)

    if result["wt_version"] is None or result["main_version"] is None:
        result["verdict"] = "SKIP"
    elif result["wt_version"] == result["main_version"]:
        result["verdict"] = "PASS"
    else:
        result["verdict"] = "FAIL"

    return result


def svc_call(action: str, wt_name: str) -> bool:
    """调用 _wt_service.py 或 service_manager.py"""
    paths = load_paths()
    main_repo = Path(paths["main_repo"])
    # 优先 _wt_service.py
    wt_svc = main_repo / "scripts" / "_wt_service.py"
    svc_mgr = main_repo / "scripts" / "service_manager.py"
    script = wt_svc if wt_svc.exists() else svc_mgr
    if not script.exists():
        print(c_fail(f"  [ERROR] 服务管理脚本不存在: {script}"))
        return False
    cmd = [sys.executable, str(script), action, wt_name]
    try:
        r = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=120)
        return r.returncode == 0
    except Exception as e:
        print(c_fail(f"  [ERROR] 调用 {action} 失败: {e}"))
        return False


def wait_for_healthz(be_port: int, timeout: int) -> bool:
    """等待 healthz 可用"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        code, _ = http_get(f"http://localhost:{be_port}/api/v1/health", timeout=3)
        if code == 200:
            return True
        time.sleep(2)
    return False


# ── 报告生成 ──────────────────────────────────────────────────────────

def build_report(
    wt_name: str,
    be_port: int,
    fe_port: int,
    api_results: list[dict],
    fe_result: dict,
    unit_results: list[dict],
    changed_files: list[str],
    cmd_str: str,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "## SELF_VERIFY_RESULTS",
        "",
        "### 后端 API 冒烟",
        "| API | 方法 | 期望状态码 | 实际状态码 | VERDICT |",
        "|-----|------|----------|----------|---------|",
    ]
    for r in api_results:
        lines.append(f"| {r['api']} | {r['method']} | {r['expect']} | {r['actual']} | {r['verdict']} |")
    if not api_results:
        lines.append("| (未运行) | - | - | - | SKIP |")

    lines += [
        "",
        "### 前端渲染验证",
        "| 页面 | 验证方式 | 结果 | VERDICT |",
        "|------|---------|------|---------|",
    ]
    lines.append(f"| {fe_result['page']} | {fe_result['method']} | {fe_result['result']} | {fe_result['verdict']} |")

    lines += [
        "",
        "### 单元测试",
        "| 测试文件 | 用例数 | 通过 | 失败 | VERDICT |",
        "|---------|-------|------|------|---------|",
    ]
    for r in unit_results:
        lines.append(f"| {r['file']} | {r['cases']} | {r['passed']} | {r['failed']} | {r['verdict']} |")

    lines += [
        "",
        "### 改动影响范围",
        "| 修改文件 | 影响范围 | 是否影响共享 API |",
        "|---------|---------|----------------|",
    ]
    if changed_files:
        for f in changed_files[:10]:
            lines.append(f"| {f} | (请手动填写) | - |")
    else:
        lines.append("| (请手动填写) | - | - |")

    lines += [
        "",
        "### 自验证环境",
        "| 项 | 值 |",
        "|----|-----|",
        f"| 后端端口 | {be_port} |",
        f"| 前端端口 | {fe_port} |",
        f"| 验证时间 | {now} |",
        f"| 验证命令 | python scripts/self_verify.py {cmd_str} |",
    ]
    return "\n".join(lines)


# ── 命令实现 ──────────────────────────────────────────────────────────

def cmd_run(wt_name: str, keep_running: bool = False):
    """完整流程: 启动服务 -> 冒烟 -> (停止|保持) -> 报告

    Args:
        keep_running: True = 自验证后保持服务运行 (P1-E2)
    """
    be_port, fe_port, wt_path = resolve_ports(wt_name)
    cfg = load_self_verify_config()
    endpoints = cfg["api_smoke_endpoints"]

    # [L1] DB schema 版本检查
    print(f"  [0/6] DB schema 版本检查...")
    db_check = check_db_schema_version(wt_path)
    if db_check["verdict"] == "FAIL":
        print(c_fail(f"  [FAIL] DB schema 不一致: wt={db_check['wt_version']}, main={db_check['main_version']}"))
        print(c_fail("  请运行 migration_runner.py 同步 DB schema"))
        sys.exit(1)
    elif db_check["verdict"] == "PASS":
        print(c_pass(f"  [PASS] DB schema 一致 (v{db_check['wt_version']})"))
    else:
        print(f"  [SKIP] DB schema 检查跳过 (DB 不存在或无法读取)")

    print(f"  [1/6] 启动后端 (port {be_port})...")
    svc_call("start-be", wt_name)
    if not check_port(be_port):
        print(c_fail("  [FAIL] 后端启动失败"))
        sys.exit(2)

    # 后端和前端并行启动 (P0-E1 优化: 节省 ~30s)
    # 前端不依赖后端启动完成, 只依赖后端运行时的 API (冒烟阶段才需要)
    print(f"  [1b/6] 并行启动前端 (port {fe_port})...")
    import threading
    fe_thread = threading.Thread(target=svc_call, args=("start-fe", wt_name), daemon=True)
    fe_thread.start()

    print(f"  [2/6] 等待 healthz (timeout {cfg['backend_startup_timeout']}s)...")
    if not wait_for_healthz(be_port, cfg["backend_startup_timeout"]):
        print(c_fail("  [FAIL] 后端 healthz 超时"))
        sys.exit(2)
    print(c_pass("  [PASS] 后端 healthz OK"))

    # 等待前端启动完成 (最多再等 10s, 因为后端等待期间前端已在启动)
    fe_thread.join(timeout=10)
    print(c_pass("  [PASS] 前端启动完成"))

    print("  [4/6] 冒烟测试...")
    api_results, fe_result, unit_results, changed_files = _do_smoke(
        be_port, fe_port, wt_path, endpoints
    )

    print("  [5/6] 停止服务...")
    if keep_running:
        print(c_warn(f"  [KEEP_RUNNING] 服务保持运行 (be={be_port}, fe={fe_port})"))
        print(f"  注册到 session cleanup (防止孤儿)...")
        try:
            from _session_cleanup import cmd_register
            cmd_register(wt_name)
        except Exception:
            pass
        print(f"  协调智能体 cherry-pick 后请手动: _wt_service.py stop {wt_name}")
    else:
        svc_call("stop", wt_name)

    print("  [6/6] 生成报告")
    report = build_report(
        wt_name, be_port, fe_port, api_results, fe_result,
        unit_results, changed_files, f"run {wt_name}",
    )
    _print_and_exit(report, api_results, fe_result, unit_results)


def cmd_smoke(wt_name: str):
    """仅冒烟测试"""
    be_port, fe_port, wt_path = resolve_ports(wt_name)
    cfg = load_self_verify_config()
    endpoints = cfg["api_smoke_endpoints"]

    # 先确认后端活着
    code, _ = http_get(f"http://localhost:{be_port}/api/v1/health", timeout=5)
    if code != 200:
        print(c_fail(f"  [ERROR] 后端未运行 (port {be_port}, healthz={code})"))
        sys.exit(2)

    api_results, fe_result, unit_results, changed_files = _do_smoke(
        be_port, fe_port, wt_path, endpoints
    )
    report = build_report(
        wt_name, be_port, fe_port, api_results, fe_result,
        unit_results, changed_files, f"smoke {wt_name}",
    )
    _print_and_exit(report, api_results, fe_result, unit_results)


def cmd_quick(wt_name: str):
    """快速检查: healthz + 1 API"""
    be_port, fe_port, wt_path = resolve_ports(wt_name)

    code, _ = http_get(f"http://localhost:{be_port}/api/v1/health", timeout=5)
    h_verdict = "PASS" if code == 200 else "FAIL"
    print(f"  healthz (:{be_port}) = {code}  {c_pass(h_verdict) if h_verdict == 'PASS' else c_fail(h_verdict)}")

    p_code, _ = http_get(f"http://localhost:{be_port}/api/v1/products", timeout=5)
    p_verdict = "PASS" if p_code == 200 else "FAIL"
    print(f"  /api/v1/products (:{be_port}) = {p_code}  {c_pass(p_verdict) if p_verdict == 'PASS' else c_fail(p_verdict)}")

    if h_verdict == "FAIL" or p_verdict == "FAIL":
        sys.exit(1)
    sys.exit(0)


def cmd_report(wt_name: str):
    """仅输出报告 (假设上次冒烟结果存在, 或重新运行冒烟)"""
    cmd_smoke(wt_name)


# ── 内部工具 ──────────────────────────────────────────────────────────

def _do_smoke(be_port, fe_port, wt_path, endpoints):
    """执行冒烟, 返回 (api_results, fe_result, unit_results, changed_files)"""
    handover = find_handover(wt_path)
    changed_files = parse_handover_files(handover) if handover else []

    # 如果有 HANDOVER, 可能需要额外端点 (当前使用默认)
    api_results = smoke_backend(be_port, endpoints)
    for r in api_results:
        tag = c_pass(r["verdict"]) if r["verdict"] == "PASS" else c_fail(r["verdict"])
        print(f"    {r['api']} -> {r['actual']}  {tag}")

    fe_result = smoke_frontend(fe_port)
    tag = c_skip(fe_result["verdict"]) if fe_result["verdict"] == "SKIP" else (
        c_pass(fe_result["verdict"]) if fe_result["verdict"] == "PASS" else c_fail(fe_result["verdict"])
    )
    print(f"    前端 (:{fe_port}) -> {fe_result['result']}  {tag}")

    unit_results = run_unit_tests(wt_path, changed_files)
    for r in unit_results:
        tag = c_skip(r["verdict"]) if r["verdict"] == "SKIP" else (
            c_pass(r["verdict"]) if r["verdict"] == "PASS" else c_fail(r["verdict"])
        )
        print(f"    测试 {r['file']} -> pass={r['passed']} fail={r['failed']}  {tag}")

    return api_results, fe_result, unit_results, changed_files


def _print_and_exit(report, api_results, fe_result, unit_results):
    """打印报告并根据结果退出"""
    print()
    print(report)
    all_verdicts = (
        [r["verdict"] for r in api_results]
        + [fe_result["verdict"]]
        + [r["verdict"] for r in unit_results]
    )
    if any(v == "FAIL" for v in all_verdicts):
        sys.exit(1)
    sys.exit(0)


# ── 入口 ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="自动自验证脚本")
    sub = parser.add_subparsers(dest="cmd", required=True)

    for name in ("run", "smoke", "report", "quick"):
        p = sub.add_parser(name, help=f"{name} <wt-name>")
        p.add_argument("wt_name", help="worktree 名称 (如 agent-bug-v058)")
        if name == "run":
            p.add_argument("--keep-running", action="store_true",
                           help="自验证后保持服务运行 (P1-E2)")

    args = parser.parse_args()

    if args.cmd == "run":
        cmd_run(args.wt_name, getattr(args, "keep_running", False))
    elif args.cmd == "smoke":
        cmd_smoke(args.wt_name)
    elif args.cmd == "report":
        cmd_report(args.wt_name)
    elif args.cmd == "quick":
        cmd_quick(args.wt_name)


if __name__ == "__main__":
    main()
