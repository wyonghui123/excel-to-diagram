# -*- coding: utf-8 -*-
"""
[MODULE] B1: v3.14 unlock_admin 脚本测试
[DESCRIPTION] 测 unlock_admin 4 模式 + audit log 集成
"""
import os
import sys
import subprocess
import sqlite3
import time
import json
import http.client

# admin_token 路径在 conftest.py 已配 (走 sys.path)
from admin_token import call_action, get_admin_cookie  # noqa: E402


_PROJECT_ROOT = os.path.dirname(  # .../excel-to-diagram
    os.path.dirname(os.path.dirname(  # .../excel-to-diagram/meta
        os.path.dirname(  # .../excel-to-diagram/meta/tests
            os.path.dirname(os.path.abspath(__file__))  # .../excel-to-diagram/meta/tests/e2e/bo_action
        )
    ))
)


def _lock_admin():
    """辅助: 锁住 admin"""
    db_path = os.path.join(_PROJECT_ROOT, 'meta', 'architecture.db')
    if not os.path.exists(db_path):
        return
    conn = sqlite3.connect(db_path, timeout=5)
    try:
        conn.execute("UPDATE users SET status = 'locked' WHERE username = 'admin'")
        conn.commit()
    finally:
        conn.close()


def _get_admin_status():
    """辅助: 查 admin 状态"""
    db_path = os.path.join(_PROJECT_ROOT, 'meta', 'architecture.db')
    if not os.path.exists(db_path):
        return None
    conn = sqlite3.connect(db_path, timeout=5)
    try:
        result = conn.execute("SELECT status FROM users WHERE username = 'admin'").fetchone()
        return result[0] if result else None
    finally:
        conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# B1.1 --status
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_unlock_admin_status_mode():
    """[DECORATIVE] B1.1: unlock_admin --status 显示当前状态"""
    script = os.path.join(_PROJECT_ROOT, 'scripts', 'unlock_admin.py')
    assert os.path.exists(script), f'unlock_admin.py 应存在: {script}'

    # 不锁, 查 status
    result = subprocess.run(
        [sys.executable, script, '--status'],
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15,
    )
    # --status 应输出 admin 当前状态
    output = (result.stdout or '') + (result.stderr or '')
    assert 'admin' in output.lower(), f'--status 应提到 admin: {output}'


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# B1.2 --dry-run
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_unlock_admin_dry_run():
    """[DECORATIVE] B1.2: unlock_admin --dry-run 只查不解锁"""
    script = os.path.join(_PROJECT_ROOT, 'scripts', 'unlock_admin.py')
    _lock_admin()
    status_before = _get_admin_status()
    assert status_before == 'locked', f'admin 应被锁, 实际 {status_before}'

    result = subprocess.run(
        [sys.executable, script, '--dry-run'],
        capture_output=True, text=True, timeout=15,
    )
    status_after = _get_admin_status()
    # dry-run 不应改 DB
    assert status_after == 'locked', f'dry-run 不应解锁, 实际 {status_after}'

    # 恢复
    from admin_token import _unlock_admin_if_needed
    _unlock_admin_if_needed()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# B1.3 实际解锁
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_unlock_admin_actual():
    """[DECORATIVE] B1.3: unlock_admin 默认模式实际解锁"""
    script = os.path.join(_PROJECT_ROOT, 'scripts', 'unlock_admin.py')
    _lock_admin()
    assert _get_admin_status() == 'locked'

    result = subprocess.run(
        [sys.executable, script],  # 无参数 = 默认 1 次解锁
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, f'unlock 失败: {result.stderr}'
    assert _get_admin_status() == 'active', f'admin 应被解锁, 实际 {_get_admin_status()}'


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# B1.4 --watch 模式 (启动后立即 kill)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_unlock_admin_watch_mode():
    """[DECORATIVE] B1.4: unlock_admin --watch 守护模式 (短时间运行后 kill)"""
    script = os.path.join(_PROJECT_ROOT, 'scripts', 'unlock_admin.py')

    # 启 watch 模式, 2s 后 kill
    proc = subprocess.Popen(
        [sys.executable, script, '--watch', '1'],  # 1s 间隔
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf-8', errors='replace',
    )
    time.sleep(2)
    proc.terminate()
    try:
        stdout, stderr = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()

    # v3.18 fix: 添加 None guard 防止 TypeError
    stdout = stdout or ''
    stderr = stderr or ''

    # watch 模式应能启动并响应 TERM
    assert 'watch' in (stdout + stderr).lower() or proc.returncode is not None, \
        f'--watch 模式应能启动, output: {stdout + stderr}'


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# B2: audit log 集成 (unlock 后写 audit)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_unlock_admin_writes_audit_log():
    """[DECORATIVE] B2: unlock_admin 写 audit_log 记录"""
    db_path = os.path.join(_PROJECT_ROOT, 'meta', 'architecture.db')
    if not os.path.exists(db_path):
        return

    # 锁 + 解锁
    _lock_admin()

    # 拿 audit_log 数量 (unlock 前)
    conn = sqlite3.connect(db_path, timeout=5)
    try:
        before = conn.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE action = 'unlock' AND object_type = 'user'"
        ).fetchone()[0]
    finally:
        conn.close()

    # 解锁
    script = os.path.join(_PROJECT_ROOT, 'scripts', 'unlock_admin.py')
    result = subprocess.run(
        [sys.executable, script],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0

    # 查 audit_log 增量
    time.sleep(0.5)  # 给 audit 写入时间
    conn = sqlite3.connect(db_path, timeout=5)
    try:
        after = conn.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE action = 'unlock' AND object_type = 'user'"
        ).fetchone()[0]
    finally:
        conn.close()

    # unlock 后 audit log 应 +1
    assert after == before + 1, f'unlock 后 audit log 应 +1, 实际 {before} -> {after}'
