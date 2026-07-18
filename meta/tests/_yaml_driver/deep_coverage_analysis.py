# -*- coding: utf-8 -*-
"""
deep_coverage_analysis.py
=========================
从 6 个维度全面分析测试覆盖度:
1. yaml-driven 自动测试覆盖
2. 手写 test_*.py 覆盖
3. factory 资产覆盖
4. RLS 规则覆盖
5. Aspects 覆盖
6. 前端 (Vue) 覆盖

每个 schema 输出:
- 6 维覆盖矩阵
- 综合评分 (0-100)
- 风险等级 (HIGH/MEDIUM/LOW)
- 改进建议
"""
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


# ============================================================
# 维度 1: yaml-driven 自动覆盖 (v1.1 推导)
# ============================================================

def collect_yaml_driven_coverage() -> Dict[str, Dict]:
    """v1.1 discoverer 推导每个 schema 的 yaml-driven case 数"""
    sys.path.insert(0, '.')
    from meta.tests._yaml_driver.loader import load_schemas
    from meta.tests._yaml_driver.discoverer import (
        discover_all_constraints, discover_v11_constraints,
    )

    objs = load_schemas()
    v1_specs = discover_all_constraints(objs)
    v11_specs = discover_v11_constraints(objs, aspects=None, rls_rules=None, factories=None)

    # 计算每个 schema 的 case 数
    coverage = {}
    for sid, obj in objs.items():
        # v1.0: 每个 persistent+testable schema 自动派生 N 个 case
        v1_count = sum(1 for s in v1_specs if s.object_id == sid)
        v11_count = sum(1 for s in v11_specs if s.object_id == sid)
        coverage[sid] = {
            'v1_count': v1_count,
            'v11_count': v11_count,
            'total_auto': v1_count + v11_count,
        }
    return coverage


# ============================================================
# 维度 2: 手写 test_*.py 覆盖
# ============================================================

def collect_manual_test_coverage(test_patterns: List[str]) -> Dict[str, Dict]:
    """对每个 schema 统计手写 test_*.py 的覆盖"""
    import glob
    files = set()
    for p in test_patterns:
        files.update(glob.glob(p, recursive=True))

    coverage = defaultdict(lambda: {
        'files_total': 0,        # 任何方式出现的文件数
        'files_strict': 0,       # 严格命中文件数
        'class_files': 0,        # 含 Test 类的文件数
        'ref_count': 0,          # 引用次数
        'sample_files': [],      # sample 文件名
    })

    file_contents = {}
    for f in files:
        try:
            with open(f, encoding='utf-8') as fh:
                file_contents[f] = fh.read()
        except (UnicodeDecodeError, OSError):
            continue

    # 收集每个 schema_id 出现信息
    # 先用 loader 拿到所有 schema id
    sys.path.insert(0, '.')
    from meta.tests._yaml_driver.loader import load_schemas
    objs = load_schemas()

    for sid in objs.keys():
        sid_underscored = sid.replace('_', '')
        sid_camel = ''.join(p.capitalize() for p in sid.split('_'))
        sid_pat = re.compile(r'\b' + re.escape(sid) + r'\b')
        cls_pat = re.compile(
            r'class\s+Test\w*' + re.escape(sid_underscored) + r'\w*\b'
            r'|class\s+Test' + re.escape(sid_camel) + r'\w*\b'
        )

        for f, content in file_contents.items():
            basename = os.path.basename(f)
            sid_hits = len(sid_pat.findall(content))
            cls_hits = bool(cls_pat.search(content))

            if sid_hits:
                coverage[sid]['files_total'] += 1
                coverage[sid]['ref_count'] += sid_hits
                if len(coverage[sid]['sample_files']) < 3:
                    coverage[sid]['sample_files'].append(basename)
            if cls_hits:
                coverage[sid]['class_files'] += 1
                if len(coverage[sid]['sample_files']) < 3:
                    bn = basename
                    if bn not in coverage[sid]['sample_files']:
                        coverage[sid]['sample_files'].append(bn)

        # 严格命中: 排除 conftest, 排除 _yaml_driver 自身
        for f, content in file_contents.items():
            if 'conftest' in f or '_yaml_driver' in f:
                continue
            if re.search(r'\b' + re.escape(sid) + r'\b', content):
                coverage[sid]['files_strict'] += 1

    return dict(coverage)


