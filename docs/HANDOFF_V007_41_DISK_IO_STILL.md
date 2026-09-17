# V007.41 disk I/O error 持续 — 部署智能体 → 开发智能体 交接

**日期**: 2026-07-08 11:42
**优先级**: P0 (阻塞业务)
**commit HEAD**: 7c71636 (V007.40 + V007.24)

---

## 1. 现象

部署 v20260708_005 (HEAD=7c71636, V007.40+V007.24 修复) 到 yonaa 后:

| 时间 | 现象 |
|------|------|
| 10:47 | 部署成功 |
| 10:47:48 | 30s postcheck PASS |
| 11:26:52 | **disk I/O error 开始** |
| 11:34:29 | disk I/O error 持续 (11:42 仍在) |
| 11:26:52 → 11:34:29 | **7.5 分钟内 138 次 disk I/O error** |

## 2. 关键证据 (从 backend-v20260708_005.log)

### 2.1 错误调用模式 (5 种)

```
A. meta.services.user_authenticate - WARNING - [user.authenticate] Failed to query must_change_password: disk I/O error
B. meta.core.enrichment_engine - WARNING - [EnrichmentEngine.enrich_fk_display_names] owner_id->user failed: disk I/O error
C. meta.api.bo_api - ERROR - [query_bo] query failed: object_type=relationship msg=disk I/O error
D. meta.core.interceptors.persistence_interceptor - ERROR - [_do_list] Error: disk I/O error, object_type=relationship
E. meta.api.bo_api - ERROR - [bo_api] architecture preview error: disk I/O error
```

### 2.2 底层错误

```
sqlite3.OperationalError: disk I/O error
[V007.16] _execute_via_read_pool: marked bad connection (tid=..., err=disk i/o error)
[V007.34] _execute_via_read_pool: retrying after disk I/O (attempt 1/3, sleep 0.051s): disk i/o error
[V007.34] _execute_via_read_pool: retrying after disk I/O (attempt 2/3, sleep 0.107s): disk i/o error
[V007.16] reader: rebuilding bad connection (last_io_error=True, consecutive_errors=1, last_err=disk i/o error)
```

**注意**: 都是 `_execute_via_read_pool` — **读路径**。V007.40 主要修写路径 + 直连，读路径仍是原版。

### 2.3 触发场景 (关联线索)

| 时间 | 事件 |
|------|------|
| **11:26:08** | Import queue processing failed: 'AsyncImportService' object has no attribute 'get_all_tasks' (Python 异常, import_handlers) |
| 11:26:52 | 第一波 disk I/O error (持续 7.5 分钟) |
| 11:34:23 | **6 个并发 retry 同时 attempt 2/3** (并发读竞争) |
| 11:34:29 | sqlite3.OperationalError: disk I/O error (真实异常未消化) |

**关联**: Import 流程失败 → 触发 db 写锁 → 后续读请求 (登录/FK enrichment/list/preview) 全部竞争 → 大量并发重试 → 最终 OperationalError 上抛。

## 3. V007.40 修了什么 vs 没修什么

| 修了 | 状态 |
|------|------|
| ✅ journal_mode=WAL 幂等 (V007.37) | 部署了 |
| ✅ query_service._try_apply_dimension_scope retry (V007.37) | 部署了 |
| ✅ task_scheduler._create_execution_record retry (V007.38) | 部署了 |
| ✅ mmap_size 64MB (V007.38) | 部署了 |
| ✅ dead_letter 表 (V007.38) | 部署了 |
| ✅ writer lock (V007.38) | 部署了 |
| ✅ cursor.lastrowid (V007.38) | 部署了 |
| ✅ 消除 wal_checkpoint(TRUNCATE) (V007.39) | 部署了 |
| ✅ V007.40 17 unsafe 直连 (sql_config/sql_adapters/sql_checkpoint/intent_resolver/subflow_template/dim_scope/runtime_dim/filter_variant/token_blacklist) | 部署了 |
| **❌ 读路径 retry 不足** | **未修** |
| **❌ Import queue Python 异常** (`AsyncImportService.get_all_tasks`) | **未修** |
| **❌ 并发读竞争** (6 个 retry 同时 attempt 2/3) | **未修** |

## 4. 假说 (dev-agent 验证)

### H1: 读路径 retry 缺失
- V007.34 retry 在 `_execute_via_read_pool` 内部触发
- 但**业务层 (user_authenticate / enrichment_engine / bo_api / persistence_interceptor)** 没 retry
- 一次 I/O 抖动 → 业务失败 → 用户看到 500

### H2: Import queue 写锁
- Import 写 db 持锁 → 读请求 busy_timeout 5s 等
- 5s 后仍 I/O 错误 → 读失败
- Import queue 还在持续失败 (get_all_tasks 不存在)

### H3: 并发读竞争
- 11:34:23 同时 6 个并发 retry (attempt 2/3)
- 这 6 个都是不同 request_id, 都在争用同一个 db connection
- 提示 connection pool 不够大 或 retry 间隔太短 (0.05-0.12s)

