#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[2026-09-13] deploy_upload.py - 通用部署上传 CLI

基于 DeployTarget 抽象的部署上传工具, 替换之前的 staging 特定脚本.

用法:
  # 解析远端路径 (dry-run)
  python tools/deploy_upload.py resolve meta/api/bo_api.py --target staging

  # 上传单个文件 (自动双发)
  python tools/deploy_upload.py upload meta/api/bo_api.py --target staging

  # 批量上传 (空格分隔多个文件)
  python tools/deploy_upload.py upload meta/api/bo_api.py meta/core/models.py --target staging

  # 指定资源类型
  python tools/deploy_upload.py upload meta/schemas/foo.yaml --target staging --resource-type yaml_config

  # 跳过 md5 验证 (快速模式)
  python tools/deploy_upload.py upload meta/api/bo_api.py --target staging --skip-verify

  # 验证远端文件 (不上传)
  python tools/deploy_upload.py verify meta/api/bo_api.py --target staging

  # 健康检查 (introspect spec22 端点)
  python tools/deploy_upload.py healthcheck --target staging

设计:
  - 调用 DeployTarget (tools/lib/deploy_topology.py)
  - 自动绑定 staging_round.remote_* 远端函数
  - introspect 验证: 远端执行 `python -c "import X; print(X.__file__)"`
    确保 Python 实际加载的是我们上传的路径, 而不是绕过 symlink
    加载 v0905 旧版
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess  # [2026-09-16] 部署后 invariant 门禁调用 prod_invariant_check.py
import sys
from pathlib import Path
from typing import List

# 让 tools/ 成为 import root
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "lib"))

from lib.deploy_topology import DeployTarget, ResourceType, UploadResult, VerifyResult  # noqa: E402
from lib.path_resolvers import list_resolvers  # noqa: E402
# [P0-2 2026-09-16] 部署前通用校验 (SQL vs DB schema)
from pre_deploy_validator import validate_files as pre_validate  # noqa: E402
# [P2 2026-09-16] 部署动作审计
from audit_viewer import append_record as audit_append  # noqa: E402

# [P1 2026-09-13 二次检查] introspect 预期缺失模块 (handoff §5.1 判读规则 row1/2):
# staging 的 meta/ 是补丁子集, 顶层包提供完整 core, introspect 缺这些模块属预期
# 行为而非事故; 不计入失败, 使退出码可作 CI 门禁 (可用 --allow-missing 追加)
DEFAULT_EXPECTED_MISSING = {
    "meta.core.bo_framework",
    "meta.core.action_constants",
}


# --------------------------------------------------------------------------
# 辅助函数
# --------------------------------------------------------------------------
def _local_md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _abs_path(lp: str) -> Path:
    """相对路径归一化: 先按 CWD, 再按 repo 根 (tools/ 上一级).

    resolve_remote_paths 要求绝对路径; CLI 文档示例均用相对路径,
    因此在 CLI 层统一转换, 支持从任意目录运行.
    """
    p = Path(lp)
    if p.is_absolute():
        return p
    if p.exists():
        return p.resolve()
    return Path(__file__).resolve().parent.parent / lp


def _print_upload_results(results: List[UploadResult]) -> bool:
    """打印上传结果, 返回 True 表示全部成功."""
    ok = True
    for r in results:
        if not r.success:
            print(f"  [FAIL] {r.remote_path} err={r.error}")
            ok = False
            continue
        if r.md5_match is False:
            print(f"  [MISMATCH] {r.remote_path} (uploaded but md5 mismatch)")
            ok = False
        else:
            md5_str = " md5=match" if r.md5_match is True else ""
            print(f"  [OK{(' ' + r.method) if r.method else ''}]{md5_str} {r.remote_path}")
    return ok