# ============================================================
# 维度 3: factory 资产覆盖
# ============================================================

def collect_factory_coverage() -> Dict[str, Dict]:
    """factory 与 schema 的对应关系"""
    sys.path.insert(0, '.')
    from meta.tests._yaml_driver.loader import load_factories
    factories = load_factories()

    sys.path.insert(0, '.')
    from meta.tests._yaml_driver.loader import load_schemas
    objs = load_schemas()

    coverage = {}
    for sid in objs.keys():
        if sid in factories:
            info = factories[sid]
            coverage[sid] = {
                'has_factory': True,
                'class_name': info.get('class_name', ''),
                'defaults_count': len(info.get('defaults_keys', []) or []),
                'file': info.get('file', ''),
            }
        else:
            coverage[sid] = {
                'has_factory': False,
                'class_name': '',
                'defaults_count': 0,
                'file': '',
            }
    return coverage


# ============================================================
# 维度 4: RLS 规则覆盖
# ============================================================

def collect_rls_coverage() -> Dict[str, Dict]:
    """rls_rules 覆盖"""
    sys.path.insert(0, '.')
    from meta.tests._yaml_driver.loader import load_rls_rules
    rls = load_rls_rules()

    sys.path.insert(0, '.')
    from meta.tests._yaml_driver.loader import load_schemas
    objs = load_schemas()

    coverage = {}
    for sid, obj in objs.items():
        persistent = getattr(obj, 'persistent', True)
        if not persistent:
            coverage[sid] = {'has_rls': False, 'rls_file': '', 'persistent': False}
            continue
        if sid in rls:
            rls_cfg = rls[sid]
            coverage[sid] = {
                'has_rls': True,
                'rls_file': rls_cfg.get('file', ''),
                'rules_count': len(rls_cfg.get('rules', [])),
                'persistent': True,
            }
        else:
            coverage[sid] = {
                'has_rls': False,
                'rls_file': '',
                'rules_count': 0,
                'persistent': True,
            }
    return coverage


# ============================================================
# 维度 5: Aspects 覆盖
# ============================================================

def collect_aspect_coverage() -> Dict[str, Dict]:
    """每个 schema 引用了哪些 aspect (从 schema 自身的 aspects 字段读)"""
    sys.path.insert(0, '.')
    from meta.tests._yaml_driver.loader import load_schemas
    objs = load_schemas()

    coverage = {}
    for sid, obj in objs.items():
        # schema 自身的 aspects 字段 (e.g. "aspects: [audit_aspect, naming_aspect]")
        aspects_attr = getattr(obj, 'aspects', []) or []
        # 兼容 raw yaml 中可能用其他字段
        if not aspects_attr:
            # 尝试从 raw data 拿
            raw = getattr(obj, '_raw', {}) or {}
            aspects_attr = raw.get('aspects', []) or []

        coverage[sid] = {
            'aspects_applied': list(aspects_attr),
            'aspects_count': len(aspects_attr),
        }
    return coverage


# ============================================================
# 维度 6: 前端 (Vue) 覆盖
# ============================================================

def collect_frontend_coverage() -> Dict[str, Dict]:
    """前端 (src/**/__tests__/*) 引用 schema 情况"""
    import glob
    src_files = glob.glob('src/**/*', recursive=True) + glob.glob('frontend/**/*', recursive=True)
    src_files = [f for f in src_files if os.path.isfile(f)]

    sys.path.insert(0, '.')
    from meta.tests._yaml_driver.loader import load_schemas
    objs = load_schemas()

    # 收集所有 .vue / .ts / .js 文件内容
    fe_contents = {}
    for f in src_files:
        if not f.endswith(('.vue', '.ts', '.tsx', '.js', '.jsx')):
            continue
        try:
            with open(f, encoding='utf-8') as fh:
                fe_contents[f] = fh.read()
        except (UnicodeDecodeError, OSError):
            continue

    coverage = {}
    for sid in objs.keys():
        # schema_id / table_name / class 名 等多种匹配
        from meta.tests._yaml_driver.loader import load_schemas
        obj = objs[sid]
        table_name = getattr(obj, 'table_name', '') or ''

        matched_files = set()
        for f, content in fe_contents.items():
            if re.search(r'\b' + re.escape(sid) + r'\b', content):
                matched_files.add(f)
            elif table_name and re.search(r'\b' + re.escape(table_name) + r'\b', content):
                matched_files.add(f)

        coverage[sid] = {
            'files_count': len(matched_files),
            'sample': sorted(matched_files)[:2],
        }
    return coverage


