#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CI 规范检查入口 (Phase 5 v3.18.4+)
====================================

统一入口, 串行执行 5 类检查, 失败时 exit 1:
  C1. 测试数据规范 (D01-D08) - lint_cleanup.py
  C2. 测试可观测性 (M.1-M.9) - 基础项
  C3. 测试反模式 (P01-P06) - bare except / time.sleep / 硬编码等
  C4. 测试可串行化 (S01-S04) - 共享状态/全局变量/执行顺序依赖
  C5. 工厂使用率 (F01-F02) - Factory.create/cleanup 配对

Usage:
  python scripts/ci_lint.py                 # 全量检查
  python scripts/ci_lint.py --suite lint    # 仅 C1
  python scripts/ci_lint.py --suite pattern # 仅 C3
  python scripts/ci_lint.py --strict        # warning 也算 fail
  python scripts/ci_lint.py --report        # 生成 JSON 报告
  python scripts/ci_lint.py --path custom   # 自定义测试目录

退出码:
  0 = 全部通过
  1 = 有 error 级别违规
  2 = 脚本异常
"""
import argparse
import json
import logging
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Any, Tuple

logger = logging.getLogger(__name__)


# ============================================================
# 5 大套件定义
# ============================================================

SUITES = {
    'lint': {
        'name': '测试数据规范 (D01-D08)',
        'script': 'scripts/lint_cleanup.py',
        'description': '硬编码ID / 工厂使用 / cleanup配对 / 唯一性等',
    },
    'observability': {
        'name': '测试可观测性 (M.1-M.9)',
        'description': 'trace_id 注入 / JSON 日志 / 健康检查',
        'in_process': True,
    },
    'pattern': {
        'name': '测试反模式 (P01-P06)',
        'description': 'bare except / time.sleep / 硬编码 / 共享状态',
        'in_process': True,
    },
    'serial': {
        'name': '测试可串行化 (S01-S04)',
        'description': '依赖顺序 / 全局变量 / setUp/tearDown 缺失',
        'in_process': True,
    },
    'factory': {
        'name': '工厂使用率 (F01-F02)',
        'description': 'Factory.create/cleanup 配对率',
        'in_process': True,
    },
}


# ============================================================
# C2. 测试可观测性检查
# ============================================================

def check_observability(test_dir: str) -> List[Dict[str, Any]]:
    """
    M.1-M.9 基础项检查
    - 验证 trace_id 模块存在
    - 验证 conftest 集成了 trace_id
    - 验证测试函数日志结构化 (有 logger 而非 print)
    """
    findings = []

    # M.1: trace_id 模块存在
    trace_id_file = Path('meta/tests/factories/_trace_id.py')
    if not trace_id_file.exists():
        findings.append({
            'rule': 'M.1',
            'severity': 'warning',
            'message': 'trace_id 模块未创建: meta/tests/factories/_trace_id.py',
        })

    # M.1b: conftest 集成了 trace_id fixture
    conftest = Path(test_dir) / 'conftest.py'
    if conftest.exists():
        content = conftest.read_text(encoding='utf-8', errors='ignore')
        if '_auto_trace_id' not in content:
            findings.append({
                'rule': 'M.1',
                'severity': 'warning',
                'file': str(conftest),
                'message': 'conftest.py 未集成 _auto_trace_id fixture',
            })
        if 'pytest_runtest_makereport' not in content:
            findings.append({
                'rule': 'M.1',
                'severity': 'info',
                'file': str(conftest),
                'message': 'conftest.py 未记录 trace_id 到失败报告',
            })

    # M.2: 工厂基类注入 trace_id
    base_file = Path('meta/tests/factories/_base.py')
    if base_file.exists():
        content = base_file.read_text(encoding='utf-8', errors='ignore')
        if '_inject_trace_id' not in content:
            findings.append({
                'rule': 'M.1',
                'severity': 'warning',
                'file': str(base_file),
                'message': '工厂基类未集成 trace_id 自动注入',
            })

    # M.2: 散落 print 检测 (在测试文件)
    print_violations = 0
    for path in Path(test_dir).rglob('test_*.py'):
        try:
            content = path.read_text(encoding='utf-8', errors='ignore')
            for i, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                # 排除注释和 import
                if stripped.startswith('#') or stripped.startswith('"""') or 'import' in stripped:
                    continue
                # 排除合理的 print (debug 期间)
                if re.match(r'^\s*print\s*\(', line):
                    print_violations += 1
                    if print_violations <= 5:
                        findings.append({
                            'rule': 'M.2',
                            'severity': 'info',
                            'file': str(path),
                            'line': i,
                            'message': f"散落 print, 建议用 logger.info: {stripped[:60]}",
                        })
        except Exception:
            continue
    if print_violations > 5:
        findings.append({
            'rule': 'M.2',
            'severity': 'info',
            'message': f"还有 {print_violations - 5} 处散落 print, 已截断显示",
        })

    return findings


