"""[OPS] 测试 server 端写文件 (用于 agent poll 模式)"""
import sys
sys.path.insert(0, r'd:\filework\release-prep-worktree\tools')
from yonaa_exec import yexec

cmd = '''mkdir -p /opt/app/deployments/.alert_state && echo "$(date -Iseconds) test_from_local" > /opt/app/deployments/.alert_state/test.txt && cat /opt/app/deployments/.alert_state/test.txt && chmod 666 /opt/app/deployments/.alert_state/test.txt && ls -la /opt/app/deployments/.alert_state/'''
r = yexec(cmd, port=9200, secret='prod_write', timeout=10)
out = (r.get('stdout', '') or r.get('stderr', '')).strip()
print(out)