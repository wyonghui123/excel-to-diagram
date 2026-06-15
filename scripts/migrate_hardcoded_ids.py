"""
硬编码 ID 检测与迁移 CLI (Phase 2)
=====================================

Usage:
  python scripts/migrate_hardcoded_ids.py --dry-run
  python scripts/migrate_hardcoded_ids.py --fix --severity high
  python scripts/migrate_hardcoded_ids.py --report
  python scripts/migrate_hardcoded_ids.py --report --output report.json

TBD-6 采纳: high 自动 fix, 其他只检测
"""
import ast
import re
import json
import argparse
import logging
from pathlib import Path
from collections import Counter, defaultdict
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


# ============================================================
# 硬编码 ID 模式 (10 种)
# ============================================================

HARDCODE_PATTERNS = [
    (re.compile(r'\bid\s*=\s*(\d+)'), 'id_equals'),
    (re.compile(r'\buser_id\s*=\s*(\d+)'), 'user_id_var'),
    (re.compile(r'\brole_id\s*=\s*(\d+)'), 'role_id_var'),
    (re.compile(r'\bbo_id\s*=\s*(\d+)'), 'bo_id_var'),
    (re.compile(r'\bversion_id\s*=\s*(\d+)'), 'version_id_var'),
    (re.compile(r'\bdomain_id\s*=\s*(\d+)'), 'domain_id_var'),
    (re.compile(r'\bsubscription_id\s*=\s*(\d+)'), 'subscription_id_var'),
    (re.compile(r'/api/v\d+/\w+/(\d+)'), 'url_id'),
    (re.compile(r'"id"\s*:\s*(\d+)'), 'json_id'),
    (re.compile(r"'id'\s*:\s*(\d+)"), 'json_id_single'),
    (re.compile(r'fake_id\s*=\s*(\d+)'), 'fake_id'),
    (re.compile(r'invalid_id\s*=\s*(\d+)'), 'invalid_id'),
]


# ============================================================
# 严重度判定
# ============================================================

def get_severity(id_val: int) -> str:
    """
    TBD-2 采纳: 1000 阈值保留

    high   id >= 1000: 跨次跑必冲突, 必须修复
    medium 5-999:      中等冲突风险
    low    < 5:        循环/sentinel, 可保留
    """
    if id_val < 5:
        return 'low'
    elif id_val < 1000:
        return 'medium'
    else:
        return 'high'


# ============================================================
# 检测函数
# ============================================================

