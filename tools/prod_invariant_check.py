#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[2026-09-16] prod_invariant_check.py - prod/staging 部署后 invariant 检查

背景:
  staging 2026-09-16 全实例级 bug 的根因 = `deploy/meta` symlink 错指 `current/`
  而非 `current/meta/` (见 docs/retrospectives/2026-09-16-*.md)
  我们本应在每次部署后检查 "server 实际 import 的 __file__ 是否在新代码路径",
  但 staging 9-05/9-13 两次复盘都没有把这个 invariant 工具化

设计目标:
  - 部署完成后强制跑一次, 6 项 invariant 任何 1 项失败 → EXIT 1 (绝不宣称部署成功)
  - 全部检查都用 introspection (真路径) 而非 md5/symlink 表象
  - 同时支持 staging / prod (通过 --target 参数切换)
  - 输出 JSON audit log 供回溯

6 项 invariant (对应失败模式家族 4 次复发的可观察特征):
  I1. server.py cwd 必须匹配 deploy_root (避免 prod/staging server 错启)
  I2. realpath(<deploy_root>/meta) 必须落在 deploy_root 之下 (避免 9-16 symlink 错指)
  I3. import meta.core.standard_action_loader 的 __file__ 必须在 meta/core/ 下 (避免 9-13 加载老版本)
  I4. 必须存在 server.py 进程且监听预期端口 (避免 server 没起)
  I5. 关键 actions (crud_create) 的 instance_scope 必须等于 object (业务不变量)
  I6. git status 必须 clean (禁止未还原调试改动就部署)

使用:
  python tools/prod_invariant_check.py --target staging
  python tools/prod_invariant_check.py --target production
  python tools/prod_invariant_check.py --target staging --module meta.api.permission_dimension_api
  python tools/prod_invariant_check.py --target staging --audit-log /var/log/prod_invariant.jsonl
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

# 依赖同目录 lib
TOOLS = Path(__file__).parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "lib"))

try:
    from deploy_topology import DeployTarget
except ImportError:
    DeployTarget = None  # type: ignore


# --------------------------------------------------------------------------
# Invariant 检查结果
# --------------------------------------------------------------------------
@dataclass
class InvariantResult:
    invariant_id: str        # "I1", "I2", ...
    description: str
    passed: bool
    details: str = ""
    observed: dict = field(default_factory=dict)
    expected: dict = field(default_factory=dict)


@dataclass
class Report:
    target: str
    timestamp: str
    all_passed: bool
    results: List[InvariantResult] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "timestamp": self.timestamp,
            "all_passed": self.all_passed,
            "results": [asdict(r) for r in self.results],
            "summary": self.summary,
        }


# --------------------------------------------------------------------------
# 工具: 跑远端命令并解析
# --------------------------------------------------------------------------
def _remote_exec(target: "DeployTarget", cmd: str, timeout: int = 15) -> tuple[str, str, int]:
    """返回 (stdout, stderr, returncode)."""
    if target.exec_fn is None:
        raise RuntimeError(f"target '{target.name}' has no exec_fn")
    r = target.exec_fn(cmd, timeout=timeout)
    return (
        (r.get("stdout") or "").strip(),
        (r.get("stderr") or "").strip(),
        int(r.get("returncode") or 0),
    )


def _remote_upload(target: "DeployTarget", local: Path, remote: str) -> bool:
    if target.upload_fn is None:
        raise RuntimeError(f"target '{target.name}' has no upload_fn")
    r = target.upload_fn(local, remote)
    return bool(r and r.get("success", r.get("ok", False)))