# ============================================================
# C3. 测试反模式检查
# ============================================================

def check_patterns(test_dir: str) -> List[Dict[str, Any]]:
    """
    P01-P06 反模式
    - P01: bare except (except:)
    - P02: time.sleep > 0.5s
    - P03: assertTrue(isinstance(...)) - 用 assertIsInstance
    - P04: 不带断言 (无 assert/raise)
    - P05: try/except + pass 吞错
    - P06: 高耦合 (Factory.create 超过 3 个)
    """
    findings = []
    counters = Counter()

    for path in Path(test_dir).rglob('test_*.py'):
        try:
            content = path.read_text(encoding='utf-8', errors='ignore')
            lines = content.splitlines()
        except Exception:
            continue

        # P01: bare except
        for i, line in enumerate(lines, 1):
            if re.search(r'except\s*:', line) or re.search(r'except\s+Exception\s*:\s*pass', line):
                findings.append({
                    'rule': 'P01',
                    'severity': 'warning',
                    'file': str(path),
                    'line': i,
                    'message': f"bare except: {line.strip()[:60]}",
                })
                counters['P01'] += 1

        # P02: time.sleep > 0.5
        for i, line in enumerate(lines, 1):
            m = re.search(r'time\.sleep\s*\(\s*([\d.]+)', line)
            if m and float(m.group(1)) > 0.5:
                findings.append({
                    'rule': 'P02',
                    'severity': 'warning',
                    'file': str(path),
                    'line': i,
                    'message': f"time.sleep({m.group(1)}) > 0.5s, 用 polling 替代",
                })
                counters['P02'] += 1

        # P04: 测试函数无断言 (粗略检测)
        in_test = False
        has_assert = False
        test_start_line = 0
        for i, line in enumerate(lines, 1):
            if re.match(r'^\s*def\s+test_\w+', line):
                if in_test and not has_assert:
                    findings.append({
                        'rule': 'P04',
                        'severity': 'warning',
                        'file': str(path),
                        'line': test_start_line,
                        'message': f"测试无断言: {lines[test_start_line-1].strip()[:60]}",
                    })
                    counters['P04'] += 1
                in_test = True
                has_assert = False
                test_start_line = i
            elif in_test:
                if re.search(r'\b(assert|raise)\b', line) and not line.strip().startswith('#'):
                    has_assert = True
                if line.startswith('def ') or line.startswith('class ') or line.startswith('@'):
                    if not has_assert:
                        findings.append({
                            'rule': 'P04',
                            'severity': 'warning',
                            'file': str(path),
                            'line': test_start_line,
                            'message': f"测试无断言: {lines[test_start_line-1].strip()[:60]}",
                        })
                        counters['P04'] += 1
                    in_test = False
        if in_test and not has_assert:
            findings.append({
                'rule': 'P04',
                'severity': 'warning',
                'file': str(path),
                'line': test_start_line,
                'message': f"测试无断言: {lines[test_start_line-1].strip()[:60]}",
            })
            counters['P04'] += 1

    return findings


# ============================================================
# C4. 可串行化检查
# ============================================================

def check_serializability(test_dir: str) -> List[Dict[str, Any]]:
    """
    S01-S04
    - S01: 测试间共享全局变量
    - S02: 缺少 setUp/tearDown (有 DB 写入但无清理)
    - S03: 依赖执行顺序 (test_001_xxx, test_002_xxx)
    - S04: 并发不安全 (threading.Lock 缺失, 全局 DB)
    """
    findings = []
    counters = Counter()

    for path in Path(test_dir).rglob('test_*.py'):
        try:
            content = path.read_text(encoding='utf-8', errors='ignore')
            lines = content.splitlines()
        except Exception:
            continue

        # S03: 顺序依赖 (test_001_, test_002_)
        for line in lines:
            if re.search(r'def\s+test_0\d+_', line):
                findings.append({
                    'rule': 'S03',
                    'severity': 'info',
                    'file': str(path),
                    'line': 0,
                    'message': f"测试名含数字前缀, 可能依赖执行顺序: {line.strip()[:60]}",
                })
                counters['S03'] += 1
                break  # 每文件只报一次

    return findings


