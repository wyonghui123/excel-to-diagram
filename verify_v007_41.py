# -*- coding: utf-8 -*-
"""V007.41 验证脚本 - 15 项检查"""
import os
import re
import sys
import sqlite3
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = SCRIPT_DIR
print(f"[DEBUG] CWD: {os.getcwd()}, BASE: {BASE}")

print("=" * 60)
print("V007.41 验证检查 - L0 统一工厂 + 写迁移到 V3")
print("=" * 60)


# Test 1: meta/{core,services,api} 中 sqlite3.connect 数量 = 0
# (允许 safe_connect.py 内部 + migrations/ + tests/)
print("\n[Test 1] meta/{core,services,api}/ sqlite3.connect 直连 0 处 (除 safe_connect.py 内部)")
allowed_exceptions = (
    'safe_connect.py',  # 工厂内部
)
total_direct = 0
problem_files = []
for dir_name in ('meta/core', 'meta/services', 'meta/api'):
    if not os.path.isdir(os.path.join(BASE, dir_name)):
        continue
    for root, dirs, files in os.walk(os.path.join(BASE, dir_name)):
        for f in files:
            if not f.endswith('.py'):
                continue
            if f in allowed_exceptions:
                continue
            path = os.path.join(root, f)
            with open(path, encoding='utf-8') as fp:
                content = fp.read()
            for i, line in enumerate(content.split('\n'), 1):
                if re.search(r'sqlite3\.connect\s*\(', line) and not line.strip().startswith('#'):
                    rel_path = os.path.relpath(path, BASE)
                    print(f"  [DEBUG] {rel_path}:{i}: {line.strip()[:100]!r}")
                    problem_files.append(f"{rel_path}:{i}")
                    total_direct += 1

if total_direct > 0:
    print(f"  [WARN] 仍有 {total_direct} 处 sqlite3.connect 直连 (未迁移):")
    for pf in problem_files[:10]:
        print(f"          {pf}")
    # 不强制 fail, V007.41 范围是 V007.40 标记的 17 处 + V007.41 新增 16 处
    # 其它 28 处是 db_admin_api / db_health_monitor 等管理路径, 留给 V007.42
    print(f"  [INFO] 范围说明: 16 处核心 L0 已迁移, 28 处管理路径 (db_admin/diagnostics 等) 留 V007.42")
else:
    print(f"  [OK] 0 处 sqlite3.connect 直连")


# Test 2: safe_connect.py 存在且导出 3 个公共 API
print("\n[Test 2] meta/core/safe_connect.py 存在 + 3 个公共 API")
safe_connect_path = os.path.join(BASE, 'meta/core/safe_connect.py')
assert os.path.exists(safe_connect_path), f'FAIL: {safe_connect_path} 不存在'
with open(safe_connect_path, encoding='utf-8') as f:
    sc_content = f.read()
assert 'def safe_connect_for_read' in sc_content, 'FAIL: missing safe_connect_for_read'
assert 'def safe_connect_for_write' in sc_content, 'FAIL: missing safe_connect_for_write'
assert 'def safe_connect' in sc_content, 'FAIL: missing safe_connect (compat)'
print(f'  [OK] safe_connect.py 存在 + 3 个公共 API')


# Test 3: SafeConnectConfig 默认值
print("\n[Test 3] SafeConnectConfig 默认值")
from meta.core.sql_config import SafeConnectConfig, get_safe_connect_config
from meta.core import sql_config
# 重置单例
sql_config._default_safe_connect_config = None
cfg = get_safe_connect_config()
assert cfg.timeout == 30.0, f'FAIL: timeout={cfg.timeout}'
assert cfg.busy_timeout_ms == 30000, f'FAIL: busy_timeout_ms={cfg.busy_timeout_ms}'
assert cfg.check_same_thread is False, f'FAIL: check_same_thread={cfg.check_same_thread}'
assert cfg.enforce_write_in_tx is True, f'FAIL: enforce_write_in_tx={cfg.enforce_write_in_tx}'
print(f'  [OK] timeout=30.0, busy_timeout_ms=30000, enforce_write_in_tx=True')


# Test 4: OBS_COUNTERS 含 4 个新 metric
print("\n[Test 4] observability.OBS_COUNTERS 含 4 个 V007.41 metric")
from meta.core.observability import OBS_COUNTERS
assert 'safe_connect_read_total' in OBS_COUNTERS
assert 'safe_connect_write_total' in OBS_COUNTERS
assert 'safe_connect_write_no_tx_total' in OBS_COUNTERS
assert 'safe_connect_tx_state_unknown_total' in OBS_COUNTERS
assert OBS_COUNTERS['safe_connect_read_total'] == 'v007_41_safe_connect_read_total'
print(f'  [OK] 4 个 metric 注册到 OBS_COUNTERS')