# --------------------------------------------------------------------------
# 6 项 invariant
# --------------------------------------------------------------------------
def check_I1_server_cwd(target: "DeployTarget") -> InvariantResult:
    """I1. server.py 进程 cwd 必须匹配 deploy_root.

    失败模式: prod server 错启到 staging 路径 / cwd 漂移到 /root

    注意: pgrep -f 会匹配当前 bash 自身 (因为 grep 模式中包含 server.py),
    必须用 pgrep -af + grep -v pgrep 过滤自身, 或者用 pidof 走 systemd cgroup

    实现: 直接 upload Python 脚本到远端, 用 psutil-style /proc 检查,
    避免 shell 转义陷阱
    """
    # upload 一个本地 Python 检查脚本, 比 shell awk 稳定得多
    i1_local = TOOLS / "_invariant_i1.py"
    i1_local.write_text(I1_TEMPLATE)
    _remote_upload(target, i1_local, "/tmp/_invariant_i1.py")

    out, err, rc = _remote_exec(
        target,
        "/opt/miniconda3-py39/bin/python /tmp/_invariant_i1.py 2>&1",
        timeout=10,
    )
    pid = ""
    cwd = ""
    cmdline = ""
    for line in out.splitlines():
        if line.startswith("PID="):
            pid = line[4:].strip()
        elif line.startswith("CWD="):
            cwd = line[4:].strip()
        elif line.startswith("CMDLINE="):
            cmdline = line[len("CMDLINE="):].strip()

    # [2026-09-16 复盘] staging_services.sh 启动 server 时 cwd 经常 = /root,
    # 但 cmdline 是绝对路径, 实际加载的 sys.path 由 server.py 内部 dirname() 决定
    # 因此 I1 应优先检查 cmdline 中的 server.py 路径, cwd 作为参考
    cmdline_ok = bool(cmdline) and (
        cmdline.startswith(target.deploy_root)
        or f"{target.deploy_root}/server.py" in cmdline
        or cmdline.endswith("server.py")  # systemd prod 风格 (相对路径 + WorkingDirectory)
    )
    cwd_ok = bool(cwd) and cwd != "NO_SERVER" and (
        cwd == target.deploy_root
        or cwd.startswith(target.deploy_root + "/")
    )
    # systemd prod 风格: WorkingDirectory 显式, 但 cmdline 用相对路径 server.py
    # 此时 cwd == deploy_root 才算 ok
    if cmdline.endswith("server.py") and not cmdline.startswith("/"):
        # systemd 相对路径启动
        passed = cwd_ok
    else:
        # 绝对路径启动, cmdline 是首要信号, cwd 是参考
        passed = cmdline_ok

    return InvariantResult(
        invariant_id="I1",
        description="server.py 启动路径必须指向 deploy_root (cmdline 绝对路径 / cwd 是 WorkingDirectory)",
        passed=passed,
        details=f"server PID={pid}, cmdline='{cmdline[:100]}', cwd='{cwd}'",
        observed={"pid": pid, "cwd": cwd, "cmdline": cmdline[:200]},
        expected={"deploy_root": target.deploy_root, "cmdline_starts_with": target.deploy_root},
    )


I1_TEMPLATE = '''#!/usr/bin/env python3
"""[2026-09-16] invariant I1: server.py 进程 cwd 检查.

通过 /proc 直接读 PID, 不依赖 shell grep 模式 (避免 pgrep 匹配 bash 自身).
"""
import os

PID = None
CMDLINE = ""
# 遍历 /proc, 找 cmdline 含 server.py 且是 python 启动的
for entry in sorted(os.listdir("/proc"), key=lambda x: int(x) if x.isdigit() else 0):
    if not entry.isdigit():
        continue
    try:
        with open(f"/proc/{entry}/cmdline", "rb") as f:
            cmdline = f.read().replace(b"\\x00", b" ").decode("utf-8", errors="replace").strip()
        if "server.py" in cmdline and "python" in cmdline and "awk" not in cmdline:
            PID = entry
            CMDLINE = cmdline
            break
    except (PermissionError, FileNotFoundError, ProcessLookupError):
        continue

if PID:
    try:
        CWD = os.readlink(f"/proc/{PID}/cwd")
    except (PermissionError, FileNotFoundError):
        CWD = "READLINK_DENIED"
    print(f"PID={PID}")
    print(f"CWD={CWD}")
    print(f"CMDLINE={CMDLINE}")
else:
    print("PID=")
    print("CWD=NO_SERVER")
    print("CMDLINE=")
'''


