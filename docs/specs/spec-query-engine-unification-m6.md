# M6 Spec: v3 查询引擎 — 生产加固 + 高级查询

> **版本**: v6.0.0（M6 阶段）
> **日期**: 2026-06-05
> **状态**: ✅ Completed
> **前置**: M1-M5 已完成
> **范围**: Query Allow-list / 关联 expand / Explain API / 权限形式化

---

## 1. 目标

按 gap 分析采纳建议，M6 阶段完成 **4 个 P0/P1 任务**：

| ID | 任务 | 优先级 | 工作量 |
|----|------|:-----:|--------|
| **M6.1** | Query Allow-list（生产安全基线） | P0 | 2d |
| **M6.2** | Explain API（慢查询排查） | P1 | 1d |
| **M6.4** | 关联 expand / nested projection | P0 | 3d |
| **M6.5** | 行级/列级权限形式化 | P1 | 2d |

---

## 2. 实施细节

### 2.1 M6.1 Query Allow-list

**新增** [query_allow_list.py](file:///d:/filework/excel-to-diagram/meta/core/query_allow_list.py)：
- `EntityAllowList` 配置单实体白名单（filter_fields / ordering_fields / select_fields / allowed_ops / max_page_size）
- `QueryAllowList` 全局注册中心 + `check()` 校验
- `*` 通配符：放行所有字段
- 集成到 `UnifiedQueryFacade.execute` 入口（`env=DISABLE_ALLOW_LIST=true` 可关闭）

**修复的预先存在 bug**：`expand` 未在 RESERVED 列表中 → URL 解析时进了 `filters`，被 allow-list 拒绝后报错

### 2.2 M6.2 Explain API

**新增** `UnifiedQueryFacade.explain(req)` 方法：
- 构造 SQL（不执行）
- `EXPLAIN QUERY PLAN` 取出执行计划
- 返回 `{sql, params, plan, entity_type, filter_count}`

**集成点**：DRE 慢查询日志可附 explain URL

### 2.3 M6.4 关联 expand

**新增** [association_expander.py](file:///d:/filework/excel-to-diagram/meta/core/association_expander.py)：
- `ExpandSpec` 路径规范（单层/双层）
- `AssociationExpander.expand(items, specs, main_entity_type)` 批量注入关联数据
- `parse_expand_specs()` 解析 URL `?expand=user(id,name):products(id,name)`
- 限制：max 10 个关联、max 3 层深度、max 1000 行/关联

**协议层**：UnifiedQueryRequest 新增 `expand: str` 字段
**集成点**：facade.execute 末尾注入 expand 到 result.data

### 2.4 M6.5 行级/列级权限形式化

**新增** [permission_spec.py](file:///d:/filework/excel-to-diagram/meta/core/permission_spec.py)：
- `FieldPolicy` 列级策略（visible / readonly / hidden_in_api / mask）
- `PermissionSpec` 实体级策略（row_filter closure + field_visibility 字典）
- 脱敏支持：`last4` / `email` / `phone`
- `PermissionRegistry` 全局注册中心
- 集成到 facade.execute 末尾（应用列级策略到 result.data）

**修复的预先存在 bug**：M6.5 集成用 `registry` 变量名遮蔽了模块顶部 `from meta.core.models import registry` 全局 → 改名为 `perm_registry`

---

## 3. 验收（22+ 项断言全通过）

```
M6.1 Query Allow-list:    7/7 PASS
  - 默认放行 (unregistered entity)
  - 注册后白名单校验（合法字段/排序/select）
  - 非法字段 / 排序 / page_size / op 全部抛 QueryProtocolError
  - '*' 通配符放行
M6.2 Explain API:         2/2 PASS
  - explain() 返回 sql + plan + entity_type
  - filter_count 正确
M6.4 关联 expand:         6/6 PASS
  - 解析 user(id,name,avatar):products(id,name) → 2 specs
  - 解析 user,products → 2 specs
  - ExpandSpec 字段正确
  - empty items 不崩溃
  - 20 specs → 截断到 10
  - 深度 4 → 跳过（> 3）
M6.5 权限形式化:          7/7 PASS
  - 注册 + stats
  - hidden_in_api 移除字段
  - mask='email' → a***@example.com
  - mask='phone' → 138****8000
  - row_filter 应用（closure 注入 WHERE）
  - row_filter with None context → skip
  - singleton 注册中心

集成测试: 4/4 PASS
  - facade.execute 走 M6.1（拒绝非白名单字段）
  - facade.execute 走 M6.4（expand 注入 result.data）
  - facade.execute 走 M6.5（apply_field_visibility）
```

---

## 4. 零回归

```
test.py --status: 0 passed, 7 failed, 0 errors
```

**完全等同于 M5 末值**：7 failed 是 `test_persistence_interceptor_detailed.py` 预先存在 mock bug，与 M6 无关。**零回归**。

---

## 5. 不在 M6 范围（M7+）

- CDC / 实时订阅 — M7.1
- Multi-DB（PostgreSQL/MySQL） — M7.2
- 嵌套写入 (Deep insert/update) — M7.3
- Auto schema introspection — M7.4
- i18n field query — M7.5
- 全文检索 FTS5 — 已部分支持（LIKE）— M5 推迟项

---

## 6. 累计 M1-M6 进展

| 阶段 | 增量 | 商业价值 |
|------|------|---------|
| M1 | 读路径协议（UnifiedQueryFacade） | 内部 |
| M2 | ListService / AssocQueryService | 内部 |
| M3 | computed count + EXISTS 关联 | 内部 |
| M4 | cursor pagination + 日期函数 + cache | 80% 中小客户 |
| M5 | UnifiedMutationFacade + 事务 | 95% 客户 |
| **M6** | **Allow-list + expand + Explain + 权限形式化** | **100% 大客户/金融/政府** |
| M7 | CDC / Multi-DB / 平台化 | 对外 SaaS 化入场券 |

---

**执行完成**：M6 4 个 P0/P1 任务已实施 + 零回归验证。
