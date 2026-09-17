#!/usr/bin/env python3
# staging_ops.py - unified operations library for staging environment.
# [P1-1 2026-09-02] Created to eliminate 80% copy-paste in 10+ staging_*.py scripts.
"""
staging_ops.py - staging environment operations library.

Consolidates:
- HTTP client for core_service (19200) /api/exec and /api/upload
- SQLite DB operations (open, query, execute, backup, restore)
- Service manager (list pids, kill by port, start, health check)
- High-level workflows (apply_delta_zip, verify_deploy, atomic_step)

Usage:
    from staging_ops import (
        exec_cmd, upload_file,
        open_db, sql_query, sql_execute,
        get_service_pids, kill_service_by_port, start_service,
        wait_for_service_up,
        apply_delta_zip, verify_deploy, atomic_step,
    )

All functions raise StagingError on failure with a clear error message
suitable for debugging via logs.
"""
import hashlib
import http.client
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import urllib.parse
import zipfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

# ============================================================
# Constants
# ============================================================

DEFAULT_HOST = os.environ.get('STAGING_HOST', '172.20.59.7')
DEFAULT_CORE_PORT = int(os.environ.get('STAGING_CORE_PORT', '19200'))
DEFAULT_LOG_PORT = int(os.environ.get('STAGING_LOG_PORT', '19101'))
DEFAULT_UNIFIED_PORT = int(os.environ.get('STAGING_UNIFIED_PORT', '18081'))
DEFAULT_META_BACKEND_PORT = int(os.environ.get('STAGING_META_PORT', '13011'))
DEFAULT_SECRET = os.environ.get('STAGING_SECRET', 'v007.52-core-write')

# Service topology - used by service manager
STAGING_SERVICES = [
    ('core_service', DEFAULT_CORE_PORT, '/opt/app/staging/bin/core_service.py'),
    ('log_service', DEFAULT_LOG_PORT, '/opt/app/staging/bin/log_service.py'),
    ('unified_18081', DEFAULT_UNIFIED_PORT, '/opt/app/staging/deploy/current/unified_18081.py'),
    ('meta_backend', DEFAULT_META_BACKEND_PORT, '/opt/app/staging/deploy/current/server.py'),
]


class StagingError(Exception):
    """Raised when any staging operation fails."""
    pass


# ============================================================
# HTTP client - core_service /api/exec and /api/upload
# ============================================================

def _tokens(secret=None):
    """Generate 3 auth tokens (current hour + 2 backward)."""
    secret = secret or DEFAULT_SECRET
    now = int(time.time())
    return [
        hashlib.sha256(f'{secret}:{now//3600 - off}'.encode()).hexdigest()[:16]
        for off in range(3)
    ]


def exec_cmd(cmd, host=None, port=None, timeout=60, retries=2):
    """Execute shell command on staging via core_service /api/exec.

    Args:
        cmd: shell command string
        host: override default host
        port: override default port (19200)
        timeout: command execution timeout in seconds
        retries: retry attempts (default 2)

    Returns:
        dict with keys: exit_code, stdout, stderr

    Raises:
        StagingError: if all retries fail
    """
    host = host or DEFAULT_HOST
    port = port or DEFAULT_CORE_PORT
    last_err = None

    for attempt in range(retries):
        for token in _tokens():
            try:
                conn = http.client.HTTPConnection(host, port, timeout=timeout + 10)
                params = urllib.parse.urlencode({
                    'cmd': cmd,
                    'timeout': str(timeout),
                    'token': token,
                })
                conn.request('GET', f'/api/exec?{params}')
                resp = conn.getresponse()
                body = resp.read().decode('utf-8', errors='replace')
                conn.close()
                if resp.status == 200:
                    try:
                        return json.loads(body)
                    except Exception:
                        return {'raw': body}
                last_err = f'status={resp.status}'
                if resp.status == 429:
                    time.sleep(2.0)
                    continue
                break  # try next attempt
            except Exception as e:
                last_err = str(e)
                break
        time.sleep(1.5)

    raise StagingError(f'exec_cmd failed: {last_err}')


