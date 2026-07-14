"""[V3] 安全清理: L1 L3 .bak 文件 (绿盟扫描会看到)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from remote_helper import http_exec


def main():
    secret = "v007.35-infra"
    print("=" * 70)
    print(" [L1+L3] 安全清理 .bak 文件")
    print("=" * 70)

    # 1. 列出 .bak 文件
    print("\n[1] /opt/app/shared/ .bak 文件")
    print("-" * 70)
    r = http_exec(
        "ls -la /opt/app/shared/*.bak /opt/app/shared/*.bak.* 2>/dev/null",
        secret=secret, timeout=5
    )
    out = r.get("stdout", "").strip()
    print(out if out else "(无)")
    print()

    # 2. 备份到隔离位置
    print("[2] 移到 /opt/app/.bak_archive/ (不删除, 隔离)")
    print("-" * 70)
    r = http_exec(
        "mkdir -p /opt/app/.bak_archive && "
        "mv -v /opt/app/shared/*.bak /opt/app/shared/*.bak.* /opt/app/.bak_archive/ 2>&1 | head -20",
        secret=secret, timeout=10
    )
    print(r.get("stdout", ""))
    print()

    # 3. 验证
    print("[3] 验证 .bak 已被移走")
    print("-" * 70)
    r = http_exec(
        "ls /opt/app/shared/*.bak /opt/app/shared/*.bak.* 2>/dev/null || echo '(无 .bak)'",
        secret=secret, timeout=5
    )
    print(r.get("stdout", ""))
    print()

    # 4. 看 archive 列表
    print("[4] .bak_archive 内容")
    print("-" * 70)
    r = http_exec("ls -la /opt/app/.bak_archive/ 2>/dev/null", secret=secret, timeout=5)
    print(r.get("stdout", ""))
    print()

    print("=" * 70)
    print(" 完成: .bak 文件已隔离 (不删除, 保留证据)")
    print("=" * 70)


if __name__ == "__main__":
    main()