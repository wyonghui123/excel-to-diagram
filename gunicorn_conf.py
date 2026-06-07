# -*- coding: utf-8 -*-
"""
Gunicorn config (v3.8 + v3.18 SQLite P0 保护)
========================

方案 A: 单 worker + 多线程 (8 线程)
- 避开 SQLite fork 损坏 DB 风险
- 满足多智能体 / 多端点并行需求
- SSE 流式响应正常工作

[WARNING] v3.18 P0 警告:
  生产环境同样使用 SQLite (architecture.db)。
  workers 必须 = 1, 严禁 = 2 或更多!
  多 worker 会导致 SQLite WAL 损坏 (database disk image is malformed)。
  本配置已加 PID 文件锁 + 启动时互斥检查，违反会被自动 abort。

Usage:
    gunicorn -c gunicorn_conf.py meta.server:app
"""
import multiprocessing
import os
import sys
import time
import sqlite3

# 跨平台文件锁
if os.name == 'nt':
    import msvcrt
else:
    import fcntl

bind = '0.0.0.0:3010'
workers = 1                                       # [DECORATIVE] v3.8: 单 worker 避开 SQLite fork
threads = 8                                       # [DECORATIVE] v3.8: 8 线程并行
worker_class = 'gthread'                          # 线程 worker
timeout = 60                                      # 请求超时 60s
graceful_timeout = 30                             # graceful shutdown
keepalive = 5                                     # keep-alive 5s
max_requests = 0                                  # 不限 worker 处理数
max_requests_jitter = 0

# 访问日志
accesslog = '-'                                    # stdout
errorlog = '-'                                     # stderr
loglevel = 'info'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s)" "%(a)s" %(L)s'

# 进程名
proc_name = 'bo_action_server'

# 重载 (dev 用)
reload = False                                    # 生产不重载; dev 时改 True
reload_engine = 'inotify' if os.name != 'nt' else 'auto'

# 环境变量
raw_env = [
    'FLASK_DEBUG=false',                          # 必须 false (FR-001 DB 保护)
    'PYTHONIOENCODING=utf-8',
    'PYTHONUNBUFFERED=1',
]


# [DECORATIVE] v3.18: PID 文件锁 - 防止多 gunicorn 实例同时打开 architecture.db
_DB_LOCK_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'meta', '.architecture.lock'
)


def _acquire_db_lock():
    """获取 DB 进程级文件锁 (跨所有 gunicorn/waitress/pytest 实例)。

    Windows 使用 msvcrt.locking (LK_NBLCK = 非阻塞)
    Linux 使用 fcntl.flock (LOCK_EX | LOCK_NB)
    """
    try:
        lock_fd = open(_DB_LOCK_FILE, 'w')
        if os.name == 'nt':
            # LK_NBLCK = 2 (Windows msvcrt)
            msvcrt.locking(lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # 写入当前 PID + 时间戳
        lock_fd.write(f"{os.getpid()}\n{time.time()}\n")
        lock_fd.flush()
        # 保存 fd 在全局,防止 GC 释放锁
        _acquire_db_lock._fd = lock_fd
        return True
    except (BlockingIOError, IOError, OSError):
        return False


def _release_db_lock():
    """释放 DB 进程级文件锁。"""
    try:
        fd = getattr(_acquire_db_lock, '_fd', None)
        if fd:
            try:
                if os.name == 'nt':
                    msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_UN)
            except Exception:
                pass
            fd.close()
        try:
            os.unlink(_DB_LOCK_FILE)
        except OSError:
            pass
    except Exception:
        pass


def _check_workers_safe():
    """[DECORATIVE] P0 防御: 阻止 workers > 1 启动, 防止 SQLite 损坏。"""
    if workers > 1:
        sys.stderr.write(
            f'\n'
            f'╔══════════════════════════════════════════════════════════╗\n'
            f'║  [P0 启动失败] workers={workers} 会导致 SQLite 损坏!   ║\n'
            f'║  生产环境使用 SQLite, 多 worker 并发写会破坏 WAL.        ║\n'
            f'║  必须设置 workers=1 (本配置默认就是 1).                  ║\n'
            f'║  如果需要更高并发, 请改用 PostgreSQL 适配器.             ║\n'
            f'╚══════════════════════════════════════════════════════════╝\n'
        )
        sys.stderr.flush()
        sys.exit(1)


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
            sys.stderr.write(
                f'\n[P0 启动失败] DB 完整性校验失败: {result[0]}\n'
                f'  DB 路径: {db_path}\n'
                f'  解决方案: python d:\\filework\\test.py --force-recover-db\n'
            )
            sys.exit(1)
    except sqlite3.DatabaseError as e:
        sys.stderr.write(
            f'\n[P0 启动失败] DB 已损坏: {e}\n'
            f'  DB 路径: {db_path}\n'
            f'  解决方案: python d:\\filework\\test.py --force-recover-db\n'
        )
        sys.exit(1)


# [DECORATIVE] v3.8: 启动时 hook
def on_starting(server):
    print('[GUNICORN] Starting v3.18 (1 worker × 8 threads, gthread + DB lock)')
    print(f'[GUNICORN] Bind: {bind}')
    print(f'[GUNICORN] FLASK_DEBUG: {os.environ.get("FLASK_DEBUG", "not set")}')

    # [DECORATIVE] P0 防御检查
    _check_workers_safe()
    _check_db_integrity_at_startup()

    # [DECORATIVE] 获取跨进程文件锁
    if not _acquire_db_lock():
        sys.stderr.write(
            f'\n[P0 启动失败] 另一个 gunicorn/waitress 实例已持有 DB 锁!\n'
            f'  锁文件: {_DB_LOCK_FILE}\n'
            f'  解决方案: 杀掉所有 meta.server.py 进程后重试, 或删除锁文件\n'
        )
        sys.exit(1)
    print(f'[GUNICORN] DB process lock acquired: {_DB_LOCK_FILE}')


def when_ready(server):
    print('[GUNICORN] Ready to serve requests')


def worker_int(worker):
    print(f'[GUNICORN] Worker {worker.pid} interrupted')


def pre_request(worker, req):
    # 仅 debug 模式下打印
    if os.environ.get('GUNICORN_DEBUG', 'false') == 'true':
        print(f'[GUNICORN] {req.method} {req.path}')


def post_request(worker, req, environ, resp):
    pass


def on_exit(server):
    """[DECORATIVE] 退出时释放 DB 锁"""
    _release_db_lock()
    print('[GUNICORN] DB process lock released')
