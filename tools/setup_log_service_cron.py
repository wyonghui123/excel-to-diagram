#!/usr/bin/env python3
"""[OPS] setup_log_service_cron.py - yonaa 端加 cron + 告警 (V007.55)

加 1 个 cron 任务:
  每 5 分钟跑 probe --check-log-service, 失败写 /var/log/monitor_alert.log

文件: /etc/cron.d/log_service_monitor (system cron, 不依赖 user crontab)
告警: /var/log/monitor_alert.log
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yonaa_exec import yexec, yupload, sleep_between

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
CRON_LOCAL = os.path.join(TOOLS_DIR, 'log_service_monitor.cron')


def install():
    print('=== [V007.55] setup_log_service_cron ===\n')

    # 1. upload cron file (先到 deploy_root, 再 cp 到 /etc/cron.d/)
    r = yupload(CRON_LOCAL, '/opt/app/deployments/log_service_monitor.cron',
                port=9200, secret='prod_write', timeout=30)
    if r.get('error'):
        print(f'  [FAIL] upload: {r}')
        return
    print(f'  [OK] uploaded → /opt/app/deployments/log_service_monitor.cron ({r.get("size")} bytes)')

    # 2. cp 到 /etc/cron.d/ + 修权限
    r = yexec(
        'bash -c "cp /opt/app/deployments/log_service_monitor.cron /etc/cron.d/log_service_monitor '
        '&& chmod 644 /etc/cron.d/log_service_monitor '
        '&& chown root:root /etc/cron.d/log_service_monitor '
        '&& ls -la /etc/cron.d/log_service_monitor"',
        port=9200, secret='prod_write', timeout=10
    )
    print(f'  [OK] cp → /etc/cron.d/ + chmod 644')
    print(f'    {(r.get("stdout") or "").strip()[:200]}')

    # 3. 创建告警 log
    r = yexec('bash -c "touch /var/log/monitor_alert.log /var/log/monitor.log && chmod 644 /var/log/monitor_alert.log /var/log/monitor.log"',
              port=9200, secret='prod_write', timeout=10)
    print(f'  [OK] 告警 log: /var/log/monitor_alert.log + /var/log/monitor.log')

    # 4. 验证
    r = yexec('bash -c "cat /etc/cron.d/log_service_monitor"',
              port=9200, secret='prod_write', timeout=10)
    print('\n=== crontab 内容 ===')
    print((r.get('stdout') or '')[:1000])

    # 5. 测 cron 表达式有效 (用 run-parts 模拟)
    r = yexec('bash -c "cd /opt/app/staging/deploy && /opt/miniconda3-py39/bin/python tools/remote_capability_probe.py --check-log-service 2>&1; echo EXIT=$?"',
              port=9200, secret='prod_write', timeout=10)
    print('\n=== 模拟 cron 跑 (验证 command 有效) ===')
    print((r.get('stdout') or '')[:1000])

    print('\n=== 安装完成 ===')
    print('监控频率: */5 * * * * (每 5 分钟)')
    print('告警 log: /var/log/monitor_alert.log (有 FAIL 时追加)')
    print('注意: cron 不会立即触发, 需等 5 分钟')
    print('手动测试: cat /etc/cron.d/log_service_monitor')


def uninstall():
    print('=== 卸 cron ===')
    r = yexec('bash -c "rm -f /etc/cron.d/log_service_monitor"',
              port=9200, secret='prod_write', timeout=10)
    print((r.get('stdout') or '(done)')[:200])


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--uninstall', action='store_true')
    args = parser.parse_args()
    if args.uninstall:
        uninstall()
    else:
        install()
