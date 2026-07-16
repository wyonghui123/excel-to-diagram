"""[V3] L1-L7 绿盟扫描重点检查 [V007.67]
绿盟 (NSFOCUS) 内网扫描主要检测:
- L1: HTTP 127.0.0.1 自调用 (反木马)
- L2: base64 + bash -c (反木马)
- L3: 脚本套脚本中间层
- L4: 0.0.0.0 绑定 / FRP / ngrok (内网隔离)
- L5: bash 解码 + 多层嵌套 (反木马)
- L6: 开放端口无 token/白名单 (内网暴露)
- L7: 弱密码 / 默认账号 / 硬编码密码
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from remote_helper import http_exec


def main():
    secret = "v007.35-infra"
    print("=" * 70)
    print(" [L1-L7] 绿盟扫描合规现状检查 [V007.67]")
    print("=" * 70)

    # L1: HTTP 127.0.0.1 自调用
    print("\n[L1] HTTP 127.0.0.1 自调用")
    print("-" * 70)
    r = http_exec(
        "grep -rn '127.0.0.1:9101' /opt/app/shared/ /opt/app/deployments/ 2>/dev/null | head -10",
        secret=secret, timeout=15
    )
    out = r.get("stdout", "").strip()
    print(f"  127.0.0.1:9101 引用: {out[:200] if out else '(无)'}")
    print()

    # L2: base64 + bash -c
    print("[L2] base64 + bash -c 实际模式 (排除注释)")
    print("-" * 70)
    r = http_exec(
        "grep -rn 'base64.b64encode\\|base64.b64decode' /opt/app/shared/*.py 2>/dev/null | grep -v '^[0-9]*:\\s*#' | head -10",
        secret=secret, timeout=15
    )
    out = r.get("stdout", "").strip()
    print(f"  base64 真实模式: {out if out else '(无 - 已修复 ✓)'}")
    print()

    # L3: 脚本套脚本中间层
    print("[L3] /tmp/*.py 立即执行的模式")
    print("-" * 70)
    r = http_exec(
        "grep -rn '/tmp/.*\\.py' /opt/app/shared/ 2>/dev/null | grep -E 'python3|sh|bash' | head -5",
        secret=secret, timeout=15
    )
    out = r.get("stdout", "").strip()
    print(f"  /tmp/*.py 立即执行: {out[:200] if out else '(无 ✓)'}")
    print()

    # L4: 0.0.0.0 绑定
    print("[L4] 0.0.0.0 监听 (绿盟重点: 内网隔离)")
    print("-" * 70)
    r = http_exec(
        "ss -tlnp 2>/dev/null | head -20",
        secret=secret, timeout=5
    )
    print(r.get("stdout", "")[:1000])
    print()

    # L5: bash 解码嵌套
    print("[L5] bash 解码嵌套 (反木马)")
    print("-" * 70)
    r = http_exec(
        "grep -rn 'base64 -d.*|.*bash\\|base64 -d.*|.*sh' /opt/app/shared/ 2>/dev/null | head -5",
        secret=secret, timeout=15
    )
    out = r.get("stdout", "").strip()
    print(f"  bash + base64 管道: {out if out else '(无 ✓)'}")
    print()

    # L6: 开放端口
    print("[L6] 开放端口 (9101/9200/9202/9203/9204/9205/9206)")
    print("-" * 70)
    r = http_exec(
        "ls -la /opt/app/shared/*.py 2>/dev/null | grep -E 'service\\.py' | awk '{print $NF}' | head -10",
        secret=secret, timeout=5
    )
    services = r.get("stdout", "").strip().split("\n")
    print(f"  服务文件: {len(services)} 个")
    for s in services:
        print(f"    {s}")
    print()

    # L7: 弱密码/默认账号
    print("[L7] 默认账号 + 弱密码 (绿盟重点)")
    print("-" * 70)
    # 检查 admin/admin123 引用
    r = http_exec(
        "grep -rn 'admin123\\|Admin@2026\\|password.*=.*['\\\"]' /opt/app/shared/*.py 2>/dev/null | grep -v '^[0-9]*:\\s*#' | head -10",
        secret=secret, timeout=15
    )
    out = r.get("stdout", "").strip()
    print(f"  默认/硬编码密码: {out[:500] if out else '(无 ✓)'}")
    print()

    print("=" * 70)


if __name__ == "__main__":
    main()