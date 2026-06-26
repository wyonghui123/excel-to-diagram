# -*- coding: utf-8 -*-
"""
lint_msg_punct.py - 业务消息 Lint (T5: BizMsg-UX v1.0)

检查 5 类业务消息反模式:
  1. 【】技术标签残留 (BizMsg-UX T1 - 13 处已替换)
  2. 通用 "操作成功/失败" 语义缺失 (DP-1)
  3. 中英标点混用 (DP-2/DP-3)
  4. 错误消息缺 trace_id (DP-5)
  5. i18n 命名空间完整 (crud/validation/system/biz 4 个必备)

用法:
  python scripts/lint_msg_punct.py              # 全量检查
  python scripts/lint_msg_punct.py --fix        # 建议修复
  python scripts/lint_msg_punct.py --json       # JSON 输出
"""

import re
import sys
import json
import os
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / 'src'
META_DIR = ROOT / 'meta'
I18N_FILE = ROOT / 'src/i18n/locales/zh-CN.json'

# [!!!] 关键反模式 [!!!]

# 1. 【】技术标签 (BizMsg-UX T1 应清零, 但 Excel 批注中保留)
# 注: 批注 (Comment) 中的【】是允许的, 代码检查时只检查 message.* 字符串
TECH_TAG_PATTERN = re.compile(r'【[^】]+】')

# 2. 通用消息
GENERIC_SUCCESS = re.compile(r"['\"]操作成功['\"]")
GENERIC_FAILURE = re.compile(r"['\"]操作失败['\"]")

# 3. 中英标点混用 (常见)
PUNCT_MIXED = [
    (re.compile(r'[a-zA-Z0-9],[^,\s]'), '半角逗号后应接空格'),
    (re.compile(r'[a-zA-Z0-9]\.[^.\s]'), '半角点后应接空格'),
    (re.compile(r'[a-zA-Z0-9]:[^:\s]'), '半角冒号后应接空格'),
    (re.compile(r'[\u4e00-\u9fa5],[^,\s]'), '中文后用全角逗号(，)'),
    (re.compile(r'[\u4e00-\u9fa5]\.[^.\s]'), '中文后用全角句号(。)'),
]

# 4. trace_id 注入 (在 ElMessage.error 字符串中应含 (错误编号: 或 traceId)
TRACE_ID_PATTERN = re.compile(r'错误编号|traceId|trace_id')

# 5. 必备 i18n namespace
REQUIRED_NAMESPACES = ['crud', 'validation', 'system', 'biz']


class LintIssue:
    def __init__(self, file, line, category, message, severity='warning'):
        self.file = str(file.relative_to(ROOT)) if file else ''
        self.line = line
        self.category = category
        self.message = message
        self.severity = severity

    def to_dict(self):
        return {
            'file': self.file,
            'line': self.line,
            'category': self.category,
            'severity': self.severity,
            'message': self.message,
        }


def find_files():
    """查找所有 .vue / .js / .ts / .py 文件"""
    files = []
    for pattern in ['**/*.vue', '**/*.js', '**/*.ts']:
        files.extend(SRC_DIR.glob(pattern))
    for pattern in ['**/*.py']:
        files.extend(META_DIR.glob(pattern))
    # 排除 AI prompt 模板文件 (【】 是合理的 prompt 章节头)
    # 排除测试 spec 文件 (【】 在 it('【场景】...') 中是测试分组标签)
    # 排除 meta/ 业务规则文件 (【】 在 docstring 中是章节头, 如 【背景 2026-MM-DD】)
    EXCLUDE_PATTERNS = [
        re.compile(r'.*Validator\.js$'),   # deepseekValidator / zhipuValidator
        re.compile(r'.*Prompt.*\.js$'),
        re.compile(r'.*prompt.*\.js$'),
        re.compile(r'.*Validator\.ts$'),
        re.compile(r'.*__tests__.*'),
        re.compile(r'.*\.spec\.js$'),
        re.compile(r'.*\.test\.js$'),
        re.compile(r'.*\.spec\.ts$'),
        re.compile(r'.*\.test\.ts$'),
    ]
    EXCLUDE_DIRS = [
        SRC_DIR / 'views/AADiagramApp/composables/__tests__',
        META_DIR,  # meta/ 全部 docstring 中的【】章节头都是合理的
    ]
    filtered = []
    for f in files:
        name = f.name
        if any(pat.match(name) for pat in EXCLUDE_PATTERNS):
            continue
        # 目录排除
        if any(excl in f.parents for excl in EXCLUDE_DIRS):
            continue
        filtered.append(f)
    return filtered


