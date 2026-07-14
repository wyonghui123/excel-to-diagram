# [ARCHIVED] DEPLOY HANDOVER V007.44 — 统一修复 disk I/O + 权限过滤

> **归档日期**: 2026-07-14 | **取代文档**: [../../DEPLOYMENT.md](../../DEPLOYMENT.md) + [SQLITE_IO_ERROR_DESIGN.md](../SQLITE_IO_ERROR_DESIGN.md)

> 日期: 2026-07-08 | 版本: V007.44 | 作者: AI Assistant

## 一、为何一直没有收口 — 根因分析

用户反馈: "为何这个问题一直没有收口，一直有遗漏"

**根因**: 每次修复只覆盖一个点，没有做全量代码路径审计。6个独立遗漏形成"打地鼠"模式:

| # | 遗漏 | 影响 | 之前为何没发现 |
|---|-------|------|---------------|
| A | `safe_connect.py` 缺 `mmap_size=0` | 138个 disk I/O error | V007.42 在 pool 加了, 但新引入的 safe_connect 工厂漏了 |
| B | `_cleanup_resources` atexit+signal 双重调用 | shutdown 时 disk I/O | 只看运行时路径, 没看 shutdown 路径的幂等性 |
| C | `import_export_service.py` OR/AND bug | 导出范围远大于权限 | BUG-V027-pt2 只修了 query_service.py, 没修 import_export |
| D | `_apply_data_permission` except 允许全部 | NameError 等异常绕过权限 | 只修了 Tuple import, 没修 except 的降级策略 |
| E | 4个查询方法无权限过滤 | 搜索/聚合绕过权限 | 只关注 search 路径, 没审查其他公开方法 |
| F | 多处裸连接无 `mmap_size=0` | 运行时 disk I/O | 只改了 pool, 没改 health_monitor/diagnostics 等 |

## 二、修复清单 (6 FIX)

### FIX-1: safe_connect.py 添加 mmap_size=0 [致命]

**文件**: `meta/core/safe_connect.py` L66-84

**改动**: `_open_safe_connection` 中添加:
```python
conn.execute("PRAGMA mmap_size = 0")
conn.execute("PRAGMA cache_size = -2000")
```

**原因**: V007.42 核心修复是禁用 mmap 避免 108MB DB 的 disk I/O error, 但 safe_connect 工厂函数漏了这行。所有通过 `safe_connect_for_read` / `safe_connect_for_write` 创建的连接都使用了操作系统默认的 mmap_size, 等于 V007.42 的修复被绕过。

---

### FIX-2: _cleanup_resources 幂等守卫 [致命]

**文件**: `meta/server.py` L290-303

**改动**: 函数开头加全局标志位:
```python
_cleanup_done = False

def _cleanup_resources(data_source):
    global _cleanup_done
    if _cleanup_done:
        return
    _cleanup_done = True
    ...
```

**原因**: `_signal_handler` 调 `_cleanup_resources` 后执行 `sys.exit(0)`, 但 `sys.exit(0)` 触发 `atexit` 回调再次调 `_cleanup_resources`。第二次调用时 pool 已关闭, PASSIVE checkpoint 触发 disk I/O error。这是 v011 的 1 个 shutdown disk I/O error 的直接原因。

---

### FIX-3: import_export_service.py OR/AND bug [致命]

**文件**: `meta/services/import_export_service.py` L4557-4587

**改动**: `_flatten` 函数添加 `leaf_op` 参数, 单角色路径用 `AND` 拼接:
```python
def _flatten(conds, leaf_op='OR'):
    ...
    return f' {leaf_op} '.join(parts)

if len(per_role_conds) == 1:
    return _flatten(per_role_conds[0], leaf_op='AND')  # 单角色: AND
```

**原因**: 与 BUG-V027-pt2 完全相同的 bug。单角色时, `domain_id=8` 和 `version_id=3` 两个 leaf 条件被 OR 拼接, 导致导出范围远大于权限允许。BUG-V027-pt2 只修了 query_service.py, 没修 import_export_service.py 的导出路径。

