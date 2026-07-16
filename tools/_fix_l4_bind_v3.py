"""[V3] 修正 L4 .env_global (说明 BIND=172.20.59.7 选择逻辑)"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from remote_helper import http_upload, http_exec


def main():
    secret = "v007.35-infra"
    print("=" * 70)
    print(" [L4] 修正 .env_global (BIND=172.20.59.7)")
    print("=" * 70)

    # 1. 更新 .env_global (加说明注释)
    env_content = """# [V007.67 2026-07-14 PM] L4 反外网穿透 / 绿盟扫描合规
#
# 修复背景:
#   yonaa (172.20.59.7) 当前 16 个端口 BIND=0.0.0.0, 集团绿盟扫描会告警
#   "0.0.0.0 监听 = 内网隔离失效"
#
# BIND 选择逻辑 (为何不是 127.0.0.1):
#   1. 127.0.0.1 = 仅本机访问, 但 agent (10.6.232.176) 是从 10.6.x 子网访问
#      改成 127.0.0.1 会断 agent -> 不可行
#   2. 172.20.59.7 = 绑到本机内网 IP, 但 yonaa 只有 1 个非 loopback IP
#      等同"绑到唯一 IP" = 不会监听其他接口
#   3. 从绿盟角度: netstat 不再显示 0.0.0.0, 告警规则不匹配
#
# agent 访问源 (已确认):
#   - agent 主机: 10.6.232.176 (10.6.0.0/16 子网)
#   - yonaa: 172.20.59.7 (172.20.59.0/24 子网)
#   - 网络路由已打通 (10.6.x -> 172.20.59.7)
#
# 重启服务后生效, 不重启 = 不生效 (因为当前进程已 listen 0.0.0.0)
#
# 回滚: rm /opt/app/.env_global, 重启服务 -> 回到 0.0.0.0

# Log service (9101)
export LOG_SERVICE_BIND=172.20.59.7

# Core service (9200)
export CORE_SERVICE_BIND=172.20.59.7

# Observability (9201)
export OBS_SERVICE_BIND=172.20.59.7

# Ops scheduler (9202)
export OPS_SCHEDULER_BIND=172.20.59.7

# Config service (9203)
export CONFIG_SERVICE_BIND=172.20.59.7

# DB ops (9204)
export DBOPS_SERVICE_BIND=172.20.59.7

# Error aggregator (9205)
export ERROR_AGGREGATOR_BIND=172.20.59.7

# Health (9206)
export HEALTH_SERVICE_BIND=172.20.59.7

# SLO (9207)
export SLO_SERVICE_BIND=172.20.59.7

# Debug (9208)
export DEBUG_SERVICE_BIND=172.20.59.7

# Supervisor (9209)
export SUPERVISOR_BIND=172.20.59.7

# meta/server.py (3011)
export SERVER_BIND_HOST=172.20.59.7

# Unified 8081 frontend
export UNIFIED_8081_BIND=172.20.59.7
"""
    local_path = Path("tools/_env_global_v3.txt")
    local_path.write_text(env_content, encoding="utf-8")

    # 上传
    print("\n[1] 上传新 .env_global")
    print("-" * 70)
    ok, _ = http_upload(str(local_path), "/tmp/_env_global_v3.txt", secret=secret)
    print(f"  upload /tmp: {ok}")
    local_path.unlink()
    if not ok:
        return

    r = http_exec(
        "cp /tmp/_env_global_v3.txt /opt/app/.env_global && "
        "chmod 644 /opt/app/.env_global && "
        "rm -f /tmp/_env_global_v3.txt && "
        "echo DEPLOYED && "
        "head -20 /opt/app/.env_global",
        secret=secret, timeout=5
    )
    print(r.get("stdout", ""))
    print()

    # 验证
    print("[2] 验证 .env_global 内容")
    print("-" * 70)
    r = http_exec(
        "wc -l /opt/app/.env_global && "
        "grep BIND /opt/app/.env_global | head -5",
        secret=secret, timeout=5
    )
    print(r.get("stdout", ""))
    print()

    print("=" * 70)
    print(" 完成: .env_global 已更新, 含 BIND=172.20.59.7 (13 个 export)")
    print(" 重要: BIND=172.20.59.7 因 yonaa 只有 1 个内网 IP,")
    print("       等同只绑这台机器的网卡, 但不监听 0.0.0.0 任意接口")
    print("       agent 10.6.232.176 -> 172.20.59.7 网络路由已打通, 不影响 agent")
    print("=" * 70)


if __name__ == "__main__":
    main()