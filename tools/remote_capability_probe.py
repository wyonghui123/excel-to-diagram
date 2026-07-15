"""remote_capability_probe.py - 一键扫描 yonaa 远端能力图谱

输出 (30 秒内完成):
  - 所有已知端口可达性 (TCP + HTTP)
  - 每个端口可用的 secret (枚举 KNOWN_SECRETS 全部候选)
  - 远端服务信息 (name/version/uptime/endpoints)
  - exec 白名单 + allowed_dirs (远端 live data)
  - upload 端点 (multipart test)

用法:
  python tools/remote_capability_probe.py            # 全量
  python tools/remote_capability_probe.py --quick   # 只 TCP 探活
"""
import hashlib
import http.client
import json
import os
import sys
import time

# [V007.55] 强制 UTF-8 stdout (Windows PowerShell 默认 GBK 会让 ✓ 报错)
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
import urllib.parse

# 让脚本能从 tools/ 目录 import yonaa_exec
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yonaa_exec import (
    HOST, KNOWN_PORTS, KNOWN_SECRETS, _gen_tokens, _http_get, _http_post, _classify_error,
    yexec,  # [V007.55] --check-log-service 用
)

# exec 白名单 (来自 tools/core_service.py L78-90)
EXEC_WHITELIST = {
    "ls", "cat", "head", "tail", "wc", "find", "grep", "du", "df",
    "ps", "top", "ss", "netstat", "curl", "wget",
    "systemctl", "journalctl", "dmesg", "iostat", "free",
    "echo", "date", "whoami", "id", "uname", "hostname",
    "chmod", "chown", "mkdir", "cp", "mv", "ln", "touch",
    "python3", "python", "pip3", "pip",
    "md5sum", "sha256sum",
    "pkill", "kill", "killall", "pgrep",
    "bash", "sh", "unzip", "tar", "nohup",
    "sed", "awk", "sort", "uniq",
    "test", "true", "false", "sleep",
}


# [V007.55] 每个端口的 health-check 路径
# 大部分服务用 GET /api, 但 3011 (Flask) 没有 /api 路由 (会 404 → Flask 报 500 误判)
# 8081 frontend 返回 HTML, 也是 200 但 body 不是 JSON
PORT_HEALTH_PATHS = {
    9101: '/api',          # prod log_service
    19101: '/api',         # staging log_service
    9200: '/api',          # prod core_service
    19200: '/api',         # staging core_service
    9201: '/api',          # observability
    3011: '/health',       # backend (Flask, server.py 有 @app.route('/health'))
    8081: '/',             # frontend (HTML, 200)
}


def probe_port(port, label):
    """TCP + GET {health_path} 健康检查
    [V007.55] 不同端口用不同路径, 避免 3011 Flask 404→500 误判
    """
    path = PORT_HEALTH_PATHS.get(port, '/api')
    try:
        conn = http.client.HTTPConnection(HOST, port, timeout=5)
        conn.request('GET', path)
        resp = conn.getresponse()
        body = resp.read().decode('utf-8', errors='replace')
        conn.close()
        return {'reachable': True, 'status': resp.status, 'body': body[:500], 'path': path}
    except Exception as e:
        return {'reachable': False, 'reason': str(e)[:100], 'path': path}


def find_working_secret(port, test_cmd='echo YONAA_PROBE_OK'):
    """枚举 KNOWN_SECRETS + env, 找能用的"""
    candidates = []
    # env 优先
    for env_name in ('YONAA_SECRET', 'CORE_SERVICE_SECRET'):
        v = os.environ.get(env_name)
        if v:
            candidates.append(('env:'+env_name, v))
    # 已知 secret
    for alias, sec in KNOWN_SECRETS.items():
        candidates.append((alias, sec))

    for alias, sec in candidates:
        for tk in _gen_tokens(sec, count=2):
            try:
                params = urllib.parse.urlencode({'cmd': test_cmd, 'timeout': '10', 'token': tk})
                status, body = _http_get(HOST, port, f'/api/exec?{params}', timeout=10)
                if status == 200:
                    try:
                        data = json.loads(body)
                        if data.get('stdout', '').strip() == 'YONAA_PROBE_OK':
                            return alias, sec
                    except Exception:
                        pass
            except Exception:
                pass
    return None, None


