"""[V3] L4 .env_global 上传 (单行命令)"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from remote_helper import http_upload, http_exec


def main():
    secret = "v007.35-infra"
    print("=" * 70)
    print(" [L4] .env_global 修复")
    print("=" * 70)

    # 1. 本地写好文件
    env_content = """# [V007.67 2026-07-14] L4 反外网穿透合规
# 强制所有服务 BIND 到内网 IP (172.20.59.7), 不监听 0.0.0.0
export LOG_SERVICE_BIND=172.20.59.7
export CORE_SERVICE_BIND=172.20.59.7
export OBS_SERVICE_BIND=172.20.59.7
export OPS_SCHEDULER_BIND=172.20.59.7
export CONFIG_SERVICE_BIND=172.20.59.7
export DBOPS_SERVICE_BIND=172.20.59.7
export ERROR_AGGREGATOR_BIND=172.20.59.7
export HEALTH_SERVICE_BIND=172.20.59.7
export SLO_SERVICE_BIND=172.20.59.7
export DEBUG_SERVICE_BIND=172.20.59.7
export SUPERVISOR_BIND=172.20.59.7
export SERVER_BIND_HOST=172.20.59.7
export UNIFIED_8081_BIND=172.20.59.7
"""
    local_path = Path("tools/_env_global_l4.txt")
    local_path.write_text(env_content, encoding="utf-8")

    # 2. 上传
    print("\n[1] 上传 /opt/app/.env_global")
    print("-" * 70)
    ok, _ = http_upload(str(local_path), "/opt/app/.env_global", secret=secret)
    print(f"  upload: {ok}")
    local_path.unlink()
    if not ok:
        return

    r = http_exec("chmod 644 /opt/app/.env_global && cat /opt/app/.env_global | head -3", secret=secret, timeout=5)
    print(r.get("stdout", ""))
    print()

    # 3. 验证 BIND 状态
    print("[2] 当前进程 BIND (重启前)")
    print("-" * 70)
    r = http_exec(
        "netstat -tlnp 2>/dev/null | head -20",
        secret=secret, timeout=5
    )
    print(r.get("stdout", ""))
    print()

    print("=" * 70)


if __name__ == "__main__":
    main()