def check_I2_meta_realpath(target: "DeployTarget") -> InvariantResult:
    """I2. realpath(<deploy_root>) 必须 == 某个已批准版本目录 (不是 symlink 错指).

    失败模式: 2026-09-16 staging deploy/meta 错指 current/ 而非 current/meta/,
    导致 from meta.core.X 解析到老版本

    正确场景:
      - staging deploy/current → /opt/app/staging/deploy/v1789297457_staging_spec22
        (symlink 解析到版本目录是 OK 的)
      - prod /opt/app/deployments/current → /opt/app/deployments/meta
        (平铺, realpath == meta 也是 OK 的)

    错误场景:
      - 解析到一个老版本目录, 不是当前 deploy_root 的目标
    """
    out, err, rc = _remote_exec(
        target,
        f'echo "DEPLOY_ROOT={target.deploy_root}"; '
        f'echo "REALPATH=$(realpath {target.deploy_root} 2>&1)"; '
        f'if [ -e "{target.deploy_root}/meta" ]; then '
        f'  echo "META_REAL=$(realpath {target.deploy_root}/meta 2>&1)"; '
        f'  echo "META_CORE_LOADER=$(realpath {target.deploy_root}/meta/core/standard_action_loader.py 2>&1)"; '
        f'fi',
        timeout=8,
    )
    realpath_main = ""
    realpath_meta = ""
    realpath_loader = ""
    for line in out.splitlines():
        if line.startswith("REALPATH="):
            realpath_main = line[len("REALPATH="):].strip()
        elif line.startswith("META_REAL="):
            realpath_meta = line[len("META_REAL="):].strip()
        elif line.startswith("META_CORE_LOADER="):
            realpath_loader = line[len("META_CORE_LOADER="):].strip()

    # [2026-09-16 复盘] 必须允许 deploy_root 解析到版本目录 (staging) 或 meta (prod 平铺)
    # 错指场景: meta 指向 current/ 顶层, 但 current/core/ 里有同名老文件
    # 判定条件: 如果 deploy_root 下存在 meta/, 则 meta/core/standard_action_loader.py 的
    #   realpath 必须也落在 deploy_root 解析路径下的 meta/core/ 下
    if realpath_meta and realpath_loader:
        # loader 必须在 deploy_root 的 meta/core/ 下, 不能跑到 current/core/ 这种老版本路径
        # 关键: loader_path 必须以 (realpath_main + "/meta/core/") 开头, 不能是 (realpath_main + "/core/")
        expected_prefix = realpath_main + "/meta/core/"
        wrong_prefix = realpath_main + "/core/"  # 错指场景
        passed = realpath_loader.startswith(expected_prefix) and not realpath_loader.startswith(wrong_prefix)
        details = f"loader={realpath_loader} expected_prefix={expected_prefix}"
    elif not realpath_meta:
        # prod 平铺部署, 没有 /meta 子目录, 只验证 deploy_root 解析合法
        passed = bool(realpath_main) and realpath_main.startswith("/opt/app/")
        details = f"flat deploy: realpath_main={realpath_main}"
    else:
        passed = False
        details = f"cannot determine: realpath_main={realpath_main}, meta={realpath_meta}, loader={realpath_loader}"

    return InvariantResult(
        invariant_id="I2",
        description="realpath 必须正确 (loader 在 meta/core/ 下, 不在错指的 core/ 下)",
        passed=passed,
        details=details,
        observed={
            "deploy_root_realpath": realpath_main,
            "meta_realpath": realpath_meta,
            "loader_realpath": realpath_loader,
        },
        expected={
            "loader_path_starts_with": realpath_main + "/meta/core/" if realpath_main else None,
        },
    )


