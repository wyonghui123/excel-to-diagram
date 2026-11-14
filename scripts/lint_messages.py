# -*- coding: utf-8 -*-
"""文案注册表 lint（spec-error-warning-framework FR-006）。

检查项：
  H1 代码引用但未注册的 key；
  H2 zh_CN / en_US key 集合不一致；
  H3 守卫文件中的硬编码中文业务文案（``message='...'``）；
  L1 已注册但未被静态引用的 key（warning）。

用法::

    python scripts/lint_messages.py --max-detail 10
    python scripts/lint_messages.py --fail-on none --json

退出码：0 = 无 high 问题；1 = 存在 high 问题（H1/H2/H3）。
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from meta.core.message_registry import DEFAULT_LOCALE, MessageRegistry  # noqa: E402

SKIP_DIRS = {'tests', 'test_temp', '__pycache__', 'node_modules', '.git',
             '.venv', 'venv', 'dist', 'build', 'coverage'}
REF_RE = re.compile(
    r"""(?:\bt|\bMessageRegistry\.(?:get|t)|"""
    r"""\bValidationMessageRegistry\.get)\s*\(\s*['"]([A-Za-z0-9_.\-]+)['"]"""
)
HARDCODED_RE = re.compile(r"""message\s*=\s*['"][^'"]*[\u4e00-\u9fff]""")
GUARD_FILES = [
    ROOT / 'meta' / 'core' / 'constraint_engine.py',
    ROOT / 'meta' / 'core' / 'metadata_driven_validator.py',
    ROOT / 'meta' / 'core' / 'interceptors' / 'attribute_guard_interceptor.py',
]


def iter_py_files():
    stack = [ROOT / 'meta']
    while stack:
        current = stack.pop()
        for entry in sorted(current.iterdir()):
            if entry.is_dir():
                if entry.name not in SKIP_DIRS:
                    stack.append(entry)
            elif entry.suffix == '.py':
                yield entry


def collect_references():
    referenced = set()
    dynamic_prefixes = set()
    hardcoded = []
    for path in iter_py_files():
        if path.name == 'message_registry.py':
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        for match in REF_RE.finditer(text):
            referenced.add(match.group(1))
        # f-string 动态拼接：validation.attribute.{rule}
        for prefix in re.findall(r"['\"]([A-Za-z0-9_.\-]+)\.\{", text):
            dynamic_prefixes.add(prefix)
    for path in GUARD_FILES:
        if not path.exists():
            continue
        for lineno, line in enumerate(
                path.read_text(encoding='utf-8').splitlines(), 1):
            if HARDCODED_RE.search(line) and 'logger.' not in line:
                hardcoded.append(f'{path.relative_to(ROOT)}:{lineno}: {line.strip()}')
    return referenced, dynamic_prefixes, hardcoded


def main() -> int:
    parser = argparse.ArgumentParser(description='文案注册表 lint')
    parser.add_argument('--json', action='store_true', help='输出 JSON')
    parser.add_argument('--max-detail', type=int, default=10,
                        help='每类问题最多展示条数（0=全部）')
    parser.add_argument('--fail-on', choices=['high', 'any', 'none'],
                        default='high')
    args = parser.parse_args()

    zh = MessageRegistry.keys(DEFAULT_LOCALE)
    en = MessageRegistry.keys('en_US')
    referenced, dynamic_prefixes, hardcoded = collect_references()

    missing_en = sorted(zh - en)
    unmatched = sorted(referenced - zh)
    unused = sorted(zh - referenced - {
        key for key in zh
        if any(key.startswith(prefix + '.') for prefix in dynamic_prefixes)
    })

    issues = []
    for key in unmatched:
        issues.append({'id': 'H1', 'key': key,
                       'message': '代码引用了未注册的文案 key'})
    for key in missing_en:
        issues.append({'id': 'H2', 'key': key,
                       'message': 'zh_CN 有该 key，en_US 缺失'})
    for line in hardcoded:
        issues.append({'id': 'H3', 'key': line,
                       'message': '守卫文件存在硬编码中文业务文案'})
    for key in unused:
        issues.append({'id': 'L1', 'key': key,
                       'message': '已注册但未被静态引用'})

    high = [i for i in issues if i['id'].startswith('H')]
    low = [i for i in issues if i['id'].startswith('L')]

    if args.json:
        print(json.dumps({
            'zh_keys': len(zh), 'en_keys': len(en),
            'missing_en': missing_en, 'unmatched': unmatched,
            'hardcoded': hardcoded, 'unused': unused,
        }, ensure_ascii=False, indent=2))
    else:
        limit = args.max_detail or None
        print(f'文案 key：zh_CN={len(zh)} en_US={len(en)} '
              f'动态前缀={len(dynamic_prefixes)}')
        for group, items in (('high', high), ('low', low)):
            for item in (items[:limit] if limit else items):
                print(f"[{item['id']}] {item['key']}: {item['message']}")
            if limit and len(items) > limit:
                print(f'... 其余 {len(items) - limit} 条已省略')
        print(f'high={len(high)} low={len(low)}')

    if args.fail_on == 'none':
        return 0
    if args.fail_on == 'any':
        return 1 if issues else 0
    return 1 if high else 0


if __name__ == '__main__':
    sys.exit(main())