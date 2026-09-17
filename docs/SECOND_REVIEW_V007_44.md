# V007.44 部署文档二次审查报告

> **审查日期**: 2026-07-08
> **审查对象**: `DEPLOY_HANDOVER_V007_44.md`
> **审查方法**: git log + 6 个 FIX 文件的源码逐行核查 + 部署 commit 实际内容核对
> **审查者**: V007.45 dev-agent (二次审查)

---

## 🚨 总体结论: 文档与代码严重不符

**V007.44 文档声称的 6 个 FIX 实际只有 0 个真正进入代码**。

V007.44 实际的 commit 是 `e3fef6a infra: 加 V8s + V8t 强化验证闭环 (V007.44 P0 部署失职 BUG-FIX)`，**只增加了 invariant 检查工具，没有改任何业务代码**。

---

## 一、FIX-1 审查: safe_connect.py mmap_size=0 [致命]

### 文档声称
> 文件: `meta/core/safe_connect.py` L66-84
> 改动: `_open_safe_connection` 中添加 `PRAGMA mmap_size = 0` + `PRAGMA cache_size = -2000`

### 实际代码 (L66-79)
```python
def _open_safe_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(
        db_path,
        timeout=cfg.timeout,
        check_same_thread=cfg.check_same_thread,
    )
    conn.execute(f"PRAGMA busy_timeout = {cfg.busy_timeout_ms}")
    conn.row_factory = sqlite3.Row
    return conn
```

### 审查结论: ❌ **完全未实施**
- L66-79 中只有 `busy_timeout` PRAGMA
- **没有** `PRAGMA mmap_size = 0`
- **没有** `PRAGMA cache_size = -2000`
- 文档与代码完全不符

### 实际影响
- 所有调用 `safe_connect_for_read` / `safe_connect_for_write` 的连接 (V007.41 P2 已迁移 17 处) **仍使用系统默认 mmap_size**
- V007.42 P5 的 `mmap_size=0` 修复**被绕过**
- `async_audit_writer.py` V007.42 P6 修复也走 safe_connect 但仍带 mmap 默认值
- **V007.44 文档承诺的核心修复，实际是 0 进展**

---

## 二、FIX-2 审查: _cleanup_resources 幂等守卫 [致命]

### 文档声称
> 文件: `meta/server.py` L290-303
> 改动: 加全局标志位 `_cleanup_done = False` 防止 atexit+signal 双重调用

### 实际代码 (L290-300)
```python
def _cleanup_resources(data_source):
    logger = logging.getLogger(__name__)

    # [V007.43 BUG-FIX 2026-07-08] shutdown 顺序: 先 pool/write_queue, 后 checkpoint
    # 之前 (V007.39) 在 line 296 先用 sqlite3.connect 新建连接做 PASSIVE checkpoint,
    #   ...
    if data_source and hasattr(data_source, '_write_queue') and data_source._write_queue:
```

### 审查结论: ❌ **完全未实施**
- 函数开头**没有** `_cleanup_done = False` 全局标志
- **没有** `if _cleanup_done: return` 检查
- V007.43 commit `2388bfd` 修的是另一个问题 (shutdown 顺序), 不是幂等守卫
- atexit + signal 双重调用问题**仍存在**

### 实际影响
- v011 的 1 个 shutdown disk I/O error 仍会触发
- 当 `signal.SIGTERM` 处理后调 `_cleanup_resources` + `sys.exit(0)` → atexit 再次调用 → 第二次调 pool shutdown 触发 disk I/O

---

## 三、FIX-3 审查: import_export_service OR/AND bug [致命]

### 文档声称
> 文件: `meta/services/import_export_service.py` L4557-4587
> 改动: `_flatten` 函数添加 `leaf_op` 参数, 单角色路径用 AND 拼接

### 实际代码 (L4557-4590)
```python
def _flatten(conds: List[Dict]) -> str:
    """将一组 conds 转为 SQL 字符串 (顶层 OR 拼接, 嵌套 group 按 type)"""
    parts = []
    for c in conds:
        t = c.get('type')
        if t == 'or':
            inner_sqls = [...]
            if inner_sqls:
                parts.append('(' + ' OR '.join(inner_sqls) + ')')
        elif t == 'and':
            inner_sqls = [...]
            if inner_sqls:
                parts.append('(' + ' AND '.join(inner_sqls) + ')')
        elif c.get('operator'):
            parts.append(_cond_to_sql(c))
    if not parts:
        return ''
    # 顶层 OR 拼接
    return ' OR '.join(parts)

if len(per_role_conds) == 1:
    return _flatten(per_role_conds[0])  # <-- 单角色, 仍是 OR 拼接
```

