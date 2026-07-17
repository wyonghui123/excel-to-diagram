"""
上传新 service 文件 + daemon-reload + restart + 验证 nobody 起服务
"""
import sys
sys.path.insert(0, r'd:\filework\worktrees/release-prep\tools')
from yonaa_exec import yexec, yupload

PROD_UNIT_LOCAL = r'd:\filework\worktrees/release-prep\tools\log_service_prod.service'
PROD_UNIT_REMOTE_TMP = '/opt/app/deployments/log_service_prod.service'
PROD_UNIT_REMOTE = '/etc/systemd/system/log_service_prod.service'

STAGING_UNIT_LOCAL = r'd:\filework\worktrees/release-prep\tools\log_service_staging.service'
STAGING_UNIT_REMOTE_TMP = '/opt/app/staging/deploy/log_service_staging.service'
STAGING_UNIT_REMOTE = '/etc/systemd/system/log_service_staging.service'


def deploy(target: str, local: str, remote_tmp: str, remote: str, port: int):
    print(f"\n========== {target} ==========")
    # 1. 上传到 core_service 白名单允许的目录
    print(f"\n[1] yuploadd {local} → {remote_tmp}")
    r = yupload(local, remote_tmp, port=port, secret='prod_write')
    print(f"    返回: {r.get('status', r)}")

    # 2. cp 到 /etc/systemd/system/
    print(f"\n[2] cp {remote_tmp} → {remote}")
    r = yexec(f'cp {remote_tmp} {remote}', port=port, secret='prod_write', timeout=10)
    print(f"    返回: {r.get('stdout', r.get('stderr', r))}")

    # 3. daemon-reload
    print(f"\n[3] systemctl daemon-reload")
    r = yexec('systemctl daemon-reload', port=port, secret='prod_write', timeout=10)
    print(f"    返回: {r.get('stdout', r.get('stderr', r))}")

    # 4. restart (systemd 会起 nobody)
    print(f"\n[4] systemctl restart log_service_{target}.service")
    unit = f'log_service_{target}.service'
    r = yexec(f'systemctl restart {unit}', port=port, secret='prod_write', timeout=15)
    print(f"    返回: {r.get('stdout', r.get('stderr', r))}")

    # 5. 等 3 秒, 看进程是不是 nobody 在跑
    import time
    time.sleep(3)
    print(f"\n[5] sleep 3 后, 看进程 user")
    r = yexec(
        f'ps -ef | grep -E "log_service\\.py.*:9[10]01" | grep -v grep',
        port=port, secret='prod_write', timeout=10)
    print(f"    ps 输出:\n{r.get('stdout', r.get('stderr', r))}")

    # 6. systemctl status 看 Active + Main PID
    print(f"\n[6] systemctl status log_service_{target}.service")
    r = yexec(
        f'systemctl status log_service_{target}.service --no-pager | head -15',
        port=port, secret='prod_write', timeout=10)
    print(f"    status:\n{r.get('stdout', r.get('stderr', r))}")


if __name__ == '__main__':
    deploy('prod', PROD_UNIT_LOCAL, PROD_UNIT_REMOTE_TMP, PROD_UNIT_REMOTE, 9200)
    deploy('staging', STAGING_UNIT_LOCAL, STAGING_UNIT_REMOTE_TMP, STAGING_UNIT_REMOTE, 19200)