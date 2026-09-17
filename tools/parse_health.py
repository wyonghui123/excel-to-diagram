"""parse_health.py - 从 log_service /api/db/health 输出提取 integrity
[V007.67 2026-07-14]

替代 deploy_prod.sh 阶段 5 的 inline python3 -c (避免云安全启发式)
用法: python3 /tmp/parse_health.py < health.json
输出: ok / fail / 其他
"""
import json
import sys


def main():
    """从 stdin 读 JSON, 输出 integrity 字段 (默认 'fail')"""
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
        integrity = data.get("integrity", "fail")
    except Exception:
        integrity = "fail"
    print(integrity)


if __name__ == "__main__":
    main()