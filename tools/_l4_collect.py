"""[V3] 检查 yonaa 网络拓扑 + 评估 L4 L7.f 修复方案"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from remote_helper import http_exec


def main():
    secret = "v007.35-infra"
    print("=" * 70)
    print(" 网络拓扑 + L4 修复方案评估")
    print("=" * 70)

    # 1. 主机 IP
    print("\n[1] 主机 IP (内网/外网?)")
    print("-" * 70)
    r = http_exec("ip addr 2>/dev/null | grep -E 'inet ' | head -10", secret=secret, timeout=5)
    print(r.get("stdout", ""))
    print()

    # 2. 默认路由
    print("[2] 路由表")
    print("-" * 70)
    r = http_exec("ip route 2>/dev/null | head -10", secret=secret, timeout=5)
    print(r.get("stdout", ""))
    print()

    # 3. 网卡名
    print("[3] 网卡")
    print("-" * 70)
    r = http_exec("ip link 2>/dev/null | head -15", secret=secret, timeout=5)
    print(r.get("stdout", ""))
    print()

    # 4. 当前 iptables 状态
    print("[4] iptables 状态 (绿盟重点)")
    print("-" * 70)
    r = http_exec("iptables -L -n 2>/dev/null | head -30", secret=secret, timeout=5)
    print(r.get("stdout", ""))
    print()

    # 5. iptables-save (看 NAT)
    print("[5] iptables-save (NAT)")
    print("-" * 70)
    r = http_exec("iptables-save 2>/dev/null | head -30", secret=secret, timeout=5)
    print(r.get("stdout", ""))
    print()

    # 6. SSH 服务 (V007.66 之后的状态)
    print("[6] 当前 SSH 进程")
    print("-" * 70)
    r = http_exec("ps -ef | grep sshd | grep -v grep | head -5", secret=secret, timeout=5)
    print(r.get("stdout", ""))
    print()

    # 7. 当前哪些 IP 在用 SSH
    print("[7] 当前 SSH 登录会话")
    print("-" * 70)
    r = http_exec("who 2>/dev/null", secret=secret, timeout=5)
    print(r.get("stdout", ""))
    print()

    # 8. 当前是 .34 / 192.168 / 172 内网?
    print("[8] 内网判定")
    print("-" * 70)
    r = http_exec("ip -4 addr show 2>/dev/null | grep -E 'inet ' | awk '{print $2}'", secret=secret, timeout=5)
    ips = r.get("stdout", "").strip().split("\n")
    print(f"  本机 IP: {ips}")
    for ip in ips:
        ip_clean = ip.split("/")[0]
        if ip_clean.startswith("10."):
            print(f"  {ip_clean} = RFC1918 10/8 (内网)")
        elif ip_clean.startswith("172."):
            second = int(ip_clean.split(".")[1])
            if 16 <= second <= 31:
                print(f"  {ip_clean} = RFC1918 172.16/12 (内网)")
        elif ip_clean.startswith("192.168."):
            print(f"  {ip_clean} = RFC1918 192.168/16 (内网)")
        else:
            print(f"  {ip_clean} = 公网或特殊")
    print()

    print("=" * 70)


if __name__ == "__main__":
    main()