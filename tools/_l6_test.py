"""[V3] L6 端口 token 测试"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from remote_helper import http_exec


def main():
    secret = "v007.35-infra"
    print("L6 端口 token 验证测试")
    for port in [9101, 9200, 9204, 9205, 9206, 9207]:
        # 不带 token
        r = http_exec(
            f"curl -s --max-time 3 -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{port}/api/system/health 2>&1",
            secret=secret, timeout=10
        )
        c1 = r.get("stdout", "").strip()
        # 带错 token
        r = http_exec(
            f"curl -s --max-time 3 -o /dev/null -w '%{{http_code}}' 'http://127.0.0.1:{port}/api/system/health?token=invalid' 2>&1",
            secret=secret, timeout=10
        )
        c2 = r.get("stdout", "").strip()
        print(f"  port {port:5}: no_token={c1}  invalid_token={c2}")


if __name__ == "__main__":
    main()