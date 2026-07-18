#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Worktree 级服务管理器 - 多智能体自验证场景下的前后端服务管理

与主仓库 service_manager.py 的区别:
  - 主仓库: 硬编码端口 3005/3010, 管理 .service_status.json
  - 本脚本: 从 .coord/ports.json 读取分配的端口, 管理 .wt_service_status.json
  - 本脚本: 每个操作需要指定 worktree 名称 (owner 字段)

用法:
  python scripts/_wt_service.py start-be <wt-name>   # 启动后端
  python scripts/_wt_service.py start-fe <wt-name>   # 启动前端
  python scripts/_wt_service.py stop <wt-name>       # 停止全部服务
  python scripts/_wt_service.py status <wt-name>     # 查看单个 worktree 状态
  python scripts/_wt_service.py status-all            # 查看所有 worktree 状态
  python scripts/_wt_service.py reconcile             # 校验 ports.json vs 实际端口一致性
  python scripts/_wt_service.py watchdog [interval]   # 定时校验+自愈 (默认60s)
  python scripts/_wt_service.py force-stop-port <port># 强制停止孤儿服务

安全机制 (v3.3):
  - 启动前检查端口 owner 冲突 (防止抢其他 Agent 端口)
  - 启动后写回 ports.json runtime_status (让其他 Agent 可见)
  - reconcile: 检测孤儿服务/端口劫持/stale状态 + 自动修正
  - watchdog: 定时校验 + 自愈 (协调智能体可长期运行)
