#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
统一服务管理器 - 多智能体协作场景下的前后端服务管理

设计原则:
  1. per-port 状态文件 .service_status_<port>.json 是唯一真相源（每个端口独立文件, 跨沙箱可读）
  2. 端口检测优先于 PID 检测（sandbox 权限隔离下 Get-Process 不可靠）
  3. 所有操作幂等：start 已运行=no-op, stop 已停止=no-op
  4. 管理锁防止并发管理操作（120s 超时）
  5. 无终端依赖：使用 subprocess DETACHED_PROCESS 启动，不占用终端槽位

用法:
  python scripts/service_manager.py doctor     # [P2] 会话第一步: 环境体检 (孤儿/锁/漂移/会话注册表)
  python scripts/service_manager.py doctor --fix  # 体检+修复 (清孤儿+残留锁)
  python scripts/service_manager.py status     # 查看服务状态
  python scripts/service_manager.py start      # 启动前后端（幂等, 自动清理端口孤儿）
  python scripts/service_manager.py stop       # 停止前后端
  python scripts/service_manager.py restart    # 重启前后端
  python scripts/service_manager.py start-fe   # 仅启动前端
  python scripts/service_manager.py start-be   # 仅启动后端
  python scripts/service_manager.py audit      # 全面审计: 端口/进程/孤儿/hijack

多会话并行 ([P0 2026-09-06]):
  python scripts/service_manager.py acquire-session           # 申请私有沙箱槽位 (改后端代码时)
  python scripts/service_manager.py start --slot 1            # 在沙箱槽位启动服务
  python scripts/service_manager.py release-session --slot 1  # 释放沙箱 (停服务+摘注册)
  python scripts/service_manager.py restart --force           # 跨会话保护拒绝时的强制逃生口

  规则:
    - 所有会话默认共享 slot 0 (FE=3006/BE=3011): 只"使用"不重启
    - 改后端代码需重启验证 → acquire-session 拿私有槽, 验证完 release-session
    - stop/restart 共享环境前自动检查注册表, 其他会话活跃时拒绝 (--force 覆盖)
    - start/restart 拉起的服务自动登记 .runtime/port_registry.json,
      其他会话的孤儿对账不会误杀已登记服务
"""

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATUS_FILE = PROJECT_ROOT / ".service_status.json"
LOCK_FILE = PROJECT_ROOT / ".service_manager.lock"
LOG_FILE = PROJECT_ROOT / ".service_manager.log"

# [P0 2026-09-06 多会话并行] 会话注册表 — 根治"孤儿对账互杀"。
#   实锤 (2026-09-06): 会话 A restart 时 _reconcile_orphans 把会话 B 正常拉起的后端
#   (PID 15996, 3011) 当孤儿杀掉, 因为 B 的服务不在 A 的 status 文件里。
#   方案: 所有 service_manager 实例把"自己拉起的服务"登记到共享注册表,
#   孤儿判定 = 端口被占 且 占用者不在注册表活跃会话中 → 才杀。
#   会话条目带心跳 (HEARTBEAT_TTL 过期视为死会话, 其端口回归"可清理")。
REGISTRY_DIR = PROJECT_ROOT / ".runtime"
REGISTRY_FILE = REGISTRY_DIR / "port_registry.json"
HEARTBEAT_TTL_SECONDS = 30 * 60  # 会话心跳 TTL: 30 分钟

# 会话 ID: env 可显式指定 (同一终端多次调用 service_manager 保持同身份),
# 否则用 launcher PID + 随机后缀 (每次 CLI 调用是独立进程, 但同一会话的
# start/restart/stop 连续调用间端口注册以"端口归属"为准, 会话 ID 仅用于展示)。
SESSION_ID = os.environ.get("SM_SESSION_ID") or f"sess-{os.getpid()}-{os.urandom(2).hex()}"

# 会话槽位: env SM_SLOT 或 CLI --slot N。
#   slot 0 = 共享环境 (默认): 端口 = ports.json 原值 (FE=3006/BE=3011), 路径全部保持现状。
#   slot N>0 = 私有沙箱: 端口派生 FE=base+N*20 / BE=base+N*20 (slot1 → 3026/3031)。
#   per-port 状态文件 (.service_status_<port>.json) 天然按端口隔离, 无需改造;
#   裸 STATUS/LOCK/LOG/STARTUP 文件在 slot>0 时加 slot 后缀, 避免跨槽互踩。
SESSION_SLOT = int(os.environ.get("SM_SLOT", "0") or 0)
SLOT_STRIDE = 20

# V4.0 根因修复：直接启动 python -u waitress_server.py（不再走 powershell 嵌套）
# 背景：V3 链 powershell → service_manager.ps1 → pythonw.exe → waitress（4 层嵌套，每层超时不同，
#       导致 service_manager.py 等 8 秒就退出，但后端实际需要 30+ 秒启动）。
#       修复：直接调用 python，单一超时 60 秒，简单可靠。
# [P0 2026-09-05 端口单一真源] 默认端口读 scripts/ports.json (FE=3006, BE=3011)。
#   历史: 硬编码 FE=3005/BE=3011 与实际使用 (3006) 漂移, 是环境顽疾根因之一。
def _load_ports():
    try:
        with open(PROJECT_ROOT / "scripts" / "ports.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        return int(data.get("frontend", 3006)), int(data.get("backend", 3011))
    except Exception:
        return 3006, 3011


FE_PORT, BE_PORT = _load_ports()


def _slot_ports(slot: int) -> tuple[int, int]:
    """按槽位派生端口 (真源仍是 ports.json, 派生公式只在这一处实现)"""
    return FE_PORT + slot * SLOT_STRIDE, BE_PORT + slot * SLOT_STRIDE


# slot>0: 应用沙箱端口派生 + 裸文件路径隔离 (slot 0 保持原路径, 完全兼容)
if SESSION_SLOT > 0:
    FE_PORT, BE_PORT = _slot_ports(SESSION_SLOT)
    STATUS_FILE = PROJECT_ROOT / f".service_status_slot{SESSION_SLOT}.json"
    LOCK_FILE = PROJECT_ROOT / f".service_manager.lock.slot{SESSION_SLOT}"
    LOG_FILE = PROJECT_ROOT / f".service_manager.log.slot{SESSION_SLOT}"
    STARTUP_STATE_FILE = PROJECT_ROOT / f".startup_state_slot{SESSION_SLOT}.json"

SERVICES = {
    "frontend": {
        "port": FE_PORT,
        "display_name": "Frontend (Vite)",
        "service_name": "frontend",
        "start_cmd": ["npm.cmd", "run", "dev"],
        "wait_seconds": 30,  # V4.0: 8 → 30（前端启动较慢）
        # M4 [V2026-07-22]: 启动前端必须传 VITE_PORT, 否则 vite 用默认 5173
        "env": {
            "VITE_PORT": str(FE_PORT),
            "BACKEND_PORT": str(BE_PORT),  # vite.config.js 需要
        },
    },
    "backend": {
        "port": BE_PORT,
        "display_name": "Backend (Waitress)",
        "service_name": "backend",
        # V4.0: 直接启动 python（不再走 powershell 中间层）
        "start_cmd": ["python.exe", "-u", "waitress_server.py"],
        "wait_seconds": 60,  # V4.0: 8 → 60（meta.server.py 初始化 + waitress 监听需 30+ 秒）
        # [R2 PM-authorized] 自动传 AGENT_PORT，避免 waitress 默认端口与 .env 不一致
        "env": {"AGENT_PORT": str(BE_PORT)},
    },
}

MANAGEMENT_LOCK_TIMEOUT = 120
if SESSION_SLOT == 0:
    STARTUP_STATE_FILE = PROJECT_ROOT / ".startup_state.json"  # V4.0: 启动状态跟踪文件


def _log(msg: str):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{timestamp}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _check_port(port: int) -> bool:
    """检查端口是否被监听（跨平台，不依赖 Get-Process）"""
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


# ============================================================================
# [P0 2026-09-06 多会话并行] 会话注册表 (port_registry)
#   共享文件: .runtime/port_registry.json
#   {
#     "sessions": {
#       "sess-1234-ab": {
#         "slot": 0, "pid": 1234,
#         "started_at": "...", "heartbeat": "...",
#         "services": {"frontend": 3006, "backend": 3011}
#       }
#     }
#   }
#   规则:
#     - start/restart 成功后登记端口归属; status/doctor 刷新心跳
#     - 孤儿对账杀进程前先查注册表: 端口被"活跃会话"(TTL 内心跳)持有 → 跳过清理
#     - 心跳过期条目视为死会话: 可清理, 清理时同步摘除条目
# ============================================================================
def _registry_read() -> dict:
    try:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("sessions"), dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"sessions": {}}


def _registry_write(data: dict) -> None:
    try:
        REGISTRY_DIR.mkdir(exist_ok=True)
        tmp = REGISTRY_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(REGISTRY_FILE)
    except OSError as e:
        _log(f"WARNING: registry write failed: {e}")


def _registry_heartbeat_of(entry: dict) -> str:
    return entry.get("heartbeat") or entry.get("started_at") or ""


def _registry_is_active(entry: dict) -> bool:
    """心跳在 TTL 内 = 活跃会话"""
    hb = _registry_heartbeat_of(entry)
    if not hb:
        return False
    try:
        dt = datetime.fromisoformat(hb.replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - dt
        return 0 <= age.total_seconds() <= HEARTBEAT_TTL_SECONDS
    except ValueError:
        return False


def _registry_prune(data: dict) -> tuple[dict, int]:
    """摘除心跳过期条目 (死会话)。返回 (data, 摘除数) — 调用方据摘除数决定写回。"""
    sessions = data.get("sessions", {})
    dead = [sid for sid, e in sessions.items() if not _registry_is_active(e)]
    for sid in dead:
        _log(f"  registry: pruned stale session {sid} (heartbeat expired)")
        del sessions[sid]
    return data, len(dead)


def _registry_register(services: dict, slot: int | None = None) -> None:
    """登记本会话端口归属并刷新心跳。services: {svc_name: port}

    slot: 显式槽位 (acquire-session 分配的槽可能与当前 SESSION_SLOT 不同, 必须传)
    """
    data, _ = _registry_prune(_registry_read())
    data["sessions"][SESSION_ID] = {
        "slot": SESSION_SLOT if slot is None else slot,
        "pid": os.getpid(),
        "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "heartbeat": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "services": services,
    }
    _registry_write(data)


def _registry_heartbeat() -> None:
    """刷新本会话心跳 (若未登记则跳过 — status/doctor 不应产生归属)"""
    data, _ = _registry_prune(_registry_read())
    entry = data.get("sessions", {}).get(SESSION_ID)
    if entry:
        entry["heartbeat"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _registry_write(data)


def _registry_remove(session_id: str | None = None) -> None:
    """摘除会话条目 (默认摘自己)"""
    sid = session_id or SESSION_ID
    data = _registry_read()
    if sid in data.get("sessions", {}):
        del data["sessions"][sid]
        _registry_write(data)


def _registry_active_entries() -> dict:
    """TTL 内活跃会话条目 {sid: entry}；死条目摘除后写回 (prune 结果必须落盘)"""
    data, n_pruned = _registry_prune(_registry_read())
    active = {sid: e for sid, e in data.get("sessions", {}).items() if _registry_is_active(e)}
    if n_pruned:
        _registry_write(data)
    return active


def _registry_port_owner(port: int) -> dict | None:
    """返回持有该端口的活跃会话条目 (含 session id), 无则 None"""
    for sid, e in _registry_active_entries().items():
        for svc, p in (e.get("services") or {}).items():
            if p == port:
                out = dict(e)
                out["session"] = sid
                out["owner_service"] = svc
                return out
    return None


def _registry_protected_pids() -> set:
    """活跃会话登记的 pid 集合 (自身除外) — 家族清理时的保护名单"""
    protected = set()
    for sid, e in _registry_active_entries().items():
        if sid == SESSION_ID:
            continue
        pid = e.get("pid")
        if pid:
            protected.add(int(pid))
    return protected


def _get_current_git_commit() -> str:
    """获取当前 git commit hash (V2.1 增强 - 防止调试旧代码)"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(PROJECT_ROOT),
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "unknown"


