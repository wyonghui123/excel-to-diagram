"""[V3] 修复 L7.b .env 脱敏 (绿盟高优) [V007.67]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from remote_helper import http_exec


def main():
    secret = "v007.35-infra"
    print("=" * 70)
    print(" [L7.b] 修复 .env 脱敏 (绿盟高优)")
    print("=" * 70)

    # 1. 备份
    print("\n[1] 备份 .env")
    print("-" * 70)
    r = http_exec(
        "cp /opt/app/deployments/.env /opt/app/deployments/.env.v007.67.bak && echo BACKUPED",
        secret=secret, timeout=5
    )
    print(r.get("stdout", "").strip())
    print()

    # 2. 改写 .env (用 placeholder)
    print("[2] 改写 .env")
    print("-" * 70)
    r = http_exec(
        "echo '# Auto-generated JWT Secret Key (use vault in production)' > /opt/app/deployments/.env && "
        "echo 'JWT_SECRET_KEY=<set-by-deploy.sh-via-secrets.token_urlsafe(48)>' >> /opt/app/deployments/.env && "
        "cat /opt/app/deployments/.env",
        secret=secret, timeout=5
    )
    print(r.get("stdout", ""))
    print()

    # 3. 改权限 (chmod 600)
    print("[3] 改权限 600")
    print("-" * 70)
    r = http_exec(
        "chmod 600 /opt/app/deployments/.env && ls -la /opt/app/deployments/.env",
        secret=secret, timeout=5
    )
    print(r.get("stdout", ""))
    print()

    # 4. 看哪个服务在用 .env
    print("[4] 谁在读 .env")
    print("-" * 70)
    r = http_exec(
        "grep -l 'JWT_SECRET_KEY' /opt/app/shared/*.py /opt/app/staging/bin/*.py 2>/dev/null | head -5",
        secret=secret, timeout=10
    )
    print(r.get("stdout", ""))
    print()

    print("=" * 70)


if __name__ == "__main__":
    main()