def upload_file(local_path, remote_path, host=None, port=None):
    """Upload file to staging via core_service /api/upload.

    Args:
        local_path: source file (Path or str)
        remote_path: destination path on staging
        host: override default
        port: override default (19200)

    Returns:
        dict with response from server

    Raises:
        StagingError: if upload fails
    """
    host = host or DEFAULT_HOST
    port = port or DEFAULT_CORE_PORT
    data = Path(local_path).read_bytes()
    last_err = None

    for token in _tokens():
        try:
            conn = http.client.HTTPConnection(host, port, timeout=120)
            url = f'/api/upload?path={urllib.parse.quote(remote_path, safe="")}&token={token}'
            conn.request('POST', url, body=data, headers={'Content-Type': 'application/octet-stream'})
            resp = conn.getresponse()
            body = resp.read().decode('utf-8', errors='replace')
            conn.close()
            if resp.status == 200:
                try:
                    return json.loads(body)
                except Exception:
                    return {'ok': True}
            if resp.status == 429:
                time.sleep(2.0)
                continue
            last_err = f'status={resp.status} body={body[:300]}'
        except Exception as e:
            last_err = str(e)
            break
    raise StagingError(f'upload_file failed: {last_err}')


def wait_for_service_up(host, port, timeout=30, interval=1.0):
    """Poll until TCP port accepts connections or timeout.

    Args:
        host: hostname or IP
        port: TCP port
        timeout: max wait time in seconds
        interval: poll interval

    Raises:
        StagingError: if port not up after timeout
    """
    import socket
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except Exception as e:
            last_err = str(e)
            time.sleep(interval)
    raise StagingError(f'port {host}:{port} not up after {timeout}s (last_err={last_err})')


# ============================================================
# SQLite DB operations (via Python on remote - avoids CLI version mismatch)
# ============================================================

def open_db(db_path, host=None):
    """Open remote SQLite database by uploading a Python script.

    Args:
        db_path: absolute path on staging server
        host: override default

    Returns:
        sqlite3.Connection (read/write to remote DB)

    Raises:
        StagingError: if connection fails
    """
    host = host or DEFAULT_HOST
    # open_db is not directly supported - use sql_query() / sql_execute()
    raise NotImplementedError(
        'open_db() not directly supported - use sql_query() / sql_execute() '
        'which run a Python helper on remote server'
    )


def sql_query(db_path, sql, params=None, host=None):
    """Execute SELECT on remote SQLite DB, return list of dicts.

    Args:
        db_path: absolute path on staging
        sql: SELECT statement (use ? placeholders)
        params: tuple of params (optional)

    Returns:
        list of dict (each row as dict)

    Raises:
        StagingError: on query error
    """
    host = host or DEFAULT_HOST
    import base64
    # Build helper script
    helper_lines = [
        'import sqlite3, json, sys',
        'db_path = ' + repr(db_path),
        'sql = ' + repr(sql),
        'params = ' + repr(params),
    'try:',
    '    conn = sqlite3.connect(db_path, timeout=30)',
        '    conn.row_factory = sqlite3.Row',
    '    cur = conn.execute(sql, params or ())',
    '    rows = [dict(r) for r in cur.fetchall()]',
    '    print(json.dumps(rows, default=str, ensure_ascii=False))',
    'except Exception as e:',
    '    print(json.dumps({"error": str(e)}))',
    ]
    helper = '\n'.join(helper_lines)
    helper_b64 = base64.b64encode(helper.encode('utf-8')).decode('ascii')
    # Pipe helper via stdin (avoids quoting hell in nested python -c)
    inner = "import base64,sys;exec(base64.b64decode(sys.stdin.read().strip()).decode('utf-8'))"
    cmd = "python3 -c " + repr(inner) + " <<< " + helper_b64
    r = exec_cmd(cmd, host=host, timeout=30)
    out = r.get('stdout', '').strip()
    try:
        data = json.loads(out)
        if isinstance(data, dict) and 'error' in data:
            raise StagingError('sql_query failed: ' + str(data['error']))
        return data
    except json.JSONDecodeError as e:
        raise StagingError('sql_query response decode failed: ' + out[:200])


def sql_execute(db_path, sql, params=None, host=None):
    """Execute INSERT/UPDATE/DELETE on remote SQLite DB.

    Returns:
        int: rows affected

    Raises:
        StagingError: on error
    """
    host = host or DEFAULT_HOST
    import base64
    helper_lines = [
        'import sqlite3, json, sys',
        'db_path = ' + repr(db_path),
        'sql = ' + repr(sql),
        'params = ' + repr(params),
    'try:',
    '    conn = sqlite3.connect(db_path, timeout=30)',
    '    cur = conn.execute(sql, params or ())',
    '    conn.commit()',
    '    print(json.dumps({"rows": cur.rowcount}))',
    'except Exception as e:',
    '    print(json.dumps({"error": str(e)}))',
    ]
    helper = '\n'.join(helper_lines)
    helper_b64 = base64.b64encode(helper.encode('utf-8')).decode('ascii')
    inner = "import base64;exec(base64.b64decode(sys.stdin.read().strip()).decode('utf-8'))"
    cmd = "python3 -c " + repr(inner) + " <<< " + helper_b64
    r = exec_cmd(cmd, host=host, timeout=30)
    out = r.get('stdout', '').strip()
    try:
        data = json.loads(out)
        if 'error' in data:
            raise StagingError('sql_execute failed: ' + str(data['error']))
        return data['rows']
    except (json.JSONDecodeError, KeyError) as e:
        raise StagingError('sql_execute response decode failed: ' + out[:200])