def _check_code_version_stale() -> dict:
    """检查关键代码版本是否比后端启动时间新（V2.1 增强）"""
    if not STATUS_FILE.exists():
        return {"stale": False}

    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            status = json.load(f)
    except Exception:
        return {"stale": False}

    backend_info = status.get("backend", {})
    started_at = backend_info.get("started_at")
    if not started_at:
        return {"stale": False}

    # 检查关键文件是否比启动时间更新
    try:
        backend_start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError:
        return {"stale": False}

    stale_files = []
    critical_files = [
        "meta/core/action_executor.py",
        "meta/core/interceptors/write_scope_interceptor.py",
        "meta/server.py",
    ]

    for f in critical_files:
        file_path = PROJECT_ROOT / f
        if not file_path.exists():
            continue
        # V2.1 增强：同时检查 git commit 时间 + 文件 mtime
        commit_time = ""
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%cI", "--", f],
                cwd=str(PROJECT_ROOT),
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                commit_time = result.stdout.strip()
        except Exception:
            pass

        # 文件 mtime（捕获未提交修改）
        mtime = ""
        try:
            mt = file_path.stat().st_mtime
            mtime = datetime.fromtimestamp(mt, tz=timezone.utc).isoformat()
        except OSError:
            pass

        latest = max([t for t in (commit_time, mtime) if t], default="")
        if not latest:
            continue
        try:
            file_dt = datetime.fromisoformat(latest)
            if file_dt > backend_start_dt:
                stale_files.append(f)
        except ValueError:
            continue

    return {"stale": len(stale_files) > 0, "stale_files": stale_files, "started_at": started_at}


def _read_status() -> dict:
    """读取服务状态文件 (向后兼容 per-port + 裸 .service_status.json)

    M8 [V2026-07-22]: 真相源迁移到 per-port 文件 .service_status_<port>.json
    这里仍读取裸文件作为 fallback, 兼容历史 watchdog 写的旧数据。
    """
    # 优先 per-port 汇总
    merged = {}
    for port_str, info in _scan_per_port_status().items():
        merged.update(info)
    if merged:
        return merged
    # fallback: 裸文件
    if not STATUS_FILE.exists():
        return {}
    try:
        # V2.1 修复：兼容 watchdog 写的 utf-8-sig BOM 文件
        for encoding in ("utf-8-sig", "utf-8"):
            try:
                with open(STATUS_FILE, "r", encoding=encoding) as f:
                    return json.load(f)
            except UnicodeDecodeError:
                continue
        return {}
    except (json.JSONDecodeError, OSError):
        return {}


def _scan_per_port_status() -> dict:
    """扫描 .service_status_<port>.json 系列文件, 返回 {port: {svc: info}}"""
    result = {}
    pattern = ".service_status_*.json"
    for p in PROJECT_ROOT.glob(pattern):
        try:
            for encoding in ("utf-8-sig", "utf-8"):
                try:
                    with open(p, "r", encoding=encoding) as f:
                        data = json.load(f)
                    port_key = p.stem.replace(".service_status_", "")
                    result[port_key] = data
                    break
                except UnicodeDecodeError:
                    continue
        except (json.JSONDecodeError, OSError):
            continue
    return result


