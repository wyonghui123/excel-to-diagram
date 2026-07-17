# -*- coding: utf-8 -*-
"""
discover_test_coverage.py
========================

分析每个 yaml schema 在 test_*.py 测试文件中的出现情况, 生成覆盖矩阵报告。

覆盖度判定 (3 个维度):
1. **schema-id 级**:  schema 名 (e.g. "user") 是否在测试文件中出现
2. **table-name 级**: table_name (e.g. "users") 是否在测试文件中出现
3. **class 级**:      Test 类名是否含 schema 名

每个维度独立统计, 综合判定:
- covered = 3 维全部命中
- partial = 1-2 维命中
- none    = 0 维命中

输出:
- 终端表格: 每个 schema 的覆盖度 + sample files
- Markdown: 完整覆盖报告
- JSON: 结构化数据 (供 CI / dashboard 消费)

使用方法:
    # 直接运行 (报告写到 .trae/coverage/)
    python meta/tests/_yaml_driver/discover_test_coverage.py

    # 仅 stdout
    python meta/tests/_yaml_driver/discover_test_coverage.py --stdout

    # 自定义 schema / test 目录
    python meta/tests/_yaml_driver/discover_test_coverage.py \
        --schema-dir meta/schemas \
        --test-pattern "meta/tests/test_*.py" "meta/tests/**/test_*.py"

集成到 v1.1:
    在 _yaml_driver 框架内, schema 缺失测试覆盖应被检测为 violation (但仅 tolerant mode)
"""
import argparse
import glob
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


# ============================================================
# Schema 资产加载 (复用 v1.1 loader)
# ============================================================

def load_schema_assets(schema_dir: str = 'meta/schemas') -> Dict[str, Dict]:
    """
    加载 schema 资产: {schema_id: {id, table_name, fields, file}}
    不依赖 yaml_loader (避免 pyc 缓存和 side-effect)
    """
    import yaml
    schemas = {}
    for f in sorted(Path(schema_dir).glob('*.yaml')):
        try:
            with open(f, encoding='utf-8') as fh:
                data = yaml.safe_load(fh)
        except Exception as e:
            print(f'[WARN] 跳过 {f}: {e}', file=sys.stderr)
            continue
        if not data:
            continue
        # 处理嵌套结构 (如 {schema_id: {...}}) 或 顶层 schema
        if isinstance(data, dict):
            if 'id' in data:
                schema_id = data['id']
                schemas[schema_id] = {
                    'id': schema_id,
                    'table_name': data.get('table_name', ''),
                    'file': str(f),
                    'fields': [fd.get('id', '') for fd in data.get('fields', []) if fd.get('id')],
                }
            else:
                # 嵌套 dict: {schema_id: {schema_body}}
                for sid, body in data.items():
                    if not isinstance(body, dict):
                        continue
                    if 'id' in body or 'fields' in body:
                        schemas[sid] = {
                            'id': sid,
                            'table_name': body.get('table_name', ''),
                            'file': str(f),
                            'fields': [fd.get('id', '') for fd in body.get('fields', []) if fd.get('id')],
                        }
    return schemas


# ============================================================
# 测试文件分析
# ============================================================

@dataclass
class TestFileCoverage:
    """单个 schema 在所有测试文件中的覆盖统计"""
    schema_id: str
    table_name: str = ''
    file: str = ''

    # 维度 1: schema_id 出现
    schema_id_files: Set[str] = field(default_factory=set)
    schema_id_refs: int = 0

    # 维度 2: table_name 出现
    table_name_files: Set[str] = field(default_factory=set)
    table_name_refs: int = 0

    # 维度 3: 类名含 schema_id
    class_files: Set[str] = field(default_factory=set)

    @property
    def total_files(self) -> Set[str]:
        return self.schema_id_files | self.table_name_files | self.class_files

    @property
    def coverage_level(self) -> str:
        n = sum([
            bool(self.schema_id_files),
            bool(self.table_name_files),
            bool(self.class_files),
        ])
        if n == 0:
            return 'none'
        elif n == 3:
            return 'covered'
        return 'partial'

    @property
    def sample_files(self) -> List[str]:
        return sorted(self.total_files)[:5]


