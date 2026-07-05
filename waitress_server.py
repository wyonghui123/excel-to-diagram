# -*- coding: utf-8 -*-
"""
Waitress WSGI server (v3.8 + v3.18 SQLite P0 保护)
=============================

方案 A 修订: Windows 用 waitress 替代 gunicorn
- 单进程 (单 worker)
- 多线程 (默认 4 线程, 可配)
- 跨平台 (Windows / Linux / macOS)
- 支持 SSE streaming
- 不需要 fcntl (Linux 限制)
- 单进程 → 不会 fork → SQLite 安全 (FR-001)

[WARNING] v3.18 P0 警告:
  生产环境同样使用 SQLite (architecture.db)。
  waitress 本身单进程, 但多个 waitress 实例 (不同端口或服务重启中) 会
  并发写 DB, 导致 WAL 损坏。本文件已加跨进程文件锁 + 启动时完整性检查。

Usage:
    waitress-serve --host=0.0.0.0 --port=3010 --threads=8 meta.server:app

或通过 Python:
    python -m waitress --host=0.0.0.0 --port=3010 --threads=8 meta.server:app

特性:
- threads=8: 8 个并发请求
- 单进程: SQLite WAL 安全
- streaming: 支持 SSE / chunked
"""
import multiprocessing
import os
import sys
import time
import sqlite3
import atexit
import signal

# [FIX V049 2026-07-05] 提升文件描述符上限, 避免大批量导入时 openpyxl read_only 临时文件
#   导致 [Errno 24] Too many open files
#   背景: openpyxl read_only 模式创建 ~3-5 个临时文件 / load_workbook;
#         import_cascade + _import_sheet 双重 load_workbook + 多 sheet = ~12 FD/导入.
#         Linux 默认 ulimit -n = 1024, 并发导入 + 日志/DB/网络 → 超过 1024.
#   修复: 启动时提升 NOFILE 软硬限制到 65536 (Linux 有效, Windows 跳过)
try:
    import resource
    _soft, _hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    _target = 65536
    if _soft < _target:
        resource.setrlimit(
            resource.RLIMIT_NOFILE,
            (_target, _hard if _hard == resource.RLIM_INFINITY else _target)
        )
        print(f"[waitress] RLIMIT_NOFILE 提升: {_soft} -> {_target}", flush=True)
except (ImportError, OSError):
    # Windows: resource module 不可用, 跳过
    pass

# [FIX 2026-07-02] 启动时加载 .env, 确保 AGENT_PORT 与 vite 代理一致
# 背景: .env 中约定 FLASK_PORT=3011 (前端 vite 代理 target), 但 waitress_server.py
#   之前只读 AGENT_PORT 环境变量, 导致默认启动在 3010, 触发前端 500.
#   修复: 加载 .env 后, 把 FLASK_PORT 同步到 AGENT_PORT (兼容两套命名).
# [FIX V043 2026-07-04] override=True: 强制覆盖父进程 env
#   背景: PM 启动 3011 的 PowerShell session 有 FLASK_ENV=production,
#         被 3011 继承 → _is_production() True → dev-login 500.
#   修复: override=True 让 .env 显式声明的非生产环境强制生效.
from dotenv import load_dotenv
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(_env_path):
    load_dotenv(_env_path, override=True)
    # [兼容] .env 写的是 FLASK_PORT, 代码用 AGENT_PORT. 双向同步.
    if not os.environ.get('AGENT_PORT') and os.environ.get('FLASK_PORT'):
        os.environ['AGENT_PORT'] = os.environ['FLASK_PORT']
    if not os.environ.get('FLASK_PORT') and os.environ.get('AGENT_PORT'):
        os.environ['FLASK_PORT'] = os.environ['AGENT_PORT']

# [DECORATIVE] v3.18 + v3.20: 多 agent 端口支持 (AGENT_PORT env, 默认 3010)
# 🆕 v3.20: 增强 fallback - 错误处理 + 范围检查 + 启动日志
_DEFAULT_PORT = 3010