def _write_status(status: dict):
    """写入服务状态文件

    M8 [V2026-07-22]: 不再写裸 .service_status.json (避免多端口冲突)
    改为写 per-port 文件 .service_status_<port>.json, 单一端口为唯一写入键
    """
    for svc_name, svc_info in status.items():
        port = svc_info.get("port")
        if not port:
            continue
        per_port_file = PROJECT_ROOT / f".service_status_{port}.json"
        # 单端口文件只含该 svc
        single_status = {svc_name: svc_info}
        with open(per_port_file, "w", encoding="utf-8") as f:
            json.dump(single_status, f, indent=2, ensure_ascii=False)


# V4.0: 启动状态跟踪（区分"启动中"vs"启动失败"vs"未启动"）
def _write_startup_state(svc_name: str, state: str, pid: int = None, port: int = None, error: str = None):
    """写入启动状态
    
    Args:
        state: 'starting' | 'ready' | 'failed' | 'stale'
    """
    states = {}
    if STARTUP_STATE_FILE.exists():
        try:
            with open(STARTUP_STATE_FILE, "r", encoding="utf-8") as f:
                states = json.load(f)
        except Exception:
            states = {}
    
    states[svc_name] = {
        "state": state,
        "pid": pid,
        "port": port,
        "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "error": error,
    }
    
    try:
        with open(STARTUP_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(states, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


def _read_startup_state() -> dict:
    """读取启动状态"""
    if not STARTUP_STATE_FILE.exists():
        return {}
    try:
        with open(STARTUP_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _acquire_lock() -> bool:
    """获取管理锁，防止并发管理操作"""
    deadline = time.time() + MANAGEMENT_LOCK_TIMEOUT
    while time.time() < deadline:
        try:
            if LOCK_FILE.exists():
                lock_age = time.time() - LOCK_FILE.stat().st_mtime
                if lock_age > 300:
                    LOCK_FILE.unlink(missing_ok=True)
                    _log("Cleaned stale lock file")
                else:
                    _log(f"Waiting for lock (age={lock_age:.0f}s)...")
                    time.sleep(2)
                    continue
            LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
            return True
        except OSError:
            time.sleep(2)
    _log("ERROR: Could not acquire management lock")
    return False


def _release_lock():
    """释放管理锁"""
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def _find_and_kill_process(port: int) -> bool:
    """根据端口查找并终止进程"""
    killed = False
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            output = subprocess.check_output(
                ["netstat", "-ano"],
                text=True,
                timeout=10,
            )
            for line in output.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    pid_str = parts[-1]
                    try:
                        pid = int(pid_str)
                        if pid == 0 or pid == 4:
                            continue
                        subprocess.run(
                            ["taskkill", "/F", "/PID", str(pid)],
                            capture_output=True,
                            timeout=10,
                        )
                        _log(f"Killed PID {pid} on port {port}")
                        killed = True
                    except (ValueError, subprocess.SubprocessError):
                        pass
        except subprocess.SubprocessError:
            pass
    return killed


def _kill_all_backend_processes(exclude: set | None = None) -> int:
    """V2.1 新增 - 杀掉所有 waitress_server.py 启动的 python 进程

    背景：2026-06-21 调试事故 - 旧后端进程（python.exe）未杀掉，
          但端口被新 pythonw.exe 占用前的瞬间，旧进程可能仍在 TIME_WAIT。
          更根本的问题：旧 python.exe 进程没有被显式清理。

    [P0 2026-09-06 多会话] exclude: 受保护 pid 集合 (其他活跃会话登记的进程及
    其后代不杀) — 多会话并行下家族清理不得跨会话误杀。

    Returns:
        int: 杀掉的进程数量
    """
    if sys.platform != "win32":
        return 0

    protected = exclude or set()

    # 用 wmic 找所有带 waitress_server.py 的 python 进程
    try:
        result = subprocess.run(
            ["wmic", "process", "where",
             "name='python.exe' or name='pythonw.exe'",
             "get", "ProcessId,CommandLine", "/format:csv"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return 0

        killed = 0
        for line in result.stdout.splitlines():
            if "waitress_server.py" not in line:
                continue
            # CSV 格式: Node,CommandLine,ProcessId
            parts = line.strip().split(",")
            if len(parts) < 3:
                continue
            pid_str = parts[-1].strip()
            try:
                pid = int(pid_str)
                if pid == os.getpid():  # 避免杀自己
                    continue
                # [P0 2026-09-06] 多会话保护: pid 本身或其祖先是活跃会话登记的 pid → 跳过
                if any(pid == p or _is_descendant_or_self(pid, p) for p in protected):
                    _log(f"  SKIP waitress PID {pid}: protected by active session registry")
                    continue
                taskkill = subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True, timeout=10,
                )
                if taskkill.returncode == 0:
                    _log(f"Killed stale backend PID {pid} (waitress_server.py)")
                    killed += 1
            except (ValueError, subprocess.SubprocessError):
                pass
        return killed
    except (subprocess.SubprocessError, FileNotFoundError):
        return 0


def _get_listener_pid(port: int) -> int | None:
    """返回监听该端口的 PID, 无监听返回 None (单次 netstat 解析)"""
    try:
        r = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=10)
        for line in r.stdout.splitlines():
            if "LISTENING" not in line:
                continue
            parts = line.strip().split()
            if len(parts) >= 5 and parts[1].endswith(f":{port}"):
                try:
                    pid = int(parts[-1])
                    if pid > 0:
                        return pid
                except ValueError:
                    pass
    except subprocess.SubprocessError:
        pass
    return None


# [P1 2026-09-05] --keep-orphans 逃生口: main() 解析后写入
KEEP_ORPHANS = False
# [P0 2026-09-06 多会话] --force: 跳过"其他活跃会话持有端口"的 stop/restart 拒绝检查
FORCE = False


def _parent_pid(pid: int) -> int | None:
    """查询进程父 PID (wmic), 失败返回 None"""
    try:
        r = subprocess.run(
            ["wmic", "process", "where", f"ProcessId={pid}",
             "get", "ParentProcessId", "/format:csv"],
            capture_output=True, text=True, timeout=10,
        )
        for line in r.stdout.splitlines():
            line = line.strip()
            if line and not line.startswith("Node,"):
                return int(line.rsplit(",", 1)[-1])
    except (subprocess.SubprocessError, ValueError, OSError):
        pass
    return None


def _is_descendant_or_self(pid: int, ancestor: int, max_depth: int = 8) -> bool:
    """判断 pid 是否为 ancestor 的后代 (npm→cmd→node 多层包装场景)"""
    cur, depth = pid, 0
    while cur and depth < max_depth:
        if cur == ancestor:
            return True
        cur = _parent_pid(cur)
        depth += 1
    return False


def _is_managed_listener(svc_name: str, port: int, listener_pid: int) -> bool:
    """端口监听者是否为本 manager 管辖。

    status 文件记录的是 start_cmd 直接子进程 (如 npm.cmd), 而真正监听端口的
    往往是孙进程 (cmd → node vite)。故: PID 相等 或 监听者是记录 PID 的后代
    均视为管辖内。
    """
    status = _read_status()
    info = status.get(svc_name, {})
    recorded_pid = info.get("pid")
    if not recorded_pid or info.get("port") != port:
        return False
    if not _is_pid_alive(recorded_pid):
        return False
    if listener_pid == recorded_pid:
        return True
    return _is_descendant_or_self(listener_pid, recorded_pid)


def _reconcile_orphans(svc_name: str) -> None:
    """[P1 2026-09-05] start 前对账: 端口被不受管进程占用 → 杀掉再干净启动。

    背景 (2026-09-05 实锤): 孤儿 waitress (PID 28420, 3010) 持有 .architecture.lock
    导致后端起不来; 孤儿 vite (3006) 代理指向死掉的旧后端被 start 误当
    'already running' 采纳。根因是 start 只看端口占用, 不看监听者归属。

    [P0 2026-09-06 多会话] 注册表保护: 端口被其他"活跃会话"(注册表 TTL 内)持有
    → 绝不清理 (实锤: 会话 A 把会话 B 正常拉起的后端当孤儿杀掉)。
    注册表条目心跳过期才视为死会话 → 摘条目并按原孤儿逻辑清理。
    """
    if KEEP_ORPHANS:
        return
    config = SERVICES[svc_name]
    port = config["port"]
    listener = _get_listener_pid(port)
    if listener is None or _is_managed_listener(svc_name, port, listener):
        return

    # 多会话保护判定 (在真正动杀器之前)
    owner = _registry_port_owner(port)
    if owner and owner["session"] != SESSION_ID:
        _log(f"SKIP orphan cleanup on port {port}: held by ACTIVE session "
             f"{owner['session']} (slot={owner.get('slot')}, pid={owner.get('pid')})")
        _log("  多会话并行保护: 该端口由其他活跃会话登记, 不作为孤儿清理")
        _log("  查看: python scripts/service_manager.py doctor --session")
        _log("  如确需接管: 先联系对方会话释放, 或使用 --slot N 私有沙箱")
        return
    if owner:
        _log(f"  registry: session {owner['session']} heartbeat expired — treating as dead, cleaning port {port}")
        _registry_remove(owner["session"])

    pname = _get_process_name(listener)
    _log(f"ORPHAN detected on port {port}: PID={listener} ({pname}) — not managed, killing")
    subprocess.run(["taskkill", "/F", "/PID", str(listener)],
                   capture_output=True, timeout=10)
    # backend 孤儿: 等价进程家族一并清 (waitress_server.py 所有实例),
    # 但保护其他活跃会话登记的 waitress ([P0 2026-09-06])
    if svc_name == "backend":
        killed = _kill_all_backend_processes(exclude=_registry_protected_pids())
        if killed:
            _log(f"  backend family cleanup: killed {killed} waitress process(es)")
    # 等待端口释放 (最多 10s)
    for _ in range(20):
        if _get_listener_pid(port) is None:
            break
        time.sleep(0.5)
    # backend: 孤儿死后若 DB 锁仍残留则清理 (锁文件含 PID, 已死才删)
    if svc_name == "backend":
        _cleanup_stale_db_lock()


def _cleanup_stale_db_lock() -> None:
    """[P1 2026-09-05] 清理无主 .architecture.lock 残留。

    只删除两种可证安全的锁文件:
      - stale: 可读且持有者 PID 已死 (msvcrt 锁随进程死亡自动释放)
      - empty: 0 字节空文件 (无主)
    live_locked (读取被字节锁拒绝) = 有活跃进程真实持有, 绝不删除。
    """
    lock_file = PROJECT_ROOT / "meta" / ".architecture.lock"
    if not lock_file.exists():
        return
    probe = _db_lock_probe()
    if probe["state"] in ("stale", "empty"):
        try:
            lock_file.unlink()
            _log(f"  removed stale DB lock (state={probe['state']}, pid={probe.get('pid', '-')})")
        except OSError:
            pass


def _db_lock_probe() -> dict:
    """[P2 2026-09-05] DB 锁状态探针。

    关键事实: waitress 用 msvcrt 字节锁锁定文件第 0 字节, 持锁期间
    其他进程读取该文件会 PermissionError → "读不了" 恰恰说明锁是活的。
    可读 = 锁已释放 (持有者进程已死或从未锁上)。
    """
    import io
    lock_file = PROJECT_ROOT / "meta" / ".architecture.lock"
    if not lock_file.exists():
        return {"state": "none"}
    try:
        with open(lock_file, "r", encoding="utf-8", errors="ignore") as f:
            first = f.readline().strip()
    except (OSError, PermissionError, io.UnsupportedOperation):
        return {"state": "live_locked"}  # 字节锁生效中 → 持有者活跃
    if not first:
        return {"state": "empty"}  # 0 字节/空内容 = 无主残留
    if not first.isdigit():
        return {"state": "corrupt", "raw": first[:40]}
    pid = int(first)
    if _is_pid_alive(pid):
        # 可读但 PID 活着: 锁未生效或已被释放, 保守按活跃持有者报告
        cmdline = ""
        try:
            r = subprocess.run(
                ["wmic", "process", "where", f"ProcessId={pid}",
                 "get", "CommandLine", "/format:csv"],
                capture_output=True, text=True, timeout=10,
            )
            for line in r.stdout.splitlines():
                if line.strip() and not line.startswith(("Node",)):
                    cmdline = line.strip()[:120]
                    break
        except subprocess.SubprocessError:
            pass
        return {"state": "pid_alive", "pid": pid, "cmdline": cmdline}
    return {"state": "stale", "pid": pid}  # 可读 + 持有者已死 = 可安全删除


def _db_lock_holder() -> tuple[int | None, str]:
    """返回 (锁持有者 PID, 进程命令行摘要) — audit 用; 拿不到时 (None, '')"""
    probe = _db_lock_probe()
    if probe.get("pid"):
        return probe["pid"], probe.get("cmdline", "")
    return None, ""


def audit_command():
    """全面审计: 端口/进程/孤儿/hijack — 开发智能体不再需要手写 audit 脚本"""
    print("=" * 64)
    print("  SERVICE AUDIT (service_manager.py audit)")
    print("=" * 64)

    # 1. 端口监听情况 (全端口扫描)
    print("\n### 端口监听")
    # M2 [V2026-07-22]: 端口从 ports.json 动态加载, 不再硬编码
    known_ports = set()
    ports_file = Path(r"D:\filework\.coord\ports.json")
    if ports_file.exists():
        try:
            with open(ports_file, encoding='utf-8-sig') as f:
                pdata = json.load(f)
            for section in ("reserved", "persistent", "allocated"):
                for port_str, info in pdata.get(section, {}).items():
                    try:
                        known_ports.add(int(port_str))
                    except ValueError:
                        pass
                    for field in ("backend_port", "frontend_port"):
                        if field in info:
                            try:
                                known_ports.add(int(info[field]))
                            except (ValueError, TypeError):
                                pass
        except Exception as e:
            print(f"  [WARN] 加载 ports.json 失败: {e}")
    # fallback: 历史硬编码
    if not known_ports:
        known_ports = {3004, 3005, 3006, 3007, 3010, 3011, 3013, 3018}
    try:
        r = subprocess.run(['netstat', '-ano'], capture_output=True, text=True, timeout=10)
        port_map = {}  # port -> (state, pid)
        for line in r.stdout.split('\n'):
            if 'LISTENING' not in line:
                continue
            parts = line.strip().split()
            if len(parts) >= 5 and ':' in parts[1]:
                try:
                    port = int(parts[1].split(':')[-1])
                    pid = int(parts[-1])
                    port_map[port] = ('LISTENING', pid)
                except ValueError:
                    pass
        for port in sorted(known_ports):
            if port in port_map:
                state, pid = port_map[port]
                # 查找进程名
                pname = _get_process_name(pid)
                owner = _find_port_owner_in_ports_json(port)
                print(f"  {port:5}  LISTENING  PID={pid:6}  {pname:15}  owner={owner or '?'}")
            else:
                owner = _find_port_owner_in_ports_json(port)
                print(f"  {port:5}  CLOSED     {'':8}    {'':15}  owner={owner or '?'}")
        # 额外发现的未知端口
        for port in sorted(port_map.keys()):
            if port not in known_ports and 3000 <= port <= 3020:
                _, pid = port_map[port]
                pname = _get_process_name(pid)
                print(f"  {port:5}  LISTENING  PID={pid:6}  {pname:15}  owner=UNKNOWN")
    except Exception as e:
        print(f"  [ERROR] netstat failed: {e}")

    # 2. 进程统计
    print("\n### 进程统计")
    for name in ['python.exe', 'pythonw.exe', 'node.exe', 'npm.cmd']:
        try:
            r = subprocess.run(['tasklist', '/FI', f'IMAGENAME eq {name}', '/FO', 'CSV'],
                             capture_output=True, text=True, timeout=10)
            count = r.stdout.count(name)
            if count > 0:
                print(f"  {name:15} count={count}")
        except Exception:
            pass

    # 3. 孤儿检测 (端口在监听但不在 .service_status_<port>.json 中)
    print("\n### 孤儿进程 (端口在监听但不受管理)")
    status = _read_status()
    managed_ports = set()
    for svc_name, svc_info in SERVICES.items():
        managed_ports.add(svc_info["port"])
    for port in sorted(port_map.keys()):
        if port not in managed_ports and 3000 <= port <= 3020:
            _, pid = port_map[port]
            pname = _get_process_name(pid)
            print(f"  port={port}  PID={pid}  {pname}  (not in .service_status_<port>.json)")

    # 4. hijack 统计
    print("\n### Hijack 历史")
    if status:
        be_hijack = status.get("backend", {}).get("hijack_count", 0)
        fe_hijack = status.get("frontend", {}).get("hijack_count", 0)
        if be_hijack > 0 or fe_hijack > 0:
            print(f"  Backend hijack_count: {be_hijack}")
            print(f"  Frontend hijack_count: {fe_hijack}")
            if be_hijack > 100 or fe_hijack > 50:
                print("  [WARN] 极高 hijack 计数 → 端口被多个 Agent 反复占用, 考虑重置")
        else:
            print("  No hijack history")

    # 4.5 [P1 2026-09-05] DB 锁持有者
    print("\n### DB 锁 (meta/.architecture.lock)")
    lock_probe = _db_lock_probe()
    if lock_probe["state"] == "none":
        print("  无锁 (正常)")
    elif lock_probe["state"] == "live_locked":
        print("  活跃持有中 (字节锁生效 → 持有者存活)")
    elif lock_probe["state"] in ("pid_alive",):
        print(f"  持有者 PID={lock_probe['pid']}  {lock_probe.get('cmdline', '')}")
    else:
        print(f"  [WARN] 残留锁 (state={lock_probe['state']}) → 建议 doctor --fix")

    # 5. service_status_<port>.json 健康检查
    print("\n### per-port service status (M8)")
    if status:
        for svc_name in ("frontend", "backend"):
            info = status.get(svc_name, {})
            pid = info.get("pid")
            port = info.get("port")
            last_seen = info.get("last_seen", "?")
            if pid:
                alive = _is_pid_alive(pid)
                port_ok = _check_port(port) if port else False
                state = "RUNNING" if (alive and port_ok) else "DEAD"
                print(f"  {svc_name}: pid={pid} port={port} last_seen={last_seen} state={state}")
            else:
                print(f"  {svc_name}: not in status file")
    else:
        print("  (empty)")

    # 6. 僵尸 node.exe 检测
    print("\n### 僵尸 node.exe")
    try:
        r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq node.exe', '/FO', 'CSV'],
                         capture_output=True, text=True, timeout=10)
        node_count = r.stdout.count('node.exe')
        if node_count > 10:
            print(f"  [WARN] {node_count} node.exe processes! Run: _wt_service.py clean-stale-node --apply")
        elif node_count > 0:
            print(f"  {node_count} node.exe (normal)")
        else:
            print("  0 node.exe")
    except Exception:
        pass

    print("\n" + "=" * 64)
    return 0


def _get_process_name(pid: int) -> str:
    """获取进程名"""
    try:
        r = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV'],
                         capture_output=True, text=True, timeout=5)
        for line in r.stdout.split('\n'):
            if str(pid) in line:
                parts = line.strip().split('","')
                if parts:
                    return parts[0].strip('"')
    except Exception:
        pass
    return "?"


def _find_port_owner_in_ports_json(port: int) -> str | None:
    """查找端口在 ports.json 中的 owner"""
    ports_file = Path(r"D:\filework\.coord\ports.json")
    if not ports_file.exists():
        return None
    try:
        with open(ports_file, encoding='utf-8-sig') as f:
            data = json.load(f)
        for section in ("reserved", "persistent", "allocated"):
            for port_str, info in data.get(section, {}).items():
                try:
                    if int(port_str) == port:
                        return info.get("owner", f"{section}:?")
                except ValueError:
                    pass
                for field in ("backend_port", "frontend_port"):
                    if info.get(field) == port:
                        return info.get("owner", f"{section}:?")
    except Exception:
        pass
    return None


def _is_pid_alive(pid: int) -> bool:
    """检查 PID 是否存活"""
    try:
        r = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV'],
                         capture_output=True, text=True, timeout=5)
        return str(pid) in r.stdout
    except Exception:
        return False


