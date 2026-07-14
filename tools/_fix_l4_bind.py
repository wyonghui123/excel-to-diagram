"""[V3] L4 完整修复: 0.0.0.0 -> 172.20.59.7 (绿盟 P0) [V007.67]

策略:
  1. 不修改服务代码 (0 风险, 完全可逆)
  2. 在 /opt/app/.env_global 加 export *_BIND=172.20.59.7
  3. systemd / start_*.sh source .env_global
  4. 重启服务 -> 新 BIND 生效
  5. 验证: netstat 看到 172.20.59.7 而非 0.0.0.0

回滚:
  1. rm /opt/app/.env_global
  2. 重启服务 -> 回到 0.0.0.0
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from remote_helper import http_upload, http_exec


def main():
    secret = "v007.35-infra"
    print("=" * 70)
    print(" [L4] 0.0.0.0 -> 172.20.59.7 修复 (绿盟 P0)")
    print("=" * 70)

    # 1. 创建 .env_global (放 L4 BIND 设置)
    print("\n[1] 创建 /opt/app/.env_global (BIND=172.20.59.7)")
    print("-" * 70)
    env_content = """# [V007.67 2026-07-14] L4 反外网穿透合规
# 强制所有服务 BIND 到内网 IP (172.20.59.7), 不监听 0.0.0.0
# 绿盟扫描关注: 0.0.0.0 暴露到内网任意 IP = 内网隔离失效
# 修复: 显式 BIND 到 172.20.59.7 (本机内网 IP), 阻止跨网段访问

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
    env_path = Path("tools/_env_global_l4_fix.sh")
    env_path.write_text(env_content, encoding="utf-8")
    ok, _ = http_upload(str(env_path), "/opt/app/.env_global", secret=secret)
    print(f"  upload: {ok}")
    if not ok:
        return

    r = http_exec("chmod 644 /opt/app/.env_global && cat /opt/app/.env_global | head -5", secret=secret, timeout=5)
    print(r.get("stdout", ""))
    env_path.unlink()
    print()

    # 2. 检查是否有 systemd 单元文件 (能否直接改 Environment)
    print("[2] systemd 单元文件")
    print("-" * 70)
    r = http_exec(
        "ls -la /etc/systemd/system/ 2>/dev/null | grep -E 'service|app' | head -20",
        secret=secret, timeout=5
    )
    print(r.get("stdout", ""))
    print()

    # 3. 看 start_*.sh 脚本 (服务是怎么启动的)
    print("[3] start_*.sh 启动脚本")
    print("-" * 70)
    r = http_exec(
        "ls -la /opt/app/shared/start_*.sh /opt/app/shared/restart.sh 2>/dev/null",
        secret=secret, timeout=5
    )
    print(r.get("stdout", ""))
    print()

    # 4. 在 start_*.sh 头部加 source .env_global
    print("[4] 给所有 start_*.sh 加 source /opt/app/.env_global (不修改, 验证可行)")
    print("-" * 70)
    # 这里仅检查，不修改
    r = http_exec(
        "head -10 /opt/app/shared/start_log.sh 2>/dev/null",
        secret=secret, timeout=5
    )
    print(r.get("stdout", ""))
    print()

    # 5. 列出所有需要重启的服务 PID
    print("[5] 当前服务 PID 清单 (重启前快照)")
    print("-" * 70)
    r = http_exec(
        "ps -ef 2>/dev/null | grep -E 'python.*service\\.py|unified_(8081|18081)\\.py|server\\.py' | grep -v grep | awk '{print $2, $NF}' | head -20",
        secret=secret, timeout=5
    )
    print(r.get("stdout", ""))
    print()

    print("=" * 70)
    print(" 完成: .env_global 已创建, 待执行重启")
    print("=" * 70)


if __name__ == "__main__":
    main()