def lint_file(file):
    issues = []
    try:
        content = file.read_text(encoding='utf-8')
    except Exception:
        return issues
    lines = content.split('\n')
    in_block_comment = False
    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # 跟踪块注释状态 (/* ... */  以及 JSDoc /** ... */)
        # 进入块注释:  /* 或 /**  (但 // 优先级更高)
        if not in_block_comment:
            # 行内出现 /* 且无 // 注释前缀
            # 行内出现 // 说明整行是单行注释, 不进入块
            if '//' not in stripped[:stripped.find('/*') if '/*' in stripped else 0]:
                if '/*' in stripped:
                    in_block_comment = True
        # 退出块注释:  */
        if in_block_comment:
            if '*/' in stripped:
                in_block_comment = False
            # 块注释中的所有行都跳过 (包括 JSDoc 的 * 续行)
            continue

        # 跳过单行注释
        if stripped.startswith('//') or stripped.startswith('#'):
            continue
        # 跳过 JSDoc 续行 (以 * 开头, 但不是 * 乘法/解构)
        if stripped.startswith('* ') or stripped == '*':
            continue
        # 跳过 Python/Shell 块注释续行
        if stripped.startswith("'''") or stripped.startswith('"""'):
            continue
        # 1. 【】技术标签
        if TECH_TAG_PATTERN.search(line):
            # 例外: Comment("...") 中的 【】是允许的
            if 'Comment(' not in line and 'comment=' not in line:
                issues.append(LintIssue(
                    file, i, 'tech_tag', f'【】技术标签残留: {line.strip()[:100]}', 'error'
                ))
        # 2. 通用消息
        if GENERIC_SUCCESS.search(line):
            issues.append(LintIssue(
                file, i, 'generic_success', f'通用"操作成功"应使用 useCrudMessage.saved(): {line.strip()[:100]}', 'warning'
            ))
        if GENERIC_FAILURE.search(line):
            issues.append(LintIssue(
                file, i, 'generic_failure', f'通用"操作失败"应含具体原因: {line.strip()[:100]}', 'warning'
            ))
        # 3. 标点
        for pat, desc in PUNCT_MIXED:
            if pat.search(line):
                # 只在 message.* 字符串中检查
                if 'message.' in line or 'ElMessage' in line:
                    issues.append(LintIssue(
                        file, i, 'punct_mixed', f'标点混用: {desc} | {line.strip()[:100]}', 'info'
                    ))
        # 4. trace_id (在 ElMessage.error 字符串中)
        if 'ElMessage' in line and 'error' in line.lower() and 'message.error' in line:
            if not TRACE_ID_PATTERN.search(line):
                issues.append(LintIssue(
                    file, i, 'trace_id_missing', f'错误消息缺 trace_id 注入 | {line.strip()[:100]}', 'warning'
                ))
    return issues


def check_i18n_namespaces():
    issues = []
    if not I18N_FILE.exists():
        issues.append(LintIssue(
            I18N_FILE, 0, 'i18n_missing', f'i18n 文件不存在: {I18N_FILE}', 'error'
        ))
        return issues
    try:
        i18n = json.loads(I18N_FILE.read_text(encoding='utf-8'))
    except Exception as e:
        issues.append(LintIssue(
            I18N_FILE, 0, 'i18n_invalid', f'i18n JSON 解析失败: {e}', 'error'
        ))
        return issues
    for ns in REQUIRED_NAMESPACES:
        if ns not in i18n:
            issues.append(LintIssue(
                I18N_FILE, 0, 'i18n_ns_missing', f'缺失必备 namespace: {ns}', 'error'
            ))
        else:
            keys = i18n[ns] if isinstance(i18n[ns], dict) else {}
            print(f'  [OK] {ns}: {len(keys)} keys')
    return issues


def main():
    print('=== BizMsg-UX Lint (T5) ===\n')

    # 1. 检查文件
    print('[1] 扫描文件...')
    files = find_files()
    print(f'  找到 {len(files)} 个文件')

    # 2. 逐文件 lint
    print('\n[2] 业务消息 lint...')
    all_issues = []
    for f in files:
        all_issues.extend(lint_file(f))
    print(f'  发现 {len(all_issues)} 个问题')

    # 3. i18n 命名空间
    print('\n[3] i18n 命名空间检查...')
    i18n_issues = check_i18n_namespaces()
    all_issues.extend(i18n_issues)

    # 4. 按类别统计
    by_cat = defaultdict(int)
    by_sev = defaultdict(int)
    for issue in all_issues:
        by_cat[issue.category] += 1
        by_sev[issue.severity] += 1

    print('\n[4] 问题统计:')
    for cat, n in sorted(by_cat.items(), key=lambda x: -x[1]):
        print(f'  {cat}: {n}')
    print('\n[5] 严重度:')
    for sev, n in sorted(by_sev.items()):
        print(f'  {sev}: {n}')

    # 5. 输出
    if '--json' in sys.argv:
        print('\n[JSON 输出]')
        print(json.dumps([i.to_dict() for i in all_issues], ensure_ascii=False, indent=2))
    else:
        # 只展示 error 级别
        errors = [i for i in all_issues if i.severity == 'error']
        if errors:
            print(f'\n[!] {len(errors)} 个 error 级别问题:')
            for e in errors[:10]:
                print(f'  {e.file}:{e.line} [{e.category}] {e.message[:80]}')

    # 6. 退出码
    if by_sev.get('error', 0) > 0:
        sys.exit(1)
    print('\n[OK] lint 通过 (无 error 级别问题)')


if __name__ == '__main__':
    main()