def status_command():
    """查看服务状态"""
    status = _read_status()
    all_healthy = True

    print("\n  Service Status")
    print("  " + "=" * 50)

    for name, config in SERVICES.items():
        port = config["port"]
        is_listening = _check_port(port)
        known = status.get(name, {})
        known_pid = known.get("pid", "?")
        known_time = known.get("started_at", "?")
        known_code = known.get("code_version", "NOT SET")  # V2.1 新增
        known_health = known.get("health_url", f"http://localhost:{port}/health")  # V2.1 新增
        healthy = "RUNNING" if is_listening else "STOPPED"

        if is_listening:
            print(f"  {config['display_name']:<25s} : {healthy}  "
                  f"(port={port}, pid={known_pid}, since={known_time})")
            # V2.1 新增：显示 code_version 和 health_url
            if known_code and known_code != "NOT SET":
                print(f"  {'':<25s}   commit={known_code[:12]}")
                print(f"  {'':<25s}   health={known_health}")
        else:
            print(f"  {config['display_name']:<25s} : {healthy}  "
                  f"(port={port})")
            all_healthy = False

    print("  " + "=" * 50)

    # V2.1 新增：检测代码版本是否 stale（防止"调试旧代码"事故）
    stale_info = _check_code_version_stale()
    if stale_info.get("stale"):
        print()
        print("  [!!!] WARNING: Code version stale !!!")
        print(f"  Backend started: {stale_info.get('started_at', '?')}")
        print(f"  Stale files (modified after start):")
        for sf in stale_info.get("stale_files", []):
            print(f"    - {sf}")
        print()
        print("  >>> Run: python scripts/service_manager.py restart-be")
        print("  >>> Or:  python scripts/debug_backend.py restart-if-stale")
        all_healthy = False

    if not status:
        print("  No status file found -- services may not have been started via service_manager")
    else:
        print(f"  Status file: {STATUS_FILE}")

    if all_healthy:
        print("  Summary: ALL SERVICES HEALTHY")
    else:
        print("  Summary: SOME SERVICES NOT RUNNING")

    return 0 if all_healthy else 1


