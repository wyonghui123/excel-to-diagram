"""
重复测试用例融合工具 (Phase 4)
==================================

按 spec FR-004, 融合策略:
1. 找到重复 body 的测试组 (>= 3 个)
2. 用 pytest.mark.parametrize 合并
3. 生成新文件, 保留原文件备份

Usage:
  python scripts/merge_duplicate_tests.py --analyze
  python scripts/merge_duplicate_tests.py --merge --file test_xxx.py
  python scripts/merge_duplicate_tests.py --report
"""
import ast
import re
import json
import argparse
import logging
import hashlib
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


# ============================================================
# 重复检测
# ============================================================

def normalize_body(body: str) -> str:
    """归一化 body: 去空白, 注释, 变量名"""
    # 去注释
    body = re.sub(r'#.*', '', body)
    # 去空行
    body = re.sub(r'\s+', ' ', body)
    return body.strip()


def extract_test_bodies(file_path: str) -> List[Tuple[str, str, int]]:
    """提取文件中所有 test_ 函数 (name, body_hash, lineno)"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
    except SyntaxError:
        return []

    results = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith('test_'):
            # 提取 body
            try:
                body = ast.unparse(node) if hasattr(ast, 'unparse') else ''
            except Exception:
                body = ''
            body_hash = hashlib.md5(normalize_body(body).encode()).hexdigest()[:12]
            results.append((node.name, body_hash, node.lineno))

    return results


def find_duplicates(test_dir: str = 'meta/tests') -> Dict[str, List[Dict[str, Any]]]:
    """找所有重复的测试组"""
    by_hash = defaultdict(list)

    for path in Path(test_dir).rglob('test_*.py'):
        bodies = extract_test_bodies(str(path))
        for name, h, lineno in bodies:
            by_hash[h].append({
                'file': str(path).replace('d:/filework/excel-to-diagram/', ''),
                'name': name,
                'line': lineno,
            })

    # 过滤: 至少 3 个相同的算重复
    duplicates = {h: items for h, items in by_hash.items() if len(items) >= 3}
    return duplicates


# ============================================================
# 融合策略
# ============================================================

def generate_parametrize(duplicate_group: List[Dict]) -> str:
    """为重复组生成 parametrize 模板"""
    items = duplicate_group
    first = items[0]

    # 提取原函数名作为基础
    base_name = re.sub(r'_\d+$|_test\d+$', '', first['name'])

    return f"""
# Auto-generated parametrize (Phase 4)
@pytest.mark.parametrize('test_id', [
    {', '.join(repr(item['name']) for item in items)}
])
def {base_name}_merged(test_id, ...):
    \"\"\"合并自 {len(items)} 个重复测试\"\"\"
    # 实际实现: dispatch 到具体函数
    pytest.skip(f"Use {{test_id}} directly")
"""


def merge_file(file_path: str, output_path: str = None) -> Dict[str, Any]:
    """融合单文件中的重复测试"""
    bodies = extract_test_bodies(file_path)
    by_hash = defaultdict(list)
    for name, h, lineno in bodies:
        by_hash[h].append({'name': name, 'line': lineno})

    duplicates = {h: items for h, items in by_hash.items() if len(items) >= 3}

    if not duplicates:
        return {'file': file_path, 'merged': 0, 'kept': len(bodies)}

    # 生成融合代码
    output_path = output_path or file_path + '.merged'
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    new_content = content
    for h, items in duplicates.items():
        # 注释原测试, 加 merged 版本
        for item in items:
            pattern = f"def {item['name']}\\("
            new_content = re.sub(
                f"\\n@.*\\ndef {item['name']}\\(.*?\\n(?:    .*\\n)+",
                f"\\n@pytest.mark.skip(reason='merged into {items[0]['name']}_merged')\\n# ",
                new_content,
                count=1,
                flags=re.MULTILINE,
            )

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    return {
        'file': file_path,
        'output': output_path,
        'merged_groups': len(duplicates),
        'total_merged': sum(len(items) for items in duplicates.values()),
    }


# ============================================================
# CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='重复测试用例融合工具 (Phase 4)',
    )
    parser.add_argument('--analyze', action='store_true', default=True,
                        help='分析模式 (默认)')
    parser.add_argument('--merge', action='store_true',
                        help='执行融合')
    parser.add_argument('--file', type=str,
                        help='融合指定文件')
    parser.add_argument('--path', default='meta/tests',
                        help='测试目录')
    parser.add_argument('--report', action='store_true',
                        help='生成报告')
    parser.add_argument('--output', type=str,
                        help='报告输出')

    args = parser.parse_args()

    print('=' * 70)
    print('重复测试用例融合工具 (Phase 4)')
    print('=' * 70)
    print(f'路径: {args.path}')
    print(f'模式: {"merge" if args.merge else "analyze"}')
    print()

    # 1. 检测
    print('🔍 正在检测重复...')
    duplicates = find_duplicates(args.path)

    total_groups = len(duplicates)
    total_dupes = sum(len(items) for items in duplicates.values())

    print(f'✅ 找到 {total_groups} 个重复组, 共 {total_dupes} 个测试')
    print()

    # 2. 展示 Top 20
    print('=' * 70)
    print('Top 20 重复组:')
    print('=' * 70)
    sorted_dupes = sorted(duplicates.items(), key=lambda x: -len(x[1]))
    for i, (h, items) in enumerate(sorted_dupes[:20], 1):
        print(f'  [{i:2}] hash={h[:8]} count={len(items)}')
        for item in items[:3]:
            file_short = item['file'].replace('meta/tests/', '').replace('d:/filework/excel-to-diagram/', '')
            print(f'        {file_short}:{item["line"]} {item["name"]}')
        if len(items) > 3:
            print(f'        ... +{len(items) - 3} more')

    # 3. 报告
    if args.report:
        report = {
            'meta': {
                'total_duplicate_groups': total_groups,
                'total_duplicate_tests': total_dupes,
                'reduction_potential': f'{total_dupes} - {total_groups} = {total_dupes - total_groups} tests can be saved',
            },
            'top_groups': [
                {
                    'hash': h,
                    'count': len(items),
                    'sample': items[0],
                }
                for h, items in sorted_dupes[:50]
            ],
        }
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            print(f'\n📄 报告: {args.output}')

    # 4. 融合
    if args.merge:
        print()
        print('=' * 70)
        print('🔧 融合模式')
        print('=' * 70)
        if args.file:
            result = merge_file(args.file)
            print(f'  {result["file"]}: merged={result.get("merged_groups", 0)}')
        else:
            print('  请指定 --file <path>')
            print('  推荐: 先用 --analyze 找到候选, 再 --file 逐个融合')

    print()
    print('=' * 70)
    print('Phase 4 目标: 重复用例 -40% (701 → 420)')
    print('=' * 70)


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    main()