def _probe_remote_file(target: DeployTarget, remote_path: str) -> dict:
    """Probe 远端文件 md5 + mtime. 白名单安全: ls + md5sum.

    Returns:
        dict with keys: exists (bool), md5 (str|None), mtime (str|None), age_days (int|None), raw (str)
        文件不存在时 exists=False, md5/mtime=None
    """
    if target.exec_fn is None:
        return {"exists": None, "md5": None, "mtime": None, "age_days": None, "raw": ""}

    # 一次 ls -la + md5sum, ls 显示 "-rwxr-xr-x 1 root root 58521 Sep 15 20:54 /path"
    # 注意: mtime 字符串格式取决于 ls --time-style, 默认 mtime 不含年份
    cmd = f'ls -la {remote_path} 2>/dev/null; md5sum {remote_path} 2>/dev/null'
    r = target.exec_fn(cmd, timeout=10)
    out = (r.get("stdout") or "") if isinstance(r, dict) else str(r)

    if not out or "No such file" in out:
        return {"exists": False, "md5": None, "mtime": None, "age_days": None, "raw": out}

    # parse md5 (md5sum 第一个 whitespace 前是 hash)
    md5 = None
    mtime_str = None
    age_days = None
    import re
    m = re.search(r'([0-9a-f]{32})\s+', out)
    if m:
        md5 = m.group(1)
    # parse ls -la 第 6/7/8 列 (mtime)
    # 形如: -rwxr-xr-x 1 root root 58521 Sep 15 20:54 /path
    # 或:   -rwxr-xr-x 1 root root 58521 Sep 15  2025 /path  (老文件带年份)
    # 或:   -rwxr-xr-x 1 root root 58521 Sep 15 20:54:00 +0800  (time-style=full-iso)
    lines = out.splitlines()
    for line in lines:
        if remote_path in line and line.startswith('-'):
            parts = line.split()
            # 找月份名 (Jan/Feb/.../Dec 缩写)
            month_idx = None
            for i, p in enumerate(parts):
                if re.match(r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$', p):
                    month_idx = i
                    break
            if month_idx is not None and month_idx + 2 < len(parts):
                # mtime 形式: "Sep 15 20:54" 或 "Sep 15  2025"
                day = parts[month_idx + 1]
                time_or_year = parts[month_idx + 2]
                if ':' in time_or_year or re.match(r'^\d{4}$', time_or_year):
                    mtime_str = f"{parts[month_idx]} {day} {time_or_year}"
            break

    # 计算 age_days (用 mtime_str 解析, 如果包含年份或 HH:MM)
    if mtime_str:
        from datetime import datetime
        try:
            if ':' in mtime_str:
                # HH:MM 形式表示当年
                # ls -la 默认不显示年份 (mtime < 6 个月时), 所以我们假设是当年
                # 但更安全: 用 date 命令获取当前时间对照
                date_cmd = 'date +"%Y"'
                dr = target.exec_fn(date_cmd, timeout=5)
                year = (dr.get("stdout") or "").strip() if isinstance(dr, dict) else ""
                if year and year.isdigit():
                    parsed = datetime.strptime(f"{year} {mtime_str}", "%Y %b %d %H:%M")
                else:
                    parsed = None
            else:
                # mtime_str 形式 "Sep 15 2025"
                parsed = datetime.strptime(f"{mtime_str}", "%b %d %Y")
            if parsed:
                now_cmd = 'date +"%s"'
                nr = target.exec_fn(now_cmd, timeout=5)
                now_ts = int((nr.get("stdout") or "0").strip()) if isinstance(nr, dict) else 0
                if now_ts:
                    age_seconds = now_ts - int(parsed.timestamp())
                    age_days = age_seconds // 86400
        except Exception:
            pass

    return {"exists": True, "md5": md5, "mtime": mtime_str, "age_days": age_days, "raw": out}


# [P0-2 2026-09-16] Pre-deploy validator wrapper
def _pre_deploy_check(target: DeployTarget, local_path: Path, db_path: str = None,
                      force: bool = False) -> tuple:
    """部署前通用校验 (SQL vs DB schema drift 检测).

    Returns:
        (allow: bool, message: str)
    """
    if not db_path:
        return True, ""  # 未提供 DB, 跳过 (不强制)

    if not Path(db_path).exists():
        return True, f"[WARN] db_path 不存在: {db_path}, 跳过 validator"

    try:
        report = pre_validate(files=[local_path], db_path=Path(db_path))
    except Exception as e:
        return True, f"[WARN] validator 调用失败: {e}, 跳过"

    if report['ok']:
        return True, f"[OK] pre-deploy validator: 无 drift ({report['total_issues']} issues)"

    # 有 drift
    msg_parts = [
        f"[DRIFT] {report['error_issues']} 个 SQL vs DB schema 不兼容:",
    ]
    for r in report['results']:
        for iss in r.get('issues', [])[:10]:
            msg_parts.append(
                f"  - {iss.get('file', '?')}:{iss.get('line', 0)} "
                f"table={iss.get('table')}, column={iss.get('column')}: {iss.get('reason')}"
            )
        if len(r.get('issues', [])) > 10:
            msg_parts.append(f"  ... and {len(r['issues']) - 10} more")
    msg_parts.append("")
    msg_parts.append("可能原因:")
    msg_parts.append("  1. 代码里 SQL 引用了已重命名 / 删除的列")
    msg_parts.append("  2. DB 已迁移但代码未同步")
    msg_parts.append("  3. 部署目录的代码与 DB schema 状态不一致 (本次根因!)")
    msg_parts.append("")
    msg_parts.append("如果确认本次就是要带漂移部署, 加 --force-drift-acknowledge 继续.")
    msg_parts.append("不推荐: drift 会导致线上 server 启动失败 (no such column).")
    full_msg = "\n".join(msg_parts)

    if force:
        return True, full_msg + "\n[FORCE-DRIFT-ACK] 已强制放行"

    return False, full_msg


def _stale_check(target: DeployTarget, local_path: Path, remote_paths: list,
                 stale_days: int = 7, force: bool = False) -> tuple:
    """[1.1 2026-09-15] Pre-upload stale check.

    教训: 之前 R018 prod 部署被漏做, 1dba6c1 v3.61 单发指令时才发现 prod 远端 mtime
    是 9-04 (vs staging 9-15). 这层检查应在每次 prod upload 前自动触发, 拦截"漏做
    / 延迟部署" 类问题.

    逻辑:
      - staging (快迭代): 不检查, 频繁改动是常态
      - prod (慢运维): 拉每个远端文件 mtime + md5, 跟本地比对:
        * md5 一致 -> 跳过 (无变化)
        * md5 不一致 + mtime 距今 <= 7 天 -> 正常, 通过
        * md5 不一致 + mtime 距今 > 7 天 -> [WARN-STALE] 警告 + 强制二次确认
          (除非 --force-allow-stale 显式逃生)

    Returns:
        (allow: bool, message: str)
    """
    # staging 不限制
    if target.name != 'production':
        return True, ""

    local_md5 = _local_md5(local_path)
    stale_hits = []

    for rp in remote_paths:
        probe = _probe_remote_file(target, rp)
        if not probe["exists"]:
            continue  # 新文件, 正常
        if probe["md5"] == local_md5:
            continue  # 已一致, 跳过
        # md5 不一致: 看 mtime 是否 stale
        age = probe["age_days"]
        if age is None:
            # 解析 mtime 失败, 默认按"老文件"处理, 让用户二次确认
            stale_hits.append((rp, probe["mtime"], "未知"))
            continue
        # age >= stale_days: 当前 stale_days=7 表示 7 天前, 用 >=
        # (避免 age=0 stale_days=0 这种边界 bug)
        if age >= stale_days:
            stale_hits.append((rp, probe["mtime"], age))

    if not stale_hits:
        return True, ""

    # 有 stale 文件
    msg_parts = [f"[WARN-STALE] {len(stale_hits)} 个 prod 远端文件 mtime >= {stale_days} 天但 md5 与本地不一致:"]
    for rp, mtime_str, age in stale_hits:
        msg_parts.append(f"  - {rp} (mtime={mtime_str}, age={age}d)")
    msg_parts.append("")
    msg_parts.append("可能原因:")
    msg_parts.append("  1. prod 漏做之前的 staging 验收通过 patch")
    msg_parts.append("  2. prod 部署后被 rollback / revert")
    msg_parts.append("  3. prod 跑的是更老的 HEAD, 本次上传会把 prod 拉到本地版本")
    msg_parts.append("")
    msg_parts.append("如果确认本次就是要追平 staging -> prod (例如 R018/v3.61 整批补), 加 --force-allow-stale 继续.")
    msg_parts.append("如果不确定, 请先 git log --oneline staging-vs-prod 对照 + 询问 PM.")
    full_msg = "\n".join(msg_parts)

    if force:
        return True, full_msg + "\n[FORCE-ALLOW-STALE] 已强制放行"

    return False, full_msg


def _print_verify_results(results: List[VerifyResult]) -> bool:
    ok = True
    for r in results:
        if r.success:
            print(f"  [OK] {r.remote_path}")
        else:
            print(f"  [FAIL] {r.remote_path} {r.details}")
            ok = False
    return ok


# --------------------------------------------------------------------------
# 子命令实现
# --------------------------------------------------------------------------
def cmd_resolve(args, target: DeployTarget) -> int:
    paths = target.resolve_remote_paths(
        _abs_path(args.local_path),
        resource_type=ResourceType(args.resource_type) if args.resource_type else None,
    )
    print(f"[{target.name}] {args.local_path} -> {len(paths)} 路径:")
    for p in paths:
        print(f"  {p}")
    return 0


def cmd_upload(args, target: DeployTarget) -> int:
    rt = ResourceType(args.resource_type) if args.resource_type else None
    any_fail = False
    import time as _time
    for lp in args.local_path:
        local = _abs_path(lp)
        if not local.exists():
            print(f"  [SKIP] {lp} (本地文件不存在)")
            any_fail = True
            continue
        print(f"[{target.name}] uploading {local}")
        _t0 = _time.time()
        _drift_count = 0
        _ok = True
        _error = ""
        # [P0-2 2026-09-16] Pre-deploy validator (SQL vs DB schema drift)
        # 在 dry_run 之前也跑: 早发现问题, 即使 dry_run 也报 [ABORT]
        if not args.skip_pre_validate:
            allow, msg = _pre_deploy_check(
                target, local,
                db_path=args.pre_validate_db,
                force=args.force_drift_acknowledge,
            )
            if msg:
                # 提取 drift 数量 (msg 第一行 [DRIFT] N 个)
                import re as _re
                m = _re.search(r"\[DRIFT\] (\d+)", msg)
                if m:
                    _drift_count = int(m.group(1))
                print(msg)
            if not allow:
                print(f"\n[ABORT] pre-deploy validator 失败, 不上传. "
                      f"重跑加 --force-drift-acknowledge 强制放行 (不推荐).")
                _ok = False
                _error = "pre-deploy validator failed"
                # [P2] 审计: 失败记录
                audit_append(
                    audit_file=Path(__file__).parent.parent / ".staging_deploy_audit.jsonl",
                    action="upload",
                    target=target.name,
                    files=[str(local)],
                    ok=False,
                    duration_sec=_time.time() - _t0,
                    actor="deploy-upload",
                    drift_count=_drift_count,
                    error=_error,
                    note="abort by pre-deploy validator",
                )
                any_fail = True
                continue
        if args.dry_run:
            paths = target.resolve_remote_paths(local, resource_type=rt)
            print(f"  [DRY-RUN] -> {len(paths)} 路径:")
            for p in paths:
                print(f"    {p}")
            # [P2] 审计: dry-run 也记录
            audit_append(
                audit_file=Path(__file__).parent.parent / ".staging_deploy_audit.jsonl",
                action="upload-dry-run",
                target=target.name,
                files=[str(local)],
                ok=True,
                duration_sec=_time.time() - _t0,
                actor="deploy-upload",
                drift_count=_drift_count,
                note=f"dry-run, would upload to {len(paths)} paths",
            )
            continue
        # [1.1 2026-09-15] Pre-upload stale check (prod 拦截漏做/延迟部署)
        _stale_count = 0
        if not args.skip_stale_check:
            remote_paths = target.resolve_remote_paths(local, resource_type=rt)
            allow, msg = _stale_check(target, local, remote_paths,
                                      stale_days=args.stale_days,
                                      force=args.force_allow_stale)
            if msg:
                import re as _re
                m = _re.search(r"\[WARN-STALE\] (\d+)", msg)
                if m:
                    _stale_count = int(m.group(1))
                print(msg)
            if not allow:
                print(f"\n[ABORT] stale check 失败, 不上传. 重跑加 --force-allow-stale 强制放行 (不推荐).")
                _ok = False
                _error = "stale check failed"
                audit_append(
                    audit_file=Path(__file__).parent.parent / ".staging_deploy_audit.jsonl",
                    action="upload",
                    target=target.name,
                    files=[str(local)],
                    ok=False,
                    duration_sec=_time.time() - _t0,
                    actor="deploy-upload",
                    drift_count=_drift_count,
                    stale_count=_stale_count,
                    error=_error,
                    note="abort by stale check",
                )
                any_fail = True
                continue
        results = target.upload(local, resource_type=rt, skip_verify=args.skip_verify)
        upload_ok = _print_upload_results(results)
        if not upload_ok:
            _ok = False
            _error = "upload result mismatch/fail"
            any_fail = True
        # [P2] 审计: 成功记录
        audit_append(
            audit_file=Path(__file__).parent.parent / ".staging_deploy_audit.jsonl",
            action="upload",
            target=target.name,
            files=[str(local)],
            ok=_ok,
            duration_sec=_time.time() - _t0,
            actor="deploy-upload",
            drift_count=_drift_count,
            stale_count=_stale_count,
            error=_error,
            note="force-drift-ack" if args.force_drift_acknowledge and _drift_count else "",
        )
    return 1 if any_fail else 0


def cmd_verify(args, target: DeployTarget) -> int:
    any_fail = False
    for lp in args.local_path:
        local = _abs_path(lp)
        if not local.exists():
            print(f"  [SKIP] {lp} (本地文件不存在)")
            any_fail = True
            continue
        print(f"[{target.name}] verifying {local}")
        results = target.verify(local, remote_paths=args.remote)
        if not _print_verify_results(results):
            any_fail = True
    return 1 if any_fail else 0


def cmd_healthcheck(args, target: DeployTarget) -> int:
    """健康检查: 调用 health_check 端点 + introspect Python 模块实际加载路径.

    introspect 逻辑:
      1. 解析 health_check.spec22_endpoints 对应的 Python 模块名
         (从 endpoint 路径推断, 如 /api/v2/bo/user/state-transition-actions
          -> meta.api.v2_bo.bo_user + 关注路由定义在 meta.api.v2_bo.bo_user)
      2. 远端执行 `python -c "import X; print(X.__file__)"`
      3. 比对实际加载路径 vs 我们刚才上传的路径
         - 如果加载的是 v0905 旧路径, 说明 namespace package 解析绕过了 symlink
         - 这种情况需要再次双发 (top-level)
    """
    if target.host is None:
        print(f"[{target.name}] 本地模式, 跳过远端健康检查")
        return 0
    if target.exec_fn is None:
        print(f"[{target.name}] no exec_fn bound, 跳过 introspect")
        return 1

    # 1) HTTP 健康检查
    import json
    base_url = None
    try:
        from lib.deploy_topology import DeployTarget as _DT  # noqa
        # 拿 health_check 配置 (从原始 yaml)
        import yaml  # type: ignore
        cfg_path = Path(__file__).parent / "config" / "deploy_topology.yaml"
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        base_url = cfg.get(target.name, {}).get("health_check", {}).get("base_url")
        endpoints = cfg.get(target.name, {}).get("health_check", {}).get("spec22_endpoints", [])
    except Exception as e:
        print(f"  [WARN] 读 health_check 配置失败: {e}")
        endpoints = []

    print(f"[{target.name}] HTTP health check (base={base_url}):")
    http_ok = True
    for ep in endpoints:
        # 不依赖 requests, 用 urllib
        try:
            import urllib.request, urllib.error
            full_url = f"{base_url}{ep}" if base_url else ep
            with urllib.request.urlopen(full_url, timeout=10) as r:
                code = r.getcode()
                body = r.read().decode("utf-8", errors="replace")[:200]
                status = "OK" if 200 <= code < 300 else "FAIL"
                print(f"  [{status}] {code} {ep}")
                if status == "FAIL":
                    http_ok = False
        except urllib.error.HTTPError as e:
            # 401 = endpoint 注册 OK, 但需鉴权 (符合预期, 后端在线)
            # 404 = 路由不存在 (spec 22 路由未生效, 上传失败的信号)
            # 5xx = 后端异常
            code = e.code
            if code in (401, 403):
                print(f"  [OK-REGISTERED] {code} {ep} (endpoint 已注册, 需要鉴权)")
            elif code == 404:
                print(f"  [FAIL-404] {code} {ep} (路由不存在!)")
                http_ok = False
            else:
                print(f"  [FAIL] {code} {ep}")
                http_ok = False
        except Exception as e:
            print(f"  [FAIL] {ep} err={e}")
            http_ok = False

    # 2) Python introspect (核心: 检测模块实际加载路径)
    if args.introspect:
        print(f"\n[{target.name}] Python introspect (检测模块实际加载路径):")
        # 自动用 backend 的 python 解释器
        python_bin = args.python or "/opt/miniconda3-py39/bin/python"
        modules = args.module or []
        # [P1] 预期缺失白名单: 缺失模块 ⊆ 白名单 -> [EXPECTED] 不计失败
        allow_missing = set(DEFAULT_EXPECTED_MISSING) | set(args.allow_missing or [])
        import re as _re
        introspect_ok = True
        for m in modules:
            # 用 cd 到 deploy_root 再 import, 模拟 backend cwd
            # 用 bash -c 包裹, 避免 shell 引号嵌套
            inner = f"import {m} as x; print(x.__file__)"
            # 双重转义: outer " 包含 inner " 通过 \\"
            cmd = (
                f'bash -c "cd {target.deploy_root} && '
                f'{python_bin} -c \\"{inner}\\""'
            )
            r = target.exec_fn(cmd, timeout=30)
            out = (r.get("stdout") or "").strip() if isinstance(r, dict) else str(r)
            err = (r.get("stderr") or "").strip() if isinstance(r, dict) else ""
            if err and ("ModuleNotFoundError" in err or "ImportError" in err):
                err_short = err.splitlines()[-1] if err else ""
                missing = set(_re.findall(r"No module named '([^']+)'", err))
                if missing and missing <= allow_missing:
                    print(f"  [EXPECTED] {m}: 预期缺失 {sorted(missing)}"
                          f" (meta/ 为补丁子集, 以端到端 V1.5 为准)")
                    continue
                print(f"  [FAIL] {m}: {err_short}")
                introspect_ok = False
                continue
            if not out:
                print(f"  [FAIL] {m}: 无 stdout 输出 (exit={r.get('exit_code')})")
                introspect_ok = False
                continue
            # 路径分析: 是否在 deploy 目录下?
            # [P2 2026-09-13 二次检查] deploy_root 是 symlink, __file__ 可能解析
            # 为快照实路径 (v<ts>_xxx), 判定放宽到 deploy_root 的父目录整体.
            # 注意: 纯字符串处理, 禁用 Path (Windows 下 PosixPath 会渲染反斜杠)
            deploy_dir = target.deploy_root.rstrip('/').rsplit('/', 1)[0] if target.deploy_root else ""
            in_deploy = bool(target.deploy_root) and (
                target.deploy_root in out or (deploy_dir and deploy_dir in out)
            )
            marker = " [in deploy dir]" if in_deploy else " [WARN] OUTSIDE deploy"
            print(f"  {m} -> {out}{marker}")
            if not in_deploy:
                introspect_ok = False
        if not introspect_ok:
            print(f"\n  [WARN] 部分模块加载异常! 可能未上传, 或 backend cwd 不在 deploy 目录")
            return 1

    return 0 if http_ok else 1


def cmd_sync(args, target: DeployTarget) -> int:
    """[2026-09-16] 同步整个 meta/ 目录到目标 (替代 staging_full_sync.py).

    解决 staging "补丁子集" 长期积压问题: meta/core 只有 5/186 文件,
    server 重启因 ModuleNotFoundError 失败. 治本: 全量同步 meta/.

    流程:
      1. 本地 meta/ 统计
      2. 远端 meta/ 统计 (diff 提示)
      3. 打包 zip (排除 __pycache__/.db/.bak/.log/.jsonl/.sqlite/.pdf/.png/.jpg/.xlsx
                  + db_monitor_logs/database/docs + architecture.bak.* 前缀)
      4. upload zip + 远端备份旧 meta + unzip + 清 pycache
      5. 重启 server.py (nohup + 日志到 logs/server_post_sync.log)
      6. introspect /meta 验证 action_meta 含 >= 5 个 object-scope

    dry-run: 1+2 步后退出, 不传文件
    --no-restart: 1-4 步后退出, 不重启 (用于先看看效果)
    """
    import tempfile
    import urllib.request
    import urllib.error
    import json as _json
    import zipfile as _zipfile

    if target.host is None:
        print(f"[{target.name}] 本地模式, 无 host, 无法 sync")
        return 1
    if target.exec_fn is None or target.upload_fn is None:
        print(f"[{target.name}] no exec_fn/upload_fn bound, 无法 sync")
        return 1

    repo = Path(__file__).parent.parent  # tools/ 的上一级 = repo root
    meta_local = repo / "meta"

    if args.dry_run_sync:
        print(f"[DRY-RUN] 不会真传文件")
        print(f"[DRY-RUN] 本地 meta 路径: {meta_local}")

    # 1/6 本地统计
    print(f"=== 1/6 本地 meta 统计 ===")
    n_local = len([f for f in meta_local.rglob("*.py") if "__pycache__" not in str(f)])
    print(f"  本地 meta/*.py: {n_local} 个")

    # 2/6 远端统计
    print(f"\n=== 2/6 远端 {target.name} meta 统计 ===")
    cmd = (
        f'bash -c "find {target.deploy_root}/meta -name \\"*.py\\" '
        f'-not -path \\"*__pycache__*\\" 2>/dev/null | wc -l"'
    )
    r = target.exec_fn(cmd, timeout=10)
    n_remote_str = (r.get("stdout") or "0").strip().splitlines()[-1] if isinstance(r, dict) else "0"
    try:
        n_remote = int(n_remote_str)
    except ValueError:
        n_remote = 0
    print(f"  远端 meta/*.py: {n_remote} 个")
    print(f"  差: {n_local - n_remote} 个文件 远端缺")

    if args.dry_run_sync:
        print(f"\n[DRY-RUN] 退出, 不真传")
        return 0

    # 3/6 打包 zip
    print(f"\n=== 3/6 打包 meta/ 到 zip ===")
    zip_local = Path(tempfile.gettempdir()) / "meta_fullsync.zip"
    SKIP_SUFFIX = {
        ".pyc", ".db", ".bak", ".backup", ".log", ".jsonl",
        ".sqlite", ".sqlite3", ".pdf", ".png", ".jpg", ".xlsx",
    }
    SKIP_DIRS = {"__pycache__", ".git", "node_modules",
                 "db_monitor_logs", "database", "docs"}
    SKIP_NAMES = {"architecture.db", "architecture.db.bak_fullsync_meta"}
    SKIP_PREFIXES = ("architecture.bak.", "architecture.db.",
                     "architecture.db.bak")
    n_included = 0
    n_skipped = 0
    with _zipfile.ZipFile(zip_local, "w", _zipfile.ZIP_DEFLATED) as zf:
        for f in meta_local.rglob("*"):
            if f.is_dir():
                continue
            rel_parts = f.relative_to(meta_local).parts
            if any(part in SKIP_DIRS for part in rel_parts):
                n_skipped += 1
                continue
            if f.suffix in SKIP_SUFFIX:
                n_skipped += 1
                continue
            if f.name in SKIP_NAMES or any(f.name.startswith(p) for p in SKIP_PREFIXES):
                n_skipped += 1
                continue
            if "/bak/" in str(f) or str(f).endswith("/bak"):
                n_skipped += 1
                continue
            arcname = f.relative_to(meta_local.parent).as_posix()  # meta/...
            zf.write(f, arcname)
            n_included += 1
    zip_size = zip_local.stat().st_size / 1024 / 1024
    print(f"  zip: {zip_local} ({zip_size:.1f} MB)")
    print(f"  included: {n_included}, skipped: {n_skipped}")

    # 4/6 upload + 远端 unzip
    print(f"\n=== 4/6 upload + unzip 到 {target.name} ===")
    zip_remote = "/tmp/meta_fullsync.zip"
    up = target.upload_fn(zip_local, zip_remote, timeout=600)
    if isinstance(up, dict) and up.get("error"):
        print(f"  [FAIL] upload: {up}")
        return 1
    print(f"  uploaded ({up.get('local_md5', '')[:8]})")

    cmd = (
        f"bash -c \""
        f"mv {target.deploy_root}/meta {target.deploy_root}/meta.bak_fullsync_$(date +%Y%m%d_%H%M%S); "
        f"cd {target.deploy_root} && unzip -q -o {zip_remote}; "
        f"find {target.deploy_root}/meta -name '*.py' -not -path '*__pycache__*' | wc -l"
        f"\""
    )
    r = target.exec_fn(cmd, timeout=120)
    n_after_str = (r.get("stdout") or "0").strip().splitlines()[-1] if isinstance(r, dict) else "0"
    try:
        n_after = int(n_after_str)
    except ValueError:
        n_after = 0
    print(f"  远端 meta/*.py 同步后: {n_after} 个")
    if isinstance(r, dict) and r.get("stderr"):
        print(f"  stderr: {r.get('stderr', '')[:200]}")

    if args.no_restart:
        print(f"\n--no-restart 跳过 server 重启")
        return 0

    # 5/6 重启 server
    print(f"\n=== 5/6 重启 server ===")
    # 端口用 health_check.base_url 推断: http://host:port -> port
    try:
        import yaml as _yaml  # type: ignore
        cfg_path = Path(__file__).parent / "config" / "deploy_topology.yaml"
        cfg = _yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        base_url = cfg.get(target.name, {}).get("health_check", {}).get("base_url", "")
    except Exception as e:
        print(f"  [WARN] 读 health_check 配置失败: {e}, 用默认 13011")
        base_url = ""
    port = "13011"  # 默认 staging
    if ":" in base_url.split("/")[-1] if base_url else "":
        # 形如 http://x:5001
        tail = base_url.rsplit(":", 1)[-1].rstrip("/")
        if tail.isdigit():
            port = tail
    elif base_url:
        # 尝试 rfind ':'
        idx = base_url.rfind(":")
        if idx > 0:
            tail = base_url[idx+1:].rstrip("/")
            if tail.isdigit():
                port = tail

    cmd = (
        'bash -c "'
        f'pkill -f \\"python.*server.py\\"; sleep 3; '
        f'cd {target.deploy_root}; '
        f'rm -rf meta/core/__pycache__ meta/api/__pycache__; '
        f'nohup /opt/miniconda3-py39/bin/python server.py '
        f'> {target.deploy_root}/../logs/server_post_sync.log 2>&1 & '
        f'echo started_pid=$!; '
        f'sleep 8; '
        f'ps aux | grep server.py | grep -v grep; '
        f'ss -tlnp 2>/dev/null | grep :{port} || echo NO_LISTENER'
        '"'
    )
    r = target.exec_fn(cmd, timeout=30)
    if isinstance(r, dict):
        print(f"  {r.get('stdout', '').strip()}")
        if r.get("stderr"):
            print(f"  stderr: {r.get('stderr', '')[:200]}")

    # 6/6 验证 /meta
    print(f"\n=== 6/6 验证 /meta ===")
    introspect_ep = "/api/v2/bo/permission_dimension/meta"
    introspect_url = f"http://127.0.0.1:{port}{introspect_ep}"
    try:
        req = urllib.request.urlopen(introspect_url, timeout=10)
        body = req.read().decode("utf-8", errors="replace")
        data = _json.loads(body)
        am = data.get("data", {}).get("action_meta", {})
        n_obj = sum(1 for v in am.values() if v.get("instance_scope") == "object")
        n_inst = sum(1 for v in am.values() if v.get("instance_scope") == "instance")
        print(f"  /meta 成功: action_meta 共 {len(am)} 个动作")
        print(f"    object-scope: {n_obj} 个 (期望 >= 5)")
        print(f"    instance-scope: {n_inst} 个")
        for k, v in am.items():
            if v.get("instance_scope") == "object":
                print(f"      [OBJ] {k}")
        return 0 if n_obj >= 5 else 1
    except urllib.error.HTTPError as e:
        print(f"  [FAIL-HTTP] {e.code} {introspect_url}")
        return 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        return 1


def cmd_list_resolvers(args) -> int:
    print("Available resolvers:")
    for n in list_resolvers():
        print(f"  {n}")
    return 0


# --------------------------------------------------------------------------
# CLI 主入口
# --------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(
        description="通用部署上传 CLI (基于 DeployTarget 抽象)"
    )
    p.add_argument("--target", "-t", default="staging",
                   help="部署目标 (staging/production/dev/preview)")
    p.add_argument("--dry-run", action="store_true",
                   help="只解析路径, 不实际上传")

    sub = p.add_subparsers(dest="cmd", required=True)

    # resolve
    sp = sub.add_parser("resolve", help="解析远端路径")
    sp.add_argument("local_path")
    sp.add_argument("--resource-type", "-r", default=None)

    # upload
    sp = sub.add_parser("upload", help="上传本地文件到所有解析的远端路径")
    sp.add_argument("local_path", nargs="+", help="本地文件 (可多个)")
    sp.add_argument("--resource-type", "-r", default=None)
    sp.add_argument("--skip-verify", action="store_true")
    # [P0-2 2026-09-16] pre-deploy validator (SQL vs DB schema drift)
    sp.add_argument("--skip-pre-validate", action="store_true",
                    help="跳过 pre-deploy validator (默认开启, 未提供 --pre-validate-db 时自动跳过)")
    sp.add_argument("--pre-validate-db", default=None,
                    help="DB schema 路径 (默认 None=跳过; 建议传 .sqlite 或 staging 拉回的 schema dump)")
    sp.add_argument("--force-drift-acknowledge", action="store_true",
                    help="强制放行 drift 警告 (必须显式声明, 推荐先 git log 对照)")
    # [1.1 2026-09-15] prod stale check: 拦截"漏做/延迟部署" 类问题
    sp.add_argument("--skip-stale-check", action="store_true",
                    help="跳过 prod 远端 mtime 落差检查 (默认开启, 仅 staging 自动跳过)")
    sp.add_argument("--stale-days", type=int, default=7,
                    help="prod 远端 mtime 距今超过 N 天视为 stale (默认 7)")
    sp.add_argument("--force-allow-stale", action="store_true",
                    help="强制放行 stale 警告 (必须显式声明, 推荐先 git log 对照)")

    # verify
    sp = sub.add_parser("verify", help="校验本地 vs 远端 md5")
    sp.add_argument("local_path", nargs="+")
    sp.add_argument("--remote", action="append", default=None,
                     help="指定要校验的远端路径 (可多次); 默认自动 resolve")

    # healthcheck
    sp = sub.add_parser("healthcheck", help="HTTP 健康检查 + Python introspect")
    sp.add_argument("--introspect", action="store_true",
                     help="额外 introspect Python 模块加载路径")
    sp.add_argument("--module", action="append", default=None,
                     help="introspect 的模块名 (可多次), 例: meta.api.v2_bo.bo_user")
    sp.add_argument("--python", default=None,
                    help="远端 python 解释器路径 (默认 /opt/miniconda3-py39/bin/python)")
    sp.add_argument("--allow-missing", action="append", default=None,
                    help="额外的预期缺失模块 (可多次); 默认含 meta 补丁子集已知缺失"
                         " (meta.core.bo_framework / meta.core.action_constants)")

    # resolvers
    sp = sub.add_parser("list-resolvers", help="列出所有可用 resolver")

    # [2026-09-16] sync - 同步整个 meta/ 目录 (替代 staging_full_sync.py)
    sp = sub.add_parser("sync", help="全量同步 meta/ 目录 + 重启 server + introspect 验证")
    sp.add_argument("--dry-run-sync", action="store_true",
                    help="只统计本地/远端 diff, 不传文件 (注意用 --dry-run-sync 避免与顶级 --dry-run 冲突)")
    sp.add_argument("--no-restart", action="store_true",
                    help="同步后不重启 server")

    args = p.parse_args()

    if args.cmd == "list-resolvers":
        return cmd_list_resolvers(args)

    target = DeployTarget.from_name(args.target)

    # [GUARD 2026-09-14] prod 写操作（upload/verify）需用户显式批准
    # 触发原因: r013 开发智能体越权将"代码优化"扩成"双环境部署"，无任何确认。
    # 缓解: staging 不限制 (快迭代, 部署智能体仍可自主作业);
    #       prod 写操作必须 shell 设 APPROVED_DEPLOY=1 后才能跑。
    # 走读/只读 (resolve/healthcheck) 不限制。
    if args.target in ("production", "prod") and args.cmd in ("upload", "verify", "sync"):
        if os.environ.get("APPROVED_DEPLOY") != "1":
            sys.stderr.write(
                f"[GUARD] prod {args.cmd} 被门禁拦截: 需用户显式批准。\n"
                f"       请在终端执行: export APPROVED_DEPLOY=1\n"
                f"       再重跑: deploy_upload.py {args.cmd} ... --target {args.target}\n"
                f"       提示: staging 不受此门禁, 部署智能体仍可自主作业。\n"
            )
            return 2

    if args.cmd == "resolve":
        return cmd_resolve(args, target)
    if args.cmd == "upload":
        rc = cmd_upload(args, target)
        # [2026-09-16] upload 后强制跑 invariant check (治 9-16 全实例级家族复发)
        # 上传代码变更后, 必须验证 server 实际 import 的路径是新代码
        # 而不是绕过 symlink 加载 v0905 老版本
        if rc == 0 and not os.environ.get("SKIP_INVARIANT_CHECK"):
            rc = _run_invariant_check(args.target)
        return rc
    if args.cmd == "verify":
        rc = cmd_verify(args, target)
        if rc == 0 and not os.environ.get("SKIP_INVARIANT_CHECK"):
            rc = _run_invariant_check(args.target)
        return rc
    if args.cmd == "healthcheck":
        rc = cmd_healthcheck(args, target)
        if rc == 0 and not os.environ.get("SKIP_INVARIANT_CHECK"):
            rc = _run_invariant_check(args.target)
        return rc
    if args.cmd == "sync":
        # sync 涉及上传 + 重启, 部署强度最高, 必须走 invariant 门禁
        # (即使 rc != 0 也要跑: 因为重启失败更要验证是不是 invariant 被破坏)
        rc = cmd_sync(args, target)
        if not os.environ.get("SKIP_INVARIANT_CHECK"):
            rc_invariant = _run_invariant_check(args.target)
            if rc == 0:
                rc = rc_invariant
        return rc

    p.print_help()
    return 1