def probe_exec_whitelist(port, secret):
    """通过 /api/exec 探活远端白名单实际支持情况 (本机白名单 + 服务端)"""
    # 我们只探测: 服务端是否真的接受这些命令 (本机白名单已知)
    # 用一个无害命令测试 3 个代表性命令
    test_cmds = [
        ('ls_test', 'ls /tmp | head -1'),
        ('python3_test', 'python3 -c "print(1)"'),
        ('bash_test', 'bash -c "echo bash_works"'),
        ('cd_test', 'cd /tmp; pwd'),  # 已知 cd 不在白名单
    ]
    results = []
    for label, cmd in test_cmds:
        params = urllib.parse.urlencode({'cmd': cmd, 'timeout': '5', 'token': _gen_tokens(secret)[0]})
        status, body = _http_get(HOST, port, f'/api/exec?{params}', timeout=10)
        if status == 200:
            try:
                data = json.loads(body)
                ok = data.get('exit_code') == 0
                results.append((label, '✓' if ok else '✗', data.get('stdout', '')[:30]))
            except Exception:
                results.append((label, '?', body[:30]))
        else:
            err = _classify_error(status, body)
            results.append((label, '✗', err.get('error_class', '?') if err else '?'))
    return results


def probe_upload(port, secret):
    """测试 /api/upload 与 /api/upload_multi 端点"""
    # 创建测试文件
    test_path = os.path.join(os.environ.get('TEMP', 'C:\\Windows\\Temp'), 'yonaa_probe.txt')
    with open(test_path, 'w') as f:
        f.write('yonaa_capability_probe\n')
    try:
        with open(test_path, 'rb') as f:
            data = f.read()
        # /api/upload (octet-stream)
        for ep in ['/api/upload', '/api/upload_multi']:
            for tk in _gen_tokens(secret):
                sep = '?' if '?' not in ep else '&'
                url = f'{ep}{sep}path=%2Ftmp%2Fyonaa_probe.txt&token={tk}'
                if ep == '/api/upload_multi':
                    # multipart 协议, 这里只测端点存在性
                    status, body = _http_get(HOST, port, url, timeout=5)
                else:
                    status, body = _http_post(HOST, port, url, data, timeout=10)
                if status in (200, 400):  # 400 也算端点存在 (参数问题)
                    return ep, status, body[:200]
        return None, 0, 'no upload endpoint'
    finally:
        try: os.remove(test_path)
        except: pass


