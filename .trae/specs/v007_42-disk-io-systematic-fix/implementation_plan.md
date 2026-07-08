# V007.42 实施计划

## 1. 总体策略

**目标**：从 V007.41 的 "L0 统一" 升级到 "Disk I/O 系统性修复"

**核心修改优先级**:
1. **P0 (银弹)**: mmap_size=0 — 可能直接根治 disk I/O error
2. **P1 (防护)**: Retry 升级 + I/O 限流 — 防止雪崩
3. **P2 (可观测)**: WAL 监控 + 长事务检测 — 问题定位
4. **P3 (修复)**: Import fix + 审计统一 — 消除噪音

**原则**：
1. **零破坏性**：V007.41 已通过的验证必须仍然 100% 通过
2. **渐进式**：3 个 Phase，每个 Phase 单独 commit + 单独可回滚
3. **可降级**：所有关键修改均有环境变量逃生口
4. **银弹优先**：mmap_size=0 放在 Phase 5 最前面，效果立竿见影

## 2. 3 个 Phase 时间表

```
Day 1: Phase 5 (mmap 修正 + Retry 升级 + I/O 限流)
Day 2: Phase 6 (WAL 监控 + Import Fix + 长事务防护 + 审计统一)
Day 3: Phase 7 (集成验证 + 文档) + 部署
```

## 3. Phase 5: mmap 修正 + Retry 升级 + I/O 限流 (Day 1)

### 3.1 目标

- `mmap_size` 默认 0 (禁用), 可能直接根治 disk I/O
- Retry 从固定指数 → Decorrelated Jitter (base=200ms, cap=2s)
- I/O 限流器 (60s 窗口/10 次阈值, sleep 200ms 不拒绝)
- max_readers 20→10
- 4 个新 metric

### 3.2 提交清单

**Commit 1**: `fix(be): V007.42 P5 - mmap fix + retry upgrade + I/O rate limiter`

包含：
- `meta/core/sql_connection_pool.py` (修改: ConnectionConfig.mmap_size, I/O 限流器, max_readers)
- `meta/core/sql_adapters.py` (修改: Decorrelated Jitter)
- `meta/core/observability.py` (修改: 4 个新 metric)
- `meta/tests/test_v007_42_read_retry.py` (新建)

### 3.3 关键代码变更

#### 3.3.1 ConnectionConfig 新增 mmap_size

```python
# sql_connection_pool.py
@dataclass
class ConnectionConfig:
    db_path: str = ""
    max_readers: int = 10  # V007.42: 20→10
    mmap_size: int = 0     # V007.42: 新增, 默认禁用
    ...
```

#### 3.3.2 _create_connection PRAGMA mmap_size 可配置

```python
# 旧: conn.execute("PRAGMA mmap_size = 67108864")
# 新:
mmap_size = int(os.environ.get('SQLITE_MMAP_SIZE', str(config.mmap_size)))
conn.execute(f"PRAGMA mmap_size = {mmap_size}")
logger.info("[V007.42] PRAGMA mmap_size = %d", mmap_size)
```

#### 3.3.3 I/O 限流器

```python
# sql_connection_pool.py SQLiteConnectionPool
def _record_io_error(self):
    """记录 disk I/O error, 检查是否需要限流"""
    with self._io_error_lock:
        now = time.time()
        window = float(os.environ.get('SQLITE_IO_RATE_LIMIT_WINDOW', '60'))
        if now - self._io_error_window_start > window:
            self._io_error_count = 0
            self._io_error_window_start = now
            self._io_rate_limit_active = False
        self._io_error_count += 1
        threshold = int(os.environ.get('SQLITE_IO_RATE_LIMIT_THRESHOLD', '10'))
        if self._io_error_count >= threshold and not self._io_rate_limit_active:
            self._io_rate_limit_active = True
            logger.warning(
                "[V007.42] I/O rate limit activated: %d errors in %.0fs",
                self._io_error_count, now - self._io_error_window_start
            )
            metrics_inc('io_rate_limit_triggered_total')

def _check_io_rate_limit(self):
    """限流状态时 sleep 200ms (减速不拒绝)"""
    if os.environ.get('SQLITE_IO_RATE_LIMIT_DISABLE', '').lower() in ('1', 'true'):
        return
    if self._io_rate_limit_active:
        time.sleep(0.2)
```

