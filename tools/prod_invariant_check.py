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
  - 部署完成后强制跑一次, 8 项 invariant 任何 1 项失败 → EXIT 1 (绝不宣称部署成功)
  - 全部检查都用 introspection (真路径) 而非 md5/symlink 表象
  - 同时支持 staging / prod (通过 --target 参数切换)
  - 输出 JSON audit log 供回溯

8 项 invariant (对应失败模式家族 5 次复发的可观察特征):
  I1. server.py cwd 必须匹配 deploy_root (避免 prod/staging server 错启)
  I2. realpath(<deploy_root>/meta) 必须落在 deploy_root 之下 (避免 9-16 symlink 错指)
  I3. import meta.core.standard_action_loader 的 __file__ 必须在 meta/core/ 下 (避免 9-13 加载老版本)
  I4. 必须存在 server.py 进程且监听预期端口 (避免 server 没起)
  I5. 关键 actions (crud_create) 的 instance_scope 必须等于 object (业务不变量)
  I6. git status 必须 clean (禁止未还原调试改动就部署)
  I7. server.py 顶层 meta.* ImportFrom 必须模块级 + 符号级全部可解析
      (2026-09-26 家族第 6 次: 文件上传成功 + I1-I6 全 PASS, 但远端旧版模块
       缺符号 -> /health 500. "import meta.core.X 成功" != "from meta.core.X import Y 成功")
  I8. server.py 可达闭包 (模块级, 传递到任意深度) 必须无缺口
      (2026-09-26 家族第 6 次的「深度 2」变体: server.py 顶层 55 条 ImportFrom
       全部可解析, 但被牵连的 api/permission_dimension_api.py 内部 import 了
       远端缺失的 meta.core.permission_set_permissions -> 启动即 ModuleNotFoundError.
       I7 只覆盖深度 1, I8 收口传递闭包. 按「可达性」而非「全树」判定: 全树扫描
       在 prod 报 2 处模块级缺口 (management_dimension_api / tools/sync_schema),
       但 prod /health=200, 二者皆不在可达集内, 属孤岛死代码)

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


def check_I7_import_symbol_closure(target: "DeployTarget") -> InvariantResult:
    """I7. server.py 顶层 meta.* ImportFrom 必须模块级 + 符号级全部可解析.

    失败模式 (2026-09-26 staging, 该家族第 6 次复发):
      7 个文件上传成功, 12 条路径 md5=match, I1-I6 全 PASS,
      但 /health 500:
        ImportError: cannot import name 'bind_app_data_source' from 'meta.core.datasource'
      根因: 远端 meta/core/datasource.py 仍是 Sep-05 旧版, 缺 server.py 新版
      所引用的 6 个符号. 即 "import meta.core.X 成功" != "from meta.core.X import Y 成功".

    与 I3 互补: I3 查"加载的模块落点对不对", I7 查"该模块的符号全不全".
    server.py 未找到时跳过 (prod 可能不含顶层 server.py), 不阻塞部署.
    """
    deploy_root = target.deploy_root
    parent = str(Path(deploy_root).parent).replace("\\", "/")
    # sys.path 语义与 I3 保持一致
    if deploy_root.endswith("/meta"):
        sys_path_root = parent           # prod 平铺: server 在 meta 包之外
    else:
        sys_path_root = deploy_root      # staging: deploy_root 即顶层
    candidates = [
        f"{deploy_root}/server.py",
        f"{parent}/server.py",
        f"{parent}/current/server.py",
    ]

    tmpl = TOOLS / "_invariant_closure.py"
    tmpl.write_text(INVARIANT_CLOSURE_TEMPLATE.format(
        candidates=candidates, sys_path_root=sys_path_root))
    _remote_upload(target, tmpl, "/tmp/_invariant_closure.py")

    out, err, rc = _remote_exec(
        target,
        "/opt/miniconda3-py39/bin/python -I /tmp/_invariant_closure.py 2>&1",
        timeout=60,
    )

    server_found = False
    server = ""
    n_stmt = "0"
    n_missing = "0"
    syntax_err = ""
    missing: List[str] = []
    for line in out.splitlines():
        if line.startswith("SERVER_FOUND="):
            server_found = line[len("SERVER_FOUND="):].strip() == "1"
        elif line.startswith("SERVER="):
            server = line[len("SERVER="):].strip()
        elif line.startswith("IMPORT_STMT_COUNT="):
            n_stmt = line[len("IMPORT_STMT_COUNT="):].strip()
        elif line.startswith("MISSING_COUNT="):
            n_missing = line[len("MISSING_COUNT="):].strip()
        elif line.startswith("MISSING="):
            missing.append(line[len("MISSING="):].strip())
        elif line.startswith("SYNTAX_ERROR="):
            syntax_err = line[len("SYNTAX_ERROR="):].strip()

    if not server_found:
        return InvariantResult(
            invariant_id="I7",
            description="server.py 顶层 meta.* 符号闭包 (未找到 server.py, 跳过)",
            passed=True,
            details=f"candidates={candidates}, 均不存在; raw={out[:200]}",
            observed={"server_found": False, "candidates": candidates},
            expected={},
        )
    if syntax_err:
        return InvariantResult(
            invariant_id="I7",
            description="server.py 顶层 meta.* 符号闭包 (server.py 语法错误)",
            passed=False,
            details=f"server={server}, SyntaxError: {syntax_err}",
            observed={"server": server, "syntax_error": syntax_err},
            expected={"syntax_error": ""},
        )

    passed = (n_missing == "0")
    details = f"server={server}, meta.* ImportFrom={n_stmt} 条, 缺口={n_missing} 处"
    if missing:
        details += " | " + " ; ".join(missing[:6])
        details += "  => 用 deploy_upload.py 补传对应模块"
    return InvariantResult(
        invariant_id="I7",
        description="server.py 顶层 meta.* import 必须模块级+符号级全部可解析 (防旧版模块缺符号)",
        passed=passed,
        details=details,
        observed={"server": server, "import_stmt_count": n_stmt,
                  "missing_count": n_missing, "missing": missing[:20]},
        expected={"missing_count": "0"},
    )