def _run_invariant_check(target_name: str) -> int:
    """[2026-09-16] 部署后 invariant 门禁.

    失败模式: 9-16 全实例级 bug (deploy/meta 错指 current/, loader 加载老版本).
    失败模式: 9-16 debug print 未还原就 restart (syntax error).

    治本: 每次 upload/verify/healthcheck 末尾自动跑 prod_invariant_check.py,
    任何1项 invariant 失败就 EXIT 1 (禁止宣称部署成功).

    跳过方式: export SKIP_INVARIANT_CHECK=1 (不推荐, 仅紧急逃生)
    """
    invariant_tool = Path(__file__).parent / "prod_invariant_check.py"
    if not invariant_tool.exists():
        sys.stderr.write(f"[invariant] WARN: {invariant_tool} not found, skip\n")
        return 0
    audit_log = Path(__file__).parent / ".deploy_invariant_audit.jsonl"
    cmd = [sys.executable, str(invariant_tool),
           "--target", target_name,
           "--audit-log", str(audit_log)]
    print(f"[invariant] running: {' '.join(cmd)}", flush=True)
    rc = subprocess.call(cmd, cwd=str(Path(__file__).parent.parent))
    if rc != 0:
        sys.stderr.write(
            f"\n[invariant] FAIL: rc={rc}, 部署未通过 invariant 检查, 禁止宣称部署成功\n"
            f"[invariant] 修复后重跑: python {invariant_tool} --target {target_name}\n"
            f"[invariant] 紧急逃生: export SKIP_INVARIANT_CHECK=1 (不推荐)\n"
        )
    return rc


if __name__ == "__main__":
    sys.exit(main())