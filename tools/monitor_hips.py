"""
监控 nobody log_service 2 分钟, 看 HIPS 还杀不杀
每秒检查一次, 如果进程死了就报告
"""
import sys
import time
sys.path.insert(0, r'd:\filework\release-prep-worktree\tools')
from yonaa_exec import yexec

print("监控 2 分钟 (每 10 秒一次), 检查 nobody log_service 是否被杀...")
print("="*70)

start = time.time()
check_count = 0
killed_count = 0

while time.time() - start < 120:  # 2 min
    check_count += 1
    elapsed = int(time.time() - start)
    print(f"\n[T+{elapsed:3d}s] 检查 #{check_count}")

    for target, port in [('prod', 9200), ('staging', 19200)]:
        # 看进程是否存在
        r = yexec(
            'ps -ef | grep -E "log_service\\.py" | grep -v grep | grep nobody || echo "NO_NOBODY_PROCESS"',
            port=port, secret='prod_write', timeout=10)
        out = (r.get('stdout', '') or '').strip()

        # 看端口是否活
        port_num = 9101 if target == 'prod' else 19101
        r2 = yexec(
            f'curl -s -o /dev/null -w "%{{http_code}}" --max-time 3 http://localhost:{port_num}/api/health 2>&1 || echo "FAIL"',
            port=port, secret='prod_write', timeout=10)
        http_status = (r2.get('stdout', '') or '').strip()

        # 看 journalctl 有没有新的 killed
        r3 = yexec(
            f'journalctl -u log_service_{target}.service --since "30 seconds ago" --no-pager 2>&1 | grep -E "(killed|KILL|status=9)" | tail -3 || echo "no_kill_msg"',
            port=port, secret='prod_write', timeout=10)
        kill_msg = (r3.get('stdout', '') or '').strip()

        status = "[OK]" if "nobody" in out and http_status == "200" else "[DEAD]"
        print(f"  {target:8s} {status} process={out[:60]!r:60s} http={http_status}")
        if kill_msg and kill_msg != 'no_kill_msg':
            print(f"  KILL MSG: {kill_msg[:120]}")
            killed_count += 1

    time.sleep(10)

print(f"\n{'='*70}")
print(f"[DONE] 检查 {check_count} 次, 杀进程事件 {killed_count} 次")
if killed_count == 0:
    print("[OK] HIPS 未杀 nobody 进程 — 修复成功")
else:
    print("[FAIL] 仍有杀进程事件, 需进一步调查")