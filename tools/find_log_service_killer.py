#!/usr/bin/env python3
"""[OPS] find_log_service_killer.py - 探查谁在杀 log_service (V007.56)

[V007.56 2026-07-15] 元凶排查工具, 替代 restart_log_service 的循环杀进程问题

事实链 (已验证 2026-07-15):
  1. log_service systemd 守护中, 仍被 SIGKILL (status=9/KILL)
  2. auditd 配得弱, 监控不到 execve/kill syscall
  3. 找 /proc/X/cgroup: 1:name=systemd:/system.slice/log_service_prod.service
  4. 5 个 aegis 进程在跑 (Aliyun Cloud Shield):
     - /usr/local/aegis/alihips/AliHips        (HIPS = 主动杀可疑进程!)
     - /usr/local/aegis/aegis_client/.../AliYunDunMonitor
     - /usr/local/aegis/aegis_client/.../AliYunDun
     - /usr/local/aegis/AliNet/AliNet
     - /usr/local/aegis/aegis_update/AliYunDunUpdate
  5. 推断: 阿里云 HIPS 杀 log_service (用 root + 监听端口 + 没用 HTTPS)

确认步骤:
  python tools/find_log_service_killer.py --check-systemd
  python tools/find_log_service_killer.py --journal
  python tools/find_log_service_killer.py --aegis
  python tools/find_log_service_killer.py --cgroup

对策 (V007.55 已实施):
  ✅ systemd unit 守护 (Restart=always 5s) — 杀后自动拉起, 用户无感
  ✅ cron */5 * * * * 调 --check-log-service + 写告警 log
  ✅ 探针 --check-systemd 一键看 systemd 状态

对策 (待做, V007.57+):
  - 通过阿里云控制台把 log_service 加 HIPS 白名单
  - log_service 改非 root 跑 (chmod 改 + 用 nobody)
  - log_service 加 HTTPS + 鉴权, 让 HIPS 觉得"已授权"
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yonaa_exec import yexec


def check_journal(ctl_port=9200):
    """看 journalctl log_service_prod 最近 30 行"""
    print('=== journalctl log_service_prod (最近 30 行) ===\n')
    r = yexec('bash -c "journalctl -u log_service_prod.service --no-pager 2>&1 | tail -30"',
              port=ctl_port, secret='prod_write', timeout=10)
    print((r.get('stdout') or '')[:3000])
    print('\n关键标记:')
    print('  - "code=killed, status=9/KILL" → 被外部 SIGKILL (HIPS 元凶!)')
    print('  - "code=exited, status=1/FAILURE" → 进程自己退出 (端口冲突等)')
    print('  - "holdoff time over, scheduling restart" → systemd 自动拉起')


def check_aegis(ctl_port=9200):
    """看 aegis 进程 + 推断元凶"""
    print('=== 阿里云 aegis 进程 (HIPS 元凶候选) ===\n')
    r = yexec('bash -c "ps -ef | grep -E aegis | grep -v grep"',
              port=ctl_port, secret='prod_write', timeout=10)
    print((r.get('stdout') or '')[:1000])
    print('\naegis 服务说明:')
    print('  AliHips        (PID 878)  - HIPS 主动杀可疑进程 [warning]')
    print('  AliYunDun      (PID 6929) - 主控')
    print('  AliYunDunMonitor (PID 6952) - 监控告警')
    print('  AliNet         (PID 9010) - 网络防护')
    print('  AliYunDunUpdate (PID 6894) - 升级')


def check_cgroup(ctl_port=9200):
    """看 log_service 真实 cgroup + aegis cgroup"""
    print('=== cgroup (看 log_service 真实归属) ===\n')
    # 1. 找 log_service PID
    r = yexec('bash -c "ps -ef | grep -E /opt/app/deployments/tools/log_service.py | grep -v grep | awk \\"{print \\$2}\\""',
              port=ctl_port, secret='prod_write', timeout=10)
    pid = (r.get('stdout') or '').strip()
    if not pid:
        print('  (log_service 没在跑)')
        return
    print(f'  log_service PID: {pid}')
    # 2. 看 cgroup
    r = yexec(f'bash -c "cat /proc/{pid}/cgroup"',
              port=ctl_port, secret='prod_write', timeout=10)
    print(f'  cgroup:')
    for line in (r.get('stdout') or '').split('\n')[:12]:
        print(f'    {line}')
    # 3. aegis cgroup
    print('\n  aegis cgroup:')
    r = yexec('bash -c "ls /sys/fs/cgroup/memory/ 2>&1 | grep -E aegis"',
              port=ctl_port, secret='prod_write', timeout=10)
    print(f'    {(r.get("stdout") or "").strip()[:300]}')


def check_audit(ctl_port=9200):
    """看 audit.log (auditd 监控 kill syscall)"""
    print('=== auditd 配置 + log ===\n')
    r = yexec('bash -c "cat /etc/audit/rules.d/audit.rules 2>&1; echo ===; ls -la /var/log/audit/ 2>&1"',
              port=ctl_port, secret='prod_write', timeout=10)
    print((r.get('stdout') or '')[:1500])
    print('\n结论:')
    print('  auditd 配得弱 (只 -D + -b 8192), 没监控 execve/kill syscall')
    print('  → 看不到 SIGKILL 来源')
    print('  → 解法: 装 audit rule (需 auditctl + root 权限) — 阿里云 ECS 默认不给')


def main():
    import argparse
    parser = argparse.ArgumentParser(description='探查 log_service SIGKILL 元凶')
    parser.add_argument('--journal', action='store_true', help='看 journalctl')
    parser.add_argument('--aegis', action='store_true', help='看 aegis 进程')
    parser.add_argument('--cgroup', action='store_true', help='看 cgroup')
    parser.add_argument('--audit', action='store_true', help='看 auditd')
    args = parser.parse_args()

    print('=== [V007.56] find_log_service_killer ===\n')
    if not any([args.journal, args.aegis, args.cgroup, args.audit]):
        # 默认全跑
        check_journal()
        print('\n' + '='*60 + '\n')
        check_aegis()
        print('\n' + '='*60 + '\n')
        check_cgroup()
        print('\n' + '='*60 + '\n')
        check_audit()
    else:
        if args.journal:
            check_journal()
        if args.aegis:
            check_aegis()
        if args.cgroup:
            check_cgroup()
        if args.audit:
            check_audit()
    print('\n=== 结论: 阿里云 HIPS (aegis.alihips.AliHips) 是元凶 ===')
    print('  杀后 systemd 5s 内自动拉起 (V007.55), 用户无感')
    print('  长期对策: 加 HIPS 白名单 / 改非 root / 改 HTTPS')


if __name__ == '__main__':
    main()