def main():
    quick = '--quick' in sys.argv
    print('='*70)
    print(f'yonaa 远端能力扫描 → {HOST}')
    print(f'已知端口: {len(KNOWN_PORTS)} | 已知 secret: {len(KNOWN_SECRETS)}')
    print('='*70)

    # Step 1: 端口 TCP 探活
    print('\n[1] 端口探活 (TCP + GET /api)')
    port_results = {}
    for label, port in KNOWN_PORTS.items():
        r = probe_port(port, label)
        port_results[label] = r
        status = '✓' if r['reachable'] else '✗'
        info = ''
        if r['reachable']:
            try:
                data = json.loads(r['body'])
                info = f'{data.get("service", "?")} v{data.get("version", "?")} ' \
                       f'uptime={data.get("uptime_sec", "?")}s ' \
                       f'ports={data.get("port", "?")} ' \
                       f'eps={data.get("endpoints", "?")}'
            except Exception:
                info = r['body'][:80]
        else:
            info = r['reason'][:80]
        print(f'  [{status}] {label:20s} port={port:5d} → {info}')

    # Step 2: 每个可达的 core_service 端口找 working secret
    if not quick:
        print('\n[2] core_service 端口找 working secret (枚举 KNOWN_SECRETS + env)')
        for label, port in KNOWN_PORTS.items():
            if 'core' not in label:
                continue
            r = port_results.get(label, {})
            if not r.get('reachable'):
                print(f'  [SKIP] {label}: 不可达')
                continue
            alias, secret = find_working_secret(port)
            if alias:
                print(f'  [✓] {label} port={port} → secret={alias} ({secret[:8]}...)')
                # 探测白名单实际工作
                wl = probe_exec_whitelist(port, secret)
                print(f'      白名单实测:')
                for wlabel, wstatus, winfo in wl:
                    print(f'        [{wstatus}] {wlabel:18s} → {winfo}')
                # 探测 upload 端点
                ep, ustatus, ubody = probe_upload(port, secret)
                if ep:
                    print(f'      upload 端点: {ep} → {ustatus}')
                else:
                    print(f'      upload 端点: 未发现 ({ubody})')
            else:
                print(f'  [✗] {label} port={port} → 无有效 secret (试了 {len(KNOWN_SECRETS)} 个)')

    # Step 3: 总结建议
    print('\n[3] 总结 / 推荐用法')
    prod_ok = port_results.get('core_prod', {}).get('reachable')
    staging_ok = port_results.get('core_staging', {}).get('reachable')
    obs_ok = port_results.get('observability', {}).get('reachable')
    print(f'  prod core_service (9200): {"✓" if prod_ok else "✗"}')
    print(f'  staging core_service (19200): {"✓" if staging_ok else "✗"}')
    print(f'  observability (9201): {"✓" if obs_ok else "✗"}')
    print()
    if staging_ok:
        print('  → 推荐 staging 操作: yexec(cmd, port=19200, secret="prod_write")')
    if prod_ok:
        print('  → 推荐 prod 操作:   yexec(cmd, port=9200,  secret="prod_write")')

    print('\n' + '='*70)
    print('本机 EXEC_WHITELIST (来自 tools/core_service.py):')
    print('  ' + ', '.join(sorted(EXEC_WHITELIST)))
    print('='*70)


def check_log_service():
    """[V007.55] 单独检查 log_service 9101/19101 状态 (绕开 probe 的 full scan)

    用法: python tools/remote_capability_probe.py --check-log-service
    返回 exit code: 0=全活, 1=部分死, 2=全死
    """
    print('=== [V007.55] log_service 健康检查 ===\n')
    log_ports = [
        (9101, 'prod log_service'),
        (19101, 'staging log_service'),
    ]
    alive = 0
    dead = 0
    for port, label in log_ports:
        r = probe_port(port, label)
        if r.get('reachable') and 200 <= r.get('status', 0) < 500:
            alive += 1
            print(f'  [✓] {label:25s} port={port:5d} status={r.get("status")} path={r.get("path", "?")}')
        else:
            dead += 1
            reason = r.get('reason') or f'status={r.get("status")}'
            print(f'  [✗] {label:25s} port={port:5d} {reason}')

    # 进程检查 (通过 9200 远端)
    print('\n  log_service 进程 (远端):')
    r = yexec('bash -c "ps -ef | grep log_service | grep -v grep || echo NO_PROCESS"',
              port=9200, secret='prod_write', timeout=10)
    out = (r.get('stdout') or '').strip()
    if out and 'NO_PROCESS' not in out:
        for line in out.split('\n')[:5]:
            print(f'    {line[:160]}')
    else:
        print('    (无)')

    print(f'\n  总结: {alive} alive / {dead} dead / {alive + dead} total')
    if dead == 0:
        return 0
    elif alive == 0:
        return 2
    else:
        return 1


def watch_loop(interval_sec):
    """[V007.55] 持续监控模式: 每 N 秒跑一次 probe, 输出变化"""
    import time
    last_state = None
    print(f'[watch] 每 {interval_sec}s 跑一次, Ctrl+C 退出\n')
    while True:
        # 清屏 (ANSI)
        print('\033[2J\033[H', end='')
        print(f'=== yonaa 远端监控 @ {time.strftime("%Y-%m-%d %H:%M:%S")} ===\n')
        # 跑 log_service 检查
        alive_n = 0
        for port, label in [(9101, 'prod log_service'), (19101, 'staging log_service')]:
            r = probe_port(port, label)
            ok = r.get('reachable') and 200 <= r.get('status', 0) < 500
            alive_n += int(ok)
            status = f'✓ status={r.get("status")}' if ok else f'✗ {r.get("reason") or "?"}'
            print(f'  {label:25s} port={port:5d} {status}')
        # 跑核心端口
        print()
        for port, label in [(9200, 'prod core'), (19200, 'staging core'), (9201, 'observability')]:
            r = probe_port(port, label)
            ok = r.get('reachable') and 200 <= r.get('status', 0) < 500
            status = f'✓ status={r.get("status")}' if ok else f'✗ {r.get("reason") or "?"}'
            print(f'  {label:25s} port={port:5d} {status}')

        print(f'\n  log_service: {alive_n}/2 alive')
        if alive_n < last_state if last_state else False:
            print(f'  [ALERT] log_service 数量下降! {last_state} -> {alive_n}')
        last_state = alive_n
        time.sleep(interval_sec)


