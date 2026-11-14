"""按保留期清理生成物 (test_temp / exports / meta 备份与监控日志)。

默认 dry-run，只打印将删除的数量与体积；加 --apply 才真正删除。
用法:
    python scripts/retention_cleanup.py            # 预览
    python scripts/retention_cleanup.py --apply    # 执行

保留策略:
    test_temp/            24 小时
    exports/              7 天
    meta/backups/         48 小时，且至少保留最新 3 个文件
    meta/db_monitor_logs/ 7 天
"""

import argparse
import os
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAY = 86400

# (相对路径, 保留小时数, 至少保留最新 N 个)
TARGETS = [
    ("test_temp", 24, 0),
    ("exports", 168, 0),
    ("meta/backups", 48, 3),
    ("meta/db_monitor_logs", 168, 0),
]


def collect(base):
    paths = []
    for dp, _, fn in os.walk(base):
        paths.extend(os.path.join(dp, f) for f in fn)
    return paths


def prune(rel, keep_hours, keep_newest, apply):
    base = os.path.join(ROOT, rel)
    if not os.path.isdir(base):
        return 0, 0
    files = [(p, os.stat(p)) for p in collect(base) if os.path.isfile(p)]
    if keep_newest:
        newest = {p for p, _ in sorted(files, key=lambda x: x[1].st_mtime, reverse=True)[:keep_newest]}
    else:
        newest = set()
    deadline = time.time() - keep_hours * 3600
    freed = count = 0
    for p, st in files:
        if p in newest or st.st_mtime > deadline:
            continue
        if apply:
            try:
                os.remove(p)
            except OSError:
                continue
        freed += st.st_size
        count += 1
    return count, freed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正删除，默认仅预览")
    args = ap.parse_args()
    total_n = total_mb = 0
    for rel, hours, newest in TARGETS:
        n, size = prune(rel, hours, newest, args.apply)
        total_n += n
        total_mb += size / 1048576
        print(f"{'DEL' if args.apply else 'WOULD DEL'} {rel:<24} files={n:<6} MB={size/1048576:.1f}")
    print(f"{'FREED' if args.apply else 'WOULD FREE'} total: files={total_n} MB={total_mb:.1f}")


if __name__ == "__main__":
    main()