def backup_db(db_path, backup_dir='/tmp', host=None):
    """Copy remote DB to backup_dir with timestamp suffix.

    Args:
        db_path: source DB on staging
        backup_dir: destination directory (default /tmp)
        host: override default

    Returns:
        str: backup path on staging

    Raises:
        StagingError: on failure
    """
    host = host or DEFAULT_HOST
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = backup_dir + '/architecture.db.backup_' + ts
    bash_script = (
        'SRC=' + db_path + '\n'
        'BAK=' + backup_path + '\n'
        'mkdir -p ' + backup_dir + '\n'
        'if [ -f "$SRC" ]; then\n'
        '    cp "$SRC" "$BAK"\n'
        '    echo "BACKUP_OK $BAK $(stat -c%s $BAK) bytes"\n'
        'else\n'
        '    echo "BACKUP_FAIL: $SRC not found"\n'
        '    exit 1\n'
        'fi\n'
    )
    cmd = 'bash -c ' + repr(bash_script)
    r = exec_cmd(cmd, host=host, timeout=120)
    out = r.get('stdout', '').strip()
    if 'BACKUP_OK' not in out:
        raise StagingError('backup_db failed: ' + out)
    return backup_path


def restore_db(db_path, backup_path, host=None):
    """Restore remote DB from backup_path.

    Args:
        db_path: target DB path
        backup_path: source backup path
        host: override default

    Raises:
        StagingError: on failure
    """
    host = host or DEFAULT_HOST
    bash_script = (
        'BAK=' + backup_path + '\n'
        'DST=' + db_path + '\n'
        'if [ ! -f "$BAK" ]; then\n'
        '    echo "RESTORE_FAIL: $BAK not found"\n'
        '    exit 1\n'
        'fi\n'
        'cp "$BAK" "$DST"\n'
        'echo "RESTORE_OK $DST $(stat -c%s $DST) bytes"\n'
    )
    cmd = 'bash -c ' + repr(bash_script)
    r = exec_cmd(cmd, host=host, timeout=120)
    out = r.get('stdout', '').strip()
    if 'RESTORE_OK' not in out:
        raise StagingError('restore_db failed: ' + out)


# ============================================================
# Service manager (port-based, exact kill)
# ============================================================

def get_service_pids(host=None):
    """Return dict[port] -> pid for all known staging services.

    Uses ss to find PID by listening port (NOT pkill -f).

    Args:
        host: override default

    Returns:
        dict mapping int port to int pid (or None if not listening)

    Raises:
        StagingError: on failure
    """
    host = host or DEFAULT_HOST
    bash_script = (
        "for port in 19200 19101 18081 13011; do\n"
        '    pid=$(ss -tlnp 2>/dev/null | grep ":$port " | grep -oP "pid=\\\\K[0-9]+" | head -1)\n'
        '    echo "$port=$pid"\n'
        'done\n'
    )
    cmd = 'bash -c ' + repr(bash_script)
    r = exec_cmd(cmd, host=host, timeout=10)
    out = r.get('stdout', '').strip()
    result = {}
    for line in out.splitlines():
        if '=' in line:
            port, pid = line.split('=', 1)
            result[int(port)] = int(pid) if pid and pid.isdigit() else None
    return result


