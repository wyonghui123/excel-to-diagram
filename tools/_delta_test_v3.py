"""upload + run v3"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from remote_helper import http_upload, http_exec


def main():
    secret = "v007.35-infra"
    print("=" * 70)
    print(" E2E v3 (Python API)")
    print("=" * 70)

    script = Path(__file__).parent / "_delta_setup_v3.py"
    print(f"local: {script} ({script.stat().st_size} bytes)")
    ok, _ = http_upload(str(script), "/tmp/_e2e.py", secret=secret)
    print(f"upload: {ok}")
    if not ok:
        return
    http_exec("chmod +x /tmp/_e2e.py", secret=secret, timeout=5)
    r = http_exec("/opt/miniconda3-py39/bin/python3 /tmp/_e2e.py", secret=secret, timeout=60)
    print(r.get("stdout", ""))
    if r.get("stderr"):
        print("STDERR:", r["stderr"])

    # cleanup
    http_exec("rm -f /tmp/_e2e.py && rm -rf /tmp/delta_test/v1 /tmp/delta_test/v2 /tmp/delta_test/target /tmp/delta_test/full.tar.gz /tmp/delta_test/delta.zip /tmp/delta_test/*.json && echo CLEANED", secret=secret, timeout=10)
    print("=" * 70)


if __name__ == "__main__":
    main()