def collect_test_files(patterns: List[str]) -> List[str]:
    """收集所有 test_*.py"""
    files = set()
    for p in patterns:
        files.update(glob.glob(p, recursive=True))
    return sorted(files)


def analyze_test_file(path: str) -> Tuple[Set[str], Dict[str, Set[str]], Dict[str, int]]:
    """
    分析单个测试文件, 返回:
    - 该文件出现的所有 schema_id (集合)
    - {schema_id: 出现行号 set} (用于详细报告)
    - {schema_id: ref_count}
    """
    try:
        with open(path, encoding='utf-8') as f:
            src = f.read()
    except (UnicodeDecodeError, OSError):
        return set(), {}, {}

    schema_ids = set()
    ref_counts = {}

    # 1. 提取类名 (Test{SchemaName}...)
    classes = set(re.findall(r'class\s+(Test\w+)\b', src))

    # 2. 提取字符串字面量中的 schema_id 候选
    string_literals = set(re.findall(r'[\'\"]([a-z_][a-z_0-9]*)[\'\"]', src))

    # 3. 提取路径 (/api/v2/bo/{type})
    api_paths = set(re.findall(r'/api/v\d+/bo/([a-z_][a-z_0-9]*)', src))

    # 4. 合并所有候选
    candidates = string_literals | api_paths
    for c in classes:
        # TestUserAuth -> user
        m = re.search(r'Test(\w+)', c)
        if m:
            name = m.group(1)
            # 尝试拆分驼峰
            parts = re.findall(r'[A-Z][a-z]+', name)
            candidates.update(p.lower() for p in parts)
            candidates.add(name.lower())

    return candidates, {}, ref_counts


def compute_coverage(
    schemas: Dict[str, Dict],
    test_files: List[str],
) -> Dict[str, TestFileCoverage]:
    """计算每个 schema 的覆盖统计"""
    # 预加载所有测试文件内容
    file_contents = {}
    for tf in test_files:
        try:
            with open(tf, encoding='utf-8') as fh:
                file_contents[tf] = fh.read()
        except (UnicodeDecodeError, OSError):
            continue

    coverages = {}
    for sid, info in schemas.items():
        cov = TestFileCoverage(
            schema_id=sid,
            table_name=info.get('table_name', ''),
            file=info.get('file', ''),
        )

        # 维度 1: schema_id 严格匹配
        sid_pattern = re.compile(r'\b' + re.escape(sid) + r'\b')
        for tf, content in file_contents.items():
            matches = sid_pattern.findall(content)
            if matches:
                cov.schema_id_files.add(tf)
                cov.schema_id_refs += len(matches)

        # 维度 2: table_name 严格匹配
        if cov.table_name:
            tn_pattern = re.compile(r'\b' + re.escape(cov.table_name) + r'\b')
            for tf, content in file_contents.items():
                matches = tn_pattern.findall(content)
                if matches:
                    cov.table_name_files.add(tf)
                    cov.table_name_refs += len(matches)

        # 维度 3: 类名含 schema_id
        # 匹配 TestXxxYyy (含 sid 子串) 或 Test{sid_camel}
        sid_underscored = sid.replace('_', '')
        sid_camel = ''.join(p.capitalize() for p in sid.split('_'))
        class_pattern = re.compile(
            r'class\s+Test(\w*' + re.escape(sid_underscored) + r'\w*)\b'
            r'|class\s+Test(' + re.escape(sid_camel) + r'\w*)\b'
        )
        for tf, content in file_contents.items():
            if class_pattern.search(content):
                cov.class_files.add(tf)

        coverages[sid] = cov

    return coverages


# ============================================================
# 报告输出
# ============================================================