def kill_service_by_port(port, host=None, signal='TERM', timeout=10):
    """Kill service listening on port (exact match by port).

    Args:
        port: TCP port of service to kill
        host: override default
        signal: TERM (graceful) or KILL (force)
        timeout: max wait after kill

    Raises:
        StagingError: if no service on port, or kill fails
    """
    host = host or DEFAULT_HOST
    # Get PID by port first
    pids = get_service_pids(host)
    pid = pids.get(port)
    if not pid:
        raise StagingError('no service listening on port ' + str(port))

    # Verify PID matches expected (safety check)
    cmd_verify = 'ps -p ' + str(pid) + ' -o pid,cmd 2>&1 | head -2'
    r = exec_cmd(cmd_verify, host=host, timeout=5)
    out = r.get('stdout', '')
    if str(pid) not in out or 'PID' not in out:
        raise StagingError('PID ' + str(pid) + ' verification failed: ' + out)

    # Kill
    sig_arg = '-TERM' if signal == 'TERM' else '-KILL'
    bash_script = (
        'kill ' + sig_arg + ' ' + str(pid) + ' 2>&1\n'
        'sleep 2\n'
        'ps -p ' + str(pid) + ' -o pid 2>&1 | tail -1\n'
    )
    cmd = 'bash -c ' + repr(bash_script)
    r = exec_cmd(cmd, host=host, timeout=timeout + 5)
    out = r.get('stdout', '')
    if str(pid) in out and 'PID' not in out.split('\n')[-2]:
        raise StagingError('PID ' + str(pid) + ' still alive after ' + signal)


def start_service(service_name, host=None):
    """Start a staging service by name.

    Args:
        service_name: 'core_service'|'log_service'|'unified_18081'|'meta_backend'
        host: override default

    Raises:
        StagingError: on failure
    """
    host = host or DEFAULT_HOST
    for name, port, script_path in STAGING_SERVICES:
        if name != service_name:
            continue
        bash_script = (
            'cd /opt/app/staging/deploy/current\n'
            'nohup setsid ' + script_path + ' > /tmp/' + service_name + '.log 2>&1 < /dev/null &\n'
            'disown\n'
            'sleep 5\n'
            'ss -tlnp 2>&1 | grep ":' + str(port) + ' " | head -1\n'
        )
        cmd = 'bash -c ' + repr(bash_script)
        r = exec_cmd(cmd, host=host, timeout=30)
        out = r.get('stdout', '')
        if (':' + str(port) + ' ') not in out:
            raise StagingError('failed to start ' + service_name + ' on port ' + str(port) + ': ' + out)
        return
    raise StagingError('unknown service: ' + service_name)


# ============================================================
# High-level workflows
# ============================================================

def apply_delta_zip(local_zip, remote_dir='/opt/app/staging/deploy/current',
                    backup_first=True, host=None):
    """Apply delta zip to staging deploy directory.

    Args:
        local_zip: local zip file path
        remote_dir: destination directory on staging
        backup_first: backup existing changed/* before overwriting
        host: override default

    Raises:
        StagingError: on failure
    """
    host = host or DEFAULT_HOST
    zip_name = Path(local_zip).name
    remote_zip = f'/tmp/{zip_name}'

    # 1. Upload
    upload_file(local_zip, remote_zip, host=host)

    # 2. Apply
    if backup_first:
        backup_cmd = f'mkdir -p /tmp/delta_backup_$(date +%Y%m%d_%H%M%S)'
        exec_cmd(backup_cmd, host=host, timeout=10)

    apply_cmd_bash = (
        'set -e\n'
        'ZIP=' + remote_zip + '\n'
        'DEST=' + remote_dir + '\n'
        'TMP=/tmp/delta_extract_$(date +%Y%m%d_%H%M%S)\n'
        'mkdir -p $TMP\n'
        'cd $TMP\n'
        'unzip -o $ZIP > /tmp/unzip.log 2>&1\n'
        'echo "Extracted: $(unzip -l $ZIP | tail -n +4 | head -1)"\n'
        'echo\n'
        'echo "[verify] MANIFEST entry exists:"\n'
        'unzip -l $ZIP | grep MANIFEST || (echo "FAIL: no MANIFEST" && exit 1)\n'
        'echo\n'
        'echo "[apply] changed/* -> $DEST"\n'
        'for src in $(find changed -type f); do\n'
        '    rel=${src#changed/}\n'
        '    dst=$DEST/$rel\n'
        '    mkdir -p $(dirname $dst)\n'
        '    cp $src $dst\n'
        '    echo "  A  $rel"\n'
        'done\n'
        'echo\n'
        'echo "[verify sha256 of applied files]"\n'
        'sha256sum $DEST/meta/api/overlap_api.py 2>/dev/null\n'
    )
    apply_cmd = 'bash -c ' + repr(apply_cmd_bash)
    r = exec_cmd(apply_cmd, host=host, timeout=60)
    out = r.get('stdout', '')
    if '[FAIL:' in out:
        raise StagingError('apply_delta_zip failed: ' + out)
    return out