#### 3.3.4 Decorrelated Jitter

```python
# sql_adapters.py _execute_via_read_pool
_RETRY_CAP = 2.0   # 最大延迟 2s
_RETRY_BASE = 0.2  # 基础延迟 200ms

# 旧:
# delay = 0.05 * (2 ** attempt) + random.uniform(0, 0.02)

# 新:
prev_sleep = _RETRY_BASE
for attempt in range(max_retries):
    try:
        self._pool._check_io_rate_limit()
        with self._pool.reader() as conn:
            ...
            return result
    except Exception as e:
        if "disk i/o error" in err_str or "database is locked" in err_str:
            self._pool._record_io_error()
            if attempt < max_retries - 1:
                delay = min(_RETRY_CAP, random.uniform(_RETRY_BASE, prev_sleep * 3))
                prev_sleep = delay
                logger.info("[V007.42] retry %d/%d, sleeping %.3fs", attempt+1, max_retries-1, delay)
                time.sleep(delay)
                continue
        raise
```

### 3.4 验收

- [ ] `ConnectionConfig.mmap_size` 默认 = 0
- [ ] `SQLITE_MMAP_SIZE` 环境变量可覆盖
- [ ] I/O 限流器: 60s/10次触发, sleep 200ms
- [ ] Decorrelated Jitter: base=200ms, cap=2s, **3 次总预算 ≥ 250ms** (D1 修正)
- [ ] max_readers 默认 = 10 (D3 修正: 原 5 → 10)
- [ ] SQLite 版本 < 3.51.3 触发 WARNING (FR-011)
- [ ] 后台心跳线程正常启停 (FR-012)
- [ ] `pytest meta/tests/test_v007_42_read_retry.py` 100% 通过
- [ ] V007.41 验证仍 100% 通过

## 4. Phase 6: WAL 监控 + Import Fix + 长事务 + 审计统一 (Day 2)

### 4.1 目标

- health_check 返回 checkpoint_busy + reader_health
- WAL 饥饿时缩容 max_readers
- ImportQueueHandler 不再 AttributeError
- 长事务检测 (>30s WARNING, >120s ERROR)
- async_audit_writer 使用 safe_connect_for_write
- 4 个新 metric

### 4.2 提交清单

**Commit 2**: `fix(be): V007.42 P6 - WAL monitor + import fix + long-tx guard + audit unify`

包含：
- `meta/core/sql_connection_pool.py` (修改: health_check 增强 + 动态缩容)
- `meta/services/async_import_service.py` (修改: get_all_tasks)
- `meta/core/bo_framework.py` (修改: TransactionContext 长事务检测)
- `meta/services/async_audit_writer.py` (修改: safe_connect_for_write)
- `meta/core/observability.py` (修改: 4 个新 metric)
- `meta/tests/test_v007_42_wal_monitor.py` (新建)
- `meta/tests/test_v007_42_import_fix.py` (新建)

### 4.3 关键代码变更

#### 4.3.1 health_check 增强

```python
# sql_connection_pool.py health_check()
def health_check(self) -> dict:
    ...
    # 新增: checkpoint_busy
    try:
        cursor = writer_conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        row = cursor.fetchone()
        result['checkpoint_busy'] = row[0] if row else 0  # busy 字段
    except Exception:
        result['checkpoint_busy'] = -1

    # 新增: reader_health
    healthy = 0
    errored = 0
    for pc in self._readers:
        if pc.is_valid():
            healthy += 1
        else:
            errored += 1
    result['reader_health'] = {'healthy': healthy, 'errored': errored}
    ...
```