---

### FIX-4: _apply_data_permission 异常时拒绝 [严重]

**文件**: `meta/services/query_service.py` L1610-1616

**改动**: except 路径从静默允许改为拒绝:
```python
except Exception as e:
    logger.error(f"[DataPerm] Failed to apply data permission for {object_type}: {e}", exc_info=True)
    builder.where('id', QueryOperator.EQ, -1)
```

**原因**: 原代码 except 后什么都不做 → builder 无过滤条件 → 返回全部数据。NameError (Tuple import 缺失)、disk I/O 等异常会绕过权限过滤。对比 `data_permission_filter.py` 异常时返回 `id = -1` 拒绝所有。

---

### FIX-5: 4个查询方法添加数据权限过滤 [严重]

**文件**: `meta/services/query_service.py`

**改动**: 在以下方法的 `builder.execute()` 前添加 `self._apply_data_permission(builder, meta_obj, object_id)`:
- `full_text_search` (L989)
- `query_by_hierarchy_path` (L1020)
- `suggest` (L1057)
- `aggregate` (L2194)

**原因**: 这4个方法直接查 DB, 不调用 `_apply_data_permission`, 用户可通过搜索/聚合/层级/建议接口绕过数据权限看到全部数据。

---

### FIX-6: 关键裸连接改用 safe_connect [高]

**改动**:

| 文件 | 改动 |
|------|------|
| `meta/core/db_health_monitor.py` L91 | `sqlite3.connect` → `safe_connect_for_read` |
| `meta/core/db_health_monitor.py` L207 | `sqlite3.connect(uri=True)` → `safe_connect_for_read` |
| `meta/services/async_audit_writer.py` L134 | 降级裸连接添加 `PRAGMA mmap_size=0` + `PRAGMA cache_size=-2000` |
| `meta/api/diagnostics_api.py` L80 | `sqlite3.connect` → `safe_connect_for_read` |

**原因**: 这些裸连接没有 `mmap_size=0` 和 `busy_timeout=30000`, 与连接池并发访问 108MB DB 时触发 disk I/O error。`db_health_monitor.py` 的 PASSIVE checkpoint 是运行时高频操作, 是 v005 138个 disk I/O error 的典型触发场景。

## 三、部署步骤

```bash
# 1. 构建 deploy bundle
cd d:/filework/release-prep-worktree/deploy_bundle
python tools/build_v007_15_zip.py  # 或等效的打包脚本

# 2. 上传到生产
# (按现有部署流程)

# 3. 部署
# (按现有 deploy.sh 流程, PHASE 0.5+0.6+1+4+5+6)

# 4. 验证
# - 检查日志无 disk I/O error
# - 检查 wyonghui 用户导出数据权限正确
# - 检查 suggest/full-text 搜索有权限过滤
```

## 四、验证清单

- [ ] 启动后日志无 `disk I/O error`
- [ ] `wyonghui` 用户(供应链云权限)导出数据范围正确
- [ ] 搜索接口返回结果受数据权限约束
- [ ] suggest 接口返回结果受数据权限约束
- [ ] aggregate 接口返回结果受数据权限约束
- [ ] shutdown 时无 `disk I/O error` (幂等守卫生效)
- [ ] `_apply_data_permission` 异常时返回空结果 (id=-1) 而非全部数据

## 五、涉及的文件

| 文件 | 修复项 |
|------|--------|
| `meta/core/safe_connect.py` | FIX-1 |
| `meta/server.py` | FIX-2 |
| `meta/services/import_export_service.py` | FIX-3 |
| `meta/services/query_service.py` | FIX-4, FIX-5 |
| `meta/core/db_health_monitor.py` | FIX-6 |
| `meta/services/async_audit_writer.py` | FIX-6 |
| `meta/api/diagnostics_api.py` | FIX-6 |