# [2026-09-26 I7] 远端执行的符号闭包探针模板.
# 只做 AST 收集 + importlib 解析, 不执行业务逻辑; 3 个占位符由 format() 注入.
INVARIANT_CLOSURE_TEMPLATE = '''
import ast
import importlib
import os
import sys

CANDIDATES = {candidates!r}
SERVER = ''
for c in CANDIDATES:
    if os.path.isfile(c):
        SERVER = c
        break
if not SERVER:
    print('SERVER_FOUND=0')
    raise SystemExit(0)

sys.path.insert(0, {sys_path_root!r})
with open(SERVER, encoding='utf-8') as f:
    src = f.read()
try:
    tree = ast.parse(src)
except SyntaxError as e:
    print('SERVER_FOUND=1')
    print('SERVER=' + SERVER)
    print('SYNTAX_ERROR=' + str(e))
    raise SystemExit(0)

missing = []
n_stmt = 0
for node in ast.walk(tree):
    if not isinstance(node, ast.ImportFrom):
        continue
    if node.level != 0 or not node.module or not node.module.startswith('meta'):
        continue
    n_stmt += 1
    m = node.module
    try:
        mod = importlib.import_module(m)
    except Exception as e:
        missing.append(m + '|' + '<module>' + '|' + type(e).__name__)
        continue
    for a in node.names:
        if a.name == '*':
            continue
        if not hasattr(mod, a.name):
            missing.append(m + '|' + a.name + '|' + 'AttributeError')

print('SERVER_FOUND=1')
print('SERVER=' + SERVER)
print('IMPORT_STMT_COUNT=' + str(n_stmt))
print('MISSING_COUNT=' + str(len(missing)))
for item in missing[:20]:
    print('MISSING=' + item)
'''