def watch_loop_with_auto_restart(interval_sec):
    """[V007.55] 持续监控 + 自动重启 log_service (取代手工 restart)"""
    import time
    import subprocess
    last_alive = 2  # 假设一开始都活
    restart_count = 0
    print(f'[watch+auto-restart] 每 {interval_sec}s 检查, log_service 死后自动 restart, Ctrl+C 退出\n',
          flush=True)
    try:
        while True:
            print('\033[2J\033[H', end='', flush=True)
            print(f'=== yonaa 监控 @ {time.strftime("%Y-%m-%d %H:%M:%S")} '
                  f'(restart_count={restart_count}) ===\n', flush=True)

            # 1. 探活 log_service
            alive_n = 0
            dead_ports = []
            for port, label in [(9101, 'prod log_service'), (19101, 'staging log_service')]:
                r = probe_port(port, label)
                ok = r.get('reachable') and 200 <= r.get('status', 0) < 500
                alive_n += int(ok)
                status = f'✓ status={r.get("status")}' if ok else f'✗ {r.get("reason") or "?"}'
                print(f'  {label:25s} port={port:5d} {status}', flush=True)
                if not ok:
                    dead_ports.append(port)

            # 2. 探活核心
            print(flush=True)
            for port, label in [(9200, 'prod core'), (19200, 'staging core'), (9201, 'observability')]:
                r = probe_port(port, label)
                ok = r.get('reachable') and 200 <= r.get('status', 0) < 500
                status = f'✓ status={r.get("status")}' if ok else f'✗ {r.get("reason") or "?"}'
                print(f'  {label:25s} port={port:5d} {status}', flush=True)

            # 3. 自动重启 (如果 log_service 死了)
            if dead_ports:
                print(f'\n  [AUTO] 发现 {len(dead_ports)} 个 log_service 死了, 调 restart_log_service.py',
                      flush=True)
                try:
                    result = subprocess.run(
                        ['python', 'tools/restart_log_service.py'],
                        capture_output=True, text=True, timeout=60, cwd='.',
                    )
                    restart_count += 1
                    print(f'  [AUTO] restart #{restart_count} 完成 (exit={result.returncode})',
                          flush=True)
                except Exception as e:
                    print(f'  [AUTO] restart 失败: {e}', flush=True)

            print(f'\n  log_service: {alive_n}/2 alive (last={last_alive})', flush=True)
            if alive_n < last_alive:
                print(f'  [ALERT] log_service 数量下降! {last_alive} -> {alive_n}', flush=True)
            last_alive = alive_n
            time.sleep(interval_sec)
    except KeyboardInterrupt:
        print('\n[watch] 退出', flush=True)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='yonaa 远端能力扫描')
    parser.add_argument('--quick', action='store_true', help='只 TCP 探活')
    parser.add_argument('--check-log-service', action='store_true',
                        help='[V007.55] 单独检查 log_service 9101/19101 状态')
    parser.add_argument('--watch', type=int, default=0, metavar='SEC',
                        help='[V007.55] 持续监控, 每 SEC 秒跑一次')
    parser.add_argument('--auto-restart-log', action='store_true',
                        help='[V007.55] --watch 模式下, log_service 死后自动 restart')
    args = parser.parse_args()

    if args.check_log_service:
        sys.exit(check_log_service())
    if args.watch > 0:
        if args.auto_restart_log:
            watch_loop_with_auto_restart(args.watch)
        else:
            watch_loop(args.watch)
    else:
        main()