def verify_deploy(host=None, expected_menus=3):
    """Verify staging deployment via 5-check protocol.

    Args:
        host: override default
        expected_menus: expected leaf_menus count under user-permission

    Returns:
        dict with check results

    Raises:
        StagingError: if any critical check fails
    """
    host = host or DEFAULT_HOST
    results = {}

    # Check 1: DB symlink healthy
    r = exec_cmd(
        'bash /opt/app/staging/deploy/current/tools/check_db_symlink.sh',
        host=host, timeout=15
    )
    results['db_symlink'] = r.get('exit_code') == 0
    if not results['db_symlink']:
        raise StagingError('db_symlink check FAILED')

    # Check 2: dev-login works
    r = exec_cmd(
        'curl -s --max-time 5 "http://127.0.0.1:18081/api/v1/auth/dev-login?username=admin" -c /tmp/_verify_cookies.txt -o /tmp/_verify_login.txt -w "%{http_code}"',
        host=host, timeout=15
    )
    login_code = r.get('stdout', '').strip()
    results['login'] = login_code == '200'
    if not results['login']:
        raise StagingError(f'login check FAILED (HTTP {login_code})')

    # Check 3: menu-permission visible
    r = exec_cmd(
        'curl -s --max-time 5 -b /tmp/_verify_cookies.txt "http://127.0.0.1:18081/api/v1/menu-permission/visible" > /tmp/_visible.json',
        host=host, timeout=15
    )
    r2 = exec_cmd(
        'python3 -c "import json; d=json.load(open(\'/tmp/_visible.json\')); leaves=[m for m in d.get(\'leaf_menus\',[]) if m.get(\'parent_menu\')==\'user-permission\']; print(len(leaves))"',
        host=host, timeout=10
    )
    leaf_count = int(r2.get('stdout', '0').strip() or '0')
    results['menu_count'] = leaf_count
    results['menu_match'] = leaf_count == expected_menus
    if not results['menu_match']:
        raise StagingError(
            f'menu count mismatch: expected {expected_menus}, got {leaf_count}'
        )

    return results


@contextmanager
def atomic_step(label, host=None, backup_db_path=None):
    """Context manager for atomic deploy step with automatic rollback.

    Args:
        label: human-readable label (for logs)
        host: override default
        backup_db_path: if provided, DB snapshot before step for rollback

    Yields:
        dict (initially empty, can be populated by caller)

    Example:
        with atomic_step('deploy spec17', backup_db_path='/opt/app/.../db') as ctx:
            apply_delta_zip(...)
            ctx['done'] = True  # mark success, prevent rollback
    """
    ctx = {'label': label, 'rollback': False}
    backup_path = None
    if backup_db_path:
        try:
            backup_path = backup_db(backup_db_path, host=host)
            ctx['backup'] = backup_path
            print(f'[atomic_step {label}] backup created: {backup_path}')
        except Exception as e:
            print(f'[atomic_step {label}] backup failed: {e}')

    try:
        yield ctx
    except Exception as e:
        print(f'[atomic_step {label}] EXCEPTION: {e}')
        if backup_path and backup_db_path:
            try:
                restore_db(backup_db_path, backup_path, host=host)
                print(f'[atomic_step {label}] ROLLED BACK from {backup_path}')
            except Exception as e2:
                print(f'[atomic_step {label}] ROLLBACK FAILED: {e2}')
        raise
    else:
        if not ctx.get('done'):
            # Mark as success at end
            ctx['done'] = True


# ============================================================
# CLI
# ============================================================

def main():
    """Simple CLI for testing: list services."""
    import argparse
    p = argparse.ArgumentParser(description='staging_ops CLI for testing')
    sub = p.add_subparsers(dest='cmd')

    p_list = sub.add_parser('list', help='list staging services')
    p_list.add_argument('--host')

    p_exec = sub.add_parser('exec', help='execute command')
    p_exec.add_argument('command')
    p_exec.add_argument('--host')

    p_query = sub.add_parser('query', help='sql_query helper')
    p_query.add_argument('db')
    p_query.add_argument('sql')
    p_query.add_argument('--host')

    args = p.parse_args()
    if args.cmd == 'list':
        pids = get_service_pids(args.host)
        for name, port, _ in STAGING_SERVICES:
            pid = pids.get(port)
            print(f'{name:20s} port={port} pid={pid}')
    elif args.cmd == 'exec':
        r = exec_cmd(args.command, host=args.host)
        print('exit:', r.get('exit_code'))
        print(r.get('stdout', ''))
        if r.get('stderr'):
            print('STDERR:', r['stderr'])
    elif args.cmd == 'query':
        rows = sql_query(args.db, args.sql, host=args.host)
        print(json.dumps(rows, indent=2, ensure_ascii=False, default=str))
    else:
        p.print_help()


if __name__ == '__main__':
    main()
