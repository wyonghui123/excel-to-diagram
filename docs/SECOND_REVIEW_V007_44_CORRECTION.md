# V007.44 二次审查报告 - 重要纠正

> **日期**: 2026-07-08 18:50
> **重要级别**: P0 (之前审查结论错误, 需立即纠正)
> **审查者**: V007.45 dev-agent (二次审查 + 自我纠正)
> **纠正对象**: docs/SECOND_REVIEW_V007_44.md, docs/SECOND_REVIEW_V007_44_LOCATIONS.md

---

## 🚨 严重错误声明

我之前的二次审查报告 (`SECOND_REVIEW_V007_44.md` 和 `SECOND_REVIEW_V007_44_LOCATIONS.md`) **结论错误**：

**错误结论**: "V007.44 文档声称的 6 个 FIX 实际只有 0 个真正进入代码"

**正确结论**: **V007.44 6 个 FIX 在 `deploy_bundle/meta/` 下全部已真实实施**。

**错误原因**: 我审查时只看了工作树 `meta/`，没注意到 `deploy_bundle/meta/` 才是部署包实际修复位置。

---

## 关键事实

**commit `910022e` 修改了 8 个文件**：

```
DEPLOY_HANDOVER_V007_44.md
deploy_bundle/meta/api/diagnostics_api.py
deploy_bundle/meta/core/db_health_monitor.py
deploy_bundle/meta/core/safe_connect.py
deploy_bundle/meta/server.py
deploy_bundle/meta/services/async_audit_writer.py
deploy_bundle/meta/services/import_export_service.py
deploy_bundle/meta/services/query_service.py
```

**所有 `meta/` 修复都在 `deploy_bundle/` 子目录下**（部署包位置）。

---

## 6 个 FIX 实际状态 (deploy_bundle/ 验证)

### FIX-1: safe_connect.py mmap_size=0 ✅ **已实施**

**deploy_bundle/meta/core/safe_connect.py:66-84**:
```python
def _open_safe_connection(db_path: str) -> sqlite3.Connection:
    """内部: 创建配好安全三件套 + mmap_size=0 的连接."""
    conn = sqlite3.connect(db_path, timeout=cfg.timeout, check_same_thread=cfg.check_same_thread)
    conn.execute(f"PRAGMA busy_timeout = {cfg.busy_timeout_ms}")
    # [V007.44 BUG-FIX] 禁用 mmap: 108MB DB 上 mmap 导致 disk I/O error
    conn.execute("PRAGMA mmap_size = 0")
    conn.execute("PRAGMA cache_size = -2000")
    conn.row_factory = sqlite3.Row
    return conn
```

### FIX-2: _cleanup_resources 幂等守卫 ✅ **已实施**

**deploy_bundle/meta/server.py:290-296**:
```python
_cleanup_done = False

def _cleanup_resources(data_source):
    global _cleanup_done
    if _cleanup_done:
        return
    _cleanup_done = True
    ...
```

### FIX-3: import_export_service leaf_op='AND' ✅ **已实施**

**deploy_bundle/meta/services/import_export_service.py:4557, 4587**:
```python
def _flatten(conds: List[Dict], leaf_op: str = 'OR') -> str:
    """...
    [V007.44 BUG-FIX] leaf_op 参数控制裸 leaf 条件(无 type 标记)的拼接方式:
      - 多角色路径: leaf_op='OR' (顶层 OR-of-AND)
      - 单角色路径: leaf_op='AND' (同一 role 内多个 leaf 是 AND 关系)
    """
    ...
    return f' {leaf_op} '.join(parts)

if len(per_role_conds) == 1:
    # [V007.44 BUG-FIX] 单角色: 裸 leaf 条件之间是 AND 关系
    return _flatten(per_role_conds[0], leaf_op='AND')
```

### FIX-4: _apply_data_permission 异常时拒绝 ✅ **已实施**

**deploy_bundle/meta/services/query_service.py:1620-1626**:
```python
except Exception as e:
    # [V007.44 BUG-FIX] 异常时必须拒绝, 不能静默允许全部
    logger.error(f"[DataPerm] Failed to apply data permission for {object_type}: {e}", exc_info=True)
    builder.where('id', QueryOperator.EQ, -1)
```

### FIX-5: 4 个查询方法权限过滤 ✅ **已实施**

**deploy_bundle/meta/services/query_service.py**:
- L989 (`full_text_search`): `self._apply_data_permission(builder, meta_obj, object_id)`
- L1020 (`query_by_hierarchy_path`): `self._apply_data_permission(builder, meta_obj, target_object_id)`
- L1057 (`suggest`): `self._apply_data_permission(builder, meta_obj, object_type)`
- L2194 (`aggregate`): `self._apply_data_permission(builder, meta_obj, request.object_type)`

### FIX-6: 4 处裸连接修复 ✅ **已实施**

| 文件 | 行号 | 修复 |
|------|------|------|
| `db_health_monitor.py` | L91-93 | 改 `safe_connect_for_read` |
| `db_health_monitor.py` | L207-211 | 改 `safe_connect_for_read` |
| `async_audit_writer.py` | L133-137 | 降级裸连接加 `mmap_size=0` + `cache_size=-2000` |
| `diagnostics_api.py` | L80-82 | 改 `safe_connect_for_read` |

---

## 我犯的错误 (V007.45 dev-agent 反思)

| 错误 | 反思 |
|------|------|
| 只审 `meta/` 工作树, 没审 `deploy_bundle/meta/` | **dev-agent 工作树 ≠ 部署包, 必须两个都看** |
| 没注意 commit 改的 8 个文件都在 deploy_bundle/ | **必须 `git show --name-only` 看完整文件列表** |
| 错误结论可能误导部署智能体 | **错误审查比没审查更危险** |
| 没核对 `git show 910022e` 的实际文件改动 | **审查第一步应是 git show 实际 diff, 不是看工作树** |

---

## 修正后的最终结论

**V007.44 文档声称的 6 个 FIX 全部已在 `deploy_bundle/` 真实实施**:

| FIX | 排查定位 | 修复实施 |
|-----|---------|---------|
| 1 | ✅ 成立 | ✅ 实施 (deploy_bundle) |
| 2 | ✅ 成立 | ✅ 实施 (deploy_bundle) |
| 3 | ✅ 成立 | ✅ 实施 (deploy_bundle) |
| 4 | ✅ 成立 | ✅ 实施 (deploy_bundle) |
| 5 | ✅ 成立 | ✅ 实施 (deploy_bundle) |
| 6 | ✅ 成立 | ✅ 实施 (deploy_bundle) |

**V007.44 是一份完整的"诊断 + 实施"部署文档**, 我之前的"0 实施"结论完全错误。

---

## 建议行动

1. **立即** 在 SECOND_REVIEW_V007_44.md / SECOND_REVIEW_V007_44_LOCATIONS.md 顶部加"本审查错误, 见纠正报告"
2. **不要** 按旧审查结论做 V007.46 修复任务清单
3. **V007.46 dev-agent** 用 910022e commit 作为 V007.44 已实施基准
4. **未来审查**: 始终先 `git show <hash> --name-only` 看实际改了哪些文件

---

**审查者**: V007.45 dev-agent  
**纠正时间**: 2026-07-08 18:50  
**纠正原因**: 之前审查范围错误, 漏看 deploy_bundle/ 子目录  
**结论纠正**: 6 FIX 全部已实施 ✅ | 不是 0 实施 ❌