"""

import json
import msvcrt
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── 路径配置 (从 paths.json 读, fallback 硬编码) ──

PATHS_FILE = Path("D:/filework/.coord/paths.json")
DEFAULT_PATHS = {
    "worktree_base": "D:/filework/worktrees",
    "ports_registry": "D:/filework/.coord/ports.json",
    "main_repo": "D:/filework/excel-to-diagram",
}

MAIN_FRONTEND_PORT = 3005
MAIN_BACKEND_PORT = 3010


def load_paths() -> dict:
    """从 paths.json 读路径配置, fallback 到默认"""
    if PATHS_FILE.exists():
        try:
            with open(PATHS_FILE, encoding="utf-8-sig") as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_PATHS


def load_ports() -> dict:
    """读 ports.json"""
    paths = load_paths()
    p = Path(paths["ports_registry"])
    if not p.exists():
        return {"reserved": {}, "persistent": {}, "allocated": {}}
    try:
        with open(p, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {"reserved": {}, "persistent": {}, "allocated": {}}


def save_ports(ports_data: dict):
    """写回 ports.json (带文件锁 + 自动备份, 仅更新 runtime_status, 不改结构)"""
    paths = load_paths()
    p = Path(paths["ports_registry"])
    fd = None
    try:
        # 写入前自动备份 (P0-S2)
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from _config_backup import backup as _backup_config
            _backup_config(str(p))
        except Exception:
            pass  # 备份失败不阻塞写入

        # 文件锁
        lock = p.with_suffix(".lock")
        lock.parent.mkdir(parents=True, exist_ok=True)
        fd = open(lock, "w")
        deadline = time.time() + 10
        while True:
            try:
                msvcrt.locking(fd.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.time() > deadline:
                    _log("WARNING: ports.json lock timeout, writing without lock")
                    break
                time.sleep(0.1)
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(ports_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            _log(f"WARNING: failed to update ports.json: {e}")
    finally:
        if fd:
            try:
                msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            fd.close()
            try:
                lock.unlink()
            except OSError:
                pass


def find_port_owner(port: int) -> str | None:
    """检查端口在 ports.json 中属于谁 (reserved/persistent/allocated 全扫)"""
    ports = load_ports()
    for section in ("reserved", "persistent", "allocated"):
        for port_str, info in ports.get(section, {}).items():
            # 检查 key 本身是否是这个端口
            try:
                if int(port_str) == port:
                    return info.get("owner", f"{section}:unknown")
            except ValueError:
                pass
            # 检查 value 中的 backend_port / frontend_port
            for field in ("backend_port", "frontend_port"):
                if info.get(field) == port:
                    return info.get("owner", f"{section}:unknown")
    return None


# ── 端口解析 ──

def resolve_ports(wt_name: str) -> dict:
    """从 ports.json 解析 worktree 的前后端端口

    Returns:
        {"backend_port": int, "frontend_port": int, "worktree": str}
        找不到则 sys.exit(1)
    """
    ports = load_ports()
    allocated = ports.get("allocated", {})

    # 在 allocated 中找 owner 匹配的条目
    for port_str, info in allocated.items():
        if info.get("owner") != wt_name:
            continue

        be_port = info.get("backend_port")
        fe_port = info.get("frontend_port")
        wt_path = info.get("worktree", "")

        # backend_port 可能来自 key 或 value
        if be_port is None:
            try:
                be_port = int(port_str)
            except ValueError:
                print(f"[ERROR] Cannot determine backend_port for {wt_name}")
                sys.exit(1)

        be_port = int(be_port)

        # 前端端口: 优先读字段, 否则推导
        if fe_port is not None:
            fe_port = int(fe_port)
        else:
            fe_port = be_port - 4
            # 安全检查
            if fe_port <= 3000 or fe_port == MAIN_FRONTEND_PORT:
                print(f"[ERROR] Derived frontend_port={fe_port} conflicts with "
                      f"main ({MAIN_FRONTEND_PORT}) or out of range. "
                      f"Please set frontend_port explicitly in ports.json")
                sys.exit(1)

        return {
            "backend_port": be_port,
            "frontend_port": fe_port,
            "worktree": wt_path,
        }

    print(f"[ERROR] worktree '{wt_name}' not found in ports.json allocated section")
    print(f"  Available owners: {', '.join(info.get('owner', '?') for info in allocated.values())}")
    sys.exit(1)


# ── 端口检测 ──

def check_port(port: int) -> bool:
    """检查端口是否被监听"""
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            sock = socket.socket(family, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("127.0.0.1", port))
            sock.close()
            if result == 0:
                return True
        except OSError:
            pass
    return False


def check_backend_health(port: int, timeout: int = 60) -> bool:
    """等待后端健康检查返回 200"""
    import urllib.request
    import urllib.error
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            url = f"http://localhost:{port}/api/v1/health"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


# ── 状态文件读写 ──

def _status_file(wt_path: str) -> Path:
    return Path(wt_path) / ".wt_service_status.json"


def read_status(wt_path: str) -> dict:
    """读取 worktree 的服务状态文件"""
    sf = _status_file(wt_path)
    if not sf.exists():
        return {}
    try:
        with open(sf, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}


def write_status(wt_path: str, status: dict):
    """写入 worktree 的服务状态文件"""
    sf = _status_file(wt_path)
    with open(sf, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2, ensure_ascii=False)


# ── 日志辅助 ──

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(msg: str):
    print(f"[{_now_iso()}] {msg}")


def _update_ports_runtime(port: int, owner: str, state: str, pid: int = None):
    """更新 ports.json 中的运行时状态 (让其他 Agent 可见)

    在 allocated/persistent 段中找到对应端口的条目,
    更新其 runtime_status 和 runtime_pid 字段.
    """
    ports = load_ports()
    updated = False

    for section in ("allocated", "persistent"):
        for port_str, info in ports.get(section, {}).items():
            # 匹配: key 是端口 或 backend_port/frontend_port 是端口
            match = False
            try:
                if int(port_str) == port:
                    match = True
            except ValueError:
                pass
            if info.get("backend_port") == port or info.get("frontend_port") == port:
                match = True

            if match and info.get("owner") == owner:
                info["runtime_status"] = state
                if pid is not None:
                    info["runtime_pid"] = pid
                elif state == "stopped":
                    info.pop("runtime_pid", None)
                    info.pop("runtime_status", None)
                info["runtime_updated_at"] = _now_iso()
                updated = True
                break
        if updated:
            break

    if updated:
        save_ports(ports)


# ── 进程启动 (Windows DETACHED_PROCESS) ──

def _start_process(cmd: list, cwd: str, env_extra: dict) -> int:
    """启动后台进程, 返回 PID"""
    env = os.environ.copy()
    env.update(env_extra)

    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

    # 日志目录
    log_dir = Path(cwd) / "scripts" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    stdout_path = log_dir / "wt_service.out"
    stderr_path = log_dir / "wt_service.err"

    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdout=open(stdout_path, "ab"),
        stderr=open(stderr_path, "ab"),
        creationflags=creation_flags,
    )
    return proc.pid


# ── 启动命令 ──

def cmd_start_be(wt_name: str):
    """启动后端 (waitress_server.py)"""
    info = resolve_ports(wt_name)
    be_port = info["backend_port"]
    wt_path = info["worktree"]

    if not Path(wt_path).exists():
        print(f"[ERROR] worktree path does not exist: {wt_path}")
        sys.exit(1)

    # [冲突检测] 端口被其他 owner 占用
    port_owner = find_port_owner(be_port)
    if port_owner and port_owner != wt_name:
        if check_port(be_port):
            print(f"[CONFLICT] port {be_port} is owned by '{port_owner}' and already in use!")
            print(f"  You are '{wt_name}'. Cannot start backend on another owner's port.")
            print(f"  Resolve: check ports.json or ask coordinator to reallocate.")
            sys.exit(1)

    # 幂等: 端口已监听则跳过
    if check_port(be_port):
        _log(f"Backend already listening on port {be_port}, skip")
        return

    _log(f"Starting backend for {wt_name} on port {be_port} ...")

    pid = _start_process(
        cmd=["python", "-u", "waitress_server.py"],
        cwd=wt_path,
        env_extra={"AGENT_PORT": str(be_port)},
    )
    _log(f"  Backend PID={pid}, waiting for health check ...")

    # 等待健康检查
    if check_backend_health(be_port, timeout=60):
        status = read_status(wt_path)
        status["backend"] = {
            "pid": pid,
            "port": be_port,
            "started_at": _now_iso(),
            "state": "ready",
        }
        write_status(wt_path, status)
        _update_ports_runtime(be_port, wt_name, "running", pid)
        _log(f"  Backend READY on port {be_port}")
    else:
        # 即使 health check 失败也记录, 方便排查
        status = read_status(wt_path)
        status["backend"] = {
            "pid": pid,
            "port": be_port,
            "started_at": _now_iso(),
            "state": "health_check_failed",
        }
        write_status(wt_path, status)
        _update_ports_runtime(be_port, wt_name, "starting", pid)
        _log(f"  WARNING: Backend PID={pid} spawned but health check failed on port {be_port}")
        _log(f"  Check logs: {Path(wt_path) / 'scripts' / 'logs' / 'wt_service.err'}")


def cmd_start_fe(wt_name: str):
    """启动前端 (npm run dev, vite.config.js 在 worktree 根目录)"""
    info = resolve_ports(wt_name)
    fe_port = info["frontend_port"]
    be_port = info["backend_port"]
    wt_path = info["worktree"]

    if not Path(wt_path).exists():
        print(f"[ERROR] worktree path does not exist: {wt_path}")
        sys.exit(1)

    # [冲突检测] 前端端口被其他 owner 占用
    port_owner = find_port_owner(fe_port)
    if port_owner and port_owner != wt_name:
        if check_port(fe_port):
            print(f"[CONFLICT] port {fe_port} is owned by '{port_owner}' and already in use!")
            print(f"  You are '{wt_name}'. Cannot start frontend on another owner's port.")
            sys.exit(1)

    # 幂等: 端口已监听则跳过
    if check_port(fe_port):
        _log(f"Frontend already listening on port {fe_port}, skip")
        return

    _log(f"Starting frontend for {wt_name} on port {fe_port} ...")

    pid = _start_process(
        cmd=["npm", "run", "dev"],
        cwd=wt_path,
        env_extra={
            "VITE_PORT": str(fe_port),
            "BACKEND_PORT": str(be_port),
        },
    )
    _log(f"  Frontend PID={pid}, waiting for port {fe_port} ...")

    # 等待端口监听 (最多 30 秒)
    ready = False
    for _ in range(60):  # 60 * 0.5s = 30s
        time.sleep(0.5)
        if check_port(fe_port):
            ready = True
            break

    if ready:
        status = read_status(wt_path)
        status["frontend"] = {
            "pid": pid,
            "port": fe_port,
            "started_at": _now_iso(),
            "state": "ready",
        }
        write_status(wt_path, status)
        _update_ports_runtime(fe_port, wt_name, "running", pid)
        _log(f"  Frontend READY on port {fe_port}")
    else:
        status = read_status(wt_path)
        status["frontend"] = {
            "pid": pid,
            "port": fe_port,
            "started_at": _now_iso(),
            "state": "port_not_listening",
        }
        write_status(wt_path, status)
        _update_ports_runtime(fe_port, wt_name, "starting", pid)
        _log(f"  WARNING: Frontend PID={pid} spawned but port {fe_port} not listening within 30s")


# ── 停止命令 ──

def cmd_stop(wt_name: str):
    """停止 worktree 的所有服务"""
    info = resolve_ports(wt_name)
    wt_path = info["worktree"]
    status = read_status(wt_path)

    for svc in ("backend", "frontend"):
        svc_info = status.get(svc, {})
        pid = svc_info.get("pid")
        port = svc_info.get("port")

        # 优先通过端口查找并杀进程
        if port and check_port(port):
            _kill_by_port(port)
            _log(f"  {svc} stopped (port {port})")
        elif pid:
            # 端口不监听但 PID 记录存在, 尝试杀 PID
            _kill_by_pid(pid)
            _log(f"  {svc} stopped (PID {pid})")
        else:
            _log(f"  {svc} not running, skip")

        # 清理 ports.json 运行时状态
        if port:
            _update_ports_runtime(port, wt_name, "stopped")

    # 清理前端缓存 (.vite/cache) - 避免跨 worktree 冲突
    vite_cache = Path(wt_path) / "frontend" / ".vite" / "cache"
    if not vite_cache.exists():
        vite_cache = Path(wt_path) / ".vite" / "cache"
    if vite_cache.exists():
        import shutil
        shutil.rmtree(vite_cache, ignore_errors=True)
        _log(f"  Cleaned .vite/cache")

    # 清理状态文件
    write_status(wt_path, {})


def _kill_by_port(port: int):
    """通过端口查找并杀进程"""
    try:
        output = subprocess.check_output(
            ["netstat", "-ano"], text=True, timeout=10,
        )
        for line in output.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.strip().split()
                pid_str = parts[-1]
                try:
                    pid = int(pid_str)
                    if pid in (0, 4):
                        continue
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                                   capture_output=True, timeout=10)
                except (ValueError, subprocess.SubprocessError):
                    pass
    except subprocess.SubprocessError:
        pass


def _kill_by_pid(pid: int):
    """通过 PID 杀进程"""
    try:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                       capture_output=True, timeout=10)
    except subprocess.SubprocessError:
        pass


# ── 状态命令 ──

def _show_status(wt_name: str, info: dict, status: dict):
    """打印单个 worktree 的服务状态"""
    be_port = info["backend_port"]
    fe_port = info["frontend_port"]
    wt_path = info["worktree"]

    print(f"  Worktree: {wt_name}")
    print(f"  Path:     {wt_path}")
    print()

    for svc, port in [("backend", be_port), ("frontend", fe_port)]:
        listening = check_port(port)
        svc_status = status.get(svc, {})
        pid = svc_status.get("pid", "?")
        state = svc_status.get("state", "?")
        started = svc_status.get("started_at", "?")

        label = "RUNNING" if listening else "STOPPED"
        print(f"  {svc:<10s}: {label}  port={port}  PID={pid}  state={state}  since={started}")

    print()


def cmd_status(wt_name: str):
    """查看单个 worktree 状态"""
    info = resolve_ports(wt_name)
    status = read_status(info["worktree"])
    _show_status(wt_name, info, status)


def cmd_status_all():
    """查看所有 worktree 的服务状态"""
    ports = load_ports()
    allocated = ports.get("allocated", {})

    if not allocated:
        print("  No allocated worktrees found in ports.json")
        return

    print("=" * 60)
    print("  Worktree Service Status (all)")
    print("=" * 60)

    for port_str, entry in allocated.items():
        wt_name = entry.get("owner", "?")
        try:
            info = resolve_ports(wt_name)
        except SystemExit:
            # resolve_ports 找不到会 exit, 这里捕获跳过
            # 但 allocated 里的条目一定能找到, 所以不该走到这里
            continue
        status = read_status(info["worktree"])
        _show_status(wt_name, info, status)


# ── 运行时校验命令 (v3.3 安全加固) ──

def _get_listening_ports() -> dict[int, str]:
    """获取本机所有监听端口及进程信息 (Windows netstat)

    Returns: {port: "PID/process_name"} 格式
    """
    result = {}
    try:
        r = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True, encoding="utf-8", errors="replace", timeout=10,
        )
        if r.returncode != 0:
            return result
        for line in r.stdout.split("\n"):
            # TCP    0.0.0.0:3010    0.0.0.0:0    LISTENING    1234
            parts = line.split()
            if len(parts) >= 5 and parts[0] == "TCP" and parts[3] == "LISTENING":
                try:
                    local_addr = parts[1]
                    port = int(local_addr.rsplit(":", 1)[-1])
                    pid = parts[4]
                    result[port] = pid
                except (ValueError, IndexError):
                    pass
    except Exception:
        pass
    return result


def cmd_reconcile():
    """校验 ports.json 运行时状态与实际端口监听的一致性

    检测 3 类不一致:
      1. ports.json 说 running 但端口没监听 → stale runtime (需清理)
      2. 端口在监听但 ports.json 无记录 → 孤儿服务 (Agent绕过工具启动)
      3. 端口在监听但 owner 不匹配 → 端口劫持

    输出: 分类报告 + 自动修正建议
    """
    ports = load_ports()
    actual = _get_listening_ports()
    now = _now_iso()

    # 收集 ports.json 中所有端口的运行时信息
    registered_ports = {}  # port -> (section, owner, runtime_status)
    for section in ("reserved", "persistent", "allocated"):
        for port_str, info in ports.get(section, {}).items():
            owner = info.get("owner", f"{section}:unknown")
            rt = info.get("runtime_status")
            for field in ("backend_port", "frontend_port"):
                p = info.get(field)
                if p is not None:
                    registered_ports[int(p)] = (section, owner, rt)
            try:
                if int(port_str) not in registered_ports:
                    registered_ports[int(port_str)] = (section, owner, rt)
            except ValueError:
                pass

    # 分类检查
    stale_runtime = []     # ports.json说running但实际没监听
    orphan_services = []   # 端口在监听但ports.json无记录
    port_hijack = []       # 端口在监听但owner不匹配

    # 检查1: registered but not listening
    for port, (section, owner, rt) in registered_ports.items():
        if rt == "running" and port not in actual:
            stale_runtime.append((port, section, owner))

    # 检查2: listening but not registered in our project port range
    project_port_range = set()
    for port in registered_ports:
        project_port_range.add(port)
    # 也加 reserved
    for port_str in ports.get("reserved", {}):
        try:
            project_port_range.add(int(port_str))
        except ValueError:
            pass

    for port in actual:
        if port in project_port_range and port not in registered_ports:
            orphan_services.append((port, actual[port]))

    # 检查3: listening and registered but runtime_status mismatch
    for port, (section, owner, rt) in registered_ports.items():
        if port in actual and rt != "running":
            port_hijack.append((port, section, owner, actual[port]))

    # 报告
    print("=" * 70)
    print("  PORT RECONCILIATION REPORT")
    print(f"  Generated: {now}")
    print("=" * 70)
    print(f"\n  Registered ports: {len(registered_ports)}")
    print(f"  Actually listening: {len(actual)} (system-wide)")

    issues = 0

    if stale_runtime:
        issues += len(stale_runtime)
        print(f"\n  [STALE RUNTIME] {len(stale_runtime)} port(s) marked running but not listening:")
        for port, section, owner in stale_runtime:
            print(f"    - port {port}: owner={owner} section={section}")
            print(f"      FIX: _wt_service.py stop {owner}")
        # 自动修正: 清理 stale runtime_status
        fixed = 0
        for port, section, owner in stale_runtime:
            for p_str, info in ports.get(section, {}).items():
                match = False
                try:
                    match = int(p_str) == port
                except ValueError:
                    pass
                if not match:
                    for field in ("backend_port", "frontend_port"):
                        if info.get(field) == port:
                            match = True
                if match and info.get("owner") == owner and info.get("runtime_status") == "running":
                    info.pop("runtime_status", None)
                    info.pop("runtime_pid", None)
                    info.pop("runtime_updated_at", None)
                    info["runtime_corrected_at"] = now
                    fixed += 1
        if fixed:
            save_ports(ports)
            print(f"    [AUTO-FIXED] Cleaned {fixed} stale runtime entries in ports.json")

    if orphan_services:
        issues += len(orphan_services)
        print(f"\n  [ORPHAN SERVICE] {len(orphan_services)} port(s) listening but not tracked:")
        for port, pid in orphan_services:
            print(f"    - port {port}: PID={pid}")
            print(f"      WARNING: Agent may have started service directly (bypassed _wt_service.py)")
            print(f"      FIX: _wt_service.py force-stop-port {port}")

    if port_hijack:
        issues += len(port_hijack)
        print(f"\n  [PORT HIJACK] {len(port_hijack)} port(s) listening but runtime_status not 'running':")
        for port, section, owner, pid in port_hijack:
            print(f"    - port {port}: owner={owner} section={section} actual_PID={pid}")
            print(f"      Service was likely restarted externally. Updating ports.json...")
        # 自动修正: 更新 runtime_status 为 running
        fixed = 0
        for port, section, owner, pid in port_hijack:
            for p_str, info in ports.get(section, {}).items():
                match = False
                try:
                    match = int(p_str) == port
                except ValueError:
                    pass
                if not match:
                    for field in ("backend_port", "frontend_port"):
                        if info.get(field) == port:
                            match = True
                if match and info.get("owner") == owner:
                    info["runtime_status"] = "running"
                    info["runtime_pid"] = int(pid) if pid.isdigit() else pid
                    info["runtime_updated_at"] = now
                    info["runtime_source"] = "reconcile-auto"
                    fixed += 1
        if fixed:
            save_ports(ports)
            print(f"    [AUTO-FIXED] Updated {fixed} runtime entries to 'running'")

    if issues == 0:
        print(f"\n  [OK] All ports consistent. No issues found.")
    else:
        print(f"\n  Total issues: {issues} ({len(stale_runtime)} stale + "
              f"{len(orphan_services)} orphan + {len(port_hijack)} hijack)")

    return issues


def cmd_watchdog(interval: int = 60):
    """定时校验服务存活 + 自动清理 stale 运行时状态

    用法:
      _wt_service.py watchdog           # 默认 60 秒检查一次
      _wt_service.py watchdog 30        # 30 秒检查一次

    检查内容:
      1. ports.json 中 runtime_status=running 的端口是否真的在监听
      2. .wt_service_status.json 中记录的 PID 是否还活着
      3. 发现不一致自动修正
    """
    print(f"[WATCHDOG] Starting (interval={interval}s, Ctrl+C to stop)")
    cycle = 0
    try:
        while True:
            cycle += 1
            time.sleep(interval)
            print(f"\n[WATCHDOG] Cycle #{cycle} at {_now_iso()}")
            issues = cmd_reconcile()
            if issues > 0:
                print(f"[WATCHDOG] Found {issues} issues, auto-fixed where possible")
            else:
                print(f"[WATCHDOG] All clean")
    except KeyboardInterrupt:
        print(f"\n[WATCHDOG] Stopped after {cycle} cycles")


def cmd_force_stop_port(port: int):
    """强制停止指定端口上的服务 (用于清理孤儿服务)

    用法: _wt_service.py force-stop-port 3013
    """
    if not check_port(port):
        print(f"  Port {port} is not listening, nothing to stop")
        return

    # 找到占用该端口的 PID
    actual = _get_listening_ports()
    pid_str = actual.get(port)
    if not pid_str:
        print(f"  Port {port} is listening but cannot find PID via netstat")
        print(f"  Try manual: taskkill /F /PID <pid>")
        return

    pid = int(pid_str) if pid_str.isdigit() else None
    if pid is None:
        print(f"  Invalid PID: {pid_str}")
        return

    # 检查是否是已知 owner
    owner = find_port_owner(port)
    if owner:
        print(f"  WARNING: Port {port} is registered to owner '{owner}'")
        print(f"  Are you sure you want to force-stop? (use 'stop {owner}' instead)")

    # 强制杀进程
    try:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                       capture_output=True, timeout=10)
        print(f"  [DONE] Killed PID {pid} on port {port}")

        # 清理 ports.json 运行时状态
        ports = load_ports()
        for section in ("reserved", "persistent", "allocated"):
            for p_str, info in ports.get(section, {}).items():
                match = False
                try:
                    match = int(p_str) == port
                except ValueError:
                    pass
                if not match:
                    for field in ("backend_port", "frontend_port"):
                        if info.get(field) == port:
                            match = True
                if match:
                    info.pop("runtime_status", None)
                    info.pop("runtime_pid", None)
                    info.pop("runtime_updated_at", None)
        save_ports(ports)
        print(f"  [DONE] Cleaned runtime status in ports.json")
    except Exception as e:
        print(f"  [ERROR] Failed to kill PID {pid}: {e}")


def cmd_recover(wt_name: str = None):
    """异常恢复: 清理指定 worktree (或全部) 的残留状态

    用法:
      _wt_service.py recover <wt-name>   # 恢复指定 worktree
      _wt_service.py recover --all       # 恢复所有 worktree

    恢复操作:
      1. 强制停止该 wt 的所有服务 (即使状态文件丢失)
      2. 清理 ports.json 运行时状态
      3. 清理 .wt_service_status.json
      4. 清理 .vite/cache (前端缓存)
      5. 清理 __pycache__ (可选)
      6. 记录恢复事件到 events.jsonl
    """
    if wt_name == "--all":
        # 恢复所有: 扫描 ports.json 中所有 owner
        ports = load_ports()
        owners = set()
        for section in ("allocated", "persistent"):
            for _, info in ports.get(section, {}).items():
                owner = info.get("owner")
                if owner:
                    owners.add(owner)
        if not owners:
            print("  No worktrees to recover")
            return
        print(f"  Recovering {len(owners)} worktree(s): {', '.join(owners)}")
        for owner in owners:
            print(f"\n  --- Recovering {owner} ---")
            cmd_recover(owner)
        return

    if not wt_name:
        print("Usage: _wt_service.py recover <wt-name> | --all")
        return 1

    info = resolve_ports(wt_name)
    wt_path = info["worktree"]
    be_port = info["backend_port"]
    fe_port = info["frontend_port"]

    print(f"  [RECOVER] {wt_name} (wt: {wt_path})")

    # 1. 强制停止服务 (基于端口, 不依赖状态文件)
    for port_name, port in [("backend", be_port), ("frontend", fe_port)]:
        if check_port(port):
            actual = _get_listening_ports()
            pid_str = actual.get(port)
            if pid_str and pid_str.isdigit():
                try:
                    subprocess.run(["taskkill", "/F", "/PID", pid_str],
                                   capture_output=True, timeout=10)
                    print(f"    [KILLED] {port_name} port={port} PID={pid_str}")
                except Exception:
                    pass
            else:
                print(f"    [WARN] {port_name} port={port} listening but no PID found")
        else:
            print(f"    [OK] {port_name} port={port} not listening")

    # 2. 清理 ports.json 运行时状态
    ports = load_ports()
    for section in ("allocated", "persistent"):
        for p_str, p_info in ports.get(section, {}).items():
            if p_info.get("owner") == wt_name:
                p_info.pop("runtime_status", None)
                p_info.pop("runtime_pid", None)
                p_info.pop("runtime_updated_at", None)
    save_ports(ports)
    print(f"    [OK] Cleaned ports.json runtime status")

    # 3. 清理 .wt_service_status.json
    status_file = Path(wt_path) / ".wt_service_status.json"
    if status_file.exists():
        status_file.unlink()
        print(f"    [OK] Removed .wt_service_status.json")

    # 4. 清理 .vite/cache (前端缓存)
    vite_cache = Path(wt_path) / "frontend" / ".vite" / "cache"
    if not vite_cache.exists():
        vite_cache = Path(wt_path) / ".vite" / "cache"  # 可能在 wt 根目录
    if vite_cache.exists():
        import shutil
        shutil.rmtree(vite_cache, ignore_errors=True)
        print(f"    [OK] Cleaned .vite/cache")

    # 5. 记录事件
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from _events import cmd_log
        cmd_log("RECOVERED", f"worktree {wt_name} recovered (stopped services, cleaned caches)", wt_name)
    except Exception:
        pass

    print(f"  [DONE] {wt_name} recovered")


# ── 主入口 ──

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    command = sys.argv[1]

    if command in ("start-be", "start_be"):
        if len(sys.argv) < 3:
            print("Usage: _wt_service.py start-be <wt-name>")
            return 1
        cmd_start_be(sys.argv[2])
    elif command in ("start-fe", "start_fe"):
        if len(sys.argv) < 3:
            print("Usage: _wt_service.py start-fe <wt-name>")
            return 1
        cmd_start_fe(sys.argv[2])
    elif command == "stop":
        if len(sys.argv) < 3:
            print("Usage: _wt_service.py stop <wt-name>")
            return 1
        cmd_stop(sys.argv[2])
    elif command == "status":
        if len(sys.argv) < 3:
            print("Usage: _wt_service.py status <wt-name>")
            return 1
        cmd_status(sys.argv[2])
    elif command == "status-all":
        cmd_status_all()
    elif command == "reconcile":
        cmd_reconcile()
    elif command == "watchdog":
        interval = int(sys.argv[2]) if len(sys.argv) >= 3 else 60
        cmd_watchdog(interval)
    elif command == "force-stop-port":
        if len(sys.argv) < 3:
            print("Usage: _wt_service.py force-stop-port <port>")
            return 1
        cmd_force_stop_port(int(sys.argv[2]))
    elif command == "recover":
        wt_name = sys.argv[2] if len(sys.argv) >= 3 else None
        cmd_recover(wt_name)
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