#### 4.3.2 长事务检测

```python
# bo_framework.py TransactionContext
class TransactionContext:
    def __enter__(self):
        self._start_time = time.time()  # V007.42: 长事务检测
        ...
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self._start_time  # V007.42
        if duration > 30:
            logger.warning(
                "[V007.42] long transaction: %.1fs, txn=%s",
                duration, getattr(self, 'tran', '?')
            )
        if duration > 120:
            logger.error(
                "[V007.42] very long transaction: %.1fs, txn=%s",
                duration, getattr(self, 'tran', '?')
            )
            metrics_inc('long_transaction_total')
        ...
```

#### 4.3.3 async_audit_writer 统一

```python
# async_audit_writer.py
# 旧: conn = sqlite3.connect(self._db_path, ...)
# 新:
from meta.core.safe_connect import safe_connect_for_write

with safe_connect_for_write(self._db_path, force_no_tx=True) as conn:
    cursor = conn.cursor()
    cursor.execute("INSERT INTO audit_log ...", ...)
    conn.commit()
```

### 4.4 验收

- [ ] health_check 返回 checkpoint_busy + reader_health
- [ ] ImportQueueHandler 不再 AttributeError
- [ ] TransactionContext 有 _start_time + 长事务检测
- [ ] async_audit_writer 不含裸 sqlite3.connect
- [ ] `pytest meta/tests/test_v007_42_*.py` 100% 通过
- [ ] V007.41 验证仍 100% 通过

## 5. Phase 7: 集成验证 + 文档 (Day 3)

### 5.1 目标

- `verify_v007_42.py` 15 项 100% 通过
- `docs/SPEC_V007.42.md` 镜像同步

### 5.2 提交清单

**Commit 3**: `fix(be): V007.42 P7 - verify + docs`

包含：
- `verify_v007_42.py` (新建)
- `docs/SPEC_V007.42.md` (新建)

### 5.3 verify_v007_42.py 15 项验证

| # | 验证项 | 方法 |
|---|--------|------|
| 1 | ConnectionConfig.mmap_size 默认 = 0 | import + assert |
| 2 | _create_connection PRAGMA mmap_size 读取 config | 创建连接检查 PRAGMA |
| 3 | SQLITE_MMAP_SIZE 环境变量覆盖 | os.environ + assert |
| 4 | max_readers 默认 = 10 | import + assert |
| 5 | _execute_via_read_pool max_retries = 3 | 代码检查 |
| 6 | Decorrelated Jitter base=200ms, cap=2s | 常量检查 |
| 7 | I/O 限流器存在 | hasattr 检查 |
| 8 | SQLITE_IO_RATE_LIMIT_DISABLE 逃生口 | 代码检查 |
| 9 | health_check 返回 checkpoint_busy | 调用检查 |
| 10 | health_check 返回 reader_health | 调用检查 |
| 11 | AsyncImportService.get_all_tasks() 存在 | hasattr 检查 |
| 12 | TransactionContext 有 _start_time | hasattr 检查 |
| 13 | async_audit_writer 不含裸 sqlite3.connect | grep |
| 14 | observability 含 8 个新 metric | 检查 OBS_COUNTERS |
| 15 | verify_v007_41.py 仍 100% 通过 | subprocess |

### 5.4 验收

- [ ] `python verify_v007_42.py` 15/15 通过
- [ ] `python verify_v007_41.py` 仍通过
- [ ] 所有 3 个 commit 已合并

## 6. 部署计划

### 6.1 release-prep 服务器（先）

1. 部署 Commit 3
2. 监控 24h
3. **关键观察**: mmap_size=0 后 disk I/O error 是否完全消失
4. **性能基线**: 读 API 响应时间 (P50/P95) 变化
5. 观察 24h 无问题 → 进入 yonaa

