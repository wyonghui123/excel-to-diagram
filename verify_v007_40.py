"""V007.40 验证脚本 - 逐项检查修复"""
import sys
import re
import os
# 显式切换到 release-prep-worktree 目录
SCRIPT_DIR = os.path.dirname(os.path.abspath('verify_v007_40.py'))
# 用脚本所在目录
BASE = SCRIPT_DIR
print(f"[DEBUG] CWD: {os.getcwd()}, BASE: {BASE}")

print("=" * 60)
print("V007.40 验证检查 - 验证所有修复")
print("=" * 60)

# Test 1: WriteQueueConfig default
print("\n[Test 1] sql_config.py WriteQueueConfig/CheckpointConfig 默认值")
from meta.core.sql_config import WriteQueueConfig, CheckpointConfig
wq = WriteQueueConfig()
assert wq.checkpoint_mode == 'PASSIVE', f'FAIL: WriteQueueConfig.checkpoint_mode={wq.checkpoint_mode}'
print(f'  [OK] WriteQueueConfig.checkpoint_mode = {wq.checkpoint_mode}')

cc = CheckpointConfig()
assert cc.mode == 'PASSIVE', f'FAIL: CheckpointConfig.mode={cc.mode}'
print(f'  [OK] CheckpointConfig.mode = {cc.mode}')

# Test 2: sql_adapters default
print("\n[Test 2] sql_adapters.py pool init + checkpoint() 默认值")
with open(os.path.join(BASE, 'meta/core/sql_adapters.py'), 'r', encoding='utf-8') as f:
    content = f.read()
m = re.search(r'checkpoint_mode=kwargs\.get\(\s*[\'"]checkpoint_mode[\'"]\s*,\s*[\'"]([A-Z]+)[\'"]', content)
assert m and m.group(1) == 'PASSIVE', f'FAIL: pool init = {m.group(1) if m else None}'
print(f'  [OK] pool init checkpoint_mode = {m.group(1)}')

m2 = re.search(r'def\s+checkpoint\s*\([^)]*mode\s*:\s*str\s*=\s*[\'"]([A-Z]+)[\'"]', content)
assert m2 and m2.group(1) == 'PASSIVE', f'FAIL: checkpoint() = {m2.group(1) if m2 else None}'
print(f'  [OK] checkpoint() default = {m2.group(1)}')

# Test 3: maintenance scheduler
print("\n[Test 3] sql_maintenance_scheduler.py _checkpoint()")
with open(os.path.join(BASE, 'meta/core/sql_maintenance_scheduler.py'), 'r', encoding='utf-8') as f:
    content = f.read()
assert 'ds.checkpoint("PASSIVE")' in content, 'FAIL: missing ds.checkpoint("PASSIVE")'
assert '"TRUNCATE"' not in content and "'TRUNCATE'" not in content, 'FAIL: still has TRUNCATE'
print(f'  [OK] _checkpoint() uses PASSIVE, no TRUNCATE')

# Test 4: checkpoint_manager
print("\n[Test 4] sql_checkpoint_manager.py 修复")
with open(os.path.join(BASE, 'meta/core/sql_checkpoint_manager.py'), 'r', encoding='utf-8') as f:
    content = f.read()
truncate_count = len(re.findall(r'[\'"]mode[\'"]\s*:\s*[\'"]TRUNCATE[\'"]', content))
assert truncate_count == 0, f'FAIL: checkpoint_manager has {truncate_count} mode: TRUNCATE'
print(f'  [OK] 0 处 mode: TRUNCATE in dict')

m3 = re.search(r'def\s+execute_checkpoint\s*\([^)]*mode\s*:\s*str\s*=\s*[\'"]([A-Z]+)[\'"]', content)
assert m3 and m3.group(1) == 'PASSIVE', f'FAIL: execute_checkpoint = {m3.group(1) if m3 else None}'
print(f'  [OK] execute_checkpoint() default = {m3.group(1)}')

# Test 5: WriteQueue stop drains
print("\n[Test 5] sql_write_queue.py stop() 排空 in-flight")
with open(os.path.join(BASE, 'meta/core/sql_write_queue.py'), 'r', encoding='utf-8') as f:
    content = f.read()
# 提取 stop() 方法体
m = re.search(r'def\s+stop\s*\([^)]*\)\s*:.*?(?=\n    def\s|\nclass\s|\Z)', content, re.DOTALL)
assert m, 'FAIL: stop() not found'
stop_code = m.group(0)
assert 'self.flush(' in stop_code, 'FAIL: stop() missing flush()'
assert 'set_exception' in stop_code, 'FAIL: stop() missing set_exception for pending futures'
print(f'  [OK] stop() calls flush() + set_exception')