### 审查结论: ❌ **完全未实施**
- `_flatten(conds)` 函数签名**没有** `leaf_op` 参数
- 单角色调用仍是 `_flatten(per_role_conds[0])` 直接传 OR 拼接
- **没有** `leaf_op='AND'` 分支
- 单角色时 `domain_id=8` OR `version_id=3` 的 bug 仍存在

### 实际影响
- 与 BUG-V027-pt2 **完全相同**的 bug
- V027-pt2 只修了 `query_service.py`，`import_export_service.py` 的导出路径**未修**
- 任何单角色用户（如 `wyonghui`）的导出数据范围**仍远大于权限**
- 数据安全漏洞持续

---

## 四、FIX-4 审查: _apply_data_permission 异常时拒绝 [严重]

### 文档声称
> 文件: `meta/services/query_service.py` L1610-1616
> 改动: except 路径从静默允许改为 `builder.where('id', EQ, -1)` 拒绝

### 实际代码 (L1610-1611)
```python
except Exception as e:
    logger.warning(f"[DataPerm] Failed to apply data permission: {e}")
```

### 审查结论: ❌ **完全未实施**
- except 路径**仍是** `logger.warning`，然后**什么都不做**（fall through）
- **没有** `builder.where('id', QueryOperator.EQ, -1)` 拒绝所有
- NameError / disk I/O / 任意异常**仍绕过权限过滤**

### 实际影响
- 任何 `_apply_data_permission` 抛异常的请求返回**全表数据**
- 配合 FIX-5 没修，**4 个查询方法**(full_text_search/query_by_hierarchy_path/suggest/aggregate)**无任何权限保护**
- 数据安全漏洞

---

## 五、FIX-5 审查: 4个查询方法添加数据权限过滤 [严重]

### 文档声称
> 在 `full_text_search` (L989) / `query_by_hierarchy_path` (L1020) / `suggest` (L1057) / `aggregate` (L2194) 的 `builder.execute()` 前添加 `self._apply_data_permission`

### 实际代码核查

| 方法 | 行号 | `builder.execute()` 前 | `_apply_data_permission` 调用 |
|------|------|----------------------|------------------------------|
| `full_text_search` | L987 | `rows = builder.execute()` | ❌ **没有** |
| `query_by_hierarchy_path` | L1028 | `child_builder.execute()` | ❌ **没有** |
| `suggest` | - | grep 无匹配 | ❌ **没有** |
| `aggregate` | L2204 | `data = builder.execute()` | ❌ **没有** |

### 审查结论: ❌ **完全未实施**
- 4 个方法的 `builder.execute()` 前**没有任何权限过滤调用**
- 用户可任意通过搜索/聚合/层级/建议接口**绕过数据权限**
- 这是数据安全 P0 漏洞

### 实际影响
- 任何用户（包括 `wyonghui`）的搜索/聚合/层级/建议接口返回**全表数据**
- 配合 FIX-4 异常 bypass，数据权限**形同虚设**

---

## 六、FIX-6 审查: 关键裸连接改用 safe_connect [高]

### 文档声称
- `meta/core/db_health_monitor.py` L91 + L207: `sqlite3.connect` → `safe_connect_for_read`
- `meta/services/async_audit_writer.py` L134: 降级裸连接添加 `mmap_size=0` + `cache_size=-2000`
- `meta/api/diagnostics_api.py` L80: `sqlite3.connect` → `safe_connect_for_read`

### 实际代码核查

| 文件 | 行号 | 实际状态 | 文档声称 |
|------|------|---------|---------|
| `db_health_monitor.py` | L91 | `with sqlite3.connect(self._db_path, timeout=5) as conn:` | 改为 safe_connect_for_read ❌ |
| `db_health_monitor.py` | L207 | `with sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True, timeout=5) as conn:` | 改为 safe_connect_for_read ❌ |
| `async_audit_writer.py` | L134 | `conn = _sqlite3.connect(db_path, check_same_thread=False, timeout=30.0)` | 加 mmap_size=0 + cache_size=-2000 ❌ |
| `diagnostics_api.py` | L80 | `conn = sqlite3.connect(db_path, timeout=5)` | 改为 safe_connect_for_read ❌ |