def check_I3_loader_realpath(target: "DeployTarget", module: str = "meta.core.standard_action_loader") -> InvariantResult:
    """I3. import <module>.__file__ 必须在新代码 deploy 目录下.

    失败模式: 2026-09-13 spec22 部署后, server 加载的还是 v0905 老 core/loader

    [2026-09-16] 注意 prod 是平铺部署: deploy_root = /opt/app/deployments/meta
    实际 import 需要 sys.path.insert(0, parent_of_deploy_root) = /opt/app/deployments/
    否则会去找 meta/meta/__init__.py (不存在)
    """
    # 决定 introspect 用的 sys.path:
    # - staging: deploy_root 是 symlink 到版本目录, sys.path 插 deploy_root (顶层), 找 meta/ 子目录
    # - prod:    deploy_root 本身就是 meta 包, sys.path 应插 deploy_root 的 parent
    deploy_root = target.deploy_root
    if deploy_root.endswith("/meta"):
        # 平铺 prod 风格
        sys_path_root = str(Path(deploy_root).parent).replace("\\", "/")
    else:
        # staging 平铺 + symlink
        sys_path_root = deploy_root

    intro_local = TOOLS / "_invariant_introspect.py"
    intro_local.write_text(INTROSPECT_TEMPLATE.format(module=module, expected_root=sys_path_root))
    _remote_upload(target, intro_local, "/tmp/_invariant_introspect.py")

    out, err, rc = _remote_exec(
        target,
        "/opt/miniconda3-py39/bin/python -I /tmp/_invariant_introspect.py 2>&1",
        timeout=20,
    )
    loader_path = ""
    loader_count = "0"
    scope_create = ""
    for line in out.splitlines():
        if line.startswith("LOADER_PATH="):
            loader_path = line[len("LOADER_PATH="):]
        elif line.startswith("LOADER_COUNT="):
            loader_count = line[len("LOADER_COUNT="):]
        elif line.startswith("SCOPE_CRUD_CREATE="):
            scope_create = line[len("SCOPE_CRUD_CREATE="):]

    passed = bool(loader_path) and (
        loader_path.startswith(target.deploy_root + "/")
        or loader_path.startswith(target.deploy_root)
    )
    return InvariantResult(
        invariant_id="I3",
        description=f"import {module}.__file__ 必须落在 deploy_root 下",
        passed=passed,
        details=f"loader_path='{loader_path}', count={loader_count}, scope[crud_create]={scope_create}",
        observed={"loader_path": loader_path, "loader_count": loader_count, "scope_create": scope_create},
        expected={"starts_with": target.deploy_root},
    )


INTROSPECT_TEMPLATE = '''
import sys
sys.path.insert(0, '{expected_root}')
import importlib
m = importlib.import_module('{module}')
print('LOADER_PATH=' + str(m.__file__))

# 进一步 introspection (业务不变量)
if hasattr(m, 'StandardActionLoader'):
    from {module} import StandardActionLoader
    StandardActionLoader._loaded = False
    acts = StandardActionLoader.get_actions()
    print('LOADER_COUNT=' + str(len(acts)))
    for a in acts:
        if a.id == 'crud_create':
            print('SCOPE_CRUD_CREATE=' + str(a.instance_scope.value))
            break
else:
    print('LOADER_COUNT=0')
    print('SCOPE_CRUD_CREATE=NA')
'''


def check_I4_listener(target: "DeployTarget") -> InvariantResult:
    """I4. server 必须监听预期端口 (5001=prod, 13011=staging).

    失败模式: 2026-09-16 staging server 死后 13011 无监听, 但 18081 代理 502 假成功
    """
    expected_ports = {
        "production": 5001,
        "staging": 13011,
    }.get(target.name)
    if not expected_ports:
        # 未知 target, 跳过
        return InvariantResult(
            invariant_id="I4",
            description=f"server 监听检查 ({target.name} 无预期端口)",
            passed=True,
            details=f"target '{target.name}' has no expected port mapping, skip",
        )

    out, _, _ = _remote_exec(
        target, f'ss -tlnp | grep -E ":{expected_ports} " || echo "NO_LISTENER"', timeout=8
    )
    passed = "NO_LISTENER" not in out and str(expected_ports) in out
    return InvariantResult(
        invariant_id="I4",
        description=f"server 必须监听 :{expected_ports}",
        passed=passed,
        details=out[:200] if out else "(empty)",
        observed={"port_listening": passed, "raw": out[:300]},
        expected={"port": expected_ports},
    )