# ============================================================
# 综合评分 & 风险等级
# ============================================================

@dataclass
class SchemaScore:
    schema_id: str
    yaml_auto_cases: int = 0          # 维度 1
    manual_test_files: int = 0         # 维度 2 (strict)
    manual_test_refs: int = 0          # 维度 2 (引用数)
    has_factory: bool = False          # 维度 3
    has_rls: bool = False              # 维度 4
    aspects_count: int = 0             # 维度 5
    frontend_files: int = 0            # 维度 6

    @property
    def score(self) -> int:
        """0-100 综合评分"""
        # yaml-driven: 30 分
        v1_part = min(30, self.yaml_auto_cases * 2)

        # 手写测试: 25 分
        manual_part = min(25, self.manual_test_files * 2 + (5 if self.manual_test_refs > 50 else 0))

        # factory: 15 分
        fac_part = 15 if self.has_factory else 0

        # RLS: 10 分 (持久化对象必须有)
        rls_part = 10 if self.has_rls else 0

        # aspects: 10 分
        asp_part = min(10, self.aspects_count * 3)

        # 前端: 10 分
        fe_part = min(10, self.frontend_files)

        return v1_part + manual_part + fac_part + rls_part + asp_part + fe_part

    @property
    def risk(self) -> str:
        if self.score >= 70:
            return 'LOW'
        elif self.score >= 40:
            return 'MEDIUM'
        return 'HIGH'

    @property
    def missing_dims(self) -> List[str]:
        miss = []
        if not self.has_factory:
            miss.append('factory')
        if not self.has_rls:
            miss.append('rls')
        if self.aspects_count == 0:
            miss.append('aspects')
        if self.frontend_files == 0:
            miss.append('frontend')
        if self.yaml_auto_cases == 0:
            miss.append('yaml-driven')
        if self.manual_test_files == 0:
            miss.append('manual-test')
        return miss


# ============================================================
# 报告
# ============================================================