def print_terminal_report(coverages: Dict[str, TestFileCoverage]) -> None:
    """打印终端表格"""
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    none_schemas = []
    partial_schemas = []
    covered_schemas = []

    for sid, cov in coverages.items():
        if cov.coverage_level == 'none':
            none_schemas.append(cov)
        elif cov.coverage_level == 'partial':
            partial_schemas.append(cov)
        else:
            covered_schemas.append(cov)

    print()
    print('=' * 100)
    print(f'测试覆盖矩阵报告 (生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")})')
    print('=' * 100)
    print(f'  Schema 总数:  {len(coverages)}')
    print(f'  完全覆盖:      {len(covered_schemas)} ({len(covered_schemas)*100//max(len(coverages),1)}%)')
    print(f'  部分覆盖:      {len(partial_schemas)} ({len(partial_schemas)*100//max(len(coverages),1)}%)')
    print(f'  无覆盖:        {len(none_schemas)} ({len(none_schemas)*100//max(len(coverages),1)}%)')
    print()

    if none_schemas:
        print('--- [!!!] 无测试覆盖的 schema (HIGH PRIORITY) ---')
        for cov in sorted(none_schemas, key=lambda c: c.schema_id):
            print(f'  [NONE] {cov.schema_id:30s} table={cov.table_name:25s} file={Path(cov.file).name}')
        print()

    if partial_schemas:
        print('--- 部分覆盖的 schema (MEDIUM PRIORITY) ---')
        for cov in sorted(partial_schemas, key=lambda c: c.schema_id):
            dim = []
            if cov.schema_id_files: dim.append(f'id({len(cov.schema_id_files)})')
            if cov.table_name_files: dim.append(f'table({len(cov.table_name_files)})')
            if cov.class_files: dim.append(f'class({len(cov.class_files)})')
            print(f'  [PARTIAL] {cov.schema_id:30s} {"+".join(dim):30s} samples={[Path(f).name for f in cov.sample_files[:2]]}')
        print()

    if covered_schemas:
        print('--- 完全覆盖的 schema (LOW PRIORITY) ---')
        for cov in sorted(covered_schemas, key=lambda c: -len(c.total_files))[:15]:
            print(f'  [OK] {cov.schema_id:30s} files={len(cov.total_files):>3d} refs={cov.schema_id_refs:>4d}')
        if len(covered_schemas) > 15:
            print(f'  ... ({len(covered_schemas)-15} more)')
        print()


def write_markdown_report(coverages: Dict[str, TestFileCoverage], path: str) -> None:
    """写 Markdown 报告"""
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    none = [c for c in coverages.values() if c.coverage_level == 'none']
    partial = [c for c in coverages.values() if c.coverage_level == 'partial']
    covered = [c for c in coverages.values() if c.coverage_level == 'covered']

    md = []
    md.append('# Schema → 测试覆盖矩阵报告\n')
    md.append(f'**生成时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}  ')
    md.append(f'**Schema 总数**: {len(coverages)}\n')

    md.append('## 摘要\n')
    md.append('| 覆盖度 | 数量 | 占比 |')
    md.append('|---|---|---|')
    md.append(f'| 完全覆盖 (3 维) | {len(covered)} | {len(covered)*100//max(len(coverages),1)}% |')
    md.append(f'| 部分覆盖 (1-2 维) | {len(partial)} | {len(partial)*100//max(len(coverages),1)}% |')
    md.append(f'| 无覆盖 (0 维) | {len(none)} | {len(none)*100//max(len(coverages),1)}% |\n')

    if none:
        md.append('## [!!!] 无测试覆盖的 schema\n')
        md.append('这些 schema 在所有 test_*.py 文件中均未出现, 意味着修改 yaml 不会触发任何测试失败。\n')
        md.append('| schema | table | yaml 文件 |')
        md.append('|---|---|---|')
        for cov in sorted(none, key=lambda c: c.schema_id):
            md.append(f'| `{cov.schema_id}` | `{cov.table_name}` | `{Path(cov.file).name}` |')
        md.append('')

    if partial:
        md.append('## 部分覆盖的 schema\n')
        md.append('| schema | id 命中 | table 命中 | class 命中 | sample files |')
        md.append('|---|---|---|---|---|')
        for cov in sorted(partial, key=lambda c: c.schema_id):
            id_n = len(cov.schema_id_files)
            tn_n = len(cov.table_name_files)
            cl_n = len(cov.class_files)
            samples = ', '.join(Path(f).name for f in cov.sample_files[:2])
            md.append(f'| `{cov.schema_id}` | {id_n} | {tn_n} | {cl_n} | {samples} |')
        md.append('')

    if covered:
        md.append('## 完全覆盖的 schema\n')
        md.append('| schema | 测试文件数 | 引用次数 |')
        md.append('|---|---|---|')
        for cov in sorted(covered, key=lambda c: -len(c.total_files)):
            md.append(f'| `{cov.schema_id}` | {len(cov.total_files)} | {cov.schema_id_refs} |')
        md.append('')

    md.append('## 维度说明\n')
    md.append('**id 命中**: schema_id (e.g. `user`) 出现在测试文件中 (字符串字面量或路径)  ')
    md.append('**table 命中**: table_name (e.g. `users`) 出现在测试文件中  ')
    md.append('**class 命中**: 测试类名 `Test{SchemaIdCamel}` 出现\n')

    md.append('## 改进建议\n')
    if none:
        md.append('- **P0**: 为无覆盖 schema 至少补 1 个 schema-id 级测试, 防止静默回归')
    if partial:
        md.append('- **P1**: 部分覆盖 schema 补齐缺失维度, 提升 schema-id ↔ test 关联性')
    md.append('- **P2**: 长期监控, 集成到 CI, 新增 schema 必须有至少 1 个 schema-id 级测试\n')

    Path(path).write_text('\n'.join(md), encoding='utf-8')
    print(f'[OK] Markdown 报告: {path}')


