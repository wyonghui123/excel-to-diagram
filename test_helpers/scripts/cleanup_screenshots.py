"""清理 test_output/ 中超过 7 天的截图"""
import os
import time
import glob

NOW = time.time()
MAX_AGE = 7 * 24 * 3600
CLEAN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_output')

if not os.path.exists(CLEAN_DIR):
    print(f"目录不存在: {CLEAN_DIR}")
    exit(0)

deleted = 0
kept = 0
for f in glob.glob(os.path.join(CLEAN_DIR, '*.png')):
    age = NOW - os.path.getmtime(f)
    if age > MAX_AGE:
        os.remove(f)
        deleted += 1
    else:
        kept += 1

print(f"清理完成: 删除 {deleted} 张, 保留 {kept} 张 (超过 {MAX_AGE / 86400:.0f} 天)")