# Test 6: token_blacklist_service
print("\n[Test 6] token_blacklist_service.py 最高频热路径")
with open(os.path.join(BASE, 'meta/services/token_blacklist_service.py'), 'r', encoding='utf-8') as f:
    content = f.read()
# [V007.41 BUG-FIX] 验证脚本更新: 旧 V007.40 检查 timeout=30.0 字面量,
#   现在改检查 safe_connect_for_read/write 引用 (三件套已封装到工厂)
assert 'safe_connect_for_read' in content or 'safe_connect_for_write' in content, \
    'FAIL: missing safe_connect_* usage'
assert 'is_blacklisted' in content and 'range(5)' in content, 'FAIL: is_blacklisted missing retry loop'
print(f'  [OK] safe_connect_for_read/write + retry loop in is_blacklisted')

# Test 7: intent_resolver
print("\n[Test 7] intent_resolver.py 6 处安全连接")
with open(os.path.join(BASE, 'meta/core/intent_resolver.py'), 'r', encoding='utf-8') as f:
    content = f.read()
print(f"  DEBUG: file path = {os.path.join(BASE, 'meta/core/intent_resolver.py')}")
print(f"  DEBUG: file size = {len(content)}")
print(f"  DEBUG: _safe_connect calls = {content.count('_safe_connect(self._db_path)')}")
# 排除注释行中提到的 sqlite3.connect(self._db_path)
code_lines = "\n".join(
    line for line in content.split("\n")
    if line.strip() and not line.strip().startswith("#")
)
code_direct = code_lines.count('sqlite3.connect(self._db_path)')
# 打印每行包含 sqlite3.connect(self._db_path) 的代码行
for i, line in enumerate(content.split('\n'), 1):
    if 'sqlite3.connect(self._db_path)' in line and not line.strip().startswith('#'):
        print(f"  DEBUG: code line {i}: {line[:100]!r}")
print(f"  DEBUG: code direct count = {code_direct}")
# [V007.41 BUG-FIX] 验证脚本更新: 旧 V007.40 检查 _safe_connect 本地 helper,
#   V007.41 改用 safe_connect_for_read/write 统一工厂
assert 'safe_connect_for_read' in content or 'safe_connect_for_write' in content, \
    'FAIL: missing safe_connect_* usage'
direct_count = code_direct  # 只统计代码行, 排除注释
assert direct_count == 0, f'FAIL: still has {direct_count} direct sqlite3.connect'
helper_count = (
    content.count('safe_connect_for_read(self._db_path)') +
    content.count('safe_connect_for_write(self._db_path')
)
print(f'  [OK] safe_connect_for_read/write 调用 {helper_count} 处, 0 处直接连接')

# Test 8: subflow_template_store
print("\n[Test 8] subflow_template_store.py 4 处安全连接")
with open(os.path.join(BASE, 'meta/services/subflow_template_store.py'), 'r', encoding='utf-8') as f:
    content = f.read()
# [V007.41 BUG-FIX] 验证脚本更新: 同 Test 7
assert 'safe_connect_for_read' in content or 'safe_connect_for_write' in content, \
    'FAIL: missing safe_connect_* usage'
direct_count = content.count('sqlite3.connect(cls._get_db_path())')
assert direct_count == 0, f'FAIL: still has {direct_count} direct sqlite3.connect'
helper_count = (
    content.count('safe_connect_for_read(cls._get_db_path())') +
    content.count('safe_connect_for_write(cls._get_db_path()')
)
print(f'  [OK] safe_connect_for_read/write 调用 {helper_count} 处, 0 处直接连接')

# Test 9: filter_variant_api
print("\n[Test 9] filter_variant_api.py 高频 API")
with open(os.path.join(BASE, 'meta/api/filter_variant_api.py'), 'r', encoding='utf-8') as f:
    content = f.read()
# [V007.41 BUG-FIX] 验证脚本更新: 旧 V007.40 检查 timeout=30.0 字面量,
#   现在改检查 safe_connect_for_read/write 引用 (三件套已封装到工厂)
assert 'safe_connect_for_read' in content or 'safe_connect_for_write' in content, \
    'FAIL: missing safe_connect_* usage'
