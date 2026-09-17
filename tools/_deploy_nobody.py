"""[OPS] 1) chown meta 让 nobody 可写 2) 装新 unit 3) 验证"""
import sys
sys.path.insert(0, 'tools')
from yonaa_exec import yexec, yupload, sleep_between
import time

ENV_CONFIG = {
    'prod':    {'port': 9200,  'secret': 'prod_write', 'deploy_root': '/opt/app/deployments',  'meta_dirs': ['/opt/app/deployments/meta', '/opt/app/deployments/logs']},
    'staging': {'port': 19200, 'secret': 'prod_write', 'deploy_root': '/opt/app/staging/deploy', 'meta_dirs': ['/opt/app/staging/meta', '/opt/app/staging/deploy/meta', '/opt/app/staging/logs']},
}


def chown_meta(name):
    """chown -R nobody:nobody + chmod 0775 (nobody 可写 group nobody 路径)"""
    cfg = ENV_CONFIG[name]
    print(f'\n=== {name} chown + chmod ===')
    for d in cfg['meta_dirs']:
        r = yexec(f"bash -c 'chown -R nobody:nobody {d} 2>&1; chmod 0775 {d} 2>&1; ls -la {d}/ 2>&1 | head -3'",
                  port=cfg['port'], secret=cfg['secret'], timeout=15)
        out = (r.get('stdout') or '')[:600]
        print(f'  {d}: {out[:200]}')


def reinstall(name):
    """重装 (用新 unit)"""
    cfg = ENV_CONFIG[name]
    print(f'\n=== {name} reinstall (用新 unit) ===')
    # 1. upload 新 unit
    local_unit = f'd:/filework/worktrees/release-prep/tools/log_service_{name}.service'
    remote_tmp = f'{cfg["deploy_root"]}/log_service_{name}.service'
    r = yupload(local_unit, remote_tmp, port=cfg['port'], secret=cfg['secret'], timeout=30)
    if r.get('error'):
        print(f'  [FAIL] upload: {r}')
        return False
    print(f'  [OK] uploaded {local_unit} → {remote_tmp}')

    # 2. cp 到 /etc/systemd/system/
    r = yexec(
        f'bash -c "cp {remote_tmp} /etc/systemd/system/log_service_{name}.service && '
        f'systemctl daemon-reload && '
        f'systemctl restart log_service_{name}.service"',
        port=cfg['port'], secret=cfg['secret'], timeout=15
    )
    print(f'  daemon-reload + restart: {(r.get("stdout") or "").strip()[:300]}')
    sleep_between(3)

    # 3. 验证
    r = yexec(f"bash -c 'systemctl status log_service_{name}.service --no-pager 2>&1 | head -10'",
              port=cfg['port'], secret=cfg['secret'], timeout=10)
    out = r.get('stdout', '')
    active = 'Active: active (running)' in out
    print(f'  status: {"✓ active" if active else "✗ NOT active"}')
    if not active:
        for line in out.split('\n')[:10]:
            print(f'    {line}')
        return False

    # 4. 看 user 是不是 nobody
    r = yexec(f"bash -c 'ps -ef | grep -E /opt/app.*log_service.py | grep -v grep'",
              port=cfg['port'], secret=cfg['secret'], timeout=10)
    out = r.get('stdout', '') or ''
    if 'nobody' in out:
        print(f'  [✓] nobody 跑: {out.strip()[:200]}')
        return True
    print(f'  [✗] 还在 root 跑: {out.strip()[:200]}')
    return False


def main():
    print('=== [V007.57] 改 nobody 跑 log_service ===\n')

    # 1. chown
    chown_meta('prod')
    chown_meta('staging')

    # 2. 装
    ok1 = reinstall('prod')
    ok2 = reinstall('staging')

    print(f'\n=== {"✓ 全部 OK" if (ok1 and ok2) else "✗ 有失败"} ===')

    # 3. 等 30s 看 HIPS 杀不杀
    print('\n=== 30s 后 status 检查 ===')
    time.sleep(30)
    r = yexec('bash -c "systemctl status log_service_prod.service --no-pager 2>&1 | head -10"',
              port=9200, secret='prod_write', timeout=10)
    out = r.get('stdout', '')
    print(out[:1500])


if __name__ == '__main__':
    main()
