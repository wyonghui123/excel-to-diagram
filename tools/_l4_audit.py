"""[V3] L4 深度检查 - 0.0.0.0 监听 (绿盟扫描核心关注)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from remote_helper import http_exec


def main():
    secret = "v007.35-infra"
    print("=" * 70)
    print(" [L4] 0.0.0.0 监听检查 (绿盟扫描核心)")
    print("=" * 70)

    # 1. ss -tlnp (绿盟看到的就是这个)
    print("\n[1] ss -tlnp 全部监听")
    print("-" * 70)
    r = http_exec("ss -tlnp 2>/dev/null", secret=secret, timeout=10)
    print(r.get("stdout", ""))
    print()

    # 2. 所有 .py 中 BIND 默认值
    print("[2] BIND=0.0.0.0 默认值")
    print("-" * 70)
    r = http_exec(
        "grep -n 'BIND.*0\\.0\\.0\\.0' /opt/app/shared/*.py /opt/app/staging/bin/*.py 2>/dev/null",
        secret=secret, timeout=10
    )
    print(r.get("stdout", ""))
    print()

    # 3. 哪些端口绑到 0.0.0.0
    print("[3] 0.0.0.0 绑定端口清单")
    print("-" * 70)
    r = http_exec(
        "ss -tlnp 2>/dev/null | grep '0.0.0.0' | head -20",
        secret=secret, timeout=10
    )
    print(r.get("stdout", ""))
    print()

    # 4. 哪些绑到 127.0.0.1 (合规)
    print("[4] 127.0.0.1 绑定 (合规, 绿盟不告警)")
    print("-" * 70)
    r = http_exec(
        "ss -tlnp 2>/dev/null | grep '127.0.0.1' | head -20",
        secret=secret, timeout=10
    )
    print(r.get("stdout", ""))
    print()

    # 5. 哪些绑到具体 IP
    print("[5] 具体 IP 绑定 (合规)")
    print("-" * 70)
    r = http_exec(
        "ss -tlnp 2>/dev/null | grep -v '0.0.0.0\\|127.0.0.1\\|::' | head -20",
        secret=secret, timeout=10
    )
    print(r.get("stdout", ""))
    print()

    print("=" * 70)


if __name__ == "__main__":
    main()