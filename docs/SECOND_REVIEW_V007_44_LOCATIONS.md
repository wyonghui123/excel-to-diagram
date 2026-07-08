# V007.44 排查定位合理性评估 (二次审查)

> **审查日期**: 2026-07-08
> **审查方法**: 文档声称的"问题定位"逐项代码核查 + git log 对比
> **审查者**: V007.45 dev-agent
> **前置文档**: `docs/SECOND_REVIEW_V007_44.md` (代码层面), `DEPLOY_HANDOVER_V007_44.md` (原始文档)

---

## 核心结论

**V007.44 文档的 6 个"排查定位"（"之前为何没发现"列）全部成立，但**对应的修复（"修复清单"部分）**0 个进入代码**。

| # | 排查定位 | 定位合理性 | 修复是否实施 |
|---|---------|-----------|------------|
| A | safe_connect.py 缺 mmap_size=0 | ✅ 完全成立 | ❌ 未实施 |
| B | _cleanup_resources 双重调用 | ✅ 完全成立 | ❌ 未实施 |
| C | import_export OR/AND bug | ✅ 完全成立 | ❌ 未实施 |
| D | _apply_data_permission 异常 bypass | ✅ 完全成立 | ❌ 未实施 |
| E | 4 个查询方法无权限 | ✅ 完全成立 | ❌ 未实施 |
| F | 多处裸连接无 mmap_size=0 | ✅ 完全成立 | ❌ 未实施 |

**判断**: 排查定位是对的，但修复是空的。

---

## 一、逐项排查定位合理性

### 1-A: safe_connect.py 缺 mmap_size=0 ✅ 成立

**文档说法**:
> "V007.42 在 pool 加了, 但新引入的 safe_connect 工厂漏了"

**代码核查**:
- V007.42 P5 commit `bf4a106` 改 `sql_connection_pool.py` 加 `mmap_size=0`
- V007.41 P2 commit `f9ca212` 迁移 17 处 L0 到 `safe_connect_for_read/write`
- 当前 `meta/core/safe_connect.py` L77: **只有** `PRAGMA busy_timeout`，**无** `PRAGMA mmap_size = 0`

**合理性判断**:
- ✅ 定位完全正确
- ✅ 因果链清晰: V007.41 P2 引入新工厂但未带 mmap_size=0 → V007.42 P5 改 pool 时**漏掉**新工厂
- ✅ 17 处 L0 全部走 safe_connect，**V007.42 P5 的 mmap=0 修复被绕过**

### 1-B: _cleanup_resources atexit+signal 双重调用 ✅ 成立

**文档说法**:
> "atexit+signal 双重调用: shutdown 时 disk I/O"

**代码核查** (server.py L928-930):
```python
atexit.register(lambda: _cleanup_resources(data_source))                  # L928
signal.signal(signal.SIGTERM, lambda s, f, ds: _signal_handler(s, f, ds))  # L929
signal.signal(signal.SIGINT, lambda s, f, ds: _signal_handler(s, f, ds))   # L930
```

`_signal_handler` (L344-347):
```python
def _signal_handler(signum, frame, data_source=None):
    _cleanup_resources(data_source)
    sys.exit(0)  # 触发 atexit → 第二次 _cleanup_resources
```

**合理性判断**:
- ✅ 双重调用路径**完全成立**
- ✅ 第二次调用时 pool 已关闭 → PASSIVE checkpoint 触发 disk I/O error
- ✅ 这是 v011 shutdown disk I/O error 的直接原因

### 1-C: import_export_service.py OR/AND bug ✅ 成立

**文档说法**:
> "BUG-V027-pt2 只修了 query_service.py, 没修 import_export"

**代码核查**:

| 文件 | 函数 | 状态 |
|------|------|------|
| `query_service.py` L1753-1902 | `_try_apply_dimension_scope` | ✅ BUG-V027-pt2 已修 (单 role AND 段走 where_raw) |
| `import_export_service.py` L4557-4590 | `_flatten` | ❌ **未修**，单角色仍走 OR 拼接 |

**合理性判断**:
- ✅ 文档说的"BUG-V027-pt2 只修了 query_service.py"**完全正确**
- ✅ import_export 的 `_flatten(conds)` 仍是 `' OR '.join(parts)` 简单拼接
- ✅ 单角色场景下, `domain_id=8` OR `version_id=3` 与 query_service 的修复**不一致**

### 1-D: _apply_data_permission 异常 bypass ✅ 成立

**文档说法**:
> "NameError 等异常绕过权限: 只修了 Tuple import, 没修 except 的降级策略"

**代码核查** (query_service.py L1610-1611):
```python
except Exception as e:
    logger.warning(f"[DataPerm] Failed to apply data permission: {e}")
    # 没有任何 builder.where / builder.where_in → 方法结束, builder 无过滤
```