def _get_agent_port():
    """Resolve AGENT_PORT with safe fallback + validation.

    Priority:
      1. os.environ['AGENT_PORT'] (int convertible, 1-65535)
      2. _DEFAULT_PORT = 3010
    """
    raw = os.environ.get('AGENT_PORT')
    if raw is None or raw == '':
        port = _DEFAULT_PORT
        print(f'[WAITRESS] AGENT_PORT not set, using default {port}')
        return port
    try:
        port = int(raw)
    except (ValueError, TypeError):
        print(f'[WAITRESS] AGENT_PORT={raw!r} is not an integer, '
              f'falling back to default {_DEFAULT_PORT}')
        return _DEFAULT_PORT
    if not (1 <= port <= 65535):
        print(f'[WAITRESS] AGENT_PORT={port} out of range (1-65535), '
              f'falling back to default {_DEFAULT_PORT}')
        return _DEFAULT_PORT
    return port


AGENT_PORT = _get_agent_port()


# [DECORATIVE] v3.18: DB 进程级文件锁 (跨所有 waitress/gunicorn/pytest 实例)
_DB_LOCK_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'meta', '.architecture.lock'
)
_db_lock_fd = None


def _acquire_db_lock():
    """获取 DB 进程级文件锁。Windows 用 msvcrt, Linux 用 fcntl。"""
    global _db_lock_fd
    try:
        if os.path.exists(_DB_LOCK_FILE):
            # 验证锁文件 PID 是否存活, 如果死了说明是 stale 锁
            try:
                with open(_DB_LOCK_FILE, 'r') as f:
                    first_line = f.readline().strip()
                    if first_line and first_line.isdigit():
                        stale_pid = int(first_line)
                        if _is_pid_alive(stale_pid):
                            print(f'[WAITRESS][P0 启动失败] 另一个实例 PID={stale_pid} 持有 DB 锁!')
                            return False
                        else:
                            print(f'[WAITRESS] 清理 stale 锁 (PID={stale_pid} 已死)')
                            try:
                                os.unlink(_DB_LOCK_FILE)
                            except OSError:
                                pass
            except (OSError, ValueError):
                pass

        _db_lock_fd = open(_DB_LOCK_FILE, 'w')
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(_db_lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(_db_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _db_lock_fd.write(f"{os.getpid()}\n{time.time()}\n")
        _db_lock_fd.flush()
        return True
    except (BlockingIOError, IOError, OSError):
        return False


def _release_db_lock():
    """释放 DB 进程级文件锁。"""
    global _db_lock_fd
    if _db_lock_fd:
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(_db_lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(_db_lock_fd, fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            _db_lock_fd.close()
        except Exception:
            pass
        _db_lock_fd = None
    try:
        if os.path.exists(_DB_LOCK_FILE):
            os.unlink(_DB_LOCK_FILE)
    except OSError:
        pass


def _is_pid_alive(pid):
    """检查 PID 是否存活。"""
    if os.name == 'nt':
        import ctypes
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            return bool(ok) and exit_code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def _check_db_integrity_at_startup():
    """[DECORATIVE] 启动时 fail-fast integrity check, 损坏则不启动。"""
    db_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'meta', 'architecture.db'
    )
    if not os.path.exists(db_path):
        return  # 首次启动正常
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        result = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        if result and result[0] != 'ok':
            print(f'[WAITRESS][P0 启动失败] DB 完整性校验失败: {result[0]}')
            print(f'  DB 路径: {db_path}')
            print(f'  解决方案: python d:\\filework\\test.py --force-recover-db')
            sys.exit(1)
    except sqlite3.DatabaseError as e:
        print(f'[WAITRESS][P0 启动失败] DB 已损坏: {e}')
        print(f'  DB 路径: {db_path}')
        print(f'  解决方案: python d:\\filework\\test.py --force-recover-db')
        sys.exit(1)


# [FIX 2026-07-02] 启动前端口冲突预检
# 背景: 之前多次出现 vite 代理 (3011) 与后端实际端口 (3010) 不一致
#   导致前端 500, 但后端日志看起来正常.
# 修复: 启动前尝试绑定端口, 若被占用立即报错并打印占用进程.
def _check_port_available(port):
    """检测目标端口是否可用, 不可用时打印占用进程 PID + 命令行."""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(('0.0.0.0', port))
        sock.close()
        return True
    except OSError as e:
        sock.close()
        print(f'[WAITRESS][P0 启动失败] 端口 {port} 已被占用: {e}')
        # [诊断] 找出占用端口的进程
        try:
            import subprocess
            result = subprocess.run(
                ['powershell', '-NoProfile', '-Command',
                 f'Get-NetTCPConnection -State Listen -LocalPort {port} -ErrorAction SilentlyContinue | ForEach-Object {{ Get-CimInstance Win32_Process -Filter "ProcessId=$($_.OwningProcess)" | Select-Object ProcessId, CommandLine | Format-List | Out-String }}'],
                capture_output=True, text=True, timeout=5
            )
            if result.stdout.strip():
                print(f'  占用进程详情:')
                print('  ' + result.stdout.strip().replace('\n', '\n  '))
        except Exception:
            pass
        return False


# [DECORATIVE] v3.8: 启动前 hook
def _on_starting():
    print('[WAITRESS] Starting v3.18 (1 process × 8 threads + DB lock)')
    print(f'[WAITRESS] Bind: 0.0.0.0:{AGENT_PORT}')
    print(f'[WAITRESS] PID: {os.getpid()}')
    print(f'[WAITRESS] AGENT_PORT: {AGENT_PORT}')
    print(f'[WAITRESS] FLASK_PORT: {os.environ.get("FLASK_PORT", "not set")}')
    print(f'[WAITRESS] FLASK_DEBUG: {os.environ.get("FLASK_DEBUG", "not set")}')

    # [FIX 2026-07-02] 端口冲突预检
    if not _check_port_available(AGENT_PORT):
        print(f'  解决方案:')
        print(f'    1) 杀掉占用端口的进程, 或')
        print(f'    2) 设置不同的 AGENT_PORT (需同步修改 vite.config.js proxy target)')
        sys.exit(1)

    # [DECORATIVE] P0 防御检查
    _check_db_integrity_at_startup()

    # [DECORATIVE] 获取跨进程文件锁
    if not _acquire_db_lock():
        print(f'[WAITRESS][P0 启动失败] DB 锁被占用, 退出')
        print(f'  锁文件: {_DB_LOCK_FILE}')
        print(f'  解决方案: 杀掉所有 meta.server.py 进程后重试, 或删除锁文件')
        sys.exit(1)
    print(f'[WAITRESS] DB process lock acquired: {_DB_LOCK_FILE}')

    # 注册退出 hook
    atexit.register(_release_db_lock)
    try:
        signal.signal(signal.SIGTERM, lambda s, f: (_release_db_lock(), sys.exit(0)))
        signal.signal(signal.SIGINT, lambda s, f: (_release_db_lock(), sys.exit(0)))
    except (AttributeError, ValueError):
        pass  # Windows 不支持所有信号


_on_starting()


# [DECORATIVE] v3.8: 用 waitress 直接 serve Flask app
# 这一行让 waitress-serve 直接 import 时执行
from meta.server import create_app  # noqa: E402

# [DECORATIVE] v3.8: 关键修复 - create_app() 必须在 __main__ 之外
# 让 waitress-serve 也能 import 到 application
try:
    from meta.server import create_app
    application = create_app()
except Exception as e:
    print(f'[WAITRESS] Failed to create app: {e}')
    _release_db_lock()
    raise

print(f'[WAITRESS] App created: {application is not None}')

if __name__ == '__main__':
    import sys
    use_flask = os.environ.get('USE_FLASK_DEV') == '1'
    try:
        if use_flask:
            print('[WAITRESS] Using Flask dev server (USE_FLASK_DEV=1)')
            application.run(host='0.0.0.0', port=AGENT_PORT, debug=False, use_reloader=False)
        else:
            print('[WAITRESS] Starting waitress.serve()')
            from waitress import serve
            serve(
                application,
                host='0.0.0.0',
                port=AGENT_PORT,  # [DECORATIVE] v3.18: 来自 env AGENT_PORT
                threads=8,
                ident=f'bo_action_server_v3.18_port{AGENT_PORT}',
                # 调优
                channel_timeout=60,
                recv_bytes=65536,
                send_bytes=65536,
            )
    except Exception as e:
        print(f'[WAITRESS] Server ERROR: {type(e).__name__}: {e}')
        import traceback
        traceback.print_exc()
        raise
    finally:
        _release_db_lock()
