# -*- coding: utf-8 -*-
"""
修复测试文件中的数据库路径问题
"""

import os
import glob

test_dir = os.path.dirname(os.path.abspath(__file__))

# 找出所有包含错误路径的文件
pattern = os.path.join(test_dir, 'test_*.py')
files = glob.glob(pattern)

count = 0
fixed_files = []

for filepath in files:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 替换错误的路径
    new_content = content.replace('database="meta/architecture.db"', 'database="architecture.db"')

    if content != new_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        fixed_files.append(os.path.basename(filepath))
        count += 1

print(f"Total files fixed: {count}")
for f in fixed_files:
    print(f"  - {f}")