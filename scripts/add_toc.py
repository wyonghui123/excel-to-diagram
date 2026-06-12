#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
为无 TOC 的大文档自动添加目录
策略：
- 仅处理 >10KB 的活跃文档
- 仅在缺少 TOC（## 目录）时添加
- 跳过 frontmatter 部分
- 跳过 code block
- 使用 GitHub 风格 anchor（与 check_doc_links.py 一致）
"""
import os
import re
from pathlib import Path

ROOT = Path(r'd:\filework\excel-to-diagram\docs')
MIN_SIZE_KB = 10

FRONTMATTER_PATTERN = re.compile(r'^---\s*\n.+?\n---\s*\n', re.DOTALL)
HEADER_PATTERN = re.compile(r'^(#{1,6})\s+(.+?)\s*$')
TOC_PATTERN = re.compile(r'^##\s*目录', re.MULTILINE)
CODE_BLOCK = re.compile(r'^```')


def gen_anchor(title: str) -> str:
    """生成 GitHub 风格 anchor（与 check_doc_links.py 一致）"""
    anchor = title.lower()
    # 中文顿号 "、" 转为 "-"
    anchor = anchor.replace('、', '-')
    # 去除英文标点，保留中文标点
    anchor = re.sub(r'[^\w\u4e00-\u9fff\s\-、，。；：！？（）()【】《》""''…—]', '', anchor)
    # 去除连续横线
    anchor = re.sub(r'-+', '-', anchor)
    # 去除首尾横线
    anchor = anchor.strip('-')
    # 空格转 -
    anchor = re.sub(r'\s+', '-', anchor)
    return anchor


def extract_toc_entries(content: str) -> list:
    """从文档中提取 H2 标题作为 TOC 条目"""
    entries = []
    in_code = False
    for line in content.split('\n'):
        if CODE_BLOCK.match(line):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = HEADER_PATTERN.match(line)
        if m and len(m.group(1)) == 2:  # 仅 H2
            title = m.group(2).strip()
            anchor = gen_anchor(title)
            entries.append((title, anchor))
    return entries


def build_toc(entries: list) -> str:
    """构建 TOC 块"""
    lines = ['## 目录', '']
    for i, (title, anchor) in enumerate(entries, 1):
        lines.append(f'{i}. [{title}](#{anchor})')
    lines.append('')
    lines.append('---')
    lines.append('')
    return '\n'.join(lines)


def add_toc_to_doc(path: Path) -> bool:
    """为单个文档添加 TOC"""
    try:
        with open(path, encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return False

    # 已有 TOC 跳过
    if TOC_PATTERN.search(content):
        return False

    # 跳过 archive/
    if 'archive' in path.parts:
        return False

    # 文件太小跳过
    if path.stat().st_size < MIN_SIZE_KB * 1024:
        return False

    # 提取 frontmatter
    fm_match = FRONTMATTER_PATTERN.match(content)
    frontmatter = ''
    if fm_match:
        frontmatter = fm_match.group(0)
        content_after_fm = content[fm_match.end():]
    else:
        content_after_fm = content

    # 提取 H2 标题
    entries = extract_toc_entries(content_after_fm)
    if len(entries) < 3:  # 太少不添加
        return False

    # 构建 TOC
    toc = build_toc(entries)
    new_content = frontmatter + toc + content_after_fm.lstrip('\n')

    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    return True


added = 0
total = 0
for md_file in sorted(ROOT.rglob('*.md')):
    total += 1
    if add_toc_to_doc(md_file):
        added += 1
        rel = md_file.relative_to(ROOT)
        print(f'  + TOC | {rel}')

print(f'\n[OK] Added TOC to {added}/{total} files')
