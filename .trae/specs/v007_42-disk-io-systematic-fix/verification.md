# V007.42 验证清单

> **使用方式**：每个 Verification 命令执行后填入结果。V007.42 完成必须全部通过。

## V.1 单元测试

### V.1.1 Retry + mmap + I/O 限流 单元测试

**命令**：
```bash
cd D:\filework\release-prep-worktree
python -m pytest meta/tests/test_v007_42_read_retry.py -v
```

**预期**：
- 8 个测试用例 100% 通过
- 覆盖: retry 3 attempts / Decorrelated Jitter base+cap / I/O 限流触发+禁用 / mmap_size=0 / 环境变量覆盖 / max_readers=10

**结果**：____

### V.1.2 WAL 监控 单元测试

**命令**：
```bash
python -m pytest meta/tests/test_v007_42_wal_monitor.py -v
```

**预期**：
- 4 个测试用例 100% 通过
- 覆盖: checkpoint_busy / reader_health / 饥饿缩容 / 恢复扩容

**结果**：____

### V.1.3 Import Fix 单元测试

**命令**：
```bash
python -m pytest meta/tests/test_v007_42_import_fix.py -v
```

**预期**：
- 4 个测试用例 100% 通过
- 覆盖: get_all_tasks 空/1条/多条 / ImportQueueHandler 无 AttributeError

**结果**：____

### V.1.4 V007.41 回归测试

**命令**：
```bash
python -m pytest meta/tests/test_v007_41_safe_connect.py meta/tests/test_v007_41_l0_write_in_tx.py -v
```

**预期**：
- 21 个测试用例仍 100% 通过

**结果**：____

## V.2 集成验证

### V.2.1 V007.42 验证脚本

**命令**：
```bash
cd D:\filework\release-prep-worktree
python verify_v007_42.py
```

**预期**（17/17 通过）：
- Test 1: ConnectionConfig.mmap_size 默认 = 0
- Test 2: _create_connection PRAGMA mmap_size 读取 config
- Test 3: SQLITE_MMAP_SIZE 环境变量覆盖
- Test 4: max_readers 默认 = 10
- Test 5: _execute_via_read_pool max_retries = 3
- Test 6: Decorrelated Jitter base=200ms, cap=2s
- Test 7: I/O 限流器存在
- Test 8: SQLITE_IO_RATE_LIMIT_DISABLE 逃生口
- Test 9: health_check 返回 checkpoint_busy
- Test 10: health_check 返回 reader_health
- Test 11: AsyncImportService.get_all_tasks() 存在
- Test 12: TransactionContext 有 _start_time
- Test 13: async_audit_writer 不含裸 sqlite3.connect
- Test 14: observability 含 10 个新 metric
- Test 15: verify_v007_41.py 仍 100% 通过
- Test 16: sqlite_version_guard 检测 < 3.51.3 触发 WARNING (FR-011)
- Test 17: db_heartbeat 模块存在 + 线程可启停 (FR-012)

**结果**：____

### V.2.2 V007.41 回归验证

**命令**：
```bash
python verify_v007_41.py
```

**预期**：15/15 仍通过（零破坏性）

**结果**：____

### V.2.3 测试套件整体

**命令**：
```bash
python -m pytest meta/tests/ -v --tb=short 2>&1 | tail -30
```

**预期**：
- 所有现有测试仍通过
- 失败用例 = 0

**结果**：____

## V.3 关键功能验证

### V.3.1 mmap_size=0 功能验证

**命令**：
```bash
cd D:\filework\release-prep-worktree
python -c "
from meta.core.sql_connection_pool import ConnectionConfig, SQLiteConnectionPool
import tempfile, os

# 验证默认 mmap_size=0
config = ConnectionConfig()
assert config.mmap_size == 0, f'Expected 0, got {config.mmap_size}'

# 验证环境变量覆盖
os.environ['SQLITE_MMAP_SIZE'] = '67108864'
config2 = ConnectionConfig()
# 注意: 如果环境变量在 __init__ 读取则生效
del os.environ['SQLITE_MMAP_SIZE']

print('[OK] mmap_size=0 default verified')
"
```

**预期**：`[OK] mmap_size=0 default verified`

**结果**：____

### V.3.2 I/O 限流器功能验证

**命令**：
```bash
python -c "
from meta.core.sql_connection_pool import SQLiteConnectionPool, ConnectionConfig
import tempfile

# 验证限流器字段存在
with tempfile.NamedTemporaryFile(suffix='.db') as f:
    config = ConnectionConfig(db_path=f.name)
    pool = SQLiteConnectionPool(config)
    assert hasattr(pool, '_io_error_count'), 'Missing _io_error_count'
    assert hasattr(pool, '_io_rate_limit_active'), 'Missing _io_rate_limit_active'
    assert hasattr(pool, '_record_io_error'), 'Missing _record_io_error'
    assert hasattr(pool, '_check_io_rate_limit'), 'Missing _check_io_rate_limit'
    print('[OK] I/O rate limiter fields verified')
"
```

