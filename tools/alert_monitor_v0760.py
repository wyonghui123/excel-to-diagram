"""alert_monitor_v0760.py - V007.60 扩展: 分层监控 + 应用层健康 (2026-07-16)

新增检查项 (P0):
- real_health  : log_service /api/health 真实业务状态 (vs 仅端口)
- db_health    : /api/db/health integrity + wal + busy_ms
- db_can_write : /api/db/can_write (写权限/文件锁)
- disk_errors  : /api/disk/errors (dmesg + iostat)
- disk_check   : /api/disk/check (综合打分)
- disk_usage   : log_service /api/system 拿磁盘使用率
- journal_err  : 最近 5min journalctl ERROR/Traceback 计数

分层周期:
- Layer 1 [每 5 分钟]: real_health, db_can_write, journal_err
- Layer 2 [每 15 分钟]: db_health, disk_errors
- Layer 3 [每 30 分钟]: disk_check, disk_usage

设计:
- 每个检查注册到 CHECKS 字典, 自带 interval_sec
- state 里存每项的 last_run_ts / last_fail / last_msg
- run_once 调用 should_run(check_name, state) 判断是否到时间
- 失败的检查项聚合, 走和 V007.59 同样的 alert 通道 (lark_app)

用法:
    # 单次 (V007.60 模式)
    python tools/alert_monitor_v0760.py --check-now

    # 守护模式 (每 5 分钟)
    python tools/alert_monitor_v0760.py --daemon

    # 列出所有检查项
    python tools/alert_monitor_v0760.py --list-checks
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error

# 复用 V007.59 的 IM/alert 逻辑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from alert_monitor import (
    log as _orig_log, send_im, format_alert, format_recovery,
    DEFAULT_CONFIG, check_yonaa_services, check_systemd_via_agent, check_log_service_via_agent,
)


# Wrapper for log(): also writes to file if --log-file is given
def log(msg: str):
    _orig_log(msg)
    _log_to_file(msg)

# === 复用 yonaa_exec (拉 SSH 数据) ===
try:
    from yonaa_exec import yexec, sleep_between
    HAS_YEXEC = True
except ImportError:
    HAS_YEXEC = False

# ============================================================
# V007.60 检查项注册表
# ============================================================
# 通用 helper
def _http_get_local(host, port, path, timeout=5):
    """直接 HTTP GET (用于调 log_service 自己的端点)"""
    import http.client
    try:
        conn = http.client.HTTPConnection(host, port, timeout=timeout + 2)
        conn.request('GET', path)
        resp = conn.getresponse()
        body = resp.read().decode('utf-8', errors='replace')
        return resp.status, body
    except Exception as e:
        return 0, str(e)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def check_real_health():
    """Layer 1 [5min] - log_service 真实业务健康 (vs 仅端口 200)

    端口 200 不代表业务 ok. /api/health 返回 {"ok": true} 才算真健康.
    """
    results = []
    for port, label in [(9101, 'prod'), (19101, 'staging')]:
        status, body = _http_get_local('172.20.59.7', port, '/api/health', timeout=4)
        name = f'real_health:log_service:{label}'
        if status == 0:
            results.append({'name': name, 'ok': False, 'msg': f'connect fail: {body[:60]}'})
            continue
        if status != 200:
            results.append({'name': name, 'ok': False, 'msg': f'HTTP {status}'})
            continue
        try:
            data = json.loads(body)
        except Exception:
            results.append({'name': name, 'ok': False, 'msg': f'non-json: {body[:60]}'})
            continue
        ok = data.get('ok', False)
        uptime = data.get('uptime', 0)
        results.append({
            'name': name,
            'ok': ok,
            'msg': f'ok={ok} uptime={uptime}s' if ok else f'BUSINESS DOWN: {data}',
        })
    return results


def check_db_health():
    """Layer 2 [15min] - SQLite 完整性检查 (直接调 log_service HTTP, 不用 SSH)"""
    results = []
    for ls_port, label in [(9101, 'prod'), (19101, 'staging')]:
        name = f'db_health:log_service:{label}'
        status, body = _http_get_local('172.20.59.7', ls_port, '/api/db/health', timeout=8)
        if status != 200:
            results.append({'name': name, 'ok': False, 'msg': f'HTTP {status} body={body[:120]}'})
            continue
        try:
            data = json.loads(body)
        except Exception:
            results.append({'name': name, 'ok': False, 'msg': f'non-json body (truncated): {body[:120]}'})
            continue
        integrity = data.get('integrity', 'unknown')
        size_mb = data.get('size_mb', 0)
        wal_mb = data.get('wal_mb', 0)
        # busy_ms 是配置的超时 (log_service 启动时设的 PRAGMA busy_timeout)
        # 不是真锁竞争. 真正的锁等待在 /api/db/metrics 里 (如果有)
        # 简化: 只看 integrity + wal
        ok = (integrity == 'ok')
        if ok and wal_mb > 100:
            ok = False
            msg = f'integrity=ok BUT wal_mb={wal_mb:.1f} > 100 (no checkpoint)'
        else:
            msg = f'integrity={integrity} size={size_mb:.1f}MB wal={wal_mb:.1f}MB'
        results.append({'name': name, 'ok': ok, 'msg': msg, 'extra': data})
    return results


def check_db_can_write():
    """Layer 1 [5min] - SQLite 是否可写 (锁/权限/磁盘)"""
    results = []
    for port, label in [(9101, 'prod'), (19101, 'staging')]:
        name = f'db_can_write:log_service:{label}'
        status, body = _http_get_local('172.20.59.7', port, '/api/db/can_write', timeout=5)
        if status != 200:
            results.append({'name': name, 'ok': False, 'msg': f'HTTP {status} body={body[:80]}'})
            continue
        try:
            data = json.loads(body)
        except Exception:
            results.append({'name': name, 'ok': False, 'msg': f'non-json: {body[:80]}'})
            continue
        can_write = data.get('can_write', False)
        errors = data.get('errors', [])
        results.append({
            'name': name,
            'ok': can_write and not errors,
            'msg': f'can_write={can_write} errors={errors[:3]}' if errors else f'can_write={can_write} mode={data.get("mode")}',
        })
    return results


def check_disk_errors():
    """Layer 2 [15min] - 磁盘 IO 错误 (dmesg + iostat)"""
    if not HAS_YEXEC:
        return [{'name': 'disk_errors', 'ok': False, 'msg': 'yonaa_exec unavailable'}]
    results = []
    for port, label in [(9101, 'prod'), (19101, 'staging')]:
        name = f'disk_errors:log_service:{label}'
        status, body = _http_get_local('172.20.59.7', port, '/api/disk/errors', timeout=5)
        if status != 200:
            results.append({'name': name, 'ok': False, 'msg': f'HTTP {status}'})
            continue
        try:
            data = json.loads(body)
        except Exception:
            results.append({'name': name, 'ok': False, 'msg': f'non-json: {body[:80]}'})
            continue
        has_errors = data.get('has_errors', True)
        total_errors = data.get('total_errors', 0)
        status_str = data.get('status', 'unknown')
        results.append({
            'name': name,
            'ok': not has_errors,
            'msg': f'total_errors={total_errors} status={status_str}' if not has_errors
                  else f'DISK IO ERRORS: {total_errors} (samples: {list((data.get("samples") or {}).keys())[:3]})',
        })
    return results


def check_disk_check():
    """Layer 3 [30min] - 综合磁盘检查 (score + signals)"""
    if not HAS_YEXEC:
        return [{'name': 'disk_check', 'ok': False, 'msg': 'yonaa_exec unavailable'}]
    results = []
    for port, label in [(9101, 'prod'), (19101, 'staging')]:
        name = f'disk_check:log_service:{label}'
        status, body = _http_get_local('172.20.59.7', port, '/api/disk/check', timeout=8)
        if status != 200:
            results.append({'name': name, 'ok': False, 'msg': f'HTTP {status}'})
            continue
        try:
            data = json.loads(body)
        except Exception:
            results.append({'name': name, 'ok': False, 'msg': f'non-json: {body[:80]}'})
            continue
        score = data.get('score', 0)
        has_issues = data.get('has_issues', True)
        status_str = data.get('status', 'unknown')
        issues = data.get('issues', [])
        results.append({
            'name': name,
            'ok': not has_issues and score >= 80,
            'msg': f'score={score} status={status_str} issues={issues[:3]}' if has_issues
                  else f'score={score} status={status_str} (healthy)',
        })
    return results


def check_disk_usage():
    """Layer 3 [30min] - 磁盘使用率 (从 /api/system 取)"""
    results = []
    for port, label in [(9101, 'prod'), (19101, 'staging')]:
        name = f'disk_usage:log_service:{label}'
        status, body = _http_get_local('172.20.59.7', port, '/api/system', timeout=5)
        if status != 200:
            results.append({'name': name, 'ok': False, 'msg': f'HTTP {status}'})
            continue
        try:
            data = json.loads(body)
        except Exception:
            results.append({'name': name, 'ok': False, 'msg': f'non-json: {body[:80]}'})
            continue
        disk = data.get('disk', {})
        total_gb = disk.get('total_gb', 0)
        free_gb = disk.get('free_gb', 0)
        if total_gb <= 0:
            results.append({'name': name, 'ok': False, 'msg': f'invalid disk data: {disk}'})
            continue
        used_pct = (1 - free_gb / total_gb) * 100
        # 阈值: 85% warn, 95% fail (支持环境变量覆盖, 演练用)
        warn_pct = float(os.environ.get('DISK_WARN_PCT', '85'))
        fail_pct = float(os.environ.get('DISK_FAIL_PCT', '95'))
        ok = used_pct < warn_pct
        if used_pct >= fail_pct:
            ok = False
            msg = f'CRITICAL used={used_pct:.1f}% free={free_gb:.1f}GB total={total_gb:.1f}GB (>{fail_pct}%)'
        elif used_pct >= warn_pct:
            ok = False  # 强制告警
            msg = f'WARNING used={used_pct:.1f}% free={free_gb:.1f}GB total={total_gb:.1f}GB (>{warn_pct}%)'
        else:
            msg = f'used={used_pct:.1f}% free={free_gb:.1f}GB total={total_gb:.1f}GB'
        results.append({'name': name, 'ok': ok, 'msg': msg})
    return results


def check_journal_errors():
    """Layer 1 [5min] - log_service journal 最近 5min ERROR/Traceback 数"""
    if not HAS_YEXEC:
        return [{'name': 'journal_errors', 'ok': False, 'msg': 'yonaa_exec unavailable'}]
    results = []
    for unit_suffix, label, core_port in [
        ('log_service_prod', 'prod', 9200),
        ('log_service_staging', 'staging', 19200),
    ]:
        name = f'journal_errors:{label}'
        r = yexec(
            f"journalctl -u {unit_suffix}.service --since '5 minutes ago' --no-pager 2>&1 | grep -cE '(Traceback|ERROR|CRITICAL|FATAL)'",
            port=core_port, secret='prod_write', timeout=12)
        if r.get('error'):
            results.append({'name': name, 'ok': False, 'msg': f"exec fail: {r.get('reason', r)[:80]}"})
            sleep_between()
            continue
        try:
            count = int((r.get('stdout') or '0').strip() or '0')
        except ValueError:
            count = -1
        # 阈值: 0=OK, 1-5=WARN(仍 OK), >5=FAIL
        ok = count <= 5
        if count == 0:
            msg = 'no errors in 5min'
        elif count <= 5:
            msg = f'WARN: {count} errors in 5min'
        else:
            msg = f'ALERT: {count} errors in 5min (>5 threshold)'
        results.append({'name': name, 'ok': ok, 'msg': msg, 'extra': {'count': count}})
        sleep_between()
    return results


# ============================================================
# V007.61 用户使用异常监控 (按接口/错误类型分组)
# ============================================================
# 直接复用 _probe_awk_filter 模块
import re as _re
from collections import Counter as _Counter
from yonaa_exec import yuploaderun as _yuploaderun

_HTTP_5XX_RE = _re.compile(r'"(\w+) (\S+) HTTP/[\d.]+" 5(\d\d)')
_HTTP_CODE_RE = _re.compile(r'HTTP/[\d.]+" (\d{3})')
_IGNORED_EXC = {
    'werkzeug.exceptions.NotFound',
    'werkzeug.exceptions.MethodNotAllowed',
    'ConnectionResetError',
    'BrokenPipeError',
    'ConnectionAbortedError',
}
_IGNORED_PATHS = ('/health', '/api/health', '/favicon.ico')


def _v0761_upload_filter(log_path: str, minutes: int, port: int = 9200) -> dict:
    """Upload + run a Python filter script to yonaa, return stdout."""
    import tempfile as _tmp
    script_content = (
        "import sys\n"
        "from datetime import datetime, timedelta\n"
        f"minutes = {minutes}\n"
        "log_path = sys.argv[1] if len(sys.argv) > 1 else None\n"
        "if not log_path:\n"
        "    sys.stderr.write('usage: filter.py <log_path> [minutes=5]\\n')\n"
        "    sys.exit(1)\n"
        f"cutoff = datetime.now() - timedelta(minutes={minutes})\n"
        "def _parse_ts(line):\n"
        "    try:\n"
        "        return datetime.strptime(line[:19], '%Y-%m-%d %H:%M:%S')\n"
        "    except Exception:\n"
        "        return None\n"
        "kept = []\n"
        "try:\n"
        "    with open(log_path, 'r', encoding='utf-8', errors='replace') as f:\n"
        "        for line in f:\n"
        "            ts = _parse_ts(line)\n"
        "            if ts is not None and ts >= cutoff:\n"
        "                kept.append(line)\n"
        "except Exception as e:\n"
        "    sys.stderr.write(f'read fail: {e}\\n')\n"
        "    sys.exit(1)\n"
        "sys.stdout.write(''.join(kept[-3000:]))\n"
    )
    with _tmp.NamedTemporaryFile(mode='w', suffix='_v0761_filter.py', delete=False, encoding='utf-8') as f:
        f.write(script_content)
        local_script = f.name
    try:
        from yonaa_exec import yupload as _yu
        remote_script = '/tmp/_v0761_filter.py'
        up = _yu(local_script, remote_path=remote_script, port=port, secret='prod_write')
        if up.get('error'):
            return up
        r = yexec(f'python3 {remote_script} {log_path}; rm -f {remote_script}',
                  port=port, secret='prod_write', timeout=20)
        return r
    finally:
        try:
            os.unlink(local_script)
        except Exception:
            pass


def _v0761_parse_backend(lines: list) -> dict:
    """Parse backend lines, group errors."""
    http_errors = _Counter()
    traceback_types = _Counter()
    for line in lines:
        m = _HTTP_5XX_RE.search(line)
        if m:
            method, path, code = m.group(1), m.group(2), '5' + m.group(3)
            if any(path.startswith(p) for p in _IGNORED_PATHS):
                continue
            http_errors[(method, path, code)] += 1
            continue
        m2 = _re.search(r'([A-Za-z_][\w]*\.[A-Z][\w]*(?:Error|Exception|Interrupt)):', line)
        if m2:
            exc = m2.group(1)
            if exc not in _IGNORED_EXC:
                traceback_types[exc] += 1
            continue
        m3 = _re.search(r'\b([A-Z][\w]*(?:Error|Exception|Interrupt)):', line)
        if m3:
            exc = m3.group(1)
            if exc not in _IGNORED_EXC:
                traceback_types[exc] += 1
    return {
        'http_errors': {f'{m} {p} -> {c}': cnt for (m, p, c), cnt in http_errors.items()},
        'traceback_types': dict(traceback_types),
        'total_http_errors': sum(http_errors.values()),
        'total_tracebacks': sum(traceback_types.values()),
    }


def _v0761_parse_core_service(lines: list) -> dict:
    traceback_types = _Counter()
    http_errors = _Counter()
    for line in lines:
        m = _HTTP_CODE_RE.search(line)
        if m and m.group(1).startswith('5'):
            pm = _re.search(r'"(\w+) (\S+) HTTP/[\d.]+"', line)
            if pm:
                http_errors[(pm.group(1), pm.group(2), m.group(1))] += 1
        m2 = _re.search(r'([A-Za-z_][\w]*\.[A-Z][\w]*(?:Error|Exception|Interrupt)):', line)
        if m2:
            exc = m2.group(1)
            if exc not in _IGNORED_EXC:
                traceback_types[exc] += 1
            continue
        m3 = _re.search(r'\b([A-Z][\w]*(?:Error|Exception|Interrupt)):', line)
        if m3:
            exc = m3.group(1)
            if exc not in _IGNORED_EXC:
                traceback_types[exc] += 1
    return {
        'http_errors': {f'{m} {p} -> {c}': cnt for (m, p, c), cnt in http_errors.items()},
        'traceback_types': dict(traceback_types),
        'total_http_errors': sum(http_errors.values()),
        'total_tracebacks': sum(traceback_types.values()),
    }


def check_backend_err():
    """L1 [5min] - backend.log 最近 5min 的 5xx + Traceback (按接口分组)

    prod:   /opt/app/shared/logs/backend.log
    staging: /opt/app/staging/logs/backend.log
    """
    if not HAS_YEXEC:
        return [{'name': 'backend_err', 'ok': False, 'msg': 'yonaa_exec unavailable'}]
    results = []
    targets = [
        ('/opt/app/shared/logs/backend.log', 'prod', 9200),
        ('/opt/app/staging/logs/backend.log', 'staging', 19200),
    ]
    threshold = int(os.environ.get('BACKEND_ERR_THRESHOLD', '3'))
    for log_path, label, port in targets:
        name = f'backend_err:{label}'
        r = _v0761_upload_filter(log_path, 15, port=port)
        if r.get('error'):
            results.append({'name': name, 'ok': False, 'msg': f"exec fail: {r.get('reason', r)[:200]}"})
            sleep_between()
            continue
        lines = (r.get('stdout') or '').splitlines()
        parsed = _v0761_parse_backend(lines)
        total = parsed['total_http_errors'] + parsed['total_tracebacks']
        ok = total < threshold
        if total == 0:
            msg = f'no errors in last 5min (scanned {len(lines)} lines)'
        else:
            details = []
            for key, cnt in sorted(parsed['http_errors'].items(), key=lambda x: -x[1])[:3]:
                details.append(f'{key} ({cnt}x)')
            for exc, cnt in sorted(parsed['traceback_types'].items(), key=lambda x: -x[1])[:3]:
                details.append(f'{exc} ({cnt}x)')
            msg = f'{total} errors in 5min (>{threshold-1} threshold): ' + '; '.join(details)
        results.append({'name': name, 'ok': ok, 'msg': msg[:500], 'extra': parsed})
        sleep_between()
    return results


def check_core_service_err():
    """L1 [5min] - core_service.log 最近 5min 的 Traceback (按类型分组)"""
    if not HAS_YEXEC:
        return [{'name': 'core_service_err', 'ok': False, 'msg': 'yonaa_exec unavailable'}]
    results = []
    targets = [
        ('/var/log/core_service.log', 'prod', 9200),
        ('/var/log/core_service_staging.log', 'staging', 19200),
    ]
    threshold = int(os.environ.get('CORE_SVC_ERR_THRESHOLD', '1'))
    for log_path, label, port in targets:
        name = f'core_service_err:{label}'
        r = _v0761_upload_filter(log_path, 15, port=port)
        if r.get('error'):
            results.append({'name': name, 'ok': False, 'msg': f"exec fail: {r.get('reason', r)[:80]}"})
            sleep_between()
            continue
        lines = (r.get('stdout') or '').splitlines()
        parsed = _v0761_parse_core_service(lines)
        total = parsed['total_http_errors'] + parsed['total_tracebacks']
        ok = total < threshold
        if total == 0:
            msg = f'no errors in last 5min (scanned {len(lines)} lines)'
        else:
            details = []
            for exc, cnt in sorted(parsed['traceback_types'].items(), key=lambda x: -x[1])[:3]:
                details.append(f'{exc} ({cnt}x)')
            for key, cnt in sorted(parsed['http_errors'].items(), key=lambda x: -x[1])[:3]:
                details.append(f'{key} ({cnt}x)')
            msg = f'{total} errors in 5min (>{threshold-1} threshold): ' + '; '.join(details)
        results.append({'name': name, 'ok': ok, 'msg': msg[:500], 'extra': parsed})
        sleep_between()
    return results


# ============================================================
# 检查注册表
# ============================================================
CHECKS = {
    'real_health':       {'fn': check_real_health,        'interval_sec': 300,  'severity': 'P0'},   # 5min
    'db_can_write':      {'fn': check_db_can_write,       'interval_sec': 300,  'severity': 'P0'},   # 5min
    'journal_err':       {'fn': check_journal_errors,     'interval_sec': 300,  'severity': 'P0'},   # 5min
    'backend_err':       {'fn': check_backend_err,        'interval_sec': 300,  'severity': 'P0'},   # 5min (V007.61)
    'core_service_err':  {'fn': check_core_service_err,   'interval_sec': 300,  'severity': 'P0'},   # 5min (V007.61)
    'db_health':         {'fn': check_db_health,          'interval_sec': 900,  'severity': 'P0'},   # 15min
    'disk_errors':       {'fn': check_disk_errors,        'interval_sec': 900,  'severity': 'P0'},   # 15min
    'disk_check':        {'fn': check_disk_check,         'interval_sec': 1800, 'severity': 'P0'},   # 30min
    'disk_usage':        {'fn': check_disk_usage,         'interval_sec': 1800, 'severity': 'P0'},   # 30min
}


def should_run(check_name, state, now):
    """判断一个检查项是否该跑"""
    meta = CHECKS[check_name]
    interval = meta['interval_sec']
    last_run = state.get('check_last_run', {}).get(check_name, 0)
    return (now - last_run) >= interval


def load_v0760_state(state_path):
    """加载 V007.60 状态 (兼容 V007.59 state)"""
    if not os.path.exists(state_path):
        return {
            'failed_keys': [],
            'last_alert_ts': 0,
            'check_last_run': {},   # check_name -> ts
            'check_last_fail': {},  # check_name -> msg (用于恢复通知对比)
            'last_heartbeat_ts': 0,  # V007.63: 心跳时间戳
        }
    try:
        with open(state_path, 'r', encoding='utf-8') as f:
            s = json.load(f)
    except Exception:
        return {'failed_keys': [], 'last_alert_ts': 0, 'check_last_run': {}, 'check_last_fail': {}, 'last_heartbeat_ts': 0}
    # 兼容旧 state
    s.setdefault('failed_keys', [])
    s.setdefault('last_alert_ts', 0)
    s.setdefault('check_last_run', {})
    s.setdefault('check_last_fail', {})
    s.setdefault('last_heartbeat_ts', 0)
    return s


def save_v0760_state(state, state_path):
    with open(state_path, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def run_once_v0760(cfg, state_path, force=False):
    """V007.60 run_once: 分层调度 + 应用层监控"""
    log('[V007.60 CHECK] 开始分层监控...')

    state = load_v0760_state(state_path)
    now = time.time()

    # 1. 跑 Layer 1 (每 5 分钟的实时项) - 总是跑
    # 2. 跑 Layer 2/3 (15/30 分钟) - 按 should_run 判断
    all_results = []

    for check_name, meta in CHECKS.items():
        if not force and not should_run(check_name, state, now):
            continue
        log(f'  [run] {check_name} (interval={meta["interval_sec"]}s)')
        try:
            t0 = time.time()
            results = meta['fn']()
            elapsed = time.time() - t0
            log(f'    [{check_name}] {len(results)} results, {elapsed:.2f}s')
            all_results.extend(results)
            state['check_last_run'][check_name] = now
        except Exception as e:
            log(f'    [{check_name}] EXCEPTION: {e}')
            all_results.append({'name': f'{check_name}:runner', 'ok': False, 'msg': f'{type(e).__name__}: {str(e)[:80]}'})
            state['check_last_run'][check_name] = now

    # 同时保留 V007.59 的端口/systemd/log_service 检查 (5min 总是跑)
    port_results = check_yonaa_services()
    sys_results = check_systemd_via_agent()
    log_results = check_log_service_via_agent()
    all_results.extend(port_results + sys_results + log_results)
    log(f'  ports: {sum(1 for r in port_results if r["ok"])}/{len(port_results)} OK')
    log(f'  systemd: {len(sys_results)} results')
    log(f'  log_service: {len(log_results)} results')

    # === 聚合失败 / 推送 / 恢复 ===
    failed = [r for r in all_results if not r.get('ok')]
    failed_keys = {f'{r["name"]}:{r.get("port", "")}' for r in failed}
    prev_failed_keys = set(state.get('failed_keys', []))

    cooldown_sec = cfg.get('alert', {}).get('cooldown_sec', 600)
    last_alert_ts = state.get('last_alert_ts', 0)

    im_type = cfg.get('im', {}).get('default', 'lark_app')

    if failed:
        new_failed = failed_keys - prev_failed_keys
        recovered = prev_failed_keys - failed_keys
        log(f'  [SUMMARY] {len(failed)} failed, {len(new_failed)} new, {len(recovered)} recovered')

        if new_failed and (now - last_alert_ts) > cooldown_sec:
            title, content = format_alert(failed)
            at_all = cfg.get('alert', {}).get('at_all_on_fail', False)
            ok, body = send_im(im_type, cfg, title, content, at_all)
            log(f'  [IM] {im_type}: {"OK" if ok else "FAIL: " + body}')
            state['last_alert_ts'] = now

        if recovered and (now - last_alert_ts) > cooldown_sec:
            recovered_list = [r for r in all_results if f'{r["name"]}:{r.get("port", "")}' in recovered]
            title, content = format_recovery(recovered_list)
            at_all = cfg.get('alert', {}).get('at_all_on_recovery', False)
            ok, body = send_im(im_type, cfg, title, content, at_all)
            log(f'  [RECOVERY IM] {im_type}: {"OK" if ok else "FAIL: " + body}')

        state['failed_keys'] = list(failed_keys)
        save_v0760_state(state, state_path)
        _send_heartbeat(cfg, state, all_results, state_path)
        return 1
    else:
        if prev_failed_keys:
            recovered_list = [{'name': k, 'port': ''} for k in prev_failed_keys]
            title, content = format_recovery(recovered_list)
            at_all = cfg.get('alert', {}).get('at_all_on_recovery', False)
            ok, body = send_im(im_type, cfg, title, content, at_all)
            log(f'  [RECOVERY IM] {im_type}: {"OK" if ok else "FAIL: " + body}')
            state['last_alert_ts'] = now

        state['failed_keys'] = []
        save_v0760_state(state, state_path)
        _send_heartbeat(cfg, state, all_results, state_path)
        log('  [OK] 全部健康')
        # V007.86f Layer 1: every-run heartbeat in log (for check_alert_monitor_health.py)
        log(f'  [HEARTBEAT-V00786F] v00786g check_id={int(time.time())} ok={len(all_results)-sum(1 for r in all_results if not r.get("ok"))}/{len(all_results)}')
        return 0


def _send_heartbeat(cfg, state, all_results, state_path):
    """V007.63 心跳: 每 N 分钟发一次, 表明监控在跑

    频次: HEARTBEAT_INTERVAL_SEC env var (默认 1800 = 30min)
    风格: 蓝色卡片, 不 @ 全体, 跟告警区分
    内容: 9 项检查统计 + 上次告警时间 + 任务运行时长
    """
    interval = int(os.environ.get('HEARTBEAT_INTERVAL_SEC', '1800'))
    now = time.time()
    last = state.get('last_heartbeat_ts', 0)
    if (now - last) < interval:
        return  # 还没到时间

    im_type = cfg.get('im', {}).get('default', 'lark_app')
    total = len(all_results)
    failed = sum(1 for r in all_results if not r.get('ok'))
    passed = total - failed

    # 各检查项 last_run 距离 now 多久
    stale_checks = []
    for name, meta in CHECKS.items():
        last_run = state.get('check_last_run', {}).get(name, 0)
        if last_run:
            age = int(now - last_run)
            if age > meta['interval_sec'] * 2:
                stale_checks.append(f'{name} (滞后 {age}s)')

    lines = [
        f'**yonaa 监控心跳**',
        '',
        f'✓ 9 项检查通过 / 共 {total} 个子项 (failed: {failed})',
        f'• 上次告警: {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(state.get("last_alert_ts", 0))) if state.get("last_alert_ts") else "无"}',
        f'• 任务已运行: {int((now - state.get("started_ts", now))/3600)}h (Task Scheduler 持久化)',
        f'• 当前模式: {"异常" if failed else "全部健康"}',
    ]
    if stale_checks:
        lines.append(f'• 滞后项: {", ".join(stale_checks)}')

    title = f'[HEARTBEAT] yonaa 监控运行中 ({"正常" if failed == 0 else f"{failed} 项异常"})'
    ok, body = send_im(im_type, cfg, title, '\n'.join(lines), at_all=False)
    log(f'  [HEARTBEAT] {im_type}: {"OK" if ok else "FAIL: " + body}')
    if ok:
        state['last_heartbeat_ts'] = now
        save_v0760_state(state, state_path)


def run_daemon_v0760(cfg, state_path):
    """守护模式: 每 5 分钟触发一次, 检查项按各自 interval 决定跑不跑"""
    interval = cfg.get('alert', {}).get('interval_sec', 300)
    log(f'[V007.60 DAEMON] 启动, 间隔 {interval}s, 共 {len(CHECKS)} 项检查')
    while True:
        try:
            run_once_v0760(cfg, state_path)
        except KeyboardInterrupt:
            log('[DAEMON] Ctrl+C, 退出')
            break
        except Exception as e:
            log(f'[DAEMON ERROR] {e}')
        time.sleep(interval)


_LOG_FILE_HANDLE = None


def _log_to_file(msg: str):
    """写一行到 log file (Task Scheduler 用, no-console)"""
    global _LOG_FILE_HANDLE
    if _LOG_FILE_HANDLE is None:
        return
    try:
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        _LOG_FILE_HANDLE.write(f'[{ts}] {msg}\n')
        _LOG_FILE_HANDLE.flush()
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description='yonaa agent 端 IM 告警监控 (V007.60)')
    parser.add_argument('--config', default=DEFAULT_CONFIG, help=f'配置文件 (默认 {DEFAULT_CONFIG})')
    parser.add_argument('--check-now', action='store_true', help='跑一次检查并退出')
    parser.add_argument('--daemon', action='store_true', help='守护模式, 每 5 分钟')
    parser.add_argument('--force', action='store_true', help='强制跑所有检查项 (忽略 interval)')
    parser.add_argument('--list-checks', action='store_true', help='列出所有 V007.60 检查项')
    parser.add_argument('--check-one', help='只跑指定检查项 (例如 real_health)')
    parser.add_argument('--log-file', help='同时输出到日志文件 (Task Scheduler / no-console 必备)')
    args = parser.parse_args()

    # 打开 log file (如果指定)
    global _LOG_FILE_HANDLE
    if args.log_file:
        try:
            _LOG_FILE_HANDLE = open(args.log_file, 'a', encoding='utf-8')
        except Exception as e:
            print(f'[WARN] log file open fail: {e}', flush=True)

    if args.list_checks:
        print(f'\nV007.60 共 {len(CHECKS)} 项检查:')
        for name, meta in CHECKS.items():
            print(f'  - {name:18s} interval={meta["interval_sec"]:>5}s  severity={meta["severity"]}')
        if _LOG_FILE_HANDLE:
            _LOG_FILE_HANDLE.close()
        return 0

    # 加载配置
    if not os.path.exists(args.config):
        log(f'[FAIL] 配置不存在: {args.config}, 请先 --init-config 或拷贝示例')
        _log_to_file(f'[FAIL] 配置不存在: {args.config}')
        if _LOG_FILE_HANDLE:
            _LOG_FILE_HANDLE.close()
        return 2
    with open(args.config, 'r', encoding='utf-8') as f:
        cfg = json.load(f)

    state_path = args.config.replace('.json', '_state.json')

    if args.check_one:
        if args.check_one not in CHECKS:
            log(f'[FAIL] 未知检查项: {args.check_one}')
            return 2
        results = CHECKS[args.check_one]['fn']()
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return 0 if all(r.get('ok') for r in results) else 1

    if args.check_now:
        rc = run_once_v0760(cfg, state_path, force=args.force)
    elif args.daemon:
        run_daemon_v0760(cfg, state_path)
        rc = 0
    else:
        parser.print_help()
        rc = 1

    if _LOG_FILE_HANDLE:
        _LOG_FILE_HANDLE.close()
    return rc


if __name__ == '__main__':
    sys.exit(main())