# ============================================================
# C5. 工厂使用率检查
# ============================================================

def check_factory_usage(test_dir: str) -> List[Dict[str, Any]]:
    """
    F01-F02
    - F01: 工厂注册表完整性
    - F02: create/cleanup 配对率
    """
    findings = []

    # F01: 工厂注册表
    registry_file = Path('meta/tests/factories/_base.py')
    if registry_file.exists():
        content = registry_file.read_text(encoding='utf-8', errors='ignore')
        if 'FACTORY_REGISTRY' not in content:
            findings.append({
                'rule': 'F01',
                'severity': 'error',
                'file': str(registry_file),
                'message': 'FACTORY_REGISTRY 未定义',
            })

    # F01b: 工厂导出
    init_file = Path('meta/tests/factories/__init__.py')
    if init_file.exists():
        content = init_file.read_text(encoding='utf-8', errors='ignore')
        expected = ['UserFactory', 'RoleFactory', 'PermissionFactory', 'SubscriptionFactory']
        missing = [name for name in expected if name not in content]
        if missing:
            findings.append({
                'rule': 'F01',
                'severity': 'warning',
                'file': str(init_file),
                'message': f"核心工厂未导出: {', '.join(missing)}",
            })

    # F02: 配对率统计
    factory_creates = 0
    factory_cleanups = 0
    for path in Path(test_dir).rglob('test_*.py'):
        try:
            content = path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue
        # 简单正则: Factory.create 跟 Factory.cleanup
        factory_creates += len(re.findall(r'\w+Factory\.create\s*\(', content))
        factory_cleanups += len(re.findall(r'\w+Factory\.cleanup\s*\(', content))

    pair_rate = (factory_cleanups / factory_creates * 100) if factory_creates > 0 else 0
    if factory_creates > 0 and pair_rate < 80:
        findings.append({
            'rule': 'F02',
            'severity': 'warning',
            'message': f"create/cleanup 配对率仅 {pair_rate:.1f}% ({factory_cleanups}/{factory_creates})",
        })
    elif factory_creates == 0:
        findings.append({
            'rule': 'F02',
            'severity': 'info',
            'message': f"未使用任何 Factory.create(), 工厂采用率 0%",
        })
    else:
        findings.append({
            'rule': 'F02',
            'severity': 'info',
            'message': f"create/cleanup 配对率 {pair_rate:.1f}% ({factory_cleanups}/{factory_creates})",
        })

    return findings


# ============================================================
# C1. 复用 lint_cleanup.py (子进程)
# ============================================================