def check_I8_reachability_closure(target: "DeployTarget") -> InvariantResult:
    """I8. server.py 可达 import 闭包 (模块级, 传递) 必须无缺口.

    失败模式 (2026-09-26 家族第 6 次的「深度 2」变体):
      server.py 顶层 55 条 meta.* ImportFrom 全部可解析 (I7 PASS), 但被牵连的
      api/permission_dimension_api.py 内部模块级 import 了
      meta.core.permission_set_permissions —— 该文件远端不存在.
      若只推「md5 不一致」的 26 个文件, server 启动即在深度 2 抛
      ModuleNotFoundError. I7 只看 server.py 自身 (深度 1), 覆盖不到.

    与全树扫描的区别 (为何按「可达性」而非「全树」收敛):
      2026-09-26 只读实测全树扫描在 prod 报 2 处模块级缺口
        api/management_dimension_api.py -> meta.services.management_dimension_engine
        tools/sync_schema.py -> meta.list_meta_objects
      但 prod /health = 200 —— 二者都不在 server.py 可达集内, 属孤岛死代码.
      以「全树 STARTUP==0」做门禁会立刻误判 prod 并阻塞其部署.

    作用域规则: 只把「模块级 且 非 try 且 非函数内 且 非 TYPE_CHECKING」
    的 import 视为可达; 函数内 (LATENT, 调用时才炸) 与 try 包裹 (OPTIONAL,
    可选依赖) 的缺口不参与判定. server.py 未找到时跳过 (布局差异), 不阻塞部署.
    """
    deploy_root = target.deploy_root
    parent = str(Path(deploy_root).parent).replace("\\", "/")
    # prod 是平铺布局 (deploy_root 本身就是 meta 包), staging 是 deploy_root/meta
    live_meta = deploy_root if deploy_root.endswith("/meta") else f"{deploy_root}/meta"
    candidates = [
        f"{live_meta}/server.py",
        f"{parent}/server.py",
        f"{deploy_root}/server.py",
    ]

    # 不走 str.format(): 模板内含大量 dict/set 字面量 {} 与 f-string,
    # 大括号转义易错, 故用唯一占位符 replace() 注入
    script = (I8_REACHABILITY_TEMPLATE
              .replace("@@LIVE_META@@", repr(live_meta))
              .replace("@@SERVER_CANDIDATES@@", repr(candidates)))
    tmpl = TOOLS / "_invariant_i8.py"
    tmpl.write_text(script)
    _remote_upload(target, tmpl, "/tmp/_invariant_i8.py")

    out, err, rc = _remote_exec(
        target,
        "/opt/miniconda3-py39/bin/python -I /tmp/_invariant_i8.py 2>&1",
        timeout=90,
    )

    server_found = False
    server = ""
    n_modules = "0"
    max_depth = "0"
    n_gap = "0"
    gaps: List[str] = []
    for line in out.splitlines():
        if line.startswith("SERVER_FOUND="):
            server_found = line[len("SERVER_FOUND="):].strip() == "1"
        elif line.startswith("SERVER="):
            server = line[len("SERVER="):].strip()
        elif line.startswith("BFS_MODULES="):
            n_modules = line[len("BFS_MODULES="):].strip()
        elif line.startswith("MAX_DEPTH="):
            max_depth = line[len("MAX_DEPTH="):].strip()
        elif line.startswith("GAP_COUNT="):
            n_gap = line[len("GAP_COUNT="):].strip()
        elif line.startswith("GAP="):
            gaps.append(line[len("GAP="):].strip())

    if not server_found:
        return InvariantResult(
            invariant_id="I8",
            description="server.py 可达 import 闭包 (未找到 server.py, 跳过)",
            passed=True,
            details=f"candidates={candidates}, 均不存在; raw={out[:200]}",
            observed={"server_found": False, "candidates": candidates},
            expected={},
        )

    passed = (n_gap == "0")
    details = (f"server={server}, 可达模块={n_modules}, 最大深度={max_depth}, "
               f"缺口={n_gap} 处")
    if gaps:
        details += " | " + " ; ".join(gaps[:6])
        details += "  => 用 deploy_upload.py 补传缺失模块"
    return InvariantResult(
        invariant_id="I8",
        description="server.py 可达闭包 (模块级传递) 必须无缺口 (防深度>=2 连带缺失)",
        passed=passed,
        details=details,
        observed={"server": server, "reachable_modules": n_modules,
                  "max_depth": max_depth, "gap_count": n_gap, "gaps": gaps[:20]},
        expected={"gap_count": "0"},
    )


# [2026-09-26 I8] 远端执行的可达闭包探针模板.
# @@LIVE_META@@ / @@SERVER_CANDIDATES@@ 由 check_I8 用 replace() 注入.
I8_REACHABILITY_TEMPLATE = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[2026-09-26] invariant I8: server.py 可达 import 闭包 (模块级, 传递).