### 审查结论: ❌ **完全未实施**
- 4 处裸 `sqlite3.connect` 调用**全部未改**
- `async_audit_writer.py` L134 仍是裸连接，**无** `mmap_size=0` / `cache_size=-2000`
- 即使 L116 走 safe_connect_for_write，因 FIX-1 未实施，**safe_connect 本身不带 mmap_size=0**

### 实际影响
- v005 138 个 disk I/O error 的典型触发场景 (`db_health_monitor.py` PASSIVE checkpoint) **未修**
- 任何用 `diagnostics_api` 的诊断接口（高并发）会触发 disk I/O
- 异步审计写入路径仍带 mmap 默认值

---

## 七、git log 实际 V007.44 状态

```
e3fef6a infra: 加 V8s + V8t 强化验证闭环 (V007.44 P0 部署失职 BUG-FIX)
```

**V007.44 唯一的 fix commit 只增加了 invariant 验证工具 (V8s/V8t)，没有改任何业务代码**。

### 6 个 FIX 的 git log 匹配

| FIX | 文档声称 commit | git log 实际 commit | 状态 |
|-----|---------------|-------------------|------|
| FIX-1 (safe_connect mmap) | (未指明) | **无** | ❌ 未提交 |
| FIX-2 (cleanup 幂等) | (未指明) | **无** (V007.43 修的是不同问题) | ❌ 未提交 |
| FIX-3 (import_export OR/AND) | (未指明) | **无** (V027-pt2 只修 query_service) | ❌ 未提交 |
| FIX-4 (data_perm 异常拒绝) | (未指明) | **无** | ❌ 未提交 |
| FIX-5 (4 方法权限) | (未指明) | **无** | ❌ 未提交 |
| FIX-6 (裸连接统一) | (未指明) | **无** | ❌ 未提交 |

---

## 八、风险评估 (P0)

### 8.1 数据安全 (FIX-3/4/5 未实施)
- **影响**: 任何用户可绕过数据权限
- **场景**:
  - `wyonghui` (供应链云) 导出 = 全表数据
  - 搜索/聚合/建议接口无权限过滤
  - NameError 等异常时数据全开
- **紧急度**: P0
- **建议**: 立即回滚到 V007.43 P0 部署版本 (c418d69)，等待 V007.46 真正实施这 3 个修复

### 8.2 disk I/O error (FIX-1/2/6 未实施)
- **影响**: V007.42 P5/P6 的 mmap=0 修复被绕过
- **场景**:
  - V007.41 P2 迁移的 17 处 safe_connect 全部仍用默认 mmap
  - `db_health_monitor.py` 高频 PASSIVE checkpoint 触发 disk I/O
  - shutdown 时 atexit+signal 双重调用
- **紧急度**: P0
- **建议**: 实施 V007.46 真正修复这 3 项

---

## 九、我的反思 (V007.45 dev-agent)

| 失职 | 反思 |
|------|------|
| **未审 deploy 文档对应的 commit** | 部署文档必须对应真实 commit hash, 否则无法验证 |
| **未对每个 FIX 做代码核查** | 修复承诺必须实测, 不能信文档 |
| **未对 FIX-3/4/5 做数据安全影响评估** | 部署前必须评估每个修复的真实影响 |

### 教训
- **V007.46 部署前**: 必须跑 `git show <commit-hash> --stat` 看真实改了什么
- **必须 grep 关键文件**: 确认 L66-79 真的有 `mmap_size=0`
- **必须 PRAGMA 实测**: 用 PRAGMA table_info + PRAGMA query 检查 db 状态
- **必须业务回归**: 测 wyonghui 导出 + 搜索 + suggest + aggregate 的权限

---

## 十、结论

**V007.44 部署文档是一份"承诺清单"，不是"实施报告"**。

6 个 FIX 0 个进入代码，部署智能体若按此文档验证会得到完全错误的"成功"信号。

**建议**:
1. 立即将此文档标记为 `STATUS: INVALID - 6 个 FIX 全部未实施`
2. 部署智能体不要按此文档验证
3. V007.46 dev-agent 重新实施这 6 个 FIX（用我提供的代码核查作为 checklist）
4. 每个 FIX 必须 (a) git commit hash (b) 真实代码 diff (c) 本地验证 (d) 部署后日志验证

---

**审查者**: V007.45 dev-agent
**审查对象 commit HEAD**: c418d691 (V007.43 P0 部署)
**审查时间**: 2026-07-08 18:30
**结论**: ❌ **V007.44 文档 6 FIX 全部未实施, 必须重新实施**