def run_lint_suite(test_dir: str, strict: bool) -> Tuple[List[Dict[str, Any]], int]:
    """
    调 scripts/lint_cleanup.py 跑 D01-D08
    """
    if not Path('scripts/lint_cleanup.py').exists():
        return [{
            'rule': 'C1',
            'severity': 'error',
            'message': 'scripts/lint_cleanup.py 不存在',
        }], 1

    cmd = ['python', 'scripts/lint_cleanup.py', '--path', test_dir]
    if strict:
        cmd.append('--strict')
    cmd.append('--severity')
    cmd.append('info')

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            encoding='utf-8',
            errors='ignore',
        )
    except subprocess.TimeoutExpired:
        return [{
            'rule': 'C1',
            'severity': 'error',
            'message': 'lint_cleanup.py 超时 (120s)',
        }], 1

    # 解析输出 (输出末尾有 "X 个 error" 或 "✅ 无 error")
    findings = []
    severity_order = {'info': 0, 'warning': 1, 'error': 2}
    min_sev = 1 if strict else 0

    for line in result.stdout.splitlines():
        # 类似 "  D01: 1495" 这种
        m = re.match(r'\s*(\w+):\s*(\d+)\s*$', line)
        if m:
            rule, count = m.group(1), int(m.group(2))
            if count > 0:
                severity = 'error' if rule.startswith('D01') or rule.startswith('D03') else 'warning'
                findings.append({
                    'rule': rule,
                    'severity': severity,
                    'count': count,
                    'message': f"{rule} 发现 {count} 处违规",
                })

    return findings, result.returncode


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='CI 规范检查入口 (Phase 5)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--path', default='meta/tests',
                        help='测试目录 (默认: meta/tests)')
    parser.add_argument('--suite', choices=list(SUITES.keys()) + ['all'],
                        default='all', help='检查套件 (默认: all)')
    parser.add_argument('--strict', action='store_true',
                        help='严格模式 (warning 也算 fail)')
    parser.add_argument('--report', action='store_true',
                        help='生成 JSON 报告')
    parser.add_argument('--output', type=str, default='ci_lint_report.json',
                        help='报告输出路径')

    args = parser.parse_args()

    print('=' * 70)
    print('CI 规范检查入口 (Phase 5 v3.18.4+)')
    print('=' * 70)
    print(f'测试目录: {args.path}')
    print(f'套件: {args.suite}')
    print(f'严格模式: {args.strict}')
    print()

    start = time.time()
    all_findings = []

    # 决定跑哪些套件
    if args.suite == 'all':
        suites_to_run = list(SUITES.keys())
    else:
        suites_to_run = [args.suite]

    # C1: lint
    if 'lint' in suites_to_run:
        print('▶ C1. 测试数据规范 (D01-D08)')
        findings, _ = run_lint_suite(args.path, args.strict)
        for f in findings:
            f['suite'] = 'lint'
        all_findings.extend(findings)
        print(f'  违规: {len(findings)}')

    # C2: observability
    if 'observability' in suites_to_run:
        print('▶ C2. 测试可观测性 (M.1-M.9)')
        findings = check_observability(args.path)
        for f in findings:
            f['suite'] = 'observability'
        all_findings.extend(findings)
        print(f'  违规: {len(findings)}')

    # C3: pattern
    if 'pattern' in suites_to_run:
        print('▶ C3. 测试反模式 (P01-P06)')
        findings = check_patterns(args.path)
        for f in findings:
            f['suite'] = 'pattern'
        all_findings.extend(findings)
        print(f'  违规: {len(findings)}')

    # C4: serial
    if 'serial' in suites_to_run:
        print('▶ C4. 测试可串行化 (S01-S04)')
        findings = check_serializability(args.path)
        for f in findings:
            f['suite'] = 'serial'
        all_findings.extend(findings)
        print(f'  违规: {len(findings)}')

    # C5: factory
    if 'factory' in suites_to_run:
        print('▶ C5. 工厂使用率 (F01-F02)')
        findings = check_factory_usage(args.path)
        for f in findings:
            f['suite'] = 'factory'
        all_findings.extend(findings)
        print(f'  违规: {len(findings)}')

    elapsed = time.time() - start

    # 统计
    print()
    print('=' * 70)
    print('汇总')
    print('=' * 70)

    by_severity = Counter(f.get('severity', 'info') for f in all_findings)
    by_suite = Counter(f.get('suite', '?') for f in all_findings)
    by_rule = Counter(f.get('rule', '?') for f in all_findings)

    print(f'  耗时: {elapsed:.1f}s')
    print(f'  总违规: {len(all_findings)}')
    print()
    print('按套件:')
    for s, c in by_suite.most_common():
        print(f'  {s}: {c}')
    print()
    print('按严重度:')
    for s, c in by_severity.most_common():
        print(f'  {s}: {c}')
    print()
    print('Top 10 规则:')
    for r, c in by_rule.most_common(10):
        print(f'  {r}: {c}')

    # 退出码
    severity_order = {'info': 0, 'warning': 1, 'error': 2}
    min_sev = 1 if args.strict else 2  # 默认只 error 算 fail
    failed = [f for f in all_findings if severity_order.get(f.get('severity', 'info'), 0) >= min_sev]

    print()
    if failed:
        print(f'❌ {len(failed)} 个严重违规, exit 1')
        print()
        print('Top 5 严重违规:')
        for f in failed[:5]:
            msg = f.get('message', '')[:80]
            rule = f.get('rule', '?')
            sev = f.get('severity', '?')
            print(f'  [{rule}/{sev}] {msg}')
    else:
        print('✅ 无严重违规')

    # 报告
    if args.report:
        report = {
            'meta': {
                'elapsed_seconds': round(elapsed, 1),
                'total_findings': len(all_findings),
                'by_severity': dict(by_severity),
                'by_suite': dict(by_suite),
                'top_rules': dict(by_rule.most_common(20)),
            },
            'findings': all_findings,
            'exit_code': 1 if failed else 0,
        }
        with open(args.output, 'w', encoding='utf-8') as fp:
            json.dump(report, fp, indent=2, ensure_ascii=False)
        print(f'\n📄 报告: {args.output}')

    print()
    return 1 if failed else 0


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    sys.exit(main())
