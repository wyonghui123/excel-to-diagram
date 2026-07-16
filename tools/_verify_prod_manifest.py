"""[V3] 验证 prod manifest_utils.py 可用"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from remote_helper import http_exec


def main():
    secret = "v007.35-infra"
    print("=" * 70)
    print(" 验证 prod manifest_utils.py (无 cd 命令)")
    print("=" * 70)

    # 1. import 测试
    print("\n[1] import manifest_utils (miniconda3 python)")
    print("-" * 70)
    r = http_exec(
        "/opt/miniconda3-py39/bin/python3 -c \""
        "import sys; sys.path.insert(0, '/opt/app/shared'); "
        "import manifest_utils; "
        "print('manifest_utils OK, version:', getattr(manifest_utils, '__version__', 'N/A')); "
        "print('functions:', [x for x in dir(manifest_utils) if not x.startswith('_')])\"",
        secret=secret, timeout=10
    )
    print(r.get("stdout", ""))
    if r.get("stderr"):
        print("STDERR:", r["stderr"][:200])
    print()

    # 2. smart_extract.sh 功能测试
    print("\n[2] smart_extract.sh --help (实际跑一次)")
    print("-" * 70)
    r = http_exec(
        "bash -c 'source /opt/app/shared/lib/smart_extract.sh && type smart_extract'",
        secret=secret, timeout=5
    )
    print(r.get("stdout", ""))
    print()

    # 3. sha256_compare.sh 功能测试
    print("\n[3] sha256_compare.sh --help")
    print("-" * 70)
    r = http_exec(
        "bash -c 'source /opt/app/shared/lib/sha256_compare.sh && type sha256_compare'",
        secret=secret, timeout=5
    )
    print(r.get("stdout", ""))
    print()

    # 4. 用 prod manifest_utils 跑 generate_manifest (空目录测试)
    print("\n[4] manifest_utils.generate_manifest (空目录)")
    print("-" * 70)
    r = http_exec(
        "/opt/miniconda3-py39/bin/python3 -c \""
        "import sys; sys.path.insert(0, '/opt/app/shared'); "
        "from pathlib import Path; "
        "from manifest_utils import generate_manifest; "
        "m = generate_manifest(Path('/tmp'), version='test', deployment_type='full'); "
        "print(f'generate_manifest OK, files={len(m.files)}')\"",
        secret=secret, timeout=10
    )
    print(r.get("stdout", ""))
    if r.get("stderr"):
        print("STDERR:", r["stderr"][:200])
    print()

    print("=" * 70)


if __name__ == "__main__":
    main()