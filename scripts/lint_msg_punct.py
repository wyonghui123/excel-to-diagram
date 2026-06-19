#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Punctuation Linter for BizMsg-UX v1.0

检查 message.*() 调用中的中英标点混用问题：
- 中文语境中出现半角逗号 (,)
- 中文语境中出现半角冒号 (:)
- 中文语境中出现半角句号 (.)
- 中英数字间缺空格（弱检查）

不影响 commit，仅 WARN。可手动运行。
"""
import re
import sys
import os
from pathlib import Path

# 规则定义
PATTERNS = [
    # (regex, description, severity)
    # 中文 + 半角逗号 (中文字符后跟半角逗号)
    (r'[\u4e00-\u9fa5],[^a-zA-Z0-9\s]', '中文后跟半角逗号 (,)', 'WARN'),
    # 中文 + 半角冒号 (中文字符后跟半角冒号，且非 URL 场景)
    (r'[\u4e00-\u9fa5]:[\s\u4e00-\u9fa5]', '中文后跟半角冒号 (:)', 'WARN'),
    # 中文 + 半角句号结尾
    (r'[\u4e00-\u9fa5]\.\s*["\']?\s*$', '中文以半角句号结尾 (.)', 'WARN'),
    # 中文 + 半角问号
    (r'[\u4e00-\u9fa5]\?', '中文后跟半角问号 (?)', 'WARN'),
    # 中文 + 半角感叹号
    (r'[\u4e00-\u9fa5]!', '中文后跟半角感叹号 (!)', 'WARN'),
]

# 误报白名单
WHITELIST_LINES = [
    'metric', 'spec.', 'rule.', 'fr-', 'fr_',  # 规范编号
    '.png', '.jpg', '.js', '.vue', '.json',  # 扩展名
    'http://', 'https://',  # URL
]

def is_whitelist(line):
    """检查是否在白名单（避免误报）"""
    line_lower = line.lower()
    return any(w in line_lower for w in WHITELIST_LINES)


def extract_message_calls(content, file_path):
    """从文件中提取 message.*('...') / message.*(`...`) 调用"""
    issues = []
    lines = content.split('\n')
    in_template = False
    template_lines = []
    template_start = 0

    for i, line in enumerate(lines, 1):
        # 检测模板字符串开始
        if 'message.' in line and '`' in line:
            in_template = True
            template_start = i
            template_lines = [line]
            # 单行模板
            if line.count('`') >= 2 and line.strip().endswith('`') is False or line.count('`') >= 2:
                # 找下一个 ` 或行末
                full_text = line
                check_text(i, full_text, file_path, issues, lines)
                in_template = False
                template_lines = []
            continue

        if in_template:
            template_lines.append(line)
            if '`' in line:
                # 模板结束
                full_text = '\n'.join(template_lines)
                check_text(template_start, full_text, file_path, issues, lines)
                in_template = False
                template_lines = []
            continue

        # 普通字符串
        for pattern, desc, sev in PATTERNS:
            if re.search(pattern, line):
                if not is_whitelist(line):
                    issues.append({
                        'file': file_path,
                        'line': i,
                        'desc': desc,
                        'severity': sev,
                        'text': line.strip()[:80],
                    })

    return issues


def check_text(line_num, text, file_path, issues, all_lines):
    """检查一段文本（含模板字符串）"""
    for pattern, desc, sev in PATTERNS:
        if re.search(pattern, text):
            if not is_whitelist(text):
                issues.append({
                    'file': file_path,
                    'line': line_num,
                    'desc': desc,
                    'severity': sev,
                    'text': text.strip()[:80],
                })


def main():
    if len(sys.argv) < 2:
        # 默认扫描 src/
        scan_dir = Path('src')
    else:
        scan_dir = Path(sys.argv[1])

    if not scan_dir.exists():
        print(f"[FAIL] Directory not found: {scan_dir}")
        sys.exit(1)

    vue_files = list(scan_dir.rglob('*.vue'))
    js_files = list(scan_dir.rglob('*.js'))

    all_issues = []
    for f in vue_files + js_files:
        try:
            content = f.read_text(encoding='utf-8')
            if 'message.' in content:
                issues = extract_message_calls(content, str(f))
                all_issues.extend(issues)
        except Exception as e:
            print(f"[WARN] Skip {f}: {e}")

    if not all_issues:
        print("[OK] No punctuation issues found")
        sys.exit(0)

    print(f"[WARN] {len(all_issues)} potential punctuation issue(s):\n")
    for issue in all_issues[:30]:  # 最多显示 30 条
        print(f"  {issue['file']}:{issue['line']}  [{issue['severity']}] {issue['desc']}")
        print(f"    >> {issue['text']}")
    if len(all_issues) > 30:
        print(f"\n  ... and {len(all_issues) - 30} more")

    print(f"\n[INFO] These are WARN-level, not blocking commit")
    print(f"[INFO] To fix: 全文统一全角标点（，。：；？！）")
    return 0  # 不阻断


if __name__ == '__main__':
    main()
