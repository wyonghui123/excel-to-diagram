"""[V3] L4 0.0.0.0 监听 - 用 netstat 替代 ss"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from remote_helper import http_exec


def main():
    secret = "v007.35-infra"
    print("=" * 70)
    print(" [L4] 0.0.0.0 监听 (绿盟扫描核心)")
    print("=" * 70)

    # 1. netstat
    print("\n[1] netstat -tlnp")
    print("-" * 70)
    r = http_exec("netstat -tlnp 2>/dev/null", secret=secret, timeout=10)
    print(r.get("stdout", ""))
    print()

    # 2. 进程命令行
    print("[2] 进程命令行 (Python 服务如何启动)")
    print("-" * 70)
    r = http_exec(
        "ps -ef 2>/dev/null | grep -E 'python.*\\.py|unified' | grep -v grep | head -15",
        secret=secret, timeout=5
    )
    print(r.get("stdout", ""))
    print()

    # 3. log_service 当前实际绑定
    print("[3] log_service 实际绑定")
    print("-" * 70)
    r = http_exec(
        "ls -la /proc/$(pgrep -f 'log_service.py' | head -1)/net 2>/dev/null | head -5",
        secret=secret, timeout=5
    )
    out = r.get("stdout", "")
    print(f"  /proc/PID/net: {out[:200] if out else '(空 - 进程可能不在了)'}")
    print()

    # 4. /proc/PID/cmdline
    print("[4] log_service 实际启动 cmdline")
    print("-" * 70)
    r = http_exec(
        "PID=$(pgrep -f 'log_service.py' | head -1); "
        "echo PID=$PID; "
        "cat /proc/$PID/cmdline 2>/dev/null | tr '\\0' ' '",
        secret=secret, timeout=5
    )
    print(r.get("stdout", ""))
    print()

    # 5. /proc/net/tcp 看 0.0.0.0
    print("[5] /proc/net/tcp 0.0.0.0 监听端口")
    print("-" * 70)
    r = http_exec(
        "awk 'NR>1 && $2 ~ /00000000:/ {split($2, a, \":\"); print \"port \" strtonum(\"0x\" a[2])}' /proc/net/tcp 2>/dev/null | sort -u",
        secret=secret, timeout=5
    )
    print(r.get("stdout", ""))
    print()

    print("=" * 70)


if __name__ == "__main__":
    main()