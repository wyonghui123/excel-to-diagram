"""[V3] 把 delta 能力从 /tmp/delta_test 部署到 /opt/app/shared + /opt/app/deployments/lib
[V007.67 2026-07-14]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from remote_helper import http_upload, http_exec


def main():
    secret = "v007.35-infra"
    print("=" * 70)
    print(" 部署 delta 能力到 /opt/app/ (prod)")
    print("=" * 70)
    print()

    # 1. 备份 + 创建目标目录
    print("[1] 备份 + 创建目标目录")
    print("-" * 70)
    r = http_exec(
        "test -d /opt/app/shared/lib && echo 'exists' || mkdir -p /opt/app/shared/lib && echo 'created'",
        secret=secret, timeout=5
    )
    print(r.get("stdout", "").strip())
    r = http_exec(
        "test -d /opt/app/deployments/lib && echo 'exists' || mkdir -p /opt/app/deployments/lib && echo 'created'",
        secret=secret, timeout=5
    )
    print(r.get("stdout", "").strip())
    print()

    # 2. 上传 manifest_utils.py 到 /opt/app/shared/
    print("[2] 上传 manifest_utils.py -> /opt/app/shared/manifest_utils.py")
    print("-" * 70)
    src = Path(__file__).parent.parent / "tools" / "manifest_utils.py"
    print(f"  src: {src} ({src.stat().st_size} bytes)")
    ok, _ = http_upload(str(src), "/opt/app/shared/manifest_utils.py", secret=secret)
    print(f"  upload: {ok}")
    if not ok:
        return
    r = http_exec("chmod 644 /opt/app/shared/manifest_utils.py && echo OK", secret=secret, timeout=5)
    print(f"  chmod: {r.get('stdout', '').strip()}")
    print()

    # 3. 上传 smart_extract.sh 到 /opt/app/shared/lib/
    print("[3] 上传 smart_extract.sh -> /opt/app/shared/lib/")
    print("-" * 70)
    src = Path(__file__).parent.parent / "deploy_bundle" / "lib" / "smart_extract.sh"
    print(f"  src: {src} ({src.stat().st_size} bytes)")
    ok, _ = http_upload(str(src), "/opt/app/shared/lib/smart_extract.sh", secret=secret)
    print(f"  upload: {ok}")
    if not ok:
        return
    r = http_exec("chmod 755 /opt/app/shared/lib/smart_extract.sh && echo OK", secret=secret, timeout=5)
    print(f"  chmod: {r.get('stdout', '').strip()}")
    print()

    # 4. 上传 sha256_compare.sh 到 /opt/app/shared/lib/
    print("[4] 上传 sha256_compare.sh -> /opt/app/shared/lib/")
    print("-" * 70)
    src = Path(__file__).parent.parent / "deploy_bundle" / "lib" / "sha256_compare.sh"
    print(f"  src: {src} ({src.stat().st_size} bytes)")
    ok, _ = http_upload(str(src), "/opt/app/shared/lib/sha256_compare.sh", secret=secret)
    print(f"  upload: {ok}")
    if not ok:
        return
    r = http_exec("chmod 755 /opt/app/shared/lib/sha256_compare.sh && echo OK", secret=secret, timeout=5)
    print(f"  chmod: {r.get('stdout', '').strip()}")
    print()

    # 5. 验证部署结果
    print("[5] 验证部署结果")
    print("-" * 70)
    r = http_exec(
        "ls -la /opt/app/shared/manifest_utils.py /opt/app/shared/lib/ 2>/dev/null",
        secret=secret, timeout=5
    )
    print(r.get("stdout", ""))
    print()

    # 6. 测试 manifest_utils.py 在 /opt/app/shared/ 能 import
    print("[6] 测试 manifest_utils.py 在 /opt/app/shared/ 能 import (miniconda3 python)")
    print("-" * 70)
    r = http_exec(
        "cd /tmp && /opt/miniconda3-py39/bin/python3 -c 'import sys; sys.path.insert(0, \"/opt/app/shared\"); import manifest_utils; print(\"OK, yaml ver:\", __import__(\"yaml\").__version__)'",
        secret=secret, timeout=10
    )
    print(f"  stdout: {r.get('stdout', '').strip()}")
    if r.get("stderr"):
        print(f"  stderr: {r.get('stderr', '')[:200]}")
    print()

    # 7. 测试 smart_extract.sh 能 source
    print("[7] 测试 smart_extract.sh 能 source")
    print("-" * 70)
    r = http_exec(
        "bash -c 'source /opt/app/shared/lib/smart_extract.sh && declare -F smart_extract'",
        secret=secret, timeout=5
    )
    print(f"  stdout: {r.get('stdout', '').strip()}")
    print()

    # 8. 测试 sha256_compare.sh 能 source
    print("[8] 测试 sha256_compare.sh 能 source")
    print("-" * 70)
    r = http_exec(
        "bash -c 'source /opt/app/shared/lib/sha256_compare.sh && declare -F sha256_compare'",
        secret=secret, timeout=5
    )
    print(f"  stdout: {r.get('stdout', '').strip()}")
    print()

    print("=" * 70)
    print(" 完成: delta 能力已部署到 /opt/app/shared/ (prod)")
    print("=" * 70)


if __name__ == "__main__":
    main()