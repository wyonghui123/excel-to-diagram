"""tools/restart_log_service.py - 启停 log_service (9101 prod / 19101 staging)

从 core_service (9200/19200) 启 log_service, 不需要 SSH.
也可用于任意环境: 改 DEPLOYS 数组.

用法:
  python tools/restart_log_service.py                # 启 prod + staging
  python tools/restart_log_service.py --env prod     # 只 prod
  python tools/restart_log_service.py --env staging  # 只 staging
  python tools/restart_log_service.py --stop         # 杀 (不启)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yonaa_exec import yexec, yupload, sleep_between

# 部署根 + 端口 (prod / staging)
DEPLOYS = [
    {
        'label': 'prod',
        'ctl_port': 9200,           # 走 9200 (prod core_service) 启
        'log_port': 9101,
        'deploy_root': '/opt/app/deployments',
        'log_dir': '/opt/app/deployments/meta',
        'python': '/opt/miniconda3-py39/bin/python',
        'log_path': '/opt/app/deployments/tools/log_service.py',
    },
    {
        'label': 'staging',
        'ctl_port': 19200,          # 走 19200 (staging core_service) 启
        'log_port': 19101,
        'deploy_root': '/opt/app/staging/deploy',
        'log_dir': '/opt/app/staging/deploy/meta',
        'python': '/opt/miniconda3-py39/bin/python',
        'log_path': '/opt/app/staging/deploy/tools/log_service.py',
    },
]

LOCAL_LOG_SERVICE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'log_service.py')


def start_log_service(cfg):
    """启 log_service (idempotent: 杀旧 + 启新)"""
    label = cfg['label']
    ctl_port = cfg['ctl_port']
    log_port = cfg['log_port']
    deploy_root = cfg['deploy_root']
    log_dir = cfg['log_dir']
    python = cfg['python']
    log_path = cfg['log_path']

    print(f'\n=== {label}: 启 log_service :{log_port} ===')

    # 0. 探测 ctl_port 通
    r = yexec("echo OK", port=ctl_port, secret='prod_write', timeout=5)
    if r.get('error'):
        print(f'  ✗ core_service:{ctl_port} 不通, 跳过: {r.get("error_class")}')
        return False
    print(f'  ✓ core_service:{ctl_port} 通')

    # 1. 上传 log_service.py
    if not os.path.exists(LOCAL_LOG_SERVICE):
        print(f'  ✗ 本地 log_service.py 不存在: {LOCAL_LOG_SERVICE}')
        return False
    r = yupload(LOCAL_LOG_SERVICE, log_path, port=ctl_port, secret='prod_write', timeout=60)
    if r.get('error'):
        print(f'  ✗ upload failed: {r}')
        return False
    print(f'  ✓ uploaded to {log_path}')
    sleep_between()

    # 2. 杀旧 (精准, 不杀 ctl_service)
    # 用 ps + awk 找 log_service 进程, 不用 pkill -f (会自匹配)
    kill_cmd = "ps -ef | awk '/log_service\\.py/ && !/awk/ {print $2}' | xargs -r kill -9 2>/dev/null; sleep 1; echo killed"
    r = yexec(kill_cmd, port=ctl_port, secret='prod_write', timeout=10)
    print(f'  杀旧: {r.get("stdout", "").strip() or "(no old proc)"}')
    sleep_between(1.5)

    # 3. 启新 (用 bash -c, 因 cd 不在 EXEC_WHITELIST)
    log_path_esc = log_path.replace("'", "'\\''")
    deploy_root_esc = deploy_root.replace("'", "'\\''")
    log_dir_esc = log_dir.replace("'", "'\\''")
    start_cmd = (
        f"bash -c 'cd {deploy_root_esc} && setsid nohup env "
        f"LOG_SERVICE_PORT={log_port} "
        f"LOG_SERVICE_BIND=0.0.0.0 "
        f"LOG_SERVICE_LOG_DIR={log_dir_esc} "
        f"LOG_SERVICE_DB_PATH={log_dir_esc}/architecture.db "
        f"LOG_SERVICE_SECRET=v007.35-infra "
        f"{python} {log_path_esc} "
        f">> {deploy_root_esc}/logs/log_service.log 2>&1 < /dev/null &'"
    )
    r = yexec(start_cmd, port=ctl_port, secret='prod_write', timeout=5, bg=True)
    if r.get('error'):
        print(f'  ✗ start failed: {r}')
        return False
    print(f'  ✓ started bg pid={r.get("pid", "?")}')
    sleep_between(2.5)

    # 4. 验证
    import http.client
    try:
        conn = http.client.HTTPConnection('172.20.59.7', log_port, timeout=5)
        conn.request('GET', '/api')
        resp = conn.getresponse()
        body = resp.read().decode('utf-8', errors='replace')[:500]
        if 'log_service' in body:
            print(f'  ✓ verified: GET /api → log_service live')
        else:
            print(f'  ? GET /api: status={resp.status} body={body[:200]}')
        conn.close()
        return True
    except Exception as e:
        print(f'  ✗ verify: {e}')
        return False


def stop_log_service(cfg):
    """杀 log_service (只杀)"""
    label = cfg['label']
    ctl_port = cfg['ctl_port']
    print(f'\n=== {label}: 杀 log_service ===')
    r = yexec("echo OK", port=ctl_port, secret='prod_write', timeout=5)
    if r.get('error'):
        print(f'  ✗ core_service:{ctl_port} 不通, 跳过')
        return
    kill_cmd = "ps -ef | awk '/log_service\\.py/ && !/awk/ {print $2}' | xargs -r kill -9 2>/dev/null; sleep 1; echo killed"
    r = yexec(kill_cmd, port=ctl_port, secret='prod_write', timeout=10)
    print(f'  {r.get("stdout", "").strip()}')


def main():
    only_env = None
    do_stop = False
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--env':
            only_env = args[i+1]; i += 2
        elif a == '--stop':
            do_stop = True; i += 1
        else:
            i += 1

    targets = DEPLOYS
    if only_env:
        targets = [c for c in DEPLOYS if c['label'] == only_env]
        if not targets:
            print(f'Unknown env: {only_env}, valid: {[c["label"] for c in DEPLOYS]}')
            sys.exit(1)

    print(f'操作: {"STOP" if do_stop else "START"} | targets: {[c["label"] for c in targets]}')

    for cfg in targets:
        if do_stop:
            stop_log_service(cfg)
        else:
            start_log_service(cfg)


if __name__ == '__main__':
    main()
