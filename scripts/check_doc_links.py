#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Markdown 链接检查脚本
扫描 docs/ 目录下的所有 .md 文件，验证：
- 内部相对链接是否有效
- file:/// 链接是否有效
- 锚点 (#section) 是否存在
- 外部 http(s) 链接（可选）

使用方法：
    python scripts/check_doc_links.py                # 检查 docs/
    python scripts/check_doc_links.py --external    # 也检查外部链接
    python scripts/check_doc_links.py --quiet       # 仅报告错误
"""
import os
import re
import sys
import argparse
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / 'docs'

# Markdown 链接正则
LINK_PATTERN = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')
HEADER_PATTERN = re.compile(r'^(#{1,6})\s+(.+?)(?:\s*\{[^}]*\})?\s*$')
CODE_BLOCK = re.compile(r'^```')


def extract_anchors(md_path: Path) -> set:
    """从 markdown 文件提取所有标题 ID（GitHub 风格）"""
    anchors = set()
    try:
        with open(md_path, encoding='utf-8') as f:
            in_code = False
            for line in f:
                if CODE_BLOCK.match(line):
                    in_code = not in_code
                    continue
                if in_code:
                    continue
                m = HEADER_PATTERN.match(line)
                if m:
                    title = m.group(2).strip()
                    # GitHub 风格：保留中文 + 中文标点(，。) + 字母数字 + 空格 + -
                    anchor = title.lower()
                    # 中文顿号 "、" 转为 "-"（如 "一、执行摘要" -> "一-执行摘要"）
                    anchor = anchor.replace('、', '-')
                    # 去除英文标点，但保留中文标点（除顿号已转 -）
                    anchor = re.sub(r'[^\w\u4e00-\u9fff\s\-、，。；：！？（）()【】《》""''…—]', '', anchor)
                    # 去除连续横线
                    anchor = re.sub(r'-+', '-', anchor)
                    # 去除首尾横线
                    anchor = anchor.strip('-')
                    # 空格转 -
                    anchor = re.sub(r'\s+', '-', anchor)
                    anchors.add(anchor)
    except Exception as e:
        print(f'  [WARN] Failed to read {md_path}: {e}', file=sys.stderr)
    return anchors


def check_link(source_file: Path, link: str) -> tuple:
    """检查单个链接
    返回: (status, target)
    status: 'ok' | 'missing' | 'anchor_missing' | 'external' | 'invalid'
    """
    # 跳过外部链接
    if link.startswith(('http://', 'https://')):
        return ('external', link)

    # 跳过纯锚点（指向当前文件）
    if link.startswith('#'):
        anchor = link[1:]
        anchors = extract_anchors(source_file)
        if anchor in anchors:
            return ('ok', link)
        return ('anchor_missing', link)

    # 解析 file:/// 链接
    if link.startswith('file:///'):
        path_str = unquote(link[8:])
        # 去除行号锚点（如 #L36-L58）
        if '#' in path_str:
            path_str = path_str.split('#', 1)[0]
        # Windows 路径处理
        if path_str.startswith(('D:/', 'd:/', 'C:/', 'c:/')):
            target = Path(path_str)
        else:
            target = DOCS_DIR / path_str.lstrip('/')
        if target.exists():
            return ('ok', link)
        return ('missing', link)

    # 解析 file:// 链接（不带第三个斜杠）
    if link.startswith('file://'):
        path_str = unquote(link[7:])
        if '#' in path_str:
            path_str = path_str.split('#', 1)[0]
        target = Path(path_str)
        if target.exists():
            return ('ok', link)
        return ('missing', link)

    # 解析相对路径
    if '#' in link:
        path_part, anchor = link.split('#', 1)
    else:
        path_part, anchor = link, None

    if path_part == '':
        # 纯锚点链接
        anchors = extract_anchors(source_file)
        if anchor in anchors:
            return ('ok', link)
        return ('anchor_missing', link)

    # 相对路径 - 尝试多种解析方式
    candidates = [
        source_file.parent / path_part,  # 相对于当前文档
        DOCS_DIR / path_part,             # 相对于 docs/ 根
        ROOT / path_part,                 # 相对于项目根
    ]
    for cand in candidates:
        if cand.exists():
            target = cand.resolve()
            break
    else:
        return ('missing', link)

    # 检查锚点
    if anchor and target.suffix == '.md':
        anchors = extract_anchors(target)
        if anchor not in anchors:
            return ('anchor_missing', link)

    return ('ok', link)


def scan_file(md_path: Path, check_external: bool) -> list:
    """扫描单个 markdown 文件中的所有链接"""
    issues = []
    try:
        with open(md_path, encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return [('error', f'Cannot read file: {e}')]

    in_code = False
    for line_num, line in enumerate(content.split('\n'), 1):
        if CODE_BLOCK.match(line):
            in_code = not in_code
            continue
        if in_code:
            continue
        for m in LINK_PATTERN.finditer(line):
            link = m.group(2)
            # 跳过 mailto, tel 等
            if link.startswith(('mailto:', 'tel:')):
                continue
            status, target = check_link(md_path, link)
            if status == 'external' and not check_external:
                continue
            if status != 'ok':
                issues.append((status, link, line_num))
    return issues


def main():
    parser = argparse.ArgumentParser(description='Markdown 链接检查')
    parser.add_argument('--external', action='store_true', help='检查外部 http(s) 链接')
    parser.add_argument('--quiet', action='store_true', help='仅输出错误')
    parser.add_argument('--path', default='docs', help='扫描路径（默认 docs）')
    args = parser.parse_args()

    scan_dir = ROOT / args.path
    if not scan_dir.exists():
        print(f'[ERROR] Path not found: {scan_dir}', file=sys.stderr)
        sys.exit(1)

    print(f'[INFO] Scanning {scan_dir.relative_to(ROOT)}/...')
    print()

    md_files = list(scan_dir.rglob('*.md'))
    print(f'[INFO] Found {len(md_files)} markdown files')
    print()

    total_issues = 0
    files_with_issues = 0

    for md_file in sorted(md_files):
        issues = scan_file(md_file, args.external)
        if issues:
            files_with_issues += 1
            total_issues += len(issues)
            if not args.quiet:
                rel = md_file.relative_to(ROOT)
                print(f'[{rel}]')
                for status, link, line_num in issues:
                    icon = {
                        'missing': '[MISSING]',
                        'anchor_missing': '[ANCHOR]',
                        'error': '[ERROR]',
                    }.get(status, '[?]')
                    print(f'  L{line_num:4d} {icon} {link}')
                print()

    print('=' * 60)
    print(f'Summary: {total_issues} issues in {files_with_issues} files')
    print(f'  Scanned: {len(md_files)} markdown files')

    if total_issues > 0:
        sys.exit(1)
    else:
        print('  [OK] All links valid!')
        sys.exit(0)


if __name__ == '__main__':
    main()
