"""[V3] L6 L7 深度检查 - 绿盟重点"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from remote_helper import http_exec


def main():
    secret = "v007.35-infra"
    print("=" * 70)
    print(" [L6+L7] 绿盟深度检查")
    print("=" * 70)

    # L6 端口防护
    print("\n[L6] 各端口的 token/白名单 防护")
    print("-" * 70)

    # 测试 9200/9204/9205 是否要 token
    for port, name in [(9101, "log_service"), (9200, "core_service"),
                        (9204, "dbops_service"), (9205, "deploy_service")]:
        r = http_exec(
            f"curl -s --max-time 3 -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{port}/api/system/health 2>&1; "
            f"echo; "
            f"curl -s --max-time 3 -o /dev/null -w '%{{http_code}}' 'http://127.0.0.1:{port}/api/system/health?token=invalid' 2>&1",
            secret=secret, timeout=10
        )
        out = r.get("stdout", "").strip()
        print(f"  {port:5} {name:18} -> {out[:80]}")
    print()

    # L7 弱密码 - 检查数据库用户
    print("[L7] 弱密码 + 默认账号 (绿盟重点)")
    print("-" * 70)
    # 在 yonaa 上找 default password
    r = http_exec(
        "grep -rn 'admin123\\|DeployTest@2026\\|admin / admin123\\|password.*=.*['\\\"]admin' /opt/app/shared/*.py /opt/app/staging/bin/*.py 2>/dev/null | grep -v '#' | head -10",
        secret=secret, timeout=15
    )
    out = r.get("stdout", "").strip()
    print(f"  默认密码: {out if out else '(无)'}")
    print()

    # 检查 .env 文件
    print("[L7.b] .env 配置文件 (含明文密码?)")
    print("-" * 70)
    r = http_exec(
        "ls -la /opt/app/.env /opt/app/deployments/.env 2>/dev/null",
        secret=secret, timeout=5
    )
    print(r.get("stdout", ""))
    r = http_exec(
        "cat /opt/app/deployments/.env 2>/dev/null | head -5",
        secret=secret, timeout=5
    )
    print(r.get("stdout", ""))
    print()

    # 检查数据库用户
    print("[L7.c] 数据库用户 (architecture.db)")
    print("-" * 70)
    r = http_exec(
        "find /opt/app -name 'architecture.db' 2>/dev/null | head -3",
        secret=secret, timeout=10
    )
    db_paths = r.get("stdout", "").strip().split("\n")
    for db in db_paths[:1]:
        r = http_exec(
            f"echo 'SELECT username, role FROM users LIMIT 5;' | /opt/miniconda3-py39/bin/python3 -c \"import sqlite3; c=sqlite3.connect('{db}'); print('\\n'.join(str(r) for r in c.execute('SELECT username, role FROM users LIMIT 5').fetchall()))\" 2>&1",
            secret=secret, timeout=10
        )
        print(r.get("stdout", ""))
    print()

    # L7.d 文档含密码
    print("[L7.d] 文档脱敏 (DEPLOY-CHEATSHEET)")
    print("-" * 70)
    r = http_exec(
        "grep -l 'Admin@2026' /opt/app/docs/ /opt/app/deployments/docs/ -r 2>/dev/null | head -5",
        secret=secret, timeout=15
    )
    out = r.get("stdout", "").strip()
    print(f"  含明文密码的文档: {out if out else '(无)'}")
    print()

    # L7.e 系统账号
    print("[L7.e] 系统用户 (passwd)")
    print("-" * 70)
    r = http_exec(
        "cat /etc/passwd | grep -v 'nologin\\|false' | head -10",
        secret=secret, timeout=5
    )
    print(r.get("stdout", ""))
    print()

    # L7.f SSH 密码登录
    print("[L7.f] SSH PasswordAuthentication")
    print("-" * 70)
    r = http_exec(
        "grep -E 'PasswordAuthentication|PermitRootLogin' /etc/ssh/sshd_config",
        secret=secret, timeout=5
    )
    print(r.get("stdout", ""))
    print()

    # L6.g 防火墙状态
    print("[L6.g] iptables 防火墙状态")
    print("-" * 70)
    r = http_exec(
        "iptables -L INPUT 2>/dev/null | head -15",
        secret=secret, timeout=5
    )
    print(r.get("stdout", ""))
    print()

    print("=" * 70)


if __name__ == "__main__":
    main()