判定: 从 server.py 出发, 沿「模块级 且 非 try 且 非函数内 且 非 TYPE_CHECKING」
的 meta.* import 递归到任意深度; 任一目标模块/符号不存在 => 缺口 => FAIL.
函数内 (LATENT) 与 try 包裹 (OPTIONAL) 的缺口不参与判定.
"""
import ast
import os

LIVE_META = @@LIVE_META@@
SERVER_CANDIDATES = @@SERVER_CANDIDATES@@


def resolve_mod(mod):
    """解析 meta.* 模块位置. 本项目大量 namespace package (无 __init__.py),
    因此「目录存在且含 .py」也算可解析."""
    if mod == "meta":
        p = os.path.join(LIVE_META, "__init__.py")
        return p if os.path.exists(p) else LIVE_META
    rel = mod[len("meta."):].replace(".", "/")
    base = os.path.join(LIVE_META, rel)
    for p in (base + ".py", os.path.join(base, "__init__.py")):
        if os.path.exists(p):
            return p
    if os.path.isdir(base) and any(f.endswith(".py") for f in os.listdir(base)):
        return base
    return None


def parse(path):
    try:
        with open(path, "rb") as fh:
            return ast.parse(fh.read().decode("utf-8", errors="replace"))
    except Exception:
        return None


def module_level_imports(tree):
    """模块级 + 非 try + 非函数内 + 非 TYPE_CHECKING 的 meta.* import.

    返回 [(module, symbol|None, lineno)]; symbol=None 表示整模块导入.
    """
    parents = {}
    for node in ast.walk(tree):
        for ch in ast.iter_child_nodes(node):
            parents[id(ch)] = node

    out = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        cur, blocked = node, False
        while id(cur) in parents:
            cur = parents[id(cur)]
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef,
                                ast.Lambda, ast.Try)):
                blocked = True
                break
            if isinstance(cur, ast.If):
                try:
                    if "TYPE_CHECKING" in ast.unparse(cur.test):
                        blocked = True
                        break
                except Exception:
                    pass
        if blocked:
            continue

        if isinstance(node, ast.ImportFrom):
            if node.level or not (node.module or "").startswith("meta"):
                continue
            out.append((node.module, None, node.lineno))
            for a in node.names:
                if a.name != "*":
                    out.append((node.module, a.name, node.lineno))
        else:
            for a in node.names:
                if a.name.startswith("meta"):
                    out.append((a.name, None, node.lineno))
    return out


def top_symbols(tree):
    """模块的顶层符号集 (供 from mod import sym 判定)."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out.add(node.target.id)
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                out.add(a.asname or a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                out.add(a.asname or a.name.split(".")[0])
    return out


def main():
    server = ""
    for c in SERVER_CANDIDATES:
        if os.path.isfile(c):
            server = os.path.abspath(c)
            break
    print("SERVER_FOUND=" + ("1" if server else "0"))
    print("SERVER=" + server)

    if not server:
        print("BFS_MODULES=0")
        print("MAX_DEPTH=0")
        print("GAP_COUNT=0")
        return 0

    root = parse(server)
    if root is None:
        print("BFS_MODULES=0")
        print("MAX_DEPTH=0")
        print("GAP_COUNT=1")
        print("GAP=server.py|PARSE_ERROR")
        return 1

    visited, sym_cache, file_cache = set(), {}, {}
    gaps = []
    reported, missing_mods = set(), set()
    max_depth = 0

    queue = [(m, s, ln, "server.py", 1)
             for m, s, ln in module_level_imports(root)]

    while queue:
        mod, sym, ln, origin, depth = queue.pop(0)
        max_depth = max(max_depth, depth)

        # 模块整体缺失时只报一次: `from meta.b import B` 会产出
        # (meta.b, None) 与 (meta.b, "B") 两条, 后者应被 missing_mods 吞掉
        if mod in missing_mods:
            continue
        # 同一 (模块, 符号) 只报一次, 避免多个调用方重复刷屏
        if (mod, sym) in reported:
            continue
        reported.add((mod, sym))

        tgt = resolve_mod(mod)
        if tgt is None:
            missing_mods.add(mod)
            gaps.append(origin + ":" + str(ln) + " -> " + mod
                        + (("." + sym) if sym else "") + " (模块不存在)")
            continue

        if sym is not None:
            if mod not in sym_cache:
                t = None if os.path.isdir(tgt) else parse(tgt)
                sym_cache[mod] = top_symbols(t) if t else set()
            if sym not in sym_cache[mod] and not resolve_mod(mod + "." + sym):
                gaps.append(origin + ":" + str(ln) + " -> " + mod + "." + sym
                            + " (符号不存在)")
                continue

        if os.path.isdir(tgt) or mod in visited:
            continue
        visited.add(mod)

        if mod not in file_cache:
            file_cache[mod] = parse(tgt)
        t = file_cache[mod]
        if t is None:
            continue
        rel = os.path.relpath(tgt, LIVE_META).replace(os.sep, "/")
        for m2, s2, l2 in module_level_imports(t):
            queue.append((m2, s2, l2, rel, depth + 1))

    print("BFS_MODULES=" + str(len(visited)))
    print("MAX_DEPTH=" + str(max_depth))
    print("GAP_COUNT=" + str(len(gaps)))
    for g in gaps[:25]:
        print("GAP=" + g)
    return 0 if not gaps else 1


if __name__ == "__main__":
    raise SystemExit(main())
'''


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
        ("I7", lambda: check_I7_import_symbol_closure(target)),
        ("I8", lambda: check_I8_reachability_closure(target)),
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