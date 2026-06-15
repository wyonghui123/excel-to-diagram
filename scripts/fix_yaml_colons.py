#!/usr/bin/env python3
"""
修复 YAML 文件中 title 字段的冒号问题
把 title: 中文标题 改为 title: '中文标题' (加引号避免 YAML 解析错误)
"""
import re
import sys
from pathlib import Path

RULES_DIR = Path(__file__).resolve().parents[1] / '.trae' / 'specs' / '_business_rules'


def fix_title_quotes(content):
    """给 title 字段的值加单引号"""
    def replacer(match):
        prefix = match.group(1)
        value = match.group(2).strip()
        # 如果已经有引号, 跳过
        if value.startswith('"') or value.startswith("'"):
            return match.group(0)
        return "{0}'{1}'".format(prefix, value.replace("'", "\\'"))

    # title: 后跟非空内容到行尾
    return re.sub(r'(title:\s*)(.+?)$', replacer, content, flags=re.MULTILINE)


def main():
    for yaml_file in RULES_DIR.glob('_*.yaml'):
        with open(yaml_file, 'r', encoding='utf-8') as f:
            content = f.read()
        fixed = fix_title_quotes(content)
        if fixed != content:
            with open(yaml_file, 'w', encoding='utf-8') as f:
                f.write(fixed)
            print("[FIXED] {f}".format(f=yaml_file.name))
        else:
            print("[OK] {f}".format(f=yaml_file.name))


if __name__ == '__main__':
    main()