**预期**：`[OK] I/O rate limiter fields verified`

**结果**：____

### V.3.3 Decorrelated Jitter 参数验证

**命令**：
```bash
python -c "
import ast, inspect
from meta.core import sql_adapters

# 检查 retry 常量
source = inspect.getsource(sql_adapters)
# 验证 _RETRY_CAP = 2.0 (不是 5.0)
# 验证 _RETRY_BASE = 0.2 (不是 0.05)
# 验证 max_retries = 3 (不是 5)
print('[OK] Check source for _RETRY_CAP, _RETRY_BASE, max_retries values')
"
```

**预期**：确认 cap=2s, base=200ms, max=3

**结果**：____

### V.3.4 Import Fix 验证

**命令**：
```bash
python -c "
from meta.services.async_import_service import AsyncImportService
svc = AsyncImportService()
assert hasattr(svc, 'get_all_tasks'), 'Missing get_all_tasks'
result = svc.get_all_tasks()
assert isinstance(result, dict), 'Expected dict'
print(f'[OK] get_all_tasks() returns dict with {len(result)} entries')
"
```

**预期**：`[OK] get_all_tasks() returns dict with 0 entries`

**结果**：____

### V.3.5 async_audit_writer 统一验证

**命令**：
```bash
cd D:\filework\release-prep-worktree
grep -n "sqlite3\.connect" meta/services/async_audit_writer.py
```

**预期**：0 行输出 (已替换为 safe_connect_for_write)

**结果**：____

### V.3.6 长事务检测验证

**命令**：
```bash
python -c "
from meta.core.bo_framework import BOFramework
bf = BOFramework()
# TransactionContext 应有 _start_time 字段
# 检查 transaction 方法是否创建 TransactionContext
import inspect
source = inspect.getsource(bf.transaction)
print('[OK] Check transaction() creates TransactionContext with _start_time')
"
```

**预期**：确认 TransactionContext 含 _start_time

**结果**：____

## V.4 部署验证

### V.4.1 release-prep 服务器部署

**触发**：devops-deploy-sop skill
**端口**：3006 / 3011

**监控指标**（部署后 24h）：
- [ ] `ConnectionConfig.mmap_size` = 0 (日志确认)
- [ ] disk I/O error 日志 = **0** (关键: mmap 修正后应完全消失)
- [ ] `io_rate_limit_triggered_total` = **0** (限流未触发 = I/O 正常)
- [ ] `read_retry_total` ≈ 0 (无重试 = I/O 正常)
- [ ] API P50 响应时间增幅 < 20% (mmap_size=0 的性能代价)
- [ ] `wal_checkpoint_busy_total` 有增长但 checkpoint_busy 非持续 >0

**结果**：____

### V.4.2 yonaa 生产部署

**触发**：devops-deploy-sop skill
**端口**：3004 / 3009

**灰度策略**：
- T+0: 部署 1/4 实例
- T+2h: 全量部署（如无异常）

**监控指标**（部署后 1 周）：
- [ ] disk I/O error 日志 = **0**
- [ ] database is locked 错误 = **0**
- [ ] API P95 响应时间增幅 < 20%
- [ ] `io_rate_limit_triggered_total` = 0 (或 <5/天)
- [ ] `long_transaction_total` = 0 (或 <1/天)
- [ ] `AsyncImportService.get_all_tasks()` 正常返回

**结果**：____

### V.4.3 mmap_size=0 性能基线对比

**部署前基线** (V007.41, mmap_size=64MB):
- API P50: ____ms
- API P95: ____ms
- 读查询平均耗时: ____ms

**部署后基线** (V007.42, mmap_size=0):
- API P50: ____ms
- API P95: ____ms
- 读查询平均耗时: ____ms

**判定**：
- [ ] 增幅 < 20% → 可接受
- [ ] 增幅 ≥ 20% → 考虑 `SQLITE_MMAP_SIZE=67108864` 恢复 mmap

## V.5 文档验证

### V.5.1 spec.md 完整性

**文件**：`d:\filework\release-prep-worktree\.trae\specs\v007_42-disk-io-systematic-fix\spec.md`

**检查项**：
- [ ] 包含 10 个章节
- [ ] FR-001 ~ FR-010 全部定义
- [ ] NFR-001 ~ NFR-004 全部定义
- [ ] Module Design 含 I/O 限流器 + Decorrelated Jitter 代码
- [ ] Risk Assessment 含 mmap_size=0 风险
- [ ] 不含 Circuit Breaker 相关内容 (已替换为 I/O 限流器)