def detect_in_file(file_path: str) -> List[Dict[str, Any]]:
    """检测单个文件中的硬编码 ID"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')
    except Exception as e:
        logger.warning(f"Cannot read {file_path}: {e}")
        return []

    results = []
    for line_num, line in enumerate(lines, 1):
        # 跳过注释行
        stripped = line.strip()
        if stripped.startswith('#'):
            continue

        for pat, pattern_name in HARDCODE_PATTERNS:
            for m in pat.finditer(line):
                id_val_str = m.group(1)
                try:
                    id_val = int(id_val_str)
                except ValueError:
                    continue

                severity = get_severity(id_val)

                # 跳过 factory 内部 (factory 必然有默认值, 不会被检测为硬编码)
                if 'factory' in line.lower() and 'defaults' in line.lower():
                    continue

                results.append({
                    'file': file_path,
                    'line': line_num,
                    'column': m.start(),
                    'id': id_val,
                    'pattern': pattern_name,
                    'severity': severity,
                    'context': line.strip()[:120],
                })

    return results


def detect_in_directory(test_dir: str = 'meta/tests') -> List[Dict[str, Any]]:
    """检测目录中所有测试文件"""
    all_findings = []
    for path in Path(test_dir).rglob('test_*.py'):
        all_findings.extend(detect_in_file(str(path)))
    return all_findings


# ============================================================
# 报告生成
# ============================================================

def generate_report(findings: List[Dict]) -> Dict[str, Any]:
    """生成汇总报告"""
    by_severity = Counter(f['severity'] for f in findings)
    by_pattern = Counter(f['pattern'] for f in findings)
    by_file = Counter(f['file'] for f in findings)

    # 高严重度 (id >= 1000) Top 50
    high_severity = sorted(
        [f for f in findings if f['severity'] == 'high'],
        key=lambda x: -x['id']
    )[:50]

    return {
        'meta': {
            'total_findings': len(findings),
            'high_count': by_severity.get('high', 0),
            'medium_count': by_severity.get('medium', 0),
            'low_count': by_severity.get('low', 0),
            'files_affected': len(by_file),
        },
        'by_pattern': dict(by_pattern.most_common(20)),
        'top_files': by_file.most_common(20),
        'high_severity_samples': high_severity,
    }


# ============================================================
# 自动修复 (谨慎)
# ============================================================

def suggest_fix(finding: Dict[str, Any]) -> str:
    """为单个硬编码 ID 生成修复建议"""
    pattern = finding['pattern']
    id_val = finding['id']

    # 根据 pattern 给出修复建议
    if pattern == 'id_equals':
        return f"  改为:  user_id = test_user()['id']  # auto-cleanup"
    elif pattern == 'user_id_var':
        return f"  改为:  user_id = test_users()['id']"
    elif pattern == 'role_id_var':
        return f"  改为:  role_id = test_roles()['id']"
    elif pattern == 'bo_id_var':
        return f"  改为:  bo_id = test_bos()['id']"
    elif pattern == 'version_id_var':
        return f"  改为:  version_id = test_versions()['id']"
    elif pattern == 'url_id':
        return f"  改为:  url = f'/api/v2/user/{user_id}'  # 用变量"
    elif pattern == 'json_id':
        return f"  改为:  '{{\"id\": {obj_id}}}'  # 用变量"
    else:
        return f"  改为:  用 Factory.create()['id'] 替代硬编码 {id_val}"


def auto_fix_file(file_path: str, severity: str, dry_run: bool = True) -> Dict[str, Any]:
    """
    自动修复文件中的硬编码 ID

    TBD-6 采纳: high 自动 fix, 其他只检测
    """
    findings = detect_in_file(file_path)
    filtered = [f for f in findings if f['severity'] == severity]

    if not filtered:
        return {'file': file_path, 'fixed': 0, 'skipped': 0}

    if dry_run:
        return {
            'file': file_path,
            'would_fix': len(filtered),
            'fixes': [suggest_fix(f) for f in filtered[:10]],
        }

    # 真实修复 (谨慎, 仅对 high 严重度)
    fixed = 0
    skipped = 0
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    new_content = content
    for finding in filtered:
        # 安全修复模式: 注释掉硬编码, 添加 factory 调用
        # 实际修复需要人工 review, 这里只做 demo
        # 真实场景: 用 sed/script 替换, 然后人工 review diff
        skipped += 1

    return {
        'file': file_path,
        'fixed': fixed,
        'skipped': skipped,
        'note': 'Auto-fix is conservative, recommend manual review',
    }


# ============================================================
# CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='硬编码 ID 检测与迁移工具 (Phase 2)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--dry-run', action='store_true', default=True,
                        help='只检测, 不修改 (默认)')
    parser.add_argument('--fix', action='store_true',
                        help='自动修复 (仅 high 严重度)')
    parser.add_argument('--severity', choices=['low', 'medium', 'high'],
                        default='medium', help='严重度阈值')
    parser.add_argument('--path', default='meta/tests',
                        help='测试目录')
    parser.add_argument('--report', action='store_true',
                        help='生成详细报告')
    parser.add_argument('--output', type=str,
                        help='报告输出路径')

    args = parser.parse_args()

    print('=' * 70)
    print('硬编码 ID 检测与迁移工具 (Phase 2)')
    print('=' * 70)
    print(f'路径: {args.path}')
    print(f'严重度: {args.severity}+')
    print(f'模式: {"fix" if args.fix else "dry-run"}')
    print()

    # 1. 检测
    print('🔍 正在检测...')
    findings = detect_in_directory(args.path)

    severity_order = {'low': 0, 'medium': 1, 'high': 2}
    min_sev = severity_order[args.severity]
    filtered = [f for f in findings if severity_order[f['severity']] >= min_sev]

    print(f'✅ 检测到 {len(findings)} 个硬编码 ID')
    print(f'   - high:   {sum(1 for f in findings if f["severity"] == "high")}')
    print(f'   - medium: {sum(1 for f in findings if f["severity"] == "medium")}')
    print(f'   - low:    {sum(1 for f in findings if f["severity"] == "low")}')
    print(f'   过滤后 (>= {args.severity}): {len(filtered)}')
    print()

    # 2. 展示 Top 20
    print('=' * 70)
    print('Top 20 高严重度 (id >= 1000):')
    print('=' * 70)
    high = sorted(
        [f for f in findings if f['severity'] == 'high'],
        key=lambda x: -x['id']
    )[:20]
    for f in high:
        file_short = f['file'].replace('meta/tests/', '').replace('d:/filework/excel-to-diagram/', '')
        print(f'  [{f["severity"]:6}] {file_short}:{f["line"]:3} '
              f'id={f["id"]:5} ({f["pattern"]:15})')
        print(f'           {f["context"][:80]}')
    print()

    # 3. 报告模式
    if args.report:
        report = generate_report(findings)
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as fp:
                json.dump(report, fp, indent=2, ensure_ascii=False)
            print(f'📄 报告已写入: {args.output}')
        else:
            print(json.dumps(report, indent=2, ensure_ascii=False)[:2000])

    # 4. 修复模式
    if args.fix and args.severity == 'high':
        print('=' * 70)
        print('🔧 自动修复 (high 严重度, 谨慎模式)')
        print('=' * 70)
        files_to_fix = set(f['file'] for f in high)
        for f in files_to_fix:
            result = auto_fix_file(f, 'high', dry_run=True)
            print(f'  {f}:')
            print(f'    would_fix={result.get("would_fix", 0)}')
            for fix in result.get('fixes', [])[:3]:
                print(fix)
        print()
        print('⚠️  自动修复处于 dry-run 模式, 实际修复需人工 review + git commit')

    print()
    print('✅ 完成')


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    main()