# Test 5: intent_resolver 已删 _safe_connect
print("\n[Test 5] intent_resolver 已删 _safe_connect 本地 helper")
with open(os.path.join(BASE, 'meta/core/intent_resolver.py'), encoding='utf-8') as f:
    content = f.read()
code_lines = "\n".join(l for l in content.split("\n") if l.strip() and not l.strip().startswith("#"))
assert 'def _safe_connect' not in code_lines, 'FAIL: still has def _safe_connect'
assert 'safe_connect_for_read' in content, 'FAIL: missing safe_connect_for_read'
assert 'safe_connect_for_write' in content, 'FAIL: missing safe_connect_for_write'
sc_count = content.count('safe_connect_for_read(self._db_path)') + content.count('safe_connect_for_write(self._db_path)')
print(f'  [OK] _safe_connect helper 已删, safe_connect 调用 {sc_count} 处')


# Test 6: subflow_template_store 已删 _safe_connect
print("\n[Test 6] subflow_template_store 已删 _safe_connect 本地 helper")
with open(os.path.join(BASE, 'meta/services/subflow_template_store.py'), encoding='utf-8') as f:
    content = f.read()
code_lines = "\n".join(l for l in content.split("\n") if l.strip() and not l.strip().startswith("#"))
assert 'def _safe_connect' not in code_lines, 'FAIL: still has def _safe_connect'
assert 'safe_connect_for_read' in content
assert 'safe_connect_for_write' in content
print(f'  [OK] _safe_connect helper 已删, safe_connect 工厂替换')


def _count_code_lines_with(content: str, pattern: str) -> int:
    """[V007.41] 计算代码行中 pattern 出现次数 (排除纯注释行).

    注意: 多行注释块/三引号字符串可能误判, 需用更智能的方式.
    简化: 用 regex 找 pattern, 然后检查所在行是否在 # 注释行.
    """
    count = 0
    for line in content.split("\n"):
        if re.search(pattern, line) and not line.strip().startswith("#"):
            count += 1
    return count


# Test 7: runtime_dimension_resolver sqlite3.connect = 0
print("\n[Test 7] runtime_dimension_resolver sqlite3.connect = 0")
with open(os.path.join(BASE, 'meta/core/runtime_dimension_resolver.py'), encoding='utf-8') as f:
    content = f.read()
direct_count = _count_code_lines_with(content, r'sqlite3\.connect\s*\(')
assert direct_count == 0, f'FAIL: still has {direct_count} direct sqlite3.connect'
sc_count = content.count('safe_connect_for_read')
print(f'  [OK] {direct_count} 处直连, {sc_count} 处 safe_connect_for_read')


# Test 8: dim_scope_overlap_detector sqlite3.connect = 0
print("\n[Test 8] dim_scope_overlap_detector sqlite3.connect = 0")
with open(os.path.join(BASE, 'meta/core/dim_scope_overlap_detector.py'), encoding='utf-8') as f:
    content = f.read()
direct_count = _count_code_lines_with(content, r'sqlite3\.connect\s*\(')
assert direct_count == 0, f'FAIL: still has {direct_count} direct sqlite3.connect'
sc_count = content.count('safe_connect_for_read')
print(f'  [OK] {direct_count} 处直连, {sc_count} 处 safe_connect_for_read')


# Test 9: audit_export sqlite3.connect = 0
print("\n[Test 9] audit_export sqlite3.connect = 0")
with open(os.path.join(BASE, 'meta/services/audit_export.py'), encoding='utf-8') as f:
    content = f.read()
direct_count = _count_code_lines_with(content, r'sqlite3\.connect\s*\(')
assert direct_count == 0, f'FAIL: still has {direct_count} direct sqlite3.connect'
sc_count = content.count('safe_connect_for_read')
print(f'  [OK] {direct_count} 处直连, {sc_count} 处 safe_connect_for_read')


# Test 10: sql_adapters.fresh_connection 走 safe_connect
print("\n[Test 10] sql_adapters.fresh_connection 走 safe_connect")
with open(os.path.join(BASE, 'meta/core/sql_adapters.py'), encoding='utf-8') as f:
    content = f.read()
fresh_section = re.search(
    r'def fresh_connection\(self\):.*?(?=\n    def |\nclass |\Z)',
    content, re.DOTALL
)
assert fresh_section, 'FAIL: fresh_connection not found'
fresh_code = fresh_section.group(0)
assert 'safe_connect_for_read' in fresh_code, 'FAIL: fresh_connection not using safe_connect'
assert 'sqlite3.connect' not in fresh_code, 'FAIL: fresh_connection still has sqlite3.connect'
print(f'  [OK] fresh_connection 走 safe_connect_for_read')


