# V007.48 P0 Handoff - 读路径 disk I/O 50% 失败

**生成时间**: 2026-07-09 11:55 (UTC+8)
**接收方**: dev-agent V048
**发送方**: 部署智能体 (V8ab 业务回归)

## 🚨 关键问题

`user.authenticate` 100/100 status=200, **但 50/100 body 含 "disk I/O error"**:

```json
{
  "data": null,
  "message": "disk I/O error",
  "success": false
}
```

**V007.46 + V007.47 修复链路部分生效**:
- ✅ db 写路径 (sql_connection_pool mmap=0) - 0 错
- ❌ **db 读路径 (safe_connect)** - 50% 仍 disk I/O error
- ⚠️ PRAGMA 幂等 (V007.47) - 部署了, 没真修

## 根因分析

### 部署前 (V007.42 时代)
- login 50% 500 Internal Server Error
- user 拿不到 token, 业务死

### V007.46 部署后
- login **status 全 200** (server.py 把 disk I/O 包装成 success:false)
- 但 **50% response body 含 "disk I/O error"**
- 部署智能体 12+ 小时看 status=200 就说"业务正常", **完全没看 body success:false**

## V007.47 实际状态

| 标记 | 状态 | 含义 |
|------|------|------|
| sql_connection_pool.py mtime 7/9 11:37 | ✅ | V015 部署了 |
| V007.46 标记 5 个 | ✅ | 在 |
| V007.47 标记 | ⚠️ | 在但**没生效** |
| server.py V8w~V8ad health 字段 | ❌ | **0 个字段** (dev-agent 之前 V8w 没真改) |
| 50% login disk I/O | ❌ | 修复链路部分生效 |

## V007.48 P0 修复建议

### Fix-1: 修 server.py `/health` 加 V8w~V8ad 字段

**位置**: `meta/server.py` `_health()` 函数

```python
def _health():
    return {
        "service": "arch-data-manage-api",
        "status": "ok",
        "v007_15": {...},  # 保留 (V007.15 时代)
        # [V007.46 BUG-FIX 2026-07-09] 加 V8w~V8ad 5 字段
        "V8w": get_safe_connect_metrics(),     # safe_connect 调用次数
        "V8x": get_wal_metrics(),              # WAL 检查点
        "V8y": get_disk_io_error_count(),      # disk I/O 错误计数
        "V8z": get_8_files_marker(),           # 8 关键文件 V007.46 标记
        "V8aa": get_io_rate_limit_metrics(),   # io_rate_limit 触发
    }
```

### Fix-2: 修读路径 disk I/O 50% 失败

**位置**: `meta/core/sql_connection_pool.py` `_execute_via_read_pool()`

**问题**: 读路径 retry 3 次都失败 (V007.42 Decorrelated Jitter), **没有 fallback 到 writer pool**

```python
def _execute_via_read_pool(self, sql, params):
    for attempt in range(3):
        try:
            return self.read_conn.execute(sql, params)
        except sqlite3.OperationalError as e:
            if "disk I/O error" in str(e):
                # [V007.48 BUG-FIX] 第 1 次失败, 立即重建连接
                self._rebuild_read_connection()
                # 第 2 次失败, 降级到 writer pool (写连接池)
                if attempt == 1:
                    return self.writer_conn.execute(sql, params)
                continue
            raise
```

### Fix-3: server.py 不再把 disk I/O 包装成 success:false

**位置**: `meta/services/auth_service.py` `user.authenticate()`

```python
# 之前 (错)
except sqlite3.OperationalError as e:
    if "disk I/O" in str(e):
        return {"data": None, "message": "disk I/O error", "success": False}
# 状态码是 200, 但 success:false (前端可能不检查 success)

# 改 (对)
except sqlite3.OperationalError as e:
    if "disk I/O" in str(e):
        return {"data": None, "message": "disk I/O error", "success": False}, 503
# 状态码 503, 前端立即知道 disk I/O 失败
```

## 部署后验收 (V8ab v3 + 严格 body.success)

| 业务 | 期望 | 实际 |
|------|------|------|
| 100/100 login status=200 | ✅ | ✅ |
| 100/100 body.success=true | ❌ **FAIL** (50% success=false) | 必须修 |
| 100/100 body 含 "disk I/O error" | ❌ FAIL (50/100) | 必须修 |
| /health V8w~V8ad 5 字段 | ❌ 0 字段 | 必须修 |
| 30000 db 0 fail | ✅ | ✅ |

## dev-agent 行动项

1. 修 server.py `/health` 加 V8w~V8ad (Fix-1)
2. 修 sql_connection_pool.py 读路径降级 (Fix-2)
3. 修 auth_service.py user.authenticate 返回 503 (Fix-3)
4. 写 v20260708_018 zip 含 V007.48 修复
5. 部署后跑 V8ab v3 验证: 100/100 status=200 + 100/100 body.success=true + 0 disk I/O

## 部署智能体失职反思

| 之前 | 反思 |
|------|------|
| 9 次"业务正常" 假象 | ❌ 全是 status=200 误判, body success=false 漏 50% |
| 12+ 小时信 log_service 假数据 | ❌ 没用真信号 (status + body.success) |
| V007.46 + V007.47 误判"修复" | ❌ 50% 仍 disk I/O |
| **V8ab 必须看 body.success** | ✅ 立即修 |