def write_json_report(coverages: Dict[str, TestFileCoverage], path: str) -> None:
    """写 JSON 报告 (供 CI / dashboard)"""
    data = {
        'generated_at': datetime.now().isoformat(),
        'total': len(coverages),
        'covered': len([c for c in coverages.values() if c.coverage_level == 'covered']),
        'partial': len([c for c in coverages.values() if c.coverage_level == 'partial']),
        'none': len([c for c in coverages.values() if c.coverage_level == 'none']),
        'schemas': {},
    }
    for sid, cov in coverages.items():
        data['schemas'][sid] = {
            'schema_id': cov.schema_id,
            'table_name': cov.table_name,
            'file': cov.file,
            'coverage_level': cov.coverage_level,
            'schema_id_files': len(cov.schema_id_files),
            'schema_id_refs': cov.schema_id_refs,
            'table_name_files': len(cov.table_name_files),
            'table_name_refs': cov.table_name_refs,
            'class_files': len(cov.class_files),
            'sample_files': cov.sample_files,
        }
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] JSON 报告: {path}')


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='分析 yaml schema 在 test_*.py 中的覆盖情况',
    )
    parser.add_argument(
        '--schema-dir', default='meta/schemas',
        help='yaml schema 目录 (默认 meta/schemas)',
    )
    parser.add_argument(
        '--test-pattern', nargs='+',
        default=['meta/tests/test_*.py', 'meta/tests/**/test_*.py'],
        help='test_*.py 文件 glob 模式 (支持多个)',
    )
    parser.add_argument(
        '--output-dir', default='.trae/coverage',
        help='报告输出目录 (默认 .trae/coverage)',
    )
    parser.add_argument(
        '--stdout', action='store_true',
        help='仅打印到 stdout, 不写文件',
    )
    parser.add_argument(
        '--fail-on-none', action='store_true',
        help='当存在无覆盖 schema 时, exit code = 1',
    )
    args = parser.parse_args()

    # 1. 加载 schema
    print(f'[INFO] 加载 schema: {args.schema_dir}')
    schemas = load_schema_assets(args.schema_dir)
    print(f'[INFO]   找到 {len(schemas)} 个 schema')

    # 2. 收集 test 文件
    print(f'[INFO] 扫描测试文件...')
    test_files = collect_test_files(args.test_pattern)
    print(f'[INFO]   找到 {len(test_files)} 个 test_*.py')

    # 3. 计算覆盖
    print(f'[INFO] 计算覆盖矩阵...')
    coverages = compute_coverage(schemas, test_files)

    # 4. 输出
    print_terminal_report(coverages)

    if not args.stdout:
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        write_markdown_report(coverages, str(out_dir / 'test_coverage.md'))
        write_json_report(coverages, str(out_dir / 'test_coverage.json'))

    # 5. 退出码
    none_count = sum(1 for c in coverages.values() if c.coverage_level == 'none')
    if args.fail_on_none and none_count > 0:
        print(f'\n[FAIL] {none_count} 个 schema 无测试覆盖, exit 1')
        sys.exit(1)
    print(f'\n[DONE] 退出')


if __name__ == '__main__':
    main()