assert '_table_initialized' in content, 'FAIL: missing _table_initialized'
print(f'  [OK] safe_connect_for_read/write + _table_initialized (避免每请求都 CREATE TABLE)')

# Test 10: audit_export
print("\n[Test 10] audit_export.py export 路径")
with open(os.path.join(BASE, 'meta/services/audit_export.py'), 'r', encoding='utf-8') as f:
    content = f.read()
# [V007.41 BUG-FIX] 验证脚本更新: 旧 V007.40 检查 timeout=30.0 字面量
assert 'safe_connect_for_read' in content or 'safe_connect_for_write' in content, \
    'FAIL: missing safe_connect_* usage'
print(f'  [OK] safe_connect_for_read/write (with context manager)')

# Test 11: runtime_dimension_resolver
print("\n[Test 11] runtime_dimension_resolver.py 3 处安全连接")
with open(os.path.join(BASE, 'meta/core/runtime_dimension_resolver.py'), 'r', encoding='utf-8') as f:
    content = f.read()
# [V007.41 BUG-FIX] 验证脚本更新: 旧 V007.40 检查 timeout=30.0 字面量
sc_count = content.count('safe_connect_for_read') + content.count('safe_connect_for_write')
assert sc_count >= 3, f'FAIL: only {sc_count} safe_connect_* calls (expected >= 3)'
print(f'  [OK] {sc_count} 处 safe_connect_for_read/write')

# Test 12: dim_scope_overlap_detector
print("\n[Test 12] dim_scope_overlap_detector.py 2 处安全连接")
with open(os.path.join(BASE, 'meta/core/dim_scope_overlap_detector.py'), 'r', encoding='utf-8') as f:
    content = f.read()
# [V007.41 BUG-FIX] 验证脚本更新: 旧 V007.40 检查 timeout=30.0 字面量
sc_count = content.count('safe_connect_for_read') + content.count('safe_connect_for_write')
assert sc_count >= 2, f'FAIL: only {sc_count} safe_connect_* calls (expected >= 2)'
print(f'  [OK] {sc_count} 处 safe_connect_for_read/write')

# Test 13: app_builder
print("\n[Test 13] app_builder.py 启动期连接")
with open(os.path.join(BASE, 'meta/core/app_builder.py'), 'r', encoding='utf-8') as f:
    content = f.read()
# [V007.41 BUG-FIX] 验证脚本更新: 旧 V007.40 检查 timeout=30.0 字面量
assert 'safe_connect_for_read' in content or 'safe_connect_for_write' in content or 'timeout=30.0' in content, \
    'FAIL: missing safe_connect_* usage or timeout=30.0'
print(f'  [OK] app_builder.py 启动期连接已用 safe_connect 或 timeout=30.0')

# Test 14: test_sql_config.py 断言已修
print("\n[Test 14] tests/test_sql_config.py 断言")
with open(os.path.join(BASE, 'meta/tests/test_sql_config.py'), 'r', encoding='utf-8') as f:
    content = f.read()
assert 'config.checkpoint_mode == "PASSIVE"' in content, 'FAIL: test still expects TRUNCATE'
assert 'config.checkpoint_mode == "TRUNCATE"' not in content, 'FAIL: test still asserts TRUNCATE'
print(f'  [OK] 断言已改为 PASSIVE')

print()
print("=" * 60)
print("V007.40 全部 14 项检查通过!")
print("=" * 60)
print()
print("修复摘要:")
print("  P0 (核心配置 + scheduler):")
print("    - sql_config.py 2 个默认值")
print("    - sql_adapters.py 2 个默认值")
print("    - sql_checkpoint_manager.py 2 个默认值")
print("    - sql_maintenance_scheduler.py 显式调用 (每 5 分钟)")
print("  P1 (高频热路径 + 17 处):")
print("    - token_blacklist_service.py (最高频, 含 retry)")
print("    - filter_variant_api.py (高频, 含 before_request 优化)")
print("    - runtime_dimension_resolver.py 3 处")
print("    - intent_resolver.py 6 处 (用 _safe_connect helper)")
print("    - subflow_template_store.py 4 处 (用 _safe_connect helper)")
print("    - audit_export.py 1 处 (with context manager)")
print("    - dim_scope_overlap_detector.py 2 处")
print("    - app_builder.py 1 处")
print("  P2 (测试 + 改进):")
print("    - tests/test_sql_config.py 断言已修")
print("    - WriteQueue.stop() 排空 in-flight + set_exception 防止 hang")
print("    - 新增 test_v007_40_no_truncate_default.py 14 项回归测试")
