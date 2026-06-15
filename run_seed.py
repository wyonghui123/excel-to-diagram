#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
[Wrapper] 运行 init_and_seed.py, 自动加 sys.path
"""
import sys
import os

# 加 sys.path 让 meta.* 模块可导入
sys.path.insert(0, r'd:/filework')
sys.path.insert(0, r'd:/filework/excel-to-diagram')

# 把 run_seed.py 后的 -- 后续参数传给被调脚本
# PowerShell: python run_seed.py -- --force --yes
# sys.argv: ['run_seed.py', '--', '--force', '--yes']
# 切成:       ['init_and_seed.py', '--force', '--yes']

if '--' in sys.argv:
    sep_idx = sys.argv.index('--')
    extra = sys.argv[sep_idx + 1:]
    sys.argv = [sys.argv[0]] + extra  # 让 argparse 看到
    print(f"[run_seed] forwarding args: {extra}", file=sys.stderr)

# 直接 import 并 exec
with open(r'd:/filework/excel-to-diagram/meta/scripts/init_and_seed.py', 'rb') as f:
    code = f.read().decode('utf-8')

# 用 globals 替换 __file__ 让脚本能正常工作
g = {'__file__': r'd:/filework/excel-to-diagram/meta/scripts/init_and_seed.py', '__name__': '__main__'}
exec(compile(code, g['__file__'], 'exec'), g)
