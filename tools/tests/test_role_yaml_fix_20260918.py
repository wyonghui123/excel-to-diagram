"""[2026-09-18] 验证 role.yaml 修复: 没有 user_group 漏改, yaml 可解析."""
import sys, yaml
from pathlib import Path

p = Path(r'D:\filework\excel-to-diagram\meta\schemas\role.yaml')
text = p.read_text(encoding='utf-8')

# 1. yaml 可解析
doc = yaml.safe_load(text)
assert isinstance(doc, dict), f"role.yaml parse failed: {type(doc)}"
print("[OK] role.yaml yaml.safe_load 解析成功")

# 2. 不应再有 user_group / group_roles 字符串引用 (除了注释中 "已 drop" 提及)
# 只检查 active yaml content (key/value), 不检查注释
def check_no_user_group_in_active_yaml(d, path=""):
    if isinstance(d, dict):
        for k, v in d.items():
            check_no_user_group_in_active_yaml(v, f"{path}.{k}")
    elif isinstance(d, list):
        for i, v in enumerate(d):
            check_no_user_group_in_active_yaml(v, f"{path}[{i}]")
    elif isinstance(d, str):
        # active yaml value: 不应等于 'user_group' / 'group_roles'
        if d in ('user_group', 'group_roles'):
            raise AssertionError(f"Active yaml still has '{d}' at {path}")

check_no_user_group_in_active_yaml(doc)
print("[OK] role.yaml active yaml 中没有 user_group / group_roles")

# 3. associations 块不再有 assigned_groups / assigned_orgs 激活定义
# [FIX] associations 是 dict 不是 list (yaml 格式: associations: { permissions: {...}, ... })
assocs = doc.get('associations') or {}
assert isinstance(assocs, dict), f"associations 应是 dict, 实际 {type(assocs)}"
active_names = list(assocs.keys())
print(f"[INFO] active associations keys: {active_names}")
assert 'assigned_groups' not in active_names, f"assigned_groups 还在! keys={active_names}"
assert 'assigned_orgs' not in active_names, f"assigned_orgs 还在 (应被注释)! keys={active_names}"
print("[OK] 没有激活的 assigned_groups / assigned_orgs 关联")

# 4. permissions 关联仍正常
perms = assocs.get('permissions')
assert perms, f"permissions 关联丢失! assocs={list(assocs.keys())}"
print(f"[OK] permissions 关联仍存在: target={perms.get('target_entity')}, through={perms.get('through')}")

print("\n[PASS] role.yaml 修复验证通过")