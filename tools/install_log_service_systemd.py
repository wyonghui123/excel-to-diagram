#!/usr/bin/env python3
"""[OPS] install_log_service_systemd.py - 装 systemd unit 守护 log_service (V007.55)

两步:
  1. upload unit 文件到 /opt/app/deployments/ (core_service 可写)
  2. 在远端 cp 到 /etc/systemd/system/ (root 权限)
  3. daemon-reload + enable + start

用法:
  python tools/install_log_service_systemd.py
  python tools/install_log_service_systemd.py --target prod
  python tools/install_log_service_systemd.py --target staging
  python tools/install_log_service_systemd.py --uninstall
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yonaa_exec import yexec, yupload, sleep_between

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))

# port/secret 配对
ENV_CONFIG = {
    'prod':    {'port': 9200,  'secret': 'prod_write', 'deploy_root': '/opt/app/deployments'},
    'staging': {'port': 19200, 'secret': 'prod_write', 'deploy_root': '/opt/app/staging/deploy'},
}


def upload_unit(name, cfg):
    """upload unit 文件到 deploy_root (core_service 可写)"""
    local = os.path.join(TOOLS_DIR, f'log_service_{name}.service')
    if not os.path.exists(local):
        print(f'  [FATAL] {local} 不存在')
        return False
    # 远端路径: 先放到 deploy_root/, 再 cp 到 /etc/systemd/system/
    remote_tmp = f'{cfg["deploy_root"]}/log_service_{name}.service'
    r = yupload(local, remote_tmp, port=cfg['port'], secret=cfg['secret'], timeout=30)
    if r.get('error'):
        print(f'  [FAIL] upload {name}: {r}')
        return False
    print(f'  [OK] uploaded → {remote_tmp} ({r.get("size")} bytes)')

    # 移到 /etc/systemd/system/
    r = yexec(
        f'bash -c "cp {remote_tmp} /etc/systemd/system/log_service_{name}.service && '
        f'ls -la /etc/systemd/system/log_service_{name}.service"',
        port=cfg['port'], secret=cfg['secret'], timeout=10
    )
    out = r.get('stdout', '')
    if 'log_service_' in out and 'systemd' in out:
        print(f'  [OK] cp 到 /etc/systemd/system/')
        return True
    print(f'  [FAIL] cp: {out[:200]}{r.get("stderr", "")[:200]}')
    return False


def install_target(name):
    """装 + 启一个环境的 systemd unit"""
    cfg = ENV_CONFIG[name]
    port_to_check = 9101 if name == 'prod' else 19101

    print(f'\n=== {name} (port={port_to_check}, deploy_root={cfg["deploy_root"]}) ===')

    # 1. upload unit
    if not upload_unit(name, cfg):
        return False

    # 2. 杀老 log_service
    r = yexec('bash -c "pkill -9 -f log_service.py 2>/dev/null; sleep 1; ps -ef | grep log_service.py | grep -v grep || echo NO_OLD"',
              port=cfg['port'], secret=cfg['secret'], timeout=10)
    out = r.get('stdout', '')
    print(f'  1. 杀旧: {"OK (无)" if "NO_OLD" in out else "KILLED"}')
    sleep_between()

    # 3. daemon-reload
    r = yexec('bash -c "systemctl daemon-reload 2>&1; echo EXIT=$?"',
              port=cfg['port'], secret=cfg['secret'], timeout=10)
    out = r.get('stdout', '')
    print(f'  2. daemon-reload: {out.strip()[:100]}')
    sleep_between()

    # 4. enable
    r = yexec(f'bash -c "systemctl enable log_service_{name}.service 2>&1; echo EXIT=$?"',
              port=cfg['port'], secret=cfg['secret'], timeout=10)
    print(f'  3. enable: {r.get("stdout", "").strip()[:200]}')
    sleep_between()

    # 5. start
    r = yexec(f'bash -c "systemctl start log_service_{name}.service 2>&1; echo EXIT=$?"',
              port=cfg['port'], secret=cfg['secret'], timeout=10)
    print(f'  4. start: {r.get("stdout", "").strip()[:200]}')
    sleep_between(3)

    # 6. status
    r = yexec(f'bash -c "systemctl status log_service_{name}.service --no-pager 2>&1 | head -15"',
              port=cfg['port'], secret=cfg['secret'], timeout=10)
    out = r.get('stdout', '')
    active = 'Active: active (running)' in out
    print(f'  5. status: {"✓ active" if active else "✗ NOT active"}')
    if not active:
        print('  --- 错误 ---')
        for line in out.split('\n')[:15]:
            print(f'    {line}')
        return False

    # 7. 端口
    r = yexec(f'bash -c "netstat -tlnp 2>/dev/null | grep {port_to_check} || echo NOT_LISTEN"',
              port=cfg['port'], secret=cfg['secret'], timeout=10)
    out = r.get('stdout', '')
    print(f'  6. port {port_to_check}: {"✓ LISTEN" if "LISTEN" in out else "✗ NOT"}')
    return 'LISTEN' in out


def uninstall_target(name):
    cfg = ENV_CONFIG[name]
    print(f'\n=== {name} uninstall ===')
    r = yexec(
        f'bash -c "systemctl stop log_service_{name}.service 2>&1; '
        f'systemctl disable log_service_{name}.service 2>&1; '
        f'rm -f /etc/systemd/system/log_service_{name}.service; '
        f'systemctl daemon-reload 2>&1; echo DONE"',
        port=cfg['port'], secret=cfg['secret'], timeout=15
    )
    out = r.get('stdout', '')
    print(f'  {out.strip()[:300]}')


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', choices=['prod', 'staging', 'all'], default='all')
    parser.add_argument('--uninstall', action='store_true')
    args = parser.parse_args()

    print('=== [V007.55] install_log_service_systemd ===\n')
    if args.uninstall:
        if args.target in ('prod', 'all'):
            uninstall_target('prod')
        if args.target in ('staging', 'all'):
            uninstall_target('staging')
        return

    success = True
    if args.target in ('prod', 'all'):
        success &= install_target('prod')
    if args.target in ('staging', 'all'):
        success &= install_target('staging')

    print(f'\n=== {"✓ 全部 OK" if success else "✗ 有失败"} ===')
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
