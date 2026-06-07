# -*- coding: utf-8 -*-
"""检查关联/value-help/permission 相关 spec 的真实覆盖度"""
import re
from pathlib import Path

specs = [
    'value-help-filter.spec.js',
    'value-help-dialog.spec.js',
    'ValueHelp-5-layer-link.spec.js',
    'relation-scope-field.spec.js',
    'relation-scope-tree.spec.js',
    'menu-bo-linker.spec.js',
    'role-permission-center.spec.js',
    'permission-explainer.spec.js',
    'data-permission-config.spec.js',
    'user-permission.spec.js',
    'role-intents.spec.js',
    'intent-apis.spec.js',
    'user-role.spec.js',
    'data-permission-config.spec.js',
    'overlap-warning.spec.js',
    'condition-rule-dialog.spec.js',
]

print(f"{'Spec':52s} {'tests':>6s} {'desc':>4s} {'v1':>3s} {'v2':>3s} {'soft':>4s} {'skip':>4s}")
print("-" * 100)
for s in specs:
    p = Path('e2e/features') / s
    if not p.exists():
        print(f"{s:52s} NOT FOUND")
        continue
    c = p.read_text(encoding='utf-8', errors='ignore')
    tests = len(re.findall(r"^\s*test\(", c, re.MULTILINE))
    descs = len(re.findall(r"test\.describe\(", c))
    v1 = 'login(' in c and 'setAdminPermissions(' in c
    v2 = 'auto-fixtures.js' in c
    soft = 'WARN' in c or '软失败' in c
    skip = 'test.skip(' in c
    print(f"{s:52s} {tests:6d} {descs:4d} {str(v1):>3s} {str(v2):>3s} {str(soft):>4s} {str(skip):>4s}")

# 关联 C/D 操作
print()
print("=" * 60)
print("检查 association C/D (add/remove/batch) 关键词:")
print("=" * 60)
for s in specs:
    p = Path('e2e/features') / s
    if not p.exists():
        continue
    c = p.read_text(encoding='utf-8', errors='ignore').lower()
    for kw in ['add association', 'remove association', 'batch add', 'batch delete',
               'association add', 'association remove', 'm2m add', 'm2m remove',
               'add.', 'remove.']:
        if kw in c:
            print(f"  {s}: 含 '{kw}'")
            break