### H4: db 文件本身
- busy_ms=5000 但 db 仍 I/O 错误 → 不是 timeout 问题
- 可能是 db 文件已损坏 (journal_mode=WAL 但 WAL 没数据 wal_mb=0)
- 检查 architecture.db integrity=ok 但实际可能 page 损坏

## 5. V007.41 dev-agent 需要做的

### 5.1 代码层 (优先级 P0)

1. **Import queue 修复**: `AsyncImportService.get_all_tasks` 方法不存在, 加这个方法
2. **业务层 retry** (4 处):
   - `meta.services.user_authenticate.user.authenticate` (登录)
   - `meta.core.enrichment_engine.EnrichmentEngine.enrich_fk_display_names` (FK 关联)
   - `meta.api.bo_api.query_bo` (列表)
   - `meta.core.interceptors.persistence_interceptor._do_list` (持久化)
3. **读路径 retry 加强**:
   - 业务层 catch sqlite3.OperationalError 后 retry
   - retry 间隔指数退避 (0.1s → 0.5s → 2s)
4. **并发读竞争**:
   - sql_adapters.py 连接池大小调整
   - retry 时让出 connection (释放给其他线程)

### 5.2 invariant V8n (防回归)

```python
# V8n: 所有 BOAction 业务层必须有 OperationalError retry
def check_v8n_bo_action_retry() -> tuple:
    """V007.41 BUG-FIX: BOAction 业务层必须包 sqlite3.OperationalError retry
    之前 V007.34 只在 sql_adapters._execute_via_read_pool 内部 retry,
    业务层 (user_authenticate, bo_api, enrichment_engine) 没 retry,
    一次 disk I/O 抖动 → 用户看到 500
    """
    needed_business_layers = [
        ("meta/services/user_authenticate.py", "user.authenticate"),
        ("meta/core/enrichment_engine.py", "enrich_fk_display_names"),
        ("meta/api/bo_api.py", "query_bo"),
        ("meta/core/interceptors/persistence_interceptor.py", "_do_list"),
    ]
    missing = []
    for fp, fn in needed_business_layers:
        content = open(fp).read() if os.path.exists(fp) else ""
        if "OperationalError" not in content or "retry" not in content.lower():
            missing.append(f"{fp}::{fn}")
    if missing:
        return (False, f"业务层缺 OperationalError retry (V007.41 BUG 复发): {missing}")
    return (True, f"全部 {len(needed_business_layers)} 业务层有 retry")
```

### 5.3 yonaa 验证

```bash
# 部署 V007.41 后:
# 1. 在前端登录 10 次, 看是否还有 disk I/O error
# 2. 触发 import 流程, 看 import_handlers.get_all_tasks 是否修复
# 3. 并发触发 6 个 query_bo request, 看是否还有 6 并发 retry 拥堵
# 4. 监控 backend.log 中 "disk I/O error" 字符串计数, 应为 0
```

## 6. 远程诊断资源 (不需 SSH)

部署智能体已通过 yonaa log_service 9101 验证:

| 端点 | URL | 结果 |
|------|-----|------|
| /api/db/health | http://172.20.59.7:9101/api/db/health | integrity=ok, busy_ms=5000, wal=0 |
| /api/sqlite | http://172.20.59.7:9101/api/sqlite?sql=... | 直查 OK |
| /api/sqlite/load | http://172.20.59.7:9101/api/sqlite/load?count=100 | 直读 OK |
| /api/log | http://172.20.59.7:9101/api/log?file=/opt/app/shared/logs/backend-v20260708_005.log&grep=disk | **138 行匹配** |
| /api/iostat | http://172.20.59.7:9101/api/iostat?count=3 | 端点可用 |
| /api/proc/io | http://172.20.59.7:9101/api/proc/io?pid=... | 端点可用 (v4 需 python key 找 PID) |

**注**: log_service v4 `/api/log` 返回结构:
```json
{
  "file": "...",
  "size": 12345,
  "output": "...",   // 字符串, 不是 array
  "output_lines": 138,  // 匹配行数
  "elapsed_ms": 15,
  "stderr": null
}
```

不是 v3.5 那种 `{count, matches}` 结构, 部署智能体之前误判 count 字段, 已修。

## 7. yonaa 服务状态 (11:42)

| 服务 | 端口 | PID | fds |
|------|------|-----|-----|
| backend | 5001 | (nohup, 7c71636) | 331+ |
| unified_server | 8081 | (nohup) | 4 |
| log_service v4.5 | 9101 | 20364 | 6 |
| node_exporter | 9100 | 578 | 3 |

db: /opt/app/deployments/meta/architecture.db (96.26 MB, integrity=ok, wal=0)

## 8. V007.41 部署后验收

- [ ] backend.log disk I/O error 计数 0 (24h 监控)
- [ ] import queue 跑通 (get_all_tasks 修复)
- [ ] 6 并发 query_bo 不再同时 retry (读路径退避生效)
- [ ] invariant V8n PASS (4 业务层都有 OperationalError retry)
- [ ] 前端登录 10 次无 500

---

**接收方**: 开发智能体
**状态**: 等待 V007.41 fix
**yonaa 仍在持续产生 disk I/O error (138+ 次)**