**关键点**:
- L1539-1609 try 块内**任何**异常 → fall through 到 L1611 logger.warning
- 方法结束，**builder 无任何修改**
- 对比 `data_permission_filter.py:33` 异常时返回 `id = -1` 拒绝所有 (V007.44 文档已正确指出)
- V007.44 文档**没有**提到 V027-pt3 修了 Tuple import，但 except 仍 fallback

**合理性判断**:
- ✅ 排查定位完全成立
- ✅ BUG-V027-pt3 (commit `b46fe80`) 只修了 `from typing import Tuple` 缺失问题
- ✅ **没有**改 except 分支的降级策略
- ✅ 任何 try 块异常 → 静默 fall through → 无权限过滤

### 1-E: 4 个查询方法无权限过滤 ✅ 成立

**文档说法**:
> "只关注 search 路径, 没审查其他公开方法: full_text_search/query_by_hierarchy_path/suggest/aggregate"

**代码核查**:

| 方法 | 行号 | `_apply_data_permission` 调用 | 文档声称 |
|------|------|------------------------------|---------|
| `full_text_search` | L987 | ❌ 无 | 4 个方法需加 ✅ |
| `query_by_hierarchy_path` | L1028 | ❌ 无 | 同上 ✅ |
| `suggest` | L1049 | ❌ 无 | 同上 ✅ |
| `aggregate` | L2204 | ❌ 无 | 同上 ✅ |

**合理性判断**:
- ✅ 4 个公开方法**确实**没调用 `_apply_data_permission`
- ✅ grep 全文件, 这些方法都直接 `builder.execute()` 无权限过滤
- ✅ V007.44 文档的"只关注 search 路径"自我批评**完全成立**

### 1-F: 多处裸连接无 mmap_size=0 ✅ 成立

**文档说法**:
> "只改了 pool, 没改 health_monitor/diagnostics 等"

**代码核查**:

| 文件 | 行号 | 当前代码 | 是否有 mmap_size=0 |
|------|------|---------|-------------------|
| `db_health_monitor.py` | L91 | `sqlite3.connect(self._db_path, timeout=5)` | ❌ 无 |
| `db_health_monitor.py` | L207 | `sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True, timeout=5)` | ❌ 无 |
| `async_audit_writer.py` | L134 | `_sqlite3.connect(db_path, check_same_thread=False, timeout=30.0)` | ❌ 无 |
| `diagnostics_api.py` | L80 | `sqlite3.connect(db_path, timeout=5)` | ❌ 无 |

**合理性判断**:
- ✅ 4 处裸连接**确认**未改
- ✅ L91 `PRAGMA wal_checkpoint(PASSIVE)` 与 pool reader 并发 → 高频触发 disk I/O
- ✅ L207 `PRAGMA integrity_check` 全表扫描大 DB → 触发 disk I/O
- ✅ 排查定位"138 个 disk I/O error 的典型触发场景"**完全成立**

---

## 二、git log 实际 V007.44 状态

```
e3fef6a infra: 加 V8s + V8t 强化验证闭环 (V007.44 P0 部署失职 BUG-FIX)
```

**V007.44 唯一的 fix commit 只增加了 invariant 检查工具**:
- V8s: deploy_bundle 完整性检查
- V8t: zip 启动最低 API 路径检查

**这两个 invariant 的目的恰好是**: 防止 V007.43 P0 那种"部署时缺关键文件"和"server.py 启动 ImportError"问题复发。

但 V007.44 文档声称的 6 个代码修复, **git log 中完全没有对应 commit**。

---

## 三、排查定位 vs 修复承诺 的对比

| # | 排查定位（合理） | 修复承诺（文档） | 实际状态 |
|---|----------------|----------------|---------|
| A | safe_connect 缺 mmap_size=0 | 改 safe_connect.py L66-84 | ❌ 未改 |
| B | atexit+signal 双重调用 | 加 _cleanup_done 标志 | ❌ 未加 |
| C | import_export OR/AND bug | 加 leaf_op='AND' | ❌ 未加 |
| D | _apply_data_permission 异常 bypass | except 路径改 id=-1 | ❌ 未改 |
| E | 4 个方法无权限过滤 | 加 _apply_data_permission | ❌ 未加 |
| F | 多处裸连接无 mmap_size=0 | 改用 safe_connect | ❌ 未改 |

**结论**: **排查定位 100% 合理，但修复 0% 实施**。

这是 "诊断正确 + 处方未开" 的典型情况。

---

## 四、根因分析 (V007.45 dev-agent)

为什么 V007.44 会出现"诊断正确但修复未实施"？

### 4.1 流程性问题

