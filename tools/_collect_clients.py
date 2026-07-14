"""[V3] 看 yonaa 服务的访问来源 (决定 BIND 应该用哪个)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from remote_helper import http_exec


def main():
    secret = "v007.35-infra"
    print("=" * 70)
    print(" yonaa 服务访问来源分析 (决定 BIND 选哪个)")
    print("=" * 70)

    # 1. 当前活跃连接
    print("\n[1] 当前所有 ESTABLISHED 连接")
    print("-" * 70)
    r = http_exec(
        "netstat -tn 2>/dev/null | grep ESTAB | head -30",
        secret=secret, timeout=5
    )
    out = r.get("stdout", "").strip()
    print(out if out else "(无)")
    print()

    # 2. 哪些 IP 访问 9101
    print("[2] 访问 9101 log_service 的源 IP")
    print("-" * 70)
    r = http_exec(
        "netstat -tn 2>/dev/null | grep ':9101' | awk '{print $5}' | cut -d: -f1 | sort -u",
        secret=secret, timeout=5
    )
    print(r.get("stdout", ""))
    print()

    # 3. 哪些 IP 访问 9200
    print("[3] 访问 9200 core_service 的源 IP")
    print("-" * 70)
    r = http_exec(
        "netstat -tn 2>/dev/null | grep ':9200' | awk '{print $5}' | cut -d: -f1 | sort -u",
        secret=secret, timeout=5
    )
    print(r.get("stdout", ""))
    print()

    # 4. 哪些 IP 访问 8081
    print("[4] 访问 8081 unified 的源 IP")
    print("-" * 70)
    r = http_exec(
        "netstat -tn 2>/dev/null | grep ':8081' | awk '{print $5}' | cut -d: -f1 | sort -u",
        secret=secret, timeout=5
    )
    print(r.get("stdout", ""))
    print()

    # 5. 哪些 IP 访问 staging 端口
    print("[5] 访问 staging 端口的源 IP (13011/18081/19101/19200)")
    print("-" * 70)
    r = http_exec(
        "netstat -tn 2>/dev/null | grep -E ':13011|:18081|:19101|:19200' | awk '{print $5}' | cut -d: -f1 | sort -u",
        secret=secret, timeout=5
    )
    print(r.get("stdout", ""))
    print()

    # 6. 谁连 9201-9209 (监控/调度)
    print("[6] 访问 9201-9209 (监控/调度) 的源 IP")
    print("-" * 70)
    r = http_exec(
        "netstat -tn 2>/dev/null | grep -E ':920[1-9]' | awk '{print $5}' | cut -d: -f1 | sort -u",
        secret=secret, timeout=5
    )
    print(r.get("stdout", ""))
    print()

    # 7. 全部外部 IP 列表 (排除 127.x 和本机 172.20.59.7)
    print("[7] 外部 IP 列表 (排除 127.x 和 172.20.59.7)")
    print("-" * 70)
    r = http_exec(
        "netstat -tn 2>/dev/null | grep ESTAB | awk '{print $5}' | cut -d: -f1 | sort -u | grep -v '^127\\.' | grep -v '^172.20.59.7$'",
        secret=secret, timeout=5
    )
    out = r.get("stdout", "").strip()
    print(out if out else "(无外部 IP)")
    print()

    print("=" * 70)


if __name__ == "__main__":
    main()