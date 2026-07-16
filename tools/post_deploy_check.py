#!/usr/bin/env python3
"""
post_deploy_check.py - 部署后对账脚本 [V007.49-B 2026-07-13]

背景: deploy-v20260713_001 漏部署 BUG-V061 修复, 因为:
  1. deploy_bundle/meta/core/action_executor.py 是旧版 (md5 fc790a24)
  2. rebuild_zip.py 没检测这个 drift
  3. verify_deployment.py 只验证运行中服务, 不验证 zip 内容 vs git HEAD

功能 (3 层对账):
  L1: git HEAD MD5  vs  deploy_bundle/ MD5  (本地)
  L2: deploy_bundle/ MD5  vs  /opt/app/deploy-v*.zip MD5  (本地)
  L3: /opt/app/deploy-v*.zip MD5  vs  /opt/app/deployments/* MD5 (远程 + 进程 cwd)

每层不匹配都打印 [DRIFT] 警告, 任意 L3 不匹配返回 exit code 1.

用法:
  python tools/post_deploy_check.py [--worktree ROOT] [--deployments /opt/app/deployments]
                                     [--zip deploy-v20260713_002.zip]
                                     [--skip-l3]    # 只验证 L1+L2, 跳过远程
                                     [--json]        # JSON 输出 (给 CI 用)
"""
import os
import sys
import json
import hashlib
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

# 关键文件清单 (来自 rebuild_zip.py META_FILES_TO_SYNC + 核心前端入口)
DEFAULT_KEY_FILES = [
    "meta/core/action_executor.py",
    "meta/scripts/init_menu_permissions.py",
    "meta/server.py",
    "tools/log_service.py",
    "tools/core_service.py",
    "frontend_dist_files/index.html",
]


def md5_file(p: Path) -> str:
    if not p.exists():
        return ""
    h = hashlib.md5()
    try:
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception as e:
        return f"ERR:{e}"


def git_head_md5(repo: Path, rel_path: str) -> str:
    """读 git HEAD:<rel_path> 的 MD5"""
    try:
        r = subprocess.run(
            ["git", "-C", str(repo), "show", f"HEAD:{rel_path}"],
            capture_output=True, timeout=10
        )
        if r.returncode != 0:
            return ""
        return hashlib.md5(r.stdout).hexdigest()
    except Exception:
        return ""


def git_head_info(repo: Path) -> dict:
    """读 git HEAD 信息"""
    info = {"branch": "?", "commit": "?", "short": "?"}
    try:
        for cmd, key in [
            (["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"], "branch"),
            (["git", "-C", str(repo), "rev-parse", "HEAD"], "commit"),
            (["git", "-C", str(repo), "rev-parse", "--short", "HEAD"], "short"),
        ]:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                info[key] = r.stdout.strip()
    except Exception:
        pass
    return info