def stop_command(name: str = None):
    """停止服务

    [P0 2026-09-06 多会话] stop/restart 共享环境前检查注册表: 其他活跃会话
    持有目标端口时拒绝停止 (--force 逃生口), 防止跨会话中断他人验证。
    """
    if not _acquire_lock():
        return 1

    try:
        names = [name] if name else list(SERVICES.keys())
        status = _read_status()

        # 多会话保护预检: 目标端口被其他活跃会话持有 → 拒绝 (--force 才放行)
        if not FORCE:
            for svc_name in names:
                port = SERVICES[svc_name]["port"]
                owner = _registry_port_owner(port)
                if owner and owner["session"] != SESSION_ID:
                    _log(f"REFUSED stop {SERVICES[svc_name]['display_name']} (port {port}): "
                         f"held by ACTIVE session {owner['session']} (slot={owner.get('slot')})")
                    _log("  多会话并行保护: 对方可能正在跑验证。")
                    _log("  确认无人使用后可用 --force 强制停止, 或用 --slot N 私有沙箱。")
                    return 1

        for svc_name in names:
            config = SERVICES[svc_name]
            port = config["port"]
            _log(f"Stopping {config['display_name']}...")

            # V2.1 增强：先杀掉所有 waitress_server.py 启动的 python 进程
            # 防止旧 python.exe 进程残留（即使不在 LISTEN 端口）
            # [P0 2026-09-06] 保护其他活跃会话的 waitress
            if svc_name == "backend":
                killed_count = _kill_all_backend_processes(exclude=_registry_protected_pids())
                if killed_count > 0:
                    _log(f"  V2.1: Killed {killed_count} stale backend processes")

            if not _check_port(port):
                _log(f"  {config['display_name']} already stopped")
                status.pop(svc_name, None)
                continue

            # 尝试通过 PID 终止
            known = status.get(svc_name, {})
            known_pid = known.get("pid")
            killed = False

            if known_pid:
                try:
                    subprocess.run(
                        ["taskkill", "/PID", str(known_pid)],
                        capture_output=True,
                        timeout=10,
                    )
                    time.sleep(2)
                    if not _check_port(port):
                        killed = True
                        _log(f"  Stopped via PID {known_pid}")
                except subprocess.SubprocessError:
                    pass

            if not killed:
                if _find_and_kill_process(port):
                    _log(f"  Stopped via port {port} scan")

            # V2.1 增强：再杀一次所有 waitress_server.py 进程（兜底）
            # [P0 2026-09-06] 保护其他活跃会话的 waitress
            if svc_name == "backend":
                _kill_all_backend_processes(exclude=_registry_protected_pids())

            # 等待端口释放
            for _ in range(10):
                if not _check_port(port):
                    break
                time.sleep(1)

            if _check_port(port):
                _log(f"  WARNING: Port {port} still in use after stop attempt")
            else:
                _log(f"  {config['display_name']} stopped")
                status.pop(svc_name, None)

        _write_status(status)
        # [P0 2026-09-06] stop 完成后摘除本会话端口注册 (不再持有端口)
        _registry_remove()
        return 0
    finally:
        _release_lock()