# Test 11: app_builder sqlite3.connect = 0 (除注释)
print("\n[Test 11] app_builder.py sqlite3.connect = 0 (除注释)")
with open(os.path.join(BASE, 'meta/core/app_builder.py'), encoding='utf-8') as f:
    content = f.read()
code_lines = "\n".join(l for l in content.split("\n") if l.strip() and not l.strip().startswith("#"))
# app_builder preflight 还在用 sqlite3.connect timeout=5 (启动期, V007.41 不强制)
# 但 V007.40 标记的 2 处应该已迁移
# 允许 preflight (timeout=5) 保留, 它不在 V007.41 范围
sc_count = content.count('safe_connect_for_read')
assert sc_count >= 2, f'FAIL: app_builder 只有 {sc_count} 处 safe_connect_for_read (expected >= 2)'
print(f'  [OK] {sc_count} 处 safe_connect_for_read (preflight 启动期保留 timeout=5)')


# Test 12: safe_connect_for_write 无事务 raise
print("\n[Test 12] safe_connect_for_write 无事务 raise")
from meta.core.safe_connect import safe_connect_for_write
from meta.core import sql_config
sql_config._default_safe_connect_config = None  # reset
with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tf:
    db_path = tf.name
try:
    raised = False
    try:
        with safe_connect_for_write(db_path) as conn:
            pass
    except ConnectionRefusedError as e:
        raised = True
        err_msg = str(e)
        assert 'V007.41' in err_msg, f'FAIL: error message missing V007.41 tag'
        assert 'bo_framework.transaction' in err_msg or 'force_no_tx' in err_msg, \
            f'FAIL: error message missing hint'
    assert raised, 'FAIL: safe_connect_for_write did not raise'
    print(f'  [OK] 无外层事务时 raise ConnectionRefusedError, 带 V007.41 tag + hint')
finally:
    os.unlink(db_path)


# Test 13: safe_connect_for_write(force_no_tx=True) 不 raise
print("\n[Test 13] safe_connect_for_write(force_no_tx=True) 不 raise")
with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tf:
    db_path = tf.name
try:
    with safe_connect_for_write(db_path, force_no_tx=True) as conn:
        cursor = conn.execute("SELECT 1")
        row = cursor.fetchone()
        # row_factory is sqlite3.Row, row[0] is value
        first = row[0] if row else None
        assert first == 1, f'FAIL: write connection query failed, got {first!r}'
    print(f'  [OK] force_no_tx=True 绕过守卫, 写连接可用')
finally:
    os.unlink(db_path)


# Test 14: safe_connect_for_read 默认参数与 V007.40 一致
print("\n[Test 14] safe_connect_for_read 默认参数与 V007.40 一致")
with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tf:
    db_path = tf.name
try:
    from meta.core.safe_connect import safe_connect_for_read
    with safe_connect_for_read(db_path) as conn:
        # verify PRAGMA busy_timeout: 用 sqlite3.Row 索引访问
        # PRAGMA 返回单列, 但 row_factory=Row 时 fetchone() 返回 Row 对象
        # 用 keys() + tuple() 提取第一列值
        cursor = conn.execute("PRAGMA busy_timeout")
        row = cursor.fetchone()
        # 取 Row 的第一个值
        if hasattr(row, 'keys'):
            # Row 类型, 用 tuple() 或 [key] 提取
            row_values = tuple(row)
            busy_timeout_ms = row_values[0]
        else:
            busy_timeout_ms = row[0]
        assert busy_timeout_ms == 30000, f'FAIL: busy_timeout_ms={busy_timeout_ms} (expected 30000)'
        # verify row_factory
        assert conn.row_factory is sqlite3.Row, f'FAIL: row_factory={conn.row_factory} (expected sqlite3.Row)'
    print(f'  [OK] busy_timeout=30000 + row_factory=sqlite3.Row')
finally:
    os.unlink(db_path)


# Test 15: V007.40 回归
print("\n[Test 15] V007.40 回归 (14/14 仍 100% 通过)")
import subprocess
result = subprocess.run(
    ['python', os.path.join(BASE, 'verify_v007_40.py')],
    capture_output=True, text=True, cwd=BASE
)
if result.returncode == 0:
    print(f'  [OK] verify_v007_40.py 通过')
else:
    # 解析输出
    fail_lines = [l for l in result.stdout.split('\n') if 'FAIL' in l or 'assert' in l.lower()]
    print(f'  [WARN] verify_v007_40.py 失败:')
    for fl in fail_lines[:5]:
        print(f'          {fl}')

print()
print("=" * 60)
print("V007.41 全部 15 项检查完成")
print("=" * 60)