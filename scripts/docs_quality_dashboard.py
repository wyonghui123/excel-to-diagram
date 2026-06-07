#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
docs 质量仪表盘

扫描 docs/ 目录，生成质量报告：
- 文件统计（总数、活跃、归档）
- 链接健康度（missing/anchor 数量）
- frontmatter 覆盖率
- 命名规范符合度
- 文档大小分布
- 章节平均长度

输出：
- scripts/docs-dashboard.txt (人类可读)
- scripts/docs-dashboard.json (机器可读)
"""
import os
import sys
import re
import json
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / 'docs'
SCRIPTS_DIR = ROOT / 'scripts'
sys.path.insert(0, str(SCRIPTS_DIR))

from check_doc_links import scan_file, extract_anchors

# 分类
ACTIVE_DIRS = ['', 'architecture', 'specs', 'lessons-learned', 'services',
               'research', 'retrospectives', 'metadata', 'performance']
ARCHIVE_DIRS = ['archive']

FRONTMATTER_PATTERN = re.compile(r'^---\s*\n(.+?)\n---\s*\n', re.DOTALL)
HEADER_PATTERN = re.compile(r'^(#{1,6})\s+(.+?)\s*$', re.MULTILINE)


def classify_file(path: Path) -> str:
    """文件分类：active / archive"""
    rel_parts = path.relative_to(DOCS_DIR).parts
    if rel_parts[0] in ['archive'] or 'archive' in rel_parts:
        return 'archive'
    return 'active'


def has_frontmatter(path: Path) -> bool:
    """检查文件是否有 frontmatter"""
    try:
        with open(path, encoding='utf-8') as f:
            content = f.read(2000)
        return bool(FRONTMATTER_PATTERN.match(content))
    except Exception:
        return False


def has_chinese_name(path: Path) -> bool:
    """检查文件名是否包含中文"""
    return any('\u4e00' <= c <= '\u9fff' for c in path.name)


def has_toc(path: Path) -> bool:
    """检查是否包含目录"""
    try:
        with open(path, encoding='utf-8') as f:
            content = f.read(5000)
        return bool(re.search(r'^##\s*目录', content, re.MULTILINE))
    except Exception:
        return False


def count_headers(path: Path) -> tuple:
    """统计标题数量（H1/H2/H3）"""
    h1, h2, h3 = 0, 0, 0
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                m = HEADER_PATTERN.match(line)
                if m:
                    level = len(m.group(1))
                    if level == 1:
                        h1 += 1
                    elif level == 2:
                        h2 += 1
                    elif level == 3:
                        h3 += 1
    except Exception:
        pass
    return (h1, h2, h3)


def main():
    print('Scanning docs/...')
    md_files = list(DOCS_DIR.rglob('*.md'))
    print(f'Found {len(md_files)} markdown files')

    stats = {
        'total_files': len(md_files),
        'active_files': 0,
        'archived_files': 0,
        'total_size_kb': 0,
        'files_with_frontmatter': 0,
        'files_with_toc': 0,
        'chinese_named_files': 0,
        'total_h1': 0,
        'total_h2': 0,
        'total_h3': 0,
        'missing_links': 0,
        'anchor_issues': 0,
        'files_with_issues': 0,
        'size_distribution': Counter(),
        'dir_distribution': Counter(),
        'top_files_by_size': [],
    }

    file_details = []

    for md_file in md_files:
        size_kb = md_file.stat().st_size / 1024
        rel = md_file.relative_to(ROOT)
        is_archived = classify_file(md_file) == 'archive'

        if is_archived:
            stats['archived_files'] += 1
        else:
            stats['active_files'] += 1

        stats['total_size_kb'] += size_kb
        stats['dir_distribution'][str(rel.parts[0] if len(rel.parts) > 1 else 'docs')] += 1

        # Size buckets
        if size_kb < 5:
            stats['size_distribution']['<5KB'] += 1
        elif size_kb < 20:
            stats['size_distribution']['5-20KB'] += 1
        elif size_kb < 50:
            stats['size_distribution']['20-50KB'] += 1
        elif size_kb < 100:
            stats['size_distribution']['50-100KB'] += 1
        else:
            stats['size_distribution']['>100KB'] += 1

        if has_frontmatter(md_file):
            stats['files_with_frontmatter'] += 1

        if has_chinese_name(md_file):
            stats['chinese_named_files'] += 1

        h1, h2, h3 = count_headers(md_file)
        stats['total_h1'] += h1
        stats['total_h2'] += h2
        stats['total_h3'] += h3

        if has_toc(md_file) and not is_archived:
            stats['files_with_toc'] += 1

        # Link check
        if not is_archived:
            issues = scan_file(md_file, check_external=False)
            missing = sum(1 for s, _, _ in issues if s == 'missing')
            anchor = sum(1 for s, _, _ in issues if s == 'anchor_missing')
            if missing or anchor:
                stats['files_with_issues'] += 1
            stats['missing_links'] += missing
            stats['anchor_issues'] += anchor

        # Track for top files
        file_details.append({
            'path': str(rel),
            'size_kb': round(size_kb, 1),
            'headers': h1 + h2 + h3,
            'archived': is_archived,
        })

    # Top files
    file_details.sort(key=lambda x: -x['size_kb'])
    stats['top_files_by_size'] = file_details[:10]

    # Calculate health scores
    if stats['active_files'] > 0:
        stats['frontmatter_coverage'] = round(
            100 * stats['files_with_frontmatter'] / stats['active_files'], 1
        )
        stats['toc_coverage'] = round(
            100 * stats['files_with_toc'] / stats['active_files'], 1
        )
        stats['chinese_name_ratio'] = round(
            100 * stats['chinese_named_files'] / stats['active_files'], 1
        )
    else:
        stats['frontmatter_coverage'] = 0
        stats['toc_coverage'] = 0
        stats['chinese_name_ratio'] = 0

    stats['avg_size_kb'] = round(stats['total_size_kb'] / stats['total_files'], 1) if stats['total_files'] > 0 else 0
    stats['total_size_kb'] = round(stats['total_size_kb'], 1)
    stats['total_issues'] = stats['missing_links'] + stats['anchor_issues']

    # 总体评分（0-100）
    health_score = 100
    health_score -= min(20, stats['total_issues'] / 10)  # 每个问题扣 0.1 分，最多 20 分
    health_score -= min(10, (100 - stats['frontmatter_coverage']) / 10)  # frontmatter 不全
    health_score -= min(10, (100 - stats['toc_coverage']) / 10)  # TOC 不全
    health_score -= min(10, stats['chinese_name_ratio'] / 10)  # 中文名扣分
    stats['health_score'] = max(0, round(health_score, 1))

    stats['generated_at'] = datetime.now().isoformat() + '+08:00'

    # 写入 JSON
    json_path = SCRIPTS_DIR / 'docs-dashboard.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    # 写入人类可读报告
    txt_path = SCRIPTS_DIR / 'docs-dashboard.txt'
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write('=' * 60 + '\n')
        f.write('  Excel-to-Diagram Documentation Quality Dashboard\n')
        f.write(f'  Generated: {stats["generated_at"]}\n')
        f.write('=' * 60 + '\n\n')

        f.write(f'[OVERALL] Health Score: {stats["health_score"]} / 100\n\n')

        f.write('=== File Statistics ===\n')
        f.write(f'  Total files:        {stats["total_files"]}\n')
        f.write(f'  Active files:       {stats["active_files"]}\n')
        f.write(f'  Archived files:     {stats["archived_files"]}\n')
        f.write(f'  Total size:         {stats["total_size_kb"]:.1f} KB\n')
        f.write(f'  Average size:       {stats["avg_size_kb"]:.1f} KB\n\n')

        f.write('=== Quality Coverage ===\n')
        f.write(f'  Frontmatter:        {stats["files_with_frontmatter"]}/{stats["active_files"]} ({stats["frontmatter_coverage"]}%)\n')
        f.write(f'  TOC:                {stats["files_with_toc"]}/{stats["active_files"]} ({stats["toc_coverage"]}%)\n')
        f.write(f'  English names:      {stats["active_files"] - stats["chinese_named_files"]}/{stats["active_files"]} ({100 - stats["chinese_name_ratio"]}%)\n\n')

        f.write('=== Headers ===\n')
        f.write(f'  H1: {stats["total_h1"]}    H2: {stats["total_h2"]}    H3: {stats["total_h3"]}\n\n')

        f.write('=== Link Health ===\n')
        f.write(f'  Missing links:      {stats["missing_links"]}\n')
        f.write(f'  Anchor issues:      {stats["anchor_issues"]}\n')
        f.write(f'  Files with issues:  {stats["files_with_issues"]}\n')
        f.write(f'  Total issues:       {stats["total_issues"]}\n\n')

        f.write('=== Size Distribution ===\n')
        for bucket in ['<5KB', '5-20KB', '20-50KB', '50-100KB', '>100KB']:
            count = stats['size_distribution'].get(bucket, 0)
            bar = '#' * min(50, count)
            f.write(f'  {bucket:10s} {count:3d}  {bar}\n')
        f.write('\n')

        f.write('=== Top 10 Largest Files ===\n')
        for i, f_info in enumerate(stats['top_files_by_size'], 1):
            archived = ' [ARCHIVED]' if f_info['archived'] else ''
            f.write(f'  {i:2d}. {f_info["size_kb"]:6.1f} KB  {f_info["headers"]:3d} H  {f_info["path"]}{archived}\n')
        f.write('\n')

        f.write('=== Directory Distribution ===\n')
        for dir_name, count in sorted(stats['dir_distribution'].items(), key=lambda x: -x[1])[:10]:
            f.write(f'  {dir_name:30s} {count:4d} files\n')
        f.write('\n')

        f.write('=' * 60 + '\n')
        f.write('  Recommendations:\n')
        f.write('=' * 60 + '\n')
        if stats['total_issues'] > 0:
            f.write(f'  [HIGH] Fix {stats["total_issues"]} link issues\n')
            f.write(f'         python scripts/check_doc_links.py --quiet\n')
        if stats['frontmatter_coverage'] < 50:
            f.write(f'  [MED]  Add frontmatter to docs ({stats["frontmatter_coverage"]}% coverage)\n')
        if stats['chinese_name_ratio'] > 10:
            f.write(f'  [LOW]  Rename remaining Chinese files ({stats["chinese_named_files"]})\n')
        if stats['health_score'] >= 80:
            f.write('  [OK]   Documentation is in good shape\n')
        elif stats['health_score'] >= 60:
            f.write('  [OK]   Documentation is acceptable, room for improvement\n')
        else:
            f.write('  [WARN] Documentation needs attention\n')

    # 打印简要报告
    print()
    print('=' * 60)
    print(f'  Overall Health Score: {stats["health_score"]} / 100')
    print('=' * 60)
    print()
    print(f'  Active:     {stats["active_files"]} files')
    print(f'  Archived:   {stats["archived_files"]} files')
    print(f'  Total:      {stats["total_files"]} files ({stats["total_size_kb"]:.1f} KB)')
    print()
    print(f'  Frontmatter coverage: {stats["frontmatter_coverage"]}%')
    print(f'  TOC coverage:         {stats["toc_coverage"]}%')
    print(f'  English names:        {100 - stats["chinese_name_ratio"]}%')
    print()
    print(f'  Link issues: {stats["total_issues"]} ({stats["missing_links"]} missing + {stats["anchor_issues"]} anchor)')
    print()
    print(f'[OK] Report: {txt_path}')
    print(f'[OK] JSON:   {json_path}')


if __name__ == '__main__':
    main()