1. **文档先行于代码**: 部署智能体在没真正写代码前就写了"修复清单"
2. **git commit 缺失**: 修复方案没有对应 commit hash，无法验证
3. **无集成验证**: 没有"修复后跑测试"的闭环
4. **发布前未做代码 diff**: 部署智能体未 `git show <commit>` 验证

### 4.2 与 V007.42/V007.43 对比

| 版本 | 诊断质量 | 修复实施 | 验证 |
|------|---------|---------|------|
| V007.42 | 优秀 (FR-001~010) | 优秀 (3 commits, 17/17 verify) | 优秀 |
| V007.43 P0 | 优秀 (get_bo_framework) | 优秀 (1 commit + V8q) | 优秀 (import chain 验证) |
| V007.44 | 优秀 (6 个定位全成立) | **0% 实施** | **0% 验证** |
| V007.45 | 优秀 (audit_logs created_at_epoch) | 优秀 (1 commit + V8u) | 优秀 (本地测试) |

**V007.44 是质量断崖** — 排查诊断水平正常，但**修复环节完全脱节**。

### 4.3 V007.44 可能的真实意图

部署智能体可能:
1. 想"先诊断，修复留给 dev-agent"
2. 但没明确说"留给 V007.46 dev-agent"
3. 写文档时把"修复清单"写得太像已实施
4. dev-agent (我) 在 V007.42 时未参与 V007.44，没接手修复

**责任分担**:
- **部署智能体**: 文档措辞模糊（"修复"vs"建议"不分）
- **V007.44 dev-agent (未指明)**: 修复未实施
- **V007.45 dev-agent (我)**: 未在 V007.45 接手 V007.44 修复（先做了 V007.45 P0 schema 修复）

---

## 五、给 V007.46 dev-agent 的行动建议

### 5.1 必须立即实施 (P0)

| FIX | 文件:行 | 改动 |
|-----|--------|------|
| A | `safe_connect.py:66-84` | `_open_safe_connection` 加 `PRAGMA mmap_size = 0` + `PRAGMA cache_size = -2000` |
| B | `server.py:290-303` | 加全局 `_cleanup_done = False` 标志 + `if _cleanup_done: return` |
| C | `import_export_service.py:4557-4590` | `_flatten` 加 `leaf_op='AND'` 参数, 单角色调用传 AND |
| D | `query_service.py:1610-1611` | except 路径加 `builder.where('id', EQ, -1)` 拒绝所有 |
| E | `query_service.py:987, 1028, 1049, 2204` | 4 个方法 `builder.execute()` 前加 `_apply_data_permission` |
| F | 4 处裸连接 | `db_health_monitor.py:91,207` / `async_audit_writer.py:134` / `diagnostics_api.py:80` 改 safe_connect |

### 5.2 每个 FIX 必须

1. **真实 commit hash**（不能用文档描述代替）
2. **代码 diff**（必须 `git show <hash>` 可看到）
3. **本地验证**（每个 FIX 跑单独测试）
4. **集成验证**（V8s + V8t + V8q + V8u 全 PASS）
5. **业务回归**（wyonghui 导出 + 4 个查询方法权限）

### 5.3 防退化 invariant (建议新增)

- **V8w**: 验证 safe_connect.py 包含 `mmap_size = 0` 字符串
- **V8x**: 验证 import_export_service._flatten 函数签名包含 `leaf_op` 参数
- **V8y**: 验证 query_service._apply_data_permission except 路径包含 `id.*-1` 模式

---

## 六、最终结论

**V007.44 文档质量是分裂的**:

| 维度 | 评估 |
|------|------|
| 排查定位 | ✅ **优秀** - 6 个根因全部代码可验证成立 |
| 修复实施 | ❌ **失败** - 0% 真正进入代码 |
| 部署智能体可执行性 | ❌ **不可执行** - 文档无 commit hash, 验证无 anchor |
| 数据安全性 | ❌ **危险** - wyonghui 导出 + 4 个查询方法仍 bypass 权限 |
| disk I/O 根除 | ❌ **未根除** - safe_connect + health_monitor + diagnostics 三处裸连接仍触发 |

**建议**:
1. **立即** 在文档头部加 "STATUS: 6 FIX 全部未实施, 待 V007.46 dev-agent"
2. **不要** 按此文档验证 V007.46 部署
3. **V007.46 dev-agent** 用本文档 + SECOND_REVIEW_V007_44.md 作为 V007.46 修复任务清单
4. **每个 FIX 必须有 commit hash 锚定**

---

**审查者**: V007.45 dev-agent
**审查方法**: 文档"排查定位"列 vs 代码实际状态 6 项逐项核查 + git log 全 commit 列表核对
**结论**: 排查定位 100% 合理 ✅ | 修复实施 0% ❌ | 必须 V007.46 重新实施