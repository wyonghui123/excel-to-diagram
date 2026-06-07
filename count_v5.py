"""Count lines of all refactored test files - final round v3."""
from pathlib import Path

files = [
    'test_agent_api.py',
    'test_filter_variant_api.py',
    'test_value_help_api.py',
    'test_annotation_routes_api.py',
    'test_data_permission_api.py',
    'test_object_identity_api.py',
    'test_query_api.py',
    'test_permission_rule_api.py',
    'test_owner_transfer_api.py',
    'test_export_import_api.py',
    'test_task_api.py',
    'test_user_group_api.py',
]

# Original v1 (raw from initial creation)
v1 = {
    'test_agent_api.py': 72,
    'test_filter_variant_api.py': 58,
    'test_value_help_api.py': 51,
    'test_annotation_routes_api.py': 67,
    'test_data_permission_api.py': 101,
    'test_object_identity_api.py': 74,
    'test_query_api.py': 82,
    'test_permission_rule_api.py': 85,
    'test_owner_transfer_api.py': 64,
    'test_export_import_api.py': 89,
    'test_task_api.py': 42,
    'test_user_group_api.py': 101,
}

t1 = t2 = t3 = 0
print(f"  {'file':45s} {'v1':>5s} {'now':>5s} {'Δ':>6s}")
print(f"  {'-'*65}")
for f in files:
    p = Path('meta/tests') / f
    if p.exists():
        lines = len(p.read_text(encoding='utf-8', errors='ignore').splitlines())
        o = v1.get(f, 0)
        delta = lines - o
        t1 += o
        t2 += lines
        marker = '↑' if delta > 0 else '↓' if delta < 0 else '='
        print(f"  {f:45s} {o:5d} {lines:5d} {delta:+5d} {marker}")
print(f"  {'-'*65}")
print(f"  {'TOTAL':45s} {t1:5d} {t2:5d} {t2-t1:+5d} ({(t2-t1)*100/t1:+.1f}%)")