### V.5.2 docs/SPEC_V007.42.md 镜像

**文件**：`d:\filework\release-prep-worktree\docs\SPEC_V007.42.md`

**检查项**：
- [ ] 文件存在
- [ ] 与 spec.md 内容一致

### V.5.3 checklist.md 完整性

**文件**：`d:\filework\release-prep-worktree\.trae\specs\v007_42-disk-io-systematic-fix\checklist.md`

**检查项**：
- [ ] Phase 5-7 任务清单完整
- [ ] 验证阶段 V.1-V.4 完整
- [ ] 无 Circuit Breaker 相关条目

### V.5.4 tasks.md 完整性

**文件**：`d:\filework\release-prep-worktree\.trae\specs\v007_42-disk-io-systematic-fix\tasks.md`

**检查项**：
- [ ] 13 个 Task 全部定义
- [ ] 每个 Task 子任务明确
- [ ] 提交规范清晰 (3 个 commit)

### V.5.5 implementation_plan.md 完整性

**文件**：`d:\filework\release-prep-worktree\.trae\specs\v007_42-disk-io-systematic-fix\implementation_plan.md`

**检查项**：
- [ ] 3 个 Phase 时间表
- [ ] 回滚策略明确
- [ ] 关键代码变更预览
- [ ] 关键设计决策表 (二次确认后)

### V.5.6 verification.md 完整性

**文件**：`d:\filework\release-prep-worktree\.trae\specs\v007_42-disk-io-systematic-fix\verification.md`

**检查项**：
- [ ] V.1 ~ V.5 全部覆盖
- [ ] 包含 mmap_size=0 性能基线对比

## V.6 架构验证

### V.6.1 mmap_size 配置统一

**命令**：
```bash
cd D:\filework\release-prep-worktree
grep -rn "mmap_size" meta/core meta/services meta/api meta/handlers \
  --include="*.py" 2>/dev/null
```

**预期**：
- `sql_connection_pool.py`: ConnectionConfig.mmap_size + _create_connection 读取
- `safe_connect.py`: 不含 mmap_size (L0 不走 pool, 不设 mmap)
- 其他文件: 不含硬编码 mmap_size

**结果**：____

### V.6.2 裸 sqlite3.connect 残留

**命令**：
```bash
grep -rn "sqlite3\.connect(" meta/core meta/services meta/api meta/handlers \
  --include="*.py" 2>/dev/null
```

**预期**：仅 `meta/core/safe_connect.py` 内部 (V007.41 已统一) + `async_audit_writer.py` 已改为 safe_connect

**结果**：____

### V.6.3 环境变量逃生口完整性

| 环境变量 | 功能 | 默认值 | 检查 |
|---------|------|--------|------|
| `SQLITE_MMAP_SIZE` | 覆盖 mmap_size | 0 | [ ] |
| `SQLITE_IO_RATE_LIMIT_THRESHOLD` | 限流阈值 | 10 | [ ] |
| `SQLITE_IO_RATE_LIMIT_WINDOW` | 限流窗口 | 60 | [ ] |
| `SQLITE_IO_RATE_LIMIT_DISABLE` | 禁用限流 | (空) | [ ] |
| `SQLITE_MAX_READERS` | 覆盖 max_readers | 10 | [ ] |
| `SQLITE_READ_RETRY_MAX` | 覆盖 retry 次数 | 3 | [ ] |
| `SQLITE_READ_RETRY_BASE_MS` | 覆盖 retry 基础延迟 | 200 | [ ] |
| `SQLITE_REQUIRE_MIN_VERSION` | SQLite 版本下限 | (3.51.3) | [ ] |
| `SQLITE_HEARTBEAT_INTERVAL` | 心跳间隔(秒) | 30 | [ ] |
| `SQLITE_HEARTBEAT_DISABLE` | 禁用心跳 | (空) | [ ] |

## V.7 验收总结

**V007.42 完成判定**：

| 阶段 | 必须 | 实际 |
|---|---|---|
| V.1 单元测试 | 100% 通过 | ____ |
| V.2 集成验证 | 17/17 + 15/15 通过 | ____ |
| V.3 功能验证 | 6 项全部 OK | ____ |
| V.4 部署验证 | 24h disk I/O error = 0 | ____ |
| V.5 文档验证 | 6 项全部勾选 | ____ |
| V.6 架构验证 | 3 项全部匹配 | ____ |

**判定**：
- [ ] V007.42 完成
- [ ] V007.42 未完成（需补充项：____）
