"""[V3] 在 yonaa 上生成 NEW MANIFEST + 验证"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from remote_helper import http_upload, http_exec


def main():
    secret = "v007.35-infra"
    print("=" * 70)
    print(" 在 prod meta 上生成新 MANIFEST + verify")
    print("=" * 70)

    script = '''"""[V3] prod MANIFEST 生成 + verify"""
import sys
sys.path.insert(0, "/opt/app/shared")
from manifest_utils import generate_manifest, verify_delta_manifest
from pathlib import Path
import json

# 1. 生成 MANIFEST (从 /opt/app/deployments/meta 扫描)
print("=== 生成 MANIFEST ===")
m = generate_manifest(
    Path("/opt/app/deployments/meta"),
    version="v_test_20260714",
    deployment_type="delta"
)
print(f"  version: {m.version}")
print(f"  files:   {len(m.files)}")
print(f"  git_head: {m.git_head}")
print(f"  to_yaml bytes: {len(m.to_yaml())}")

# 2. verify (在同一个目录上, 应该全部 ok)
print()
print("=== verify_delta_manifest ===")
result = verify_delta_manifest(Path("/opt/app/deployments/meta"), m)
print(f"  ok: {result['ok']}")
print(f"  checked: {result['checked']}")
print(f"  mismatched: {len(result['mismatched'])}")
print(f"  missing:   {len(result['missing'])}")
if result['mismatched']:
    print(f"  first 3 mismatched: {result['mismatched'][:3]}")
if result['missing']:
    print(f"  first 3 missing: {result['missing'][:3]}")
'''

    test_path = Path("tools/_gen_verify_manifest_test.py")
    test_path.write_text(script, encoding="utf-8")

    ok, _ = http_upload(str(test_path), "/tmp/_gen_verify.py", secret=secret)
    print(f"upload: {ok}")
    if ok:
        r = http_exec(
            "/opt/miniconda3-py39/bin/python3 /tmp/_gen_verify.py",
            secret=secret, timeout=120
        )
        print(r.get("stdout", ""))
        if r.get("stderr"):
            print("STDERR:", r["stderr"][:500])
        http_exec("rm -f /tmp/_gen_verify.py && echo CLEANED", secret=secret, timeout=5)
    test_path.unlink()
    print("=" * 70)


if __name__ == "__main__":
    main()