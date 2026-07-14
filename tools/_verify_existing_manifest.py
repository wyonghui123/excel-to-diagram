"""[V3] 在 prod 上跑 verify_delta_manifest - 用真实 MANIFEST + meta"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from remote_helper import http_exec


def main():
    secret = "v007.35-infra"
    print("=" * 70)
    print(" verify_delta_manifest 在 /opt/app/ 上跑 (用现成的 MANIFEST)")
    print("=" * 70)
    print()

    # 1. 看 yonaa 上现成的 MANIFEST
    print("[1] /opt/app/deployments/MANIFEST 详情")
    print("-" * 70)
    r = http_exec(
        "ls -la /opt/app/deployments/MANIFEST && head -5 /opt/app/deployments/MANIFEST",
        secret=secret, timeout=5
    )
    print(r.get("stdout", ""))
    print()

    # 2. 写一个 verify_delta_manifest 测试脚本上传
    print("[2] 上传 + 跑 verify_delta_manifest 测试脚本")
    print("-" * 70)

    test_script = '''"""[V3] verify delta MANIFEST on yonaa meta [V007.67]"""
import sys
sys.path.insert(0, "/opt/app/shared")
from manifest_utils import parse_manifest, verify_delta_manifest
from pathlib import Path
import json

MANIFEST_PATH = Path("/opt/app/deployments/MANIFEST")
DEPLOY_DIR = Path("/opt/app/deployments/meta")

print(f"MANIFEST: {MANIFEST_PATH} ({MANIFEST_PATH.stat().st_size} bytes)")
print(f"DEPLOY_DIR: {DEPLOY_DIR}")

# parse MANIFEST
m = parse_manifest(open(MANIFEST_PATH).read())
print(f"version: {m.version}, files: {len(m.files)}")

# verify
result = verify_delta_manifest(DEPLOY_DIR, m)
print(json.dumps(result, indent=2)[:500])
'''

    # 上传
    test_path = Path("/tmp/_verify_existing.py")
    test_path.write_text(test_script, encoding="utf-8")
    from remote_helper import http_upload
    ok, _ = http_upload(str(test_path), "/tmp/_verify_existing.py", secret=secret)
    test_path.unlink()
    print(f"  upload: {ok}")
    if ok:
        r = http_exec(
            "/opt/miniconda3-py39/bin/python3 /tmp/_verify_existing.py",
            secret=secret, timeout=60
        )
        print(r.get("stdout", ""))
        if r.get("stderr"):
            print("STDERR:", r["stderr"][:500])
        # cleanup
        http_exec("rm -f /tmp/_verify_existing.py && echo CLEANED", secret=secret, timeout=5)
    print()

    print("=" * 70)


if __name__ == "__main__":
    main()