def generate_report():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    print('[1/6] 收集 yaml-driven 覆盖...')
    yaml_cov = collect_yaml_driven_coverage()

    print('[2/6] 收集手写测试覆盖...')
    manual_cov = collect_manual_test_coverage(
        ['meta/tests/test_*.py', 'meta/tests/**/test_*.py']
    )

    print('[3/6] 收集 factory 覆盖...')
    fac_cov = collect_factory_coverage()

    print('[4/6] 收集 RLS 覆盖...')
    rls_cov = collect_rls_coverage()

    print('[5/6] 收集 Aspects 覆盖...')
    asp_cov = collect_aspect_coverage()

    print('[6/6] 收集前端覆盖...')
    fe_cov = collect_frontend_coverage()

    # 综合评分 (排除空 schema_id - 那些是 _expectations 等辅助 yaml)
    all_schemas = set(yaml_cov.keys()) | set(manual_cov.keys()) | set(fac_cov.keys())
    all_schemas = {sid for sid in all_schemas if sid and not sid.startswith('_')}
    scores = []
    for sid in all_schemas:
        s = SchemaScore(schema_id=sid)
        s.yaml_auto_cases = yaml_cov.get(sid, {}).get('total_auto', 0)
        s.manual_test_files = manual_cov.get(sid, {}).get('files_strict', 0)
        s.manual_test_refs = manual_cov.get(sid, {}).get('ref_count', 0)
        s.has_factory = fac_cov.get(sid, {}).get('has_factory', False)
        s.has_rls = rls_cov.get(sid, {}).get('has_rls', False)
        s.aspects_count = asp_cov.get(sid, {}).get('aspects_count', 0)
        s.frontend_files = fe_cov.get(sid, {}).get('files_count', 0)
        scores.append(s)

    scores.sort(key=lambda s: s.score)

    # 输出
    print()
    print('=' * 100)
    print('测试覆盖度深度分析 (6 维度综合评分)')
    print('=' * 100)
    print()
    print(f'  Schema 总数:        {len(scores)}')
    print(f'  HIGH 风险:         {sum(1 for s in scores if s.risk == "HIGH")}')
    print(f'  MEDIUM 风险:       {sum(1 for s in scores if s.risk == "MEDIUM")}')
    print(f'  LOW 风险:          {sum(1 for s in scores if s.risk == "LOW")}')
    print()

    # 分类统计
    print('=== 各维度覆盖统计 ===')
    dims = [
        ('yaml-driven (>=1 case)', sum(1 for s in scores if s.yaml_auto_cases > 0)),
        ('factory', sum(1 for s in scores if s.has_factory)),
        ('rls', sum(1 for s in scores if s.has_rls)),
        ('aspects (>=1)', sum(1 for s in scores if s.aspects_count > 0)),
        ('manual test (>=1 file)', sum(1 for s in scores if s.manual_test_files > 0)),
        ('frontend (>=1 file)', sum(1 for s in scores if s.frontend_files > 0)),
    ]
    for name, count in dims:
        print(f'  {name:30s}  {count:>3d} / {len(scores)}  ({count*100//len(scores):>3d}%)')
    print()

    # HIGH 风险列表
    high_risk = [s for s in scores if s.risk == 'HIGH']
    if high_risk:
        print('=== [!!!] HIGH 风险 schema (0-39 分) ===')
        for s in high_risk:
            miss = ', '.join(s.missing_dims) if s.missing_dims else '(all dims ok)'
            print(f'  {s.schema_id:30s} score={s.score:>3d}  missing=[{miss}]')
        print()

    # MEDIUM 风险列表
    medium_risk = [s for s in scores if s.risk == 'MEDIUM']
    if medium_risk:
        print('=== MEDIUM 风险 schema (40-69 分) ===')
        for s in medium_risk:
            miss = ', '.join(s.missing_dims) if s.missing_dims else '(all dims ok)'
            print(f'  {s.schema_id:30s} score={s.score:>3d}  missing=[{miss}]')
        print()

    # LOW 风险 (按 score 升序展示 top 20)
    low_risk = [s for s in scores if s.risk == 'LOW']
    print(f'=== LOW 风险 schema (>=70 分) — top 20 by score ===')
    for s in low_risk[:20]:
        print(f'  {s.schema_id:30s} score={s.score:>3d}  yaml={s.yaml_auto_cases:>2d}  manual={s.manual_test_files:>2d}  fac={int(s.has_factory)}  rls={int(s.has_rls)}  asp={s.aspects_count}  fe={s.frontend_files}')
    print()

    # 维度交叉分析: 哪些维度常同时缺失
    print('=== 维度共缺失分析 (P0 改进信号) ===')
    dim_pairs = defaultdict(int)
    for s in scores:
        miss = s.missing_dims
        for i, d1 in enumerate(miss):
            for d2 in miss[i+1:]:
                dim_pairs[tuple(sorted([d1, d2]))] += 1
    for (d1, d2), count in sorted(dim_pairs.items(), key=lambda x: -x[1])[:10]:
        print(f'  {d1:15s} + {d2:15s}  同时缺失: {count} 个 schema')
    print()

    # 写 JSON 报告
    out = {
        'generated_at': '2026-07-17',
        'total_schemas': len(scores),
        'risk_summary': {
            'high': sum(1 for s in scores if s.risk == 'HIGH'),
            'medium': sum(1 for s in scores if s.risk == 'MEDIUM'),
            'low': sum(1 for s in scores if s.risk == 'LOW'),
        },
        'dim_coverage': {
            name: count for name, count in dims
        },
        'schemas': [
            {
                'schema_id': s.schema_id,
                'score': s.score,
                'risk': s.risk,
                'yaml_auto_cases': s.yaml_auto_cases,
                'manual_test_files': s.manual_test_files,
                'manual_test_refs': s.manual_test_refs,
                'has_factory': s.has_factory,
                'has_rls': s.has_rls,
                'aspects_count': s.aspects_count,
                'frontend_files': s.frontend_files,
                'missing_dims': s.missing_dims,
            }
            for s in scores
        ],
    }

    out_path = Path('.trae/coverage/deep_coverage.json')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] JSON 报告: {out_path}')


if __name__ == '__main__':
    generate_report()