### 6.2 yonaa 生产（后）

1. 灰度 1 个实例
2. 监控 2h
3. **关键指标**:
   - disk I/O error 日志 = 0 (期望)
   - API P95 响应时间增幅 < 20% (可接受)
   - I/O 限流器未触发 (期望)
4. 全量部署
5. 监控 1 周

### 6.3 部署后回退方案

如果 mmap_size=0 导致性能不可接受:
```bash
# 仅需 1 步, 不需回滚代码
export SQLITE_MMAP_SIZE=67108864  # 恢复 64MB mmap
# 重启服务即可
```

## 7. 回滚策略

每个 Phase 单独可回滚：

| Phase | 回滚命令 | 影响范围 |
|---|---|---|
| Phase 5 | `git revert <commit 1>` | mmap 恢复 64MB, retry 恢复旧逻辑, 无限流器, max_readers 恢复 20 |
| Phase 6 | `git revert <commit 2>` | health_check 恢复原样, ImportHandler 恢复 AttributeError, 审计恢复裸连接 |
| Phase 7 | `git revert <commit 3>` | 仅文档, 无功能影响 |

**应急逃生口**（不需回滚代码）：
- `SQLITE_MMAP_SIZE=67108864` → 恢复 mmap
- `SQLITE_IO_RATE_LIMIT_DISABLE=1` → 关闭限流
- `SQLITE_MAX_READERS=20` → 恢复连接池大小
- `SQLITE_READ_RETRY_MAX=3 SQLITE_READ_RETRY_BASE_MS=50` → 恢复旧 retry 参数

## 8. 关键设计决策 (二次 + 三次确认后)

| 决策 | 初始方案 | 二次确认 | 三次确认 (最终) | 原因 |
|------|---------|---------|-----------------|------|
| max_retries | 5 | 3 | **3** | SQLITE_IOERR 是 hard error, >3 次无效 |
| Circuit Breaker | 完整 3 态 CB | I/O 限流器 | **I/O 限流器** | CB Open 完全阻断读 = 灾难; 限流只减速不拒绝 |
| Connection pre-ping | 新增 | 不做 | **不做** | reader().is_valid() 已含 SELECT 1, 冗余 |
| mmap_size | 64MB 不变 | 0 (禁用) | **0 (禁用)** | SQLite 官方: mmap I/O error 不可恢复; V007.35→38 问题历史 |
| max_readers | 20 | 10 | **5 → 10** | D3: 实测当前默认 5, 改 10 与 Flask 8-16 worker 匹配 |
| retry cap | 5s | 2s | **2s + 总预算 ≥250ms** | D1: 实测 retry span 156~193ms, 总预算应 ≥250ms |
| 主动健康检查 | 未考虑 | 未考虑 | **新增 FR-012 心跳** | D4: 缺主动预防层, 加 PRAGMA quick_check 心跳 |
| SQLite 版本检查 | 未考虑 | 未考虑 | **新增 FR-011** | D2: 当前 3.50.4 < 3.51.3, 有 WAL-reset race 风险 |

## 9. 总结

V007.42 是 V007.41 的**系统性修复**：

**P0 银弹**: mmap_size=0 — 可能直接根治 disk I/O error (SQLite 官方明确指出 mmap I/O error 不可恢复)
**P1 防护**: I/O 限流 + Decorrelated Jitter (3 次总预算 ≥250ms) — 防止 retry storm
**P2 可观测**: WAL 监控 + 长事务检测 — 问题定位能力
**P3 修复**: Import fix + 审计统一 — 消除噪音
**P4 新增 (三次研究)**: 
- FR-011 SQLite 版本基线检查 (3.50.4 < 3.51.3 → WARNING)
- FR-012 后台心跳线程 (PRAGMA quick_check, 30s 间隔)

预计 3 个工作日完成，零破坏性，独立可回滚，所有关键修改均有环境变量逃生口。