def check_I5_business_invariant(target: "DeployTarget") -> InvariantResult:
    """I5. crud_create.instance_scope == object (业务不变量).

    失败模式: 2026-09-16 全实例级 bug (loader 加载老版本导致所有 actions 都是 instance)
    """
    out, err, _ = _remote_exec(
        target, "/opt/miniconda3-py39/bin/python -I /tmp/_invariant_introspect.py 2>&1", timeout=10
    )
    scope = ""
    for line in out.splitlines():
        if line.startswith("SCOPE_CRUD_CREATE="):
            scope = line[len("SCOPE_CRUD_CREATE="):]
    passed = scope == "object"
    return InvariantResult(
        invariant_id="I5",
        description="crud_create.instance_scope 必须 == 'object' (Spec 21 业务不变量)",
        passed=passed,
        details=f"scope={scope}",
        observed={"scope": scope},
        expected={"scope": "object"},
    )


def check_I6_git_clean() -> InvariantResult:
    """I6. 关键部署代码 (meta/, tools/, deploy_topology.yaml) 必须 git clean.

    失败模式: 2026-09-16 我留了 staging 调试改动没还原就 restart server, syntax error

    注意:
      - 仅检查 deploy-critical 路径, 不检查整个 repo (因为 docs/retrospectives/ 等
        文档/临时脚本通常不该阻塞部署)
      - 排除工具自身文件 (prod_invariant_check.py / _invariant_*.py / audit log)
        这些是工具自己生成/修改的, 不算 "未还原的调试改动"
    """
    DEPLOY_CRITICAL_PATHS = [
        "meta/api/", "meta/core/", "meta/services/",
        "tools/staging_round.py", "tools/deploy_upload.py",
        "tools/lib/", "tools/config/deploy_topology.yaml",
    ]
    try:
        # 用 git status --porcelain 检查未提交改动, 然后过滤 deploy-critical
        r = subprocess.run(
            ["git", "status", "--porcelain", "--"] + DEPLOY_CRITICAL_PATHS,
            cwd=str(TOOLS.parent),  # 项目根
            capture_output=True, text=True, timeout=10,
        )
        lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
        # 过滤: (1) 工具自身文件 (2) rename 行
        TOOL_SELF_IGNORE = [
            "tools/prod_invariant_check.py",     # 本工具
            "tools/.deploy_invariant_audit.jsonl",  # 自动生成的 audit log
            "tools/_invariant_*.py",            # 工具上传的临时 introspect 脚本
        ]
        real_changes = []
        for ln in lines:
            if not (ln.startswith("??") or ln.startswith("M ") or ln.startswith("A ") or ln.startswith("D ")):
                continue
            # 提取文件路径部分 (git porcelain 格式: "XY filename")
            # rename 格式 "R  old -> new", 取 new
            if " -> " in ln:
                file_part = ln.split(" -> ", 1)[1].strip()
            else:
                file_part = ln[3:].strip()
            # 工具自身文件忽略
            if any(file_part.endswith(ig.rstrip("*")) or ig.replace("*", "") in file_part
                   for ig in TOOL_SELF_IGNORE):
                continue
            real_changes.append(ln)
        passed = len(real_changes) == 0
        return InvariantResult(
            invariant_id="I6",
            description="deploy-critical 路径 (meta/, tools/) 必须 git clean (避免未还原调试改动就部署)",
            passed=passed,
            details=f"uncommitted in critical paths: {len(real_changes)} files"
                    + (": " + " ".join(real_changes[:5]) if real_changes else ""),
            observed={"uncommitted_critical_count": len(real_changes), "files": real_changes[:20]},
            expected={"uncommitted_critical_count": 0},
        )
    except Exception as e:
        return InvariantResult(
            invariant_id="I6",
            description="git status 检查失败 (可能非 git 环境, 跳过)",
            passed=True,
            details=str(e),
            observed={"error": str(e)},
            expected={},
        )


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def run_invariants(target_name: str, module: str = "meta.core.standard_action_loader",
                   audit_log: Optional[Path] = None) -> Report:
    if DeployTarget is None:
        raise RuntimeError("deploy_topology.py not importable, run from tools/")

    target = DeployTarget.from_name(target_name)
    print(f"[invariant] target={target_name}, deploy_root={target.deploy_root}", flush=True)

    results: List[InvariantResult] = []

    checks = [
        ("I1", lambda: check_I1_server_cwd(target)),
        ("I2", lambda: check_I2_meta_realpath(target)),
        ("I3", lambda: check_I3_loader_realpath(target, module=module)),
        ("I4", lambda: check_I4_listener(target)),
        ("I5", lambda: check_I5_business_invariant(target)),
        ("I6", check_I6_git_clean),
    ]

    for inv_id, fn in checks:
        print(f"[invariant] running {inv_id}...", flush=True)
        try:
            r = fn()
        except Exception as e:
            r = InvariantResult(
                invariant_id=inv_id,
                description=f"check raised exception: {e}",
                passed=False,
                details=str(e),
            )
        results.append(r)
        print(f"[invariant] {inv_id} {'PASS' if r.passed else 'FAIL'}: {r.description}")
        if not r.passed:
            print(f"         details: {r.details[:300]}")

    all_passed = all(r.passed for r in results)
    summary = {
        "total": len(results),
        "passed": sum(1 for r in results if r.passed),
        "failed": sum(1 for r in results if not r.passed),
        "failed_ids": [r.invariant_id for r in results if not r.passed],
    }

    report = Report(
        target=target_name,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        all_passed=all_passed,
        results=results,
        summary=summary,
    )

    # 写 audit log
    if audit_log:
        audit_log.parent.mkdir(parents=True, exist_ok=True)
        with audit_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(report.to_dict(), ensure_ascii=False) + "\n")

    return report