def start_command(name: str = None):
    """启动服务（幂等：已运行则跳过）"""
    if not _acquire_lock():
        return 1

    try:
        names = [name] if name else list(SERVICES.keys())
        status = _read_status()
        registered = {}  # [P0 2026-09-06] 本会话登记到注册表的端口归属

        for svc_name in names:
            config = SERVICES[svc_name]
            port = config["port"]

            # [P1 2026-09-05] 启动前对账: 端口被不受管进程占用 → 先清理
            #   (孤儿可能带着错误配置, 如 vite 代理指向已死的后端)
            _reconcile_orphans(svc_name)

            if _check_port(port):
                _log(f"{config['display_name']} already running on port {port}")
                _write_startup_state(svc_name, "ready")  # V4.0
                registered[svc_name] = port  # [P0 2026-09-06] 采纳现有实例为归属
                continue

            _log(f"Starting {config['display_name']}...")
            _write_startup_state(svc_name, "starting", port=port)  # V4.0: 标记启动中

            # 使用 DETACHED_PROCESS 不占用终端槽位
            creation_flags = 0
            if sys.platform == "win32":
                creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

            # 解析 start_cmd: 处理 .cmd/.bat/.ps1 等需要 shell 解释的命令
            start_cmd = config["start_cmd"]
            if start_cmd and start_cmd[0].lower().endswith(('.cmd', '.bat')):
                # .cmd/.bat 必须通过 cmd.exe /c 启动
                resolved = shutil.which(start_cmd[0])
                if not resolved:
                    # 再尝试在 PATH 中查找
                    for p in os.environ.get('PATH', '').split(os.pathsep):
                        candidate = Path(p) / start_cmd[0]
                        if candidate.exists():
                            resolved = str(candidate)
                            break
                if not resolved:
                    resolved = start_cmd[0]  # fallback, 让 Popen 自行报错
                start_cmd = ['cmd.exe', '/c', resolved] + start_cmd[1:]

            # M4: 注入 services env (VITE_PORT, BACKEND_PORT 等)
            svc_env = os.environ.copy()
            for k, v in config.get("env", {}).items():
                svc_env[k] = str(v)

            proc = subprocess.Popen(
                start_cmd,
                cwd=str(PROJECT_ROOT),
                env=svc_env,
                stdout=open(PROJECT_ROOT / "scripts" / "logs" / f"{config['service_name']}.out", "ab"),
                stderr=open(PROJECT_ROOT / "scripts" / "logs" / f"{config['service_name']}.err", "ab"),
                creationflags=creation_flags,
            )

            # 等待端口就绪（V4.0: wait_seconds * 2 = 60*2 = 120 次 * 0.5s = 60 秒）
            ready = False
            for i in range(config["wait_seconds"] * 2):
                time.sleep(0.5)
                if _check_port(port):
                    ready = True
                    break

            if ready:
                # 获取启动时的 git commit（V2.1 增强 - 防止"调试旧代码 3 小时"事故）
                code_version = _get_current_git_commit()
                # 健康检查 URL（V2.1 增强 - 避免 /api/v1/health 410 误判）
                health_url = config.get("health_url", f"http://localhost:{port}/health")

                status[svc_name] = {
                    "port": port,
                    "pid": proc.pid,
                    "started_at": datetime.now(timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                    "code_version": code_version,  # V2.1 新增
                    "health_url": health_url,      # V2.1 新增
                }
                _log(f"  {config['display_name']} started (PID={proc.pid}, port={port}, commit={code_version[:8]})")
                _write_startup_state(svc_name, "ready", proc.pid, port)  # V4.0: 标记就绪
                registered[svc_name] = port  # [P0 2026-09-06] 登记端口归属
            else:
                # V4.0: 失败时记录详细错误
                _write_startup_state(svc_name, "failed", proc.pid, port, "port not listening within timeout")
                _log(f"  WARNING: {config['display_name']} process spawned but port {port} not responding")
                _log(f"  V4.0: Check {PROJECT_ROOT / 'scripts' / 'logs' / f'{config['service_name']}.err'}")

        _write_status(status)
        # [P0 2026-09-06] 本会话端口归属登记 (孤儿对账/stop 保护的数据基础)
        if registered:
            _registry_register(registered)
        return 0
    finally:
        _release_lock()


def restart_command(name: str = None):
    """重启服务"""
    ret = stop_command(name)
    if ret != 0:
        _log("Stop failed, but continuing with start...")
    time.sleep(2)
    return start_command(name)


# [P2 2026-09-05] 会话引导一键体检 — 10 秒内回答"环境是否健康, 不健康怎么修"
# 已知的历史漂移坏值 (打地鼠时代残留), doctor 用于检测它们是否复活
_KNOWN_DRIFT_PATTERNS = [
    ("test_helpers/browser_auth_cli.py", "localhost:3010"),
    ("vite.config.js", "|| '3010'"),
    ("vite.config.js", "|| '3005'"),
    ("package.json", "localhost:3004"),
    ("playwright.config.js", "localhost:3004"),
]
_DRIFT_ENV_KEYS = ("BACKEND_PORT=", "VITE_PORT=", "PORT=")


def acquire_session_command(slot: int | None = None) -> int:
    """[P0 2026-09-06 多会话] 申请私有沙箱槽位 (改后端代码的会话用)

    - slot 自动分配: 从 1 起找最小空闲槽 (端口未被监听且不在注册表)
    - 端口派生: FE=base+N*20, BE=base+N*20 (slot1 → 3026/3031)
    - 输出 env 设置指引, 会话内后续 start/restart 用 SM_SLOT 保持同槽
    """
    active = _registry_active_entries()
    used_slots = {int(e.get("slot", 0)) for e in active.values()}

    if slot is None:
        slot = 1
        while slot in used_slots or _check_port(FE_PORT + slot * SLOT_STRIDE) \
                or _check_port(BE_PORT + slot * SLOT_STRIDE):
            slot += 1
            if slot > 50:
                _log("ERROR: no free slot (1..50)")
                return 1
    elif slot in used_slots:
        _log(f"ERROR: slot {slot} already registered by another active session")
        return 1
    elif slot == 0:
        _log("ERROR: slot 0 is the shared environment, use it without acquire-session")
        return 1

    fe = FE_PORT + slot * SLOT_STRIDE
    be = BE_PORT + slot * SLOT_STRIDE
    _registry_register({"frontend": fe, "backend": be}, slot=slot)
    print("=" * 64)
    print(f"  SESSION SANDBOX ACQUIRED (slot={slot})")
    print("=" * 64)
    print(f"  会话 ID: {SESSION_ID}")
    print(f"  前端端口: {fe}   后端端口: {be}")
    print()
    print("  本会话后续所有 service_manager 调用请带同槽位参数:")
    print(f"    python scripts/service_manager.py start --slot {slot}")
    print(f"    python scripts/service_manager.py restart --slot {slot}")
    print(f"    python scripts/service_manager.py stop --slot {slot}")
    print()
    print("  验证脚本/浏览器指向 (env 方式, PlaywrightCLI 已支持):")
    print(f"    BACKEND_PORT={be}  VITE_PORT={fe}  SM_SLOT={slot}")
    print()
    print("  用完后释放 (停止沙箱服务并摘除注册):")
    print(f"    python scripts/service_manager.py release-session --slot {slot}")
    return 0


def release_session_command() -> int:
    """[P0 2026-09-06 多会话] 释放私有沙箱: 停本槽服务 + 摘注册表条目"""
    if SESSION_SLOT == 0:
        _log("release-session: 当前为共享环境 (slot 0), 无沙箱可释放; 仅摘除本会话注册条目")
        _registry_remove()
        return 0
    ret = stop_command(None)  # stop 会摘除注册表条目
    _log(f"  sandbox slot={SESSION_SLOT} released")
    return ret


def doctor_command(fix: bool = False) -> int:
    """环境体检: 端口真源/服务/孤儿/DB锁/状态文件/配置漂移 — 会话第一步"""
    print("=" * 64)
    print("  ENV DOCTOR (service_manager.py doctor)")
    print("=" * 64)
    problems = []

    # 1. 端口真源
    print(f"\n[1] 端口真源 scripts/ports.json: FE={FE_PORT}  BE={BE_PORT}")

    # 2. 服务状态 (现实 vs 管辖)
    print("\n[2] 服务状态")
    for svc_name, config in SERVICES.items():
        port = config["port"]
        listener = _get_listener_pid(port)
        if listener is None:
            print(f"  {config['display_name']:20} port={port}  NOT RUNNING")
            problems.append(f"{svc_name} 未启动")
        elif _is_managed_listener(svc_name, port, listener):
            print(f"  {config['display_name']:20} port={port}  RUNNING (managed, PID={listener})")
        else:
            pname = _get_process_name(listener)
            print(f"  {config['display_name']:20} port={port}  ORPHAN PID={listener} ({pname})")
            problems.append(f"{svc_name} 端口被孤儿进程占用")

    # 3. DB 锁
    print("\n[3] DB 锁 (meta/.architecture.lock)")
    lock_probe = _db_lock_probe()
    lock_state = lock_probe["state"]
    if lock_state == "none":
        print("  无锁 (正常)")
    elif lock_state == "live_locked":
        print("  活跃持有中 (字节锁生效, 读取被拒 → 持有者存活)")
        if lock_probe.get("cmdline") is None and SERVICES["backend"]["port"] in (BE_PORT,):
            be_listener = _get_listener_pid(BE_PORT)
            if be_listener:
                print(f"  推断持有者: backend PID={be_listener} (正常)")
            else:
                print("  [WARN] backend 端口无监听但锁活跃 → 泄漏锁")
                problems.append("DB 锁被未知进程持有")
    elif lock_state == "pid_alive":
        print(f"  持有者 PID={lock_probe['pid']}  {lock_probe.get('cmdline', '')}")
        if "waitress_server.py" not in lock_probe.get("cmdline", ""):
            print("  [WARN] 持有者不是本仓 waitress → 可能是泄漏锁")
            problems.append(f"DB 锁被外部进程持有 (PID {lock_probe['pid']})")
    elif lock_state in ("stale", "empty"):
        print(f"  残留锁 (state={lock_state}, pid={lock_probe.get('pid', '-')}) → 可 doctor --fix")
        problems.append("DB 锁残留 (持有者已死)")
    elif lock_state == "corrupt":
        print(f"  锁文件内容异常: {lock_probe.get('raw', '')}")
        problems.append("DB 锁文件损坏")

    # 4. 状态文件 vs 现实
    print("\n[4] 状态文件一致性")
    status = _read_status()
    for svc_name in ("frontend", "backend"):
        info = status.get(svc_name, {})
        recorded_pid, recorded_port = info.get("pid"), info.get("port")
        real_port = SERVICES[svc_name]["port"]
        if recorded_pid and not _is_pid_alive(recorded_pid):
            print(f"  {svc_name}: status 记录 PID={recorded_pid} 已死 (陈旧条目)")
            problems.append(f"{svc_name} status 文件陈旧")
        elif recorded_port and recorded_port != real_port:
            print(f"  {svc_name}: status 记录 port={recorded_port} ≠ 真源 {real_port}")
            problems.append(f"{svc_name} status 文件端口漂移")
        else:
            print(f"  {svc_name}: {'一致' if info else '无记录 (未启动过)'}")

    # 5. 配置漂移 (历史坏值复活检测)
    print("\n[5] 配置漂移扫描")
    drift_found = False
    for rel_path, pattern in _KNOWN_DRIFT_PATTERNS:
        p = PROJECT_ROOT / rel_path
        if not p.exists():
            continue
        try:
            if pattern in p.read_text(encoding="utf-8", errors="ignore"):
                print(f"  [DRIFT] {rel_path} 含硬编码 '{pattern}'")
                drift_found = True
        except OSError:
            pass
    env_dev = PROJECT_ROOT / ".env.development"
    if env_dev.exists():
        for line in env_dev.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith(_DRIFT_ENV_KEYS) and not line.startswith("#"):
                print(f"  [DRIFT] .env.development 含端口行: {line}")
                drift_found = True
    if not drift_found:
        print("  无漂移 (各消费方与 ports.json 一致)")
    else:
        problems.append("存在硬编码端口漂移")

    # [P0 2026-09-06 多会话] 注册表全景: 谁在占用哪些端口 (活跃会话)
    print("\n[6] 会话注册表 (.runtime/port_registry.json)")
    active = _registry_active_entries()
    print(f"  活跃会话: {len(active)} 个 (TTL {HEARTBEAT_TTL_SECONDS // 60}min)")
    for sid, e in sorted(active.items(), key=lambda kv: (kv[1].get("slot", 0), kv[0])):
        svc_ports = "  ".join(f"{k}={v}" for k, v in sorted((e.get("services") or {}).items()))
        mine = " ← 本会话" if sid == SESSION_ID else ""
        print(f"  {sid}  slot={e.get('slot')}  pid={e.get('pid')}  {svc_ports}  {mine}")
    if not active:
        print("  (空 — 所有服务均未登记归属, 孤儿对账按无主处理)")
    # 刷新本会话心跳 (仅当已登记)
    _registry_heartbeat()
    if SESSION_SLOT > 0:
        print(f"  当前运行模式: 私有沙箱 slot={SESSION_SLOT} (FE={FE_PORT}/BE={BE_PORT})")
    else:
        print("  当前运行模式: 共享环境 slot=0 (restart/stop 受多会话保护约束)")

    # 结论
    print("\n" + "=" * 64)
    if not problems:
        print("  VERDICT: HEALTHY")
        return 0
    print(f"  VERDICT: {len(problems)} 个问题")
    for i, p in enumerate(problems, 1):
        print(f"    {i}. {p}")
    print("\n  修复路径:")
    print("    python scripts/service_manager.py doctor --fix   # 清孤儿+残留锁")
    print("    python scripts/service_manager.py restart        # 干净重启 (start 自带孤儿对账)")
    return 1


def _doctor_fix() -> int:
    """doctor --fix: 清孤儿 + 死持有者残留锁"""
    print("[FIX] 清理孤儿进程...")
    for svc_name in SERVICES:
        _reconcile_orphans(svc_name)
    print("[FIX] 清理残留 DB 锁...")
    _cleanup_stale_db_lock()
    print("[FIX] 完成, 请执行: python scripts/service_manager.py restart")
    return 0


def main():
    global SESSION_SLOT
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    command = sys.argv[1]
    target = None
    custom_port = None
    custom_slot = None
    # 解析剩余参数 (支持 --port N, 例如 restart_backend.py 委派时用)
    for i, arg in enumerate(sys.argv[2:], start=2):
        if arg == "--keep-orphans":
            # [P1 2026-09-05] 逃生口: 不清理不受管进程 (默认必清)
            globals()["KEEP_ORPHANS"] = True
        elif arg == "--force":
            # [P0 2026-09-06 多会话] 跳过 stop/restart 的跨会话保护检查
            globals()["FORCE"] = True
        elif arg == "--fix":
            pass  # doctor --fix 由 command 分支处理
        elif arg in ("--slot",) and i + 1 < len(sys.argv):
            try:
                custom_slot = int(sys.argv[i + 1])
            except ValueError:
                pass
        elif arg.startswith("--slot="):
            try:
                custom_slot = int(arg.split("=", 1)[1])
            except ValueError:
                pass
        elif arg in ("--port", "-p") and i + 1 < len(sys.argv):
            try:
                custom_port = int(sys.argv[i + 1])
            except ValueError:
                pass
        elif arg.startswith("--port="):
            try:
                custom_port = int(arg.split("=", 1)[1])
            except ValueError:
                pass
        elif "fe" in arg or "front" in arg:
            target = "frontend"
        elif "be" in arg or "back" in arg:
            target = "backend"

    # [P0 2026-09-06 多会话] --slot N: 切换会话槽位 (env SM_SLOT 或 CLI --slot, CLI 优先)
    #   端口派生 + 裸文件路径隔离在模块加载时已按 SESSION_SLOT 应用;
    #   CLI 传 --slot 时需要重应用 (重算 SERVICES 端口/env 与路径)。
    if custom_slot is not None and custom_slot != SESSION_SLOT:
        SESSION_SLOT = custom_slot
        FE_PORT_local, BE_PORT_local = _slot_ports(custom_slot)
        globals()["FE_PORT"], globals()["BE_PORT"] = FE_PORT_local, BE_PORT_local
        globals()["STATUS_FILE"] = (
            PROJECT_ROOT / f".service_status_slot{custom_slot}.json"
            if custom_slot > 0 else PROJECT_ROOT / ".service_status.json"
        )
        globals()["LOCK_FILE"] = (
            PROJECT_ROOT / f".service_manager.lock.slot{custom_slot}"
            if custom_slot > 0 else PROJECT_ROOT / ".service_manager.lock"
        )
        globals()["LOG_FILE"] = (
            PROJECT_ROOT / f".service_manager.log.slot{custom_slot}"
            if custom_slot > 0 else PROJECT_ROOT / ".service_manager.log"
        )
        globals()["STARTUP_STATE_FILE"] = (
            PROJECT_ROOT / f".startup_state_slot{custom_slot}.json"
            if custom_slot > 0 else PROJECT_ROOT / ".startup_state.json"
        )
        for svc_name in SERVICES:
            SERVICES[svc_name]["port"] = FE_PORT_local if svc_name == "frontend" else BE_PORT_local
            env_cfg = SERVICES[svc_name].get("env", {})
            for k in list(env_cfg):
                if k in ("VITE_PORT", "AGENT_PORT", "BACKEND_PORT"):
                    env_cfg[k] = str(FE_PORT_local if k == "VITE_PORT" else BE_PORT_local)

    # 如果传了 --port, 临时覆盖 SERVICES 的端口 (用于 restart_backend.py 委派)
    # [FIX 2026-09-05] 必须同步覆盖 env: backend 的 AGENT_PORT / frontend 的
    # BACKEND_PORT 硬编码在 SERVICES 配置里, 只改 port 会导致 waitress 仍绑定
    # 旧端口 (2026-09-05 实测: restart --port 3010 后端起在 3011)
    if custom_port is not None:
        for svc_name in SERVICES:
            SERVICES[svc_name]["port"] = custom_port
            env_cfg = SERVICES[svc_name].get("env", {})
            if "AGENT_PORT" in env_cfg:
                env_cfg["AGENT_PORT"] = str(custom_port)
            if "BACKEND_PORT" in env_cfg:
                env_cfg["BACKEND_PORT"] = str(custom_port)

    if command == "status":
        return status_command()
    elif command == "start":
        return start_command(target)
    elif command == "start-fe":
        return start_command("frontend")
    elif command == "start-be":
        return start_command("backend")
    elif command == "stop":
        return stop_command(target)
    elif command == "restart":
        return restart_command(target)
    elif command == "doctor":
        # [P2 2026-09-05] 会话引导体检; --fix 清孤儿+残留锁
        if "--fix" in sys.argv:
            return _doctor_fix()
        return doctor_command()
    elif command == "audit":
        return audit_command()
    elif command == "acquire-session":
        # [P0 2026-09-06 多会话] 申请私有沙箱槽位
        return acquire_session_command(custom_slot)
    elif command == "release-session":
        # [P0 2026-09-06 多会话] 释放私有沙箱
        return release_session_command()
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        return 1


if __name__ == "__main__":
    sys.exit(main())