def find_running_backend_pid(remote_exec_fn=None) -> list:
    """返回 backend 进程的 PID 列表 (本地)"""
    pids = []
    try:
        if sys.platform == "win32":
            r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq python.exe"],
                               capture_output=True, text=True, timeout=5)
            # 简化: 不在 Windows 上做这个检查
            return pids
        else:
            r = subprocess.run(["pgrep", "-f", "miniconda.*server.py"],
                               capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                pids = [int(x) for x in r.stdout.strip().split() if x.strip()]
    except Exception:
        pass
    return pids


def find_remote_backend_pids(remote_exec_fn) -> list:
    """通过远程 exec 找 backend PID"""
    if not remote_exec_fn:
        return []
    try:
        _, body = remote_exec_fn("pgrep -f 'miniconda.*server.py'", timeout=10)
        import json as _json
        j = _json.loads(body)
        if j.get("exit_code") == 0:
            stdout = j.get("stdout", "").strip()
            return [int(x) for x in stdout.split() if x.strip()]
    except Exception:
        pass
    return []


def remote_exec_factory(host: str, port: int, secret: str, token: str):
    """创建远程 exec 函数 (走 log_service:9101 /api/exec)"""
    import urllib.parse, http.client, ssl

    def _exec(cmd: str, timeout: int = 30):
        params = urllib.parse.urlencode({"cmd": cmd, "timeout": str(timeout), "token": token})
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        conn = http.client.HTTPConnection(host, port, timeout=timeout + 15)
        conn.request("GET", f"/api/exec?{params}")
        resp = conn.getresponse()
        body = resp.read().decode(errors="replace")
        conn.close()
        return resp.status, body
    return _exec


def make_log_service_token(secret: str) -> str:
    import hashlib, time
    h = int(time.time()) // 3600
    return hashlib.sha256(f"{secret}:{h}".encode()).hexdigest()[:16]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--worktree", default=".", help="git worktree 根目录")
    p.add_argument("--deployments", default="/opt/app/deployments",
                   help="远程 deployments 目录 (L3 检查)")
    p.add_argument("--zip", default="",
                   help="本地 zip 路径 (L2 检查, 留空跳过)")
    p.add_argument("--skip-l3", action="store_true",
                   help="跳过 L3 (远程 deployments 对账)")
    p.add_argument("--json", action="store_true", help="JSON 输出")
    p.add_argument("--remote-host", default="172.20.59.7")
    p.add_argument("--remote-port", type=int, default=9101)
    p.add_argument("--log-secret", default="v007.35-infra",
                   help="log_service token secret (仅 L3 远程时用)")
    args = p.parse_args()

    worktree = Path(args.worktree).resolve()
    if not (worktree / ".git").exists():
        print(f"[FAIL] {worktree} 不是 git 仓库", file=sys.stderr)
        sys.exit(2)

    report = {
        "timestamp": datetime.now().isoformat(),
        "worktree": str(worktree),
        "git_head": git_head_info(worktree),
        "deployments": args.deployments,
        "zip": args.zip,
        "layers": {"L1": [], "L2": [], "L3": []},
        "summary": {"ok": 0, "drift": 0, "missing": 0},
    }

    # L1: git HEAD vs deploy_bundle/
    deploy_bundle = worktree / "deploy_bundle"
    if not deploy_bundle.exists():
        print(f"[WARN] deploy_bundle/ 不存在: {deploy_bundle}")
    for rel in DEFAULT_KEY_FILES:
        head_md5 = git_head_md5(worktree, rel)
        bundle_md5 = md5_file(deploy_bundle / rel) if deploy_bundle.exists() else ""
        same = (head_md5 == bundle_md5) if head_md5 and bundle_md5 else False
        if head_md5 and bundle_md5 and not same:
            status = "DRIFT"
            report["summary"]["drift"] += 1
        elif not head_md5:
            status = "NOT_IN_HEAD"
        elif not bundle_md5:
            status = "NOT_IN_BUNDLE"
            report["summary"]["missing"] += 1
        else:
            status = "OK"
            report["summary"]["ok"] += 1
        report["layers"]["L1"].append({
            "file": rel,
            "head_md5": head_md5[:8] if head_md5 else "",
            "bundle_md5": bundle_md5[:8] if bundle_md5 else "",
            "status": status,
        })

    # L2: deploy_bundle/ vs zip
    if args.zip:
        zip_path = Path(args.zip)
        if not zip_path.exists():
            print(f"[WARN] zip 不存在: {zip_path}")
        else:
            import zipfile
            with zipfile.ZipFile(zip_path, "r") as z:
                zip_names = z.namelist()
                for rel in DEFAULT_KEY_FILES:
                    zip_md5 = ""
                    if rel in zip_names:
                        zip_md5 = hashlib.md5(z.read(rel)).hexdigest()
                    bundle_md5 = md5_file(deploy_bundle / rel) if deploy_bundle.exists() else ""
                    same = (zip_md5 == bundle_md5) if zip_md5 and bundle_md5 else False
                    if zip_md5 and bundle_md5 and not same:
                        status = "DRIFT"
                        report["summary"]["drift"] += 1
                    elif not zip_md5:
                        status = "NOT_IN_ZIP"
                        report["summary"]["missing"] += 1
                    elif not bundle_md5:
                        status = "NOT_IN_BUNDLE"
                        report["summary"]["missing"] += 1
                    else:
                        status = "OK"
                        report["summary"]["ok"] += 1
                    report["layers"]["L2"].append({
                        "file": rel,
                        "bundle_md5": bundle_md5[:8] if bundle_md5 else "",
                        "zip_md5": zip_md5[:8] if zip_md5 else "",
                        "status": status,
                    })

    # L3: zip vs remote /opt/app/deployments/
    if not args.skip_l3:
        token = make_log_service_token(args.log_secret)
        remote_exec = remote_exec_factory(args.remote_host, args.remote_port,
                                          args.log_secret, token)
        # 1. 找远端最新 zip
        _, body = remote_exec(f"ls -1 /opt/app/deploy-v*.zip 2>/dev/null | tail -1", timeout=10)
        import json as _json
        try:
            j = _json.loads(body)
            remote_zip = j.get("stdout", "").strip() if j.get("exit_code") == 0 else ""
        except Exception:
            remote_zip = ""
        if remote_zip:
            # 2. 对比本地 zip vs 远端 zip MD5 (如果用户传了 --zip)
            if args.zip:
                local_zip_md5 = md5_file(Path(args.zip))
                # 远端读 md5
                _, body2 = remote_exec(f"md5sum {remote_zip} | awk '{{print $1}}'", timeout=15)
                try:
                    j2 = _json.loads(body2)
                    remote_zip_md5 = j2.get("stdout", "").strip() if j2.get("exit_code") == 0 else ""
                except Exception:
                    remote_zip_md5 = ""
                same = (local_zip_md5 == remote_zip_md5) if remote_zip_md5 else False
                report["layers"]["L3"].append({
                    "check": "zip_md5_local_vs_remote",
                    "local_zip": str(args.zip),
                    "remote_zip": remote_zip,
                    "local_md5": local_zip_md5[:8],
                    "remote_md5": remote_zip_md5[:8] if remote_zip_md5 else "?",
                    "status": "OK" if same else ("DRIFT" if remote_zip_md5 else "CANNOT_VERIFY"),
                })
                if remote_zip_md5 and not same:
                    report["summary"]["drift"] += 1
                elif remote_zip_md5:
                    report["summary"]["ok"] += 1
            # 3. 对比 zip 内文件 MD5 vs 远端解压后的文件 MD5
            if args.zip:
                import zipfile
                with zipfile.ZipFile(args.zip, "r") as z:
                    for rel in DEFAULT_KEY_FILES[:4]:  # 只抽样 4 个核心文件, 避免太慢
                        # 远端读 md5
                        target_path = f"{args.deployments}/{rel}"
                        _, body3 = remote_exec(f"md5sum '{target_path}' 2>/dev/null | awk '{{print $1}}'", timeout=15)
                        try:
                            j3 = _json.loads(body3)
                            remote_md5 = j3.get("stdout", "").strip() if j3.get("exit_code") == 0 else ""
                        except Exception:
                            remote_md5 = ""
                        zip_md5 = ""
                        if rel in z.namelist():
                            zip_md5 = hashlib.md5(z.read(rel)).hexdigest()
                        same = (zip_md5 == remote_md5) if zip_md5 and remote_md5 else False
                        if not remote_md5:
                            status = "MISSING_REMOTE"
                            report["summary"]["missing"] += 1
                        elif zip_md5 and not same:
                            status = "DRIFT"
                            report["summary"]["drift"] += 1
                        elif zip_md5:
                            status = "OK"
                            report["summary"]["ok"] += 1
                        else:
                            status = "NOT_IN_ZIP"
                            report["summary"]["missing"] += 1
                        report["layers"]["L3"].append({
                            "check": f"file_md5_zip_vs_remote_deployment",
                            "file": rel,
                            "zip_md5": zip_md5[:8] if zip_md5 else "",
                            "remote_md5": remote_md5[:8] if remote_md5 else "",
                            "status": status,
                        })
        else:
            report["layers"]["L3"].append({
                "check": "remote_zip_search",
                "status": "NOT_FOUND",
                "hint": f"no deploy-v*.zip in /opt/app/",
            })

    # 输出
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print("=" * 70)
        print(f"[POST-DEPLOY CHECK] {report['timestamp']}")
        print(f"  worktree: {report['worktree']}")
        print(f"  git: {report['git_head']['branch']} @ {report['git_head']['short']}")
        print(f"  zip: {args.zip or '(skip L2)'}")
        print(f"  deployments: {args.deployments} ({'skip' if args.skip_l3 else 'check'})")
        print("=" * 70)
        for layer_name, items in report["layers"].items():
            if not items:
                continue
            print(f"\n[{layer_name}] ({len(items)} 项)")
            for it in items:
                status = it["status"]
                marker = {
                    "OK": "[OK]      ",
                    "DRIFT": "[FAIL]    ",
                    "NOT_IN_HEAD": "[WARN]    ",
                    "NOT_IN_BUNDLE": "[WARN]    ",
                    "NOT_IN_ZIP": "[WARN]    ",
                    "MISSING_REMOTE": "[WARN]    ",
                    "NOT_FOUND": "[WARN]    ",
                    "CANNOT_VERIFY": "[WARN]    ",
                }.get(status, "[?]       ")
                if "file" in it:
                    print(f"  {marker} {it['file']:50s} head={it.get('head_md5','-'):8} bundle={it.get('bundle_md5','-'):8} zip={it.get('zip_md5','-'):8} remote={it.get('remote_md5','-'):8}")
                elif "check" in it:
                    print(f"  {marker} {it['check']}: {it}")
        print()
        print("=" * 70)
        s = report["summary"]
        print(f"[SUMMARY] ok={s['ok']}  drift={s['drift']}  missing={s['missing']}")
        if s["drift"] > 0:
            print("[FAIL] 有 drift, 部署未对齐 git HEAD")
            print("  修复: cd worktree && python deploy_bundle/tools/rebuild_zip.py")
        elif s["missing"] > 0:
            print("[WARN] 有文件缺失, 建议检查")
        else:
            print("[OK] 部署与 git HEAD 一致")

    # exit code
    if report["summary"]["drift"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()