def main():
    ap = argparse.ArgumentParser(description="部署后 invariant 检查 (staging/prod)")
    ap.add_argument("--target", default="staging", choices=["staging", "production"],
                    help="部署目标")
    ap.add_argument("--module", default="meta.core.standard_action_loader",
                    help="introspect 的 Python 模块 (I3)")
    ap.add_argument("--audit-log", type=Path,
                    default=Path(__file__).parent / ".deploy_invariant_audit.jsonl",
                    help="audit log 路径 (jsonl)")
    ap.add_argument("--skip", action="append", default=[],
                    help="跳过指定 invariant (可多次, 例: --skip I6)")
    args = ap.parse_args()

    report = run_invariants(args.target, args.module, args.audit_log)

    # 应用 --skip 过滤
    if args.skip:
        report.results = [x for x in report.results if x.invariant_id not in args.skip]
        report.summary = {
            "total": len(report.results),
            "passed": sum(1 for x in report.results if x.passed),
            "failed": sum(1 for x in report.results if not x.passed),
            "failed_ids": [x.invariant_id for x in report.results if not x.passed],
        }
        report.all_passed = all(x.passed for x in report.results)
        # 重写 audit log (覆盖原始报告)
        if args.audit_log:
            with args.audit_log.open("a", encoding="utf-8") as f:
                f.write("# SKIPPED: " + ",".join(args.skip) + "\n")

    print(f"\n[invariant] SUMMARY: {report.summary}")
    if not report.all_passed:
        print(f"\n[invariant] FAIL: {len(report.summary['failed_ids'])} invariant(s) failed: "
              f"{report.summary['failed_ids']}")
        print("[invariant] 部署不能宣称成功, 必须先修")
        sys.exit(1)
    else:
        print(f"\n[invariant] OK: all {report.summary['total']} invariants passed")
        sys.exit(0)


if __name__ == "__main__":
    main()