# 排序功能修复与架构清理 — 待办追踪

> 修复日期：2026-06-10
> 涉及问题：列表页排序失效 / 多入口未同步 / 子查询重复代码

---

## 已完成

### 1. updated_at DESC 排序修复（Round 1-5）

| 日期 | 问题 | 根因 | 修复 |
|------|------|------|------|
| 2026-06-08 | DESC 排序结果乱序 | `_build_audit_derived_order_join` JOIN 中 `_audit_value=NULL` 无序 | 下沉 `COALESCE(_audit_sort._audit_value, table.created_at)` 到函数本体 |
| 2026-06-08 | Excel 导出排序失效 | 修复只覆盖列表页路径，导出走 `QueryService.search` 另一条路径 | 同上，下沉到共用函数 |
| 2026-06-08 | 前端列表页排序循环 | `filterService.js` `null` 被当作 `ascending`；`handleSortChange` 未重置分页；`el-table` 缺 `:sort` 绑定 | 3 处前端修复 |

**修复文件：**
- `meta/services/query/virtual_sort.py` — COALESCE 下沉
- `src/services/filterService.js` — null 状态处理
- `src/composables/useMetaList.js` — 分页重置
- `src/components/common/MetaListPage/MetaListPage.vue` — `:sort` 绑定

**验证：**
- 后端 ASC/DESC 排序正确
- 前端 E2E 三态循环 (desc→null→asc→desc) PASS

---

### 2. count_children 排序修复

| 日期 | 问题 | 根因 | 修复 |
|------|------|------|------|
| 2026-06-10 | 领域/子领域/服务模块的"关系数量/业务对象数量/服务模块数量"列排序失效 | `_execute_computed_field_query` 只处理 `count_relations`，`count_children` 被 fallback | 新增 `count_children` DB 排序分支 |

**修复文件：**
- `meta/services/query_service.py` — `_execute_computed_field_query` 新增 `count_children` 分支

**验证：**
- `GET /api/v2/bo/domain?ordering=-child_count` ✅ DESC 正确
- `GET /api/v2/bo/sub_domain?ordering=-child_count` ✅
- `GET /api/v2/bo/service_module?ordering=-child_count` ✅
- `count_relations` sort 无回归 ✅

---

### 3. 架构清理：computed_subqueries 模块

| 日期 | 问题 | 根因 | 修复 |
|------|------|------|------|
| 2026-06-10 | count_relations / count_children 的子查询逻辑在 query_service.py 中存在 3 处重复，易漏覆盖 | 未抽取共用函数 | 新建 `meta/services/query/computed_subqueries.py` 统一管理 |

**重构范围：**
- `query_service._execute_computed_field_query` — 22 行（vs 130 行内联）
- `query_service._apply_count_relations_filter` — 25 行（vs 87 行内联）
- `query_service._apply_count_children_filter` — 19 行（vs 33 行内联）

**新建文件：**
- `meta/services/query/computed_subqueries.py`

**验证：**
- count_children sort ✅
- count_relations sort ✅
- count_children filter ✅
- count_relations filter ✅
- 模块独立 import ✅

---

## 待补充测试

### A. 新增测试用例（优先级 P0）

- [ ] `meta/tests/test_sorting_capabilities.py` — 追加 `TestAuditDerivedFieldSortingExtended`（NULL audit 极端场景：全无/全有/混合）
- [x] `meta/tests/test_sorting_capabilities.py` — 追加 `TestCountChildrenSortRegression`（domain/sub_domain/service_module 三层 child_count sort）✅
- [ ] `meta/tests/test_import_export_api.py` — 追加 `TestExportSort`（导出 sort_by / sort_order）
- [ ] `meta/tests/test_sort_consistency_across_endpoints.py`（NEW）— 跨端点一致性（list / export / manage）
- [x] `meta/tests/test_computed_subqueries.py`（NEW）— `is_supported()` 矩阵测试 ✅ (Round 7)

### B. 测试优化（优先级 P1）

- [ ] `tests/e2e/test_frontend_sort_user_list.py` — inline 脚本 → proper pytest function
- [ ] `tests/e2e/test_backend_sort_check.py` — 断言提取到 pytest fixture
- [ ] 删除 `tests/e2e/test_backend_verify.py`（内容重复）
- [ ] 删除 `tests/e2e/test_raw_sql.py`（断言已并入 TestAuditDerivedFieldSortingExtended）

### C. 安全测试扩展（优先级 P1）

- [ ] `meta/tests/test_security_pentest.py` — INJECTION_PAYLOADS 扩展到所有端点（manage / export / query）
- [ ] 新增 `TestSortFieldLeakage` — 越权字段访问保护

### D. 性能测试（优先级 P2）

- [ ] 大数据量排序稳定性（100k 行，断言响应 < 2s）
- [ ] 跨页一致性（page5+）
- [ ] EXPLAIN QUERY PLAN 验证索引使用

---

## Round 6: *_count 过滤失效修复 (2026-06-10 11:30)

### 问题

5 个测试 fail：
- `TestCompositionCountFilter::test_domain_child_count_gte_filter` ❌
- `TestCompositionCountFilter::test_sub_domain_child_count_eq_filter` ❌
- `TestCompositionCountFilter::test_service_module_child_count_gte_filter` ❌
- `TestManyToManyCountSortFilter::test_domain_relation_count_gte_filter` ❌
- `TestCompositionCountSortRegression::test_version_child_count_sort_desc` ❌

### 根因分析

排查方向正确（"Ignoring unknown filter field: relation_count__gte"），但只看到表象，
**真正的 bug 是 `_try_build_computed_filter` 内部的早 return**：

```python
associations = getattr(meta_object, 'associations', None)
if not associations:
    return None, None
```

- domain/sub_domain/service_module 的 `associations = {}`（空 dict）
- 旧代码 `if not associations:` 命中 True → 早 return
- 后续 relations 循环 + `_try_build_count_relations_filter` 兜底都走不到

### 修复

[persistence_interceptor.py:1098-1111](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py#L1098-L1111)
```python
base_name = field_name[:-6]
table_name = meta_object.table_name

# [FIX 2026-06-10] 不要因 associations 为空就早 return！
# domain/sub_domain/service_module 的 relation_count (count_relations/descendants)
# 没有 m2m associations 段，但有 relations (composition) 和 computation.type，
# 必须 fallthrough 到下面的 relations 循环和 _try_build_count_relations_filter 兜底。
associations = getattr(meta_object, 'associations', None)
if isinstance(associations, dict):
    assoc_items = list(associations.values())
elif associations:
    assoc_items = list(associations)
else:
    assoc_items = []
```

同样的修复应用到 `_build_computed_count_sort_clause` (line 896-905)。

### 追加修复：version 漏掉

`test_version_child_count_sort_desc` 失败：`[ComputedSubqueries] count_children: unsupported object_type=version`

`version.yaml` 的 `child_count` 字段 `child_object: domain`，但 `_COUNT_CHILDREN_MAP` 没包含 version。

[computed_subqueries.py:106-112](file:///d:/filework/excel-to-diagram/meta/services/query/computed_subqueries.py#L106-L112)
```python
_COUNT_CHILDREN_MAP = {
    "version":        ("domains",          "version_id"),
    "domain":         ("sub_domains",      "domain_id"),
    "sub_domain":     ("service_modules",  "sub_domain_id"),
    "service_module": ("business_objects", "service_module_id"),
}
```

### 验证

- `test_sorting_capabilities.py`：**115 passed** (5 failed → 0 failed)
- `test_computation_by_semantics.py`：7 passed
- `test_filter_e2e.py`：10 passed
- `test_bo_api.py`：109 passed
- `test_persistence_interceptor_detailed.py`：27 passed
- `test_association_crud_operations.py`：15 passed

### 关键反思 (补充)

5. **早 return 是隐性陷阱**：`if not associations: return` 看似 defensive，
   实际截断了后续的 fallthrough 路径。`if not x: return` 应只在 `x` 是必要前置条件时使用，
   本场景 associations 不是必要前置（有 relations / computation 兜底）。

---

## Round 7: 服务层 P0 测试覆盖 (2026-06-10 20:00)

### 新增 3 个测试文件 (127 个新测试)

| 文件 | 测试数 | 覆盖 |
|------|------|------|
| [test_computation_service_unit.py](file:///d:/filework/excel-to-diagram/meta/tests/test_computation_service_unit.py) | 31 | computation_service 全部 count_* / formula / cache / merge |
| [test_computed_subqueries_matrix.py](file:///d:/filework/excel-to-diagram/meta/tests/test_computed_subqueries_matrix.py) | 50 | computed_subqueries 全部 SQL 字符串生成 + is_supported 矩阵 |
| [test_query_service_computed_unit.py](file:///d:/filework/excel-to-diagram/meta/tests/test_query_service_computed_unit.py) | 46 | query_service v3 路径的 computed 过滤/排序 + operator 矩阵 |

### TestCountChildren (7 测试)
- sub_domain/batch_count 正常路径
- 0 子节点返回 0 (不是 None)
- 无 target_object / unknown target_object / DB 异常 → 0 降级
- 多个 records + 缺 id 安全

### TestCountRelations (7 测试)
- business_object + self (3-table JOIN 等价)
- domain/sub_domain/service_module + descendants (3/2/1 表 JOIN)
- 不支持的 scope + object_type 返回 0
- DB 异常降级

### TestCountUserGroupMembers (4 测试)
- 正常批量计算
- 空 records / 全无 id 安全
- DB 异常填 0

### TestFormulaEvaluation (6 测试)
- 空 formula / 无 formula key → None
- 语法错误 → None
- 批量/无 records/未知 object_type 安全

### TestCacheInvalidation (3 测试)
- invalidate(specific) / invalidate() / 不存在 type 不报错

### TestMergeAndGetComputedColumns (4 测试)
- UI 配置优先 / 空入参 / 无 meta / 空 rules

### TestIsSupportedMatrix (24 测试) - 参数化矩阵
- count_relations: 11 组合 (BO/user_group + self, domain/sub_domain/sm + descendants 等)
- count_children: 7 组合 (version/domain/sub_domain/sm 支持, 其他不支持)
- 未知 comp_type: 8 测试

### TestBuildCountRelationsExpr (8 测试)
- BO self / user_group self / domain/sub_domain/sm descendants SQL 正确性
- 自定义 rel_table
- 不支持组合返回 None (5 参数化)

### TestBuildCountChildrenExpr (9 测试) - 参数化 FK 字段
- 4 个层级 object_type × FK 字段正确性 (regression: 之前用错字段名)
- 5 个不支持 object_type

### TestBuildCountSubqueryExprDispatch (4 测试)
- count_relations/count_children 入口分发
- 未知 comp_type 降级

### TestSqlSafety (3 测试)
- 无 "count_count" 拼写错误
- count_children 不含 relationships 表
- count_relations self 无 JOIN

### TestParseFilterValue (15 测试) - operator 矩阵
- `=`, `>`, `>=`, `<`, `<=`, `!=`, `=`, `5-20` between, `[a,b]` between
- `[a,b,c]` in
- 4 个无效格式降级

### TestBuildComputedWhereClause (10 测试) - operator 矩阵
- 6 个比较 operator
- between tuple / in list
- 未知 op → None

### TestApplyCountRelationsFilter (6 测试)
- BO self / domain descendants 成功
- 不支持 scope / object_type → False (不调 where_raw)
- DB 异常 / 未知 op → False

### TestApplyCountChildrenFilter (4 测试)
- domain / sub_domain 成功
- 不支持 object_type → False
- DB 异常 → False

### TestApplyComputedFieldFilter (10 测试)
- dispatch count_relations / count_children
- 4 种 filter_value 格式 (`>=1` / `5-10` / `[3]` / `[3,10]`)
- 不支持 comp_type / 无效 value → False
- 异常 → False

### 关键价值

✅ **直接覆盖了 Round 6 修复路径**：_try_build_count_relations_filter / _try_build_count_children_filter / _apply_count_relations_filter / _apply_count_children_filter
✅ **回归保护**：如果未来再误删 early return 或 FK 字段名回退, 这些测试会立即报错
✅ **operator 矩阵完整**: `__gte/__lte/__gt/__lt/__eq/__ne/__in/between` 全部覆盖

### 验证

- 3 个新文件: 127 passed
- 回归 (test_computation_aggregation.py): 18 passed
- 回归 (test_sorting_capabilities.py): 115 passed

### 下一阶段 (P1, 可选)

- [ ] test_list_service_v2.py - ListService / UnifiedQueryFacade v2 路径
- [ ] test_computed_subqueries_integration.py - 跟真实 DB 联跑 SQL
- [ ] test_computation_service_with_real_db.py - 用 conftest 真实 DB 测 count_*

---

## 关键反思

1. **NULL 排序是隐性陷阱**：`ORDER BY _audit_value` 中 NULL 无序，下次遇到类似场景应主动制造"全 NULL"数据集验证
2. **多入口必须搜全调用方**：修复共用函数后必须 `grep -r` 所有调用点
3. **子查询逻辑多处重复**：已通过 computed_subqueries.py 统一，下次新增 comp_type 时只改一处
4. **测试覆盖与实现分支对应不足**：yaml 中有多少种 `computation.type`，测试就应有多少条分支覆盖
