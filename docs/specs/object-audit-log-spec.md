# Spec: 对象视角审计日志三层查询增强与前端适配

> 版本: 2.0
> 日期: 2026-06-02
> 状态: 已确认

---

## 1. 背景与目标

### 1.1 背景

当前系统审计日志有两条数据通路：

| 通路 | 入口 | 查询范围 | 标注 | 使用者 |
|------|------|---------|------|--------|
| **A** | `manage_api.get_record()` → `get_object_history()` | L1+L2(parent) | `_parent_type`, `_cascade_from` | ChangeHistoryDialog |
| **B** | `useAuditLogs` → `fallback.query_audit_logs()` | L1+L2(parent) | **无** | **AuditLog.vue（主通路）** |

通路 B 是前端详情页审计日志 Tab 的实际数据来源（通过 `boService.queryAssociations('audit_logs')` → `GET /api/v2/bo/{type}/{id}/associations/audit_logs` → `fallback.py query_audit_logs()`）。其 SQL 查询为：

```sql
SELECT * FROM audit_logs
WHERE (object_type = ? AND object_id = ?)
   OR (parent_object_type = ? AND parent_object_id = ?)
ORDER BY created_at DESC
```

通路 B 存在三个缺口：

1. **无来源标注**：所有日志混在一起，用户无法区分"本条日志是本对象的操作"还是"子对象被级联删除了"还是"关联了其他对象"
2. **缺失模型配置子对象日志**：product 详情页看不到 version 的独立操作日志（非级联删除的日志）
3. **缺失关系参与方日志**：business_object 详情页看不到与其他 BO 关系变更的日志

### 1.2 三层日志模型

```
┌──────────────────────────────────────────────────────────────┐
│               对象视角审计日志 = 三层并集                     │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Layer 1: 对象自身日志                                       │
│   object_type=X AND object_id=Y                              │
│   → CREATE / UPDATE / DELETE / ASSOCIATE 等                  │
│                                                              │
│  Layer 2: 关联日志                                           │
│   parent_object_type=X AND parent_object_id=Y               │
│   ├─ FK 关联反向 (association_target)                       │
│   │   例: 查看 role 时，查出 user 的 ASSOCIATE 日志          │
│   └─ 级联删除子对象 (cascade_child)                          │
│       例: 查看 product 时，查出级联删除的 version DELETE 日志 │
│                                                              │
│  Layer 3: 子对象日志（模型配置）                               │
│   ├─ 3a: 级联子对象 → 已被 L2 覆盖                           │
│   ├─ 3b: 模型配置子对象的独立操作日志                         │
│   │   例: product → version 独立 UPDATE（非级联）             │
│   │   配置: product 只包含 version，不包含 domain             │
│   └─ 3c: 关系参与方日志 (relationship)                       │
│       例: BO_A → BO_B 的关系变更                              │
│       仅 business_objects 类型有此维度                        │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 1.3 业务目标

- 用户在对象详情页审计日志 Tab 中看到**完整的变更全景**
- 用户能**区分日志来源**（自身操作 / 关联操作 / 子对象变更 / 关系变更）

---

## 2. 需求类型概览

| 类型 | 适用 | 依据 |
|------|------|------|
| 业务需求 | 是 | 用户需要完整变更全景 |
| 用户/涉众需求 | 是 | 产品经理、架构师需要区分日志来源 |
| 解决方案需求 | 是 | 增强查询 + 前端标注 |
| 功能需求 | 是 | FR-001 至 FR-006 |
| 非功能需求 | 是 | NFR-001 分页兼容性 |
| 外部接口需求 | 是 | IF-001 前端组件适配 |
| 过渡需求 | 是 | TR-001 向后兼容 |

---

## 3. 功能需求

### FR-001: 三层日志完整查询

- **描述**：`fallback.query_audit_logs()` 必须返回三层日志的并集：
  - L1：`object_type=X AND object_id=Y`（自身日志）
  - L2：`parent_object_type=X AND parent_object_id=Y`（关联目标 + 级联子对象）
  - L3a：模型配置子对象的独立操作日志（如 product → versions 的 audit_logs）
  - L3b：关系参与方日志（如 business_object → relationships 的 audit_logs）
- **验收条件**：
  - product 详情页能显示其下 version 的独立 UPDATE 日志
  - business_object 详情页能显示涉及该 BO 的 relationship ASSOCIATE/DISSOCIATE 日志
  - 三个维度的日志在同一个分页列表中出现
- **优先级**：Must
- **类型映射**：Functional

### FR-002: `_source` 来源标注

- **描述**：查询返回的每条日志必须包含 `_source` 字段，取值为：

| 值 | 含义 | 示例 |
|----|------|------|
| `'own'` | 对象自身日志 | user CREATE/UPDATE/DELETE/ASSOCIATE |
| `'association_target'` | 对象作为 FK 关联的 target | role 视角看到 user ASSOCIATE role 的日志 |
| `'cascade_child'` | 级联删除的子对象日志 | product DELETE → version DELETE |
| `'child_object'` | 模型配置子对象的独立操作日志 | product 视角看到 version 独立 UPDATE |
| `'relationship'` | 对象参与的关系变更日志 | BO 视角看到 relationships 变更 |

- **验收条件**：
  - role 详情页中 user ASSOCIATE 标注为 `association_target`
  - product 详情页中 version 独立操作标注为 `child_object`
- **优先级**：Must
- **类型映射**：Functional

### FR-003: FK 关联的 many/one 判定

- **描述**：系统必须自动判断对象在 FK 关联中的角色并根据用户视角决定查询策略：
  - 对象是 many 侧（如 user 关联 role）→ L1 自然覆盖 ASSOCIATE 日志
  - 对象是 one 侧（如 role 被 user 关联）→ L2 通过 parent_object_type 反向查找
  - **不修改 FK 关联的审计日志写入口**（ASSOCIATE 日志始终写在 many 侧对象的 audit_log 中）
- **验收条件**：
  - user 详情页 → user ASSOCIATE role 的日志在 L1，标注为 `'own'`
  - role 详情页 → user ASSOCIATE role 的日志通过 L2 查出，标注为 `'association_target'`
- **优先级**：Must
- **类型映射**：Functional

### FR-004: 模型配置子对象包含

- **描述**：每个对象类型的审计日志视角配置如下（已确认）：

| 对象类型 | 包含的子对象 | 说明 |
|---------|------------|------|
| products | versions | 只包含版本，不包含 domain |
| versions | domains, business_objects | version 的直接子对象 |
| domains | sub_domains, business_objects | domain 的直接子对象 |
| business_objects | annotations | 备注 |
| roles | role_permissions | 角色权限 |

- **配置来源**：在 `fallback.py` 中声明 `AUDIT_CHILD_CONFIG`
- **验收条件**：
  - product 详情页包含 version 独立操作日志
  - product 详情页**不**包含 domain 日志
- **优先级**：Must
- **类型映射**：Functional

### FR-005: 关系参与方日志

- **描述**：business_object 作为 relationship 的 source 或 target 时，审计日志必须包含该 relationship 的变更记录
- **查询方式**：
  1. `SELECT id FROM relationships WHERE source_bo_id=? OR target_bo_id=?`
  2. 用查到的 relationship IDs → `WHERE object_type='relationships' AND object_id IN (...)`
- **验收条件**：
  - BO_A 和 BO_B 建立关系后，BO_A 和 BO_B 的详情页审计日志都包含该 relationship 的变更日志
- **优先级**：Should
- **类型映射**：Functional

### FR-006: 前端 AuditLog.vue 来源展示

- **描述**：AuditLog 组件根据 `_source` 字段展示来源标记，沿用 `al-cascade-from` 灰色文字风格
- **UI 设计**：

```
┌──────────────────────────────────────────────────────────┐
│ 2024-06-02 14:30   admin   更新                          │
│   name: 旧名称 → 新名称                                   │
│                                                            │
│ 2024-06-02 14:25   admin   添加关联                        │
│   roles: + 管理员（role）                    [来自关联]    │
│                                                            │
│ 2024-06-02 14:20   admin   更新                            │
│   version_number: v1.0 → v1.1               [version □]  │
│                                                            │
│ 2024-06-02 14:15   admin   删除                            │
│   删除记录                                     [级联操作]   │
└──────────────────────────────────────────────────────────┘
```

- **过滤选项新增**：
  - "关联操作" → 过滤 `_source === 'association_target'`
  - "子对象变更" → 过滤 `_source === 'child_object'`
  - "级联操作" → 过滤 `_source === 'cascade_child'`
- **优先级**：Should
- **类型映射**：Functional / External Interface

---

## 4. 非功能需求

### NFR-001: 分页兼容性

- **描述**：三层日志合并后支持分页，基于合并去重排序后的结果集
- **测量**：`?page=2&page_size=20` 返回正确偏移

### NFR-002: 查询降级

- **描述**：L3 子对象查询失败时，不影响 L1+L2 返回，仅缺失 L3 日志
- **测量**：子对象表查询异常时，审计日志 Tab 仍能展示 L1+L2

### NFR-003: 向后兼容

- **描述**：新增 `_source` 字段不破坏现有消费者
- **测量**：现有测试通过

---

## 5. 外部接口需求

### IF-001: 前端 AuditLog.vue

- **类型**：UI 组件
- **入口**：`:logs` prop（已有）
- **变更**：
  1. 新增 `_source` 字段解析 → 灰色文字来源标记
  2. `groupedLogs` 识别 `_source` 调整分组
  3. 新增过滤选项 "关联操作"、"子对象变更"、"级联操作"
- **样式**：沿用 `al-cascade-from` 灰色文字风格

### IF-002: 后端 fallback.py

- **类型**：API
- **端点**：`GET /api/v2/bo/{type}/{id}/associations/audit_logs`
- **变更**：`query_audit_logs()` 新增 L3 查询 + `_source` 标注
- **参数**：现有参数不变（page, page_size, action）
- **响应**：每条记录新增 `_source` 字段

---

## 6. 过渡需求

### TR-001: 向后兼容

- **描述**：`_source` 为新增字段，旧前端可忽略
- **策略**：新字段附加到响应中，不影响现有字段
- **回滚方案**：移除 `_source` 字段和 L3 查询逻辑即可回滚

---

## 7. 约束与假设

### 7.1 技术约束

- 子对象 ID 查询需额外 SQL（`SELECT id FROM <child_table> WHERE <parent_fk> = ?`）
- 分页在合并排序后执行，需先去重再分页
- `parent_object_type/parent_object_id` 在 FK 关联模式下承载了 target 信息

### 7.2 假设

- `parent_object_type/parent_object_id` 的语义覆盖 FK 关联反向查询 — 已验证 ✅
- `hierarchies.yaml` 的 FK 关系可推导直接子对象 — 已验证 ✅
- 子对象数量不会极大（每个 product 下不超过数百个 version）

---

## 8. 优先级与里程碑

| ID | 需求 | 优先级 |
|----|------|--------|
| FR-001 | 三层完整查询 | Must |
| FR-002 | _source 标注 | Must |
| FR-003 | many/one 判定 | Must |
| FR-004 | 模型配置子对象 | Must |
| FR-006 | 前端展示 | Should |
| FR-005 | 关系参与方 | Should |

**里程碑：**
- **M1**：后端 `_source` 标注 + L3 子对象查询（FR-001~FR-004）
- **M2**：前端 AuditLog.vue 适配 + 关系参与方（FR-005, FR-006）

---

## 9. 变更方案（RFC）

### 9.1 As-Is 分析

**通路 B（AuditLog.vue 实际数据来源）：**

```
useAuditLogs(type, id)
  → boService.queryAssociations(type, id, 'audit_logs')
    → GET /api/v2/bo/{type}/{id}/associations/audit_logs
      → bo_api → association_engine._dispatch()
        → fallback.query_audit_logs()
          SQL: WHERE (object_type,object_id) OR (parent_object_type,parent_object_id)
          无 _source 标注
          无 L3 子对象查询
          无 relationship 查询
```

**关键代码位置：**

| 文件 | 行号 | 说明 |
|------|------|------|
| `meta/core/association/fallback.py` | L91-145 | `query_audit_logs()` 核心查询 |
| `meta/services/audit_service.py` | L503-541 | `get_object_history()` |
| `src/composables/useAuditLogs.js` | L31 | 前端调用 `queryAssociations('audit_logs')` |
| `src/components/common/AuditLog/AuditLog.vue` | L1-871 | 前端展示组件 |
| `test_helpers/object_audit_verifier.py` | L1-579 | 测试验证器 |

### 9.2 目标架构

```
增强后 query_audit_logs():

1. L1 WHERE (object_type=? AND object_id=?)
   → _source='own'
  
2. L2 WHERE (parent_object_type=? AND parent_object_id=?)
   → ASSOCIATE/DISSOCIATE → _source='association_target'
   → 其他 → _source='cascade_child'

3. L3a 模型配置子对象
   AUDIT_CHILD_CONFIG → SELECT child_ids FROM child_table
   → WHERE (object_type,object_id) IN child_ids
   → _source='child_object'

4. L3b 关系参与方 (仅 business_objects)
   SELECT id FROM relationships WHERE source_bo_id=? OR target_bo_id=?
   → WHERE object_type='relationships' AND object_id IN rel_ids
   → _source='relationship'

5. 去重 + 按 created_at DESC 排序 + 分页
```

### 9.3 详细设计

#### 9.3.1 后端变更文件清单

| 文件 | 变更内容 |
|------|---------|
| `meta/core/association/fallback.py` | 增强 `query_audit_logs()`，新增 `AUDIT_CHILD_CONFIG`，新增 L3 查询，新增 `_source` 标注 |
| `meta/services/audit_service.py` | `get_object_history()` 同步增加 `_source` 标注 |
| `test_helpers/object_audit_verifier.py` | 增加 `_source` 字段验证 |

#### 9.3.2 前端变更文件清单

| 文件 | 变更内容 |
|------|---------|
| `src/components/common/AuditLog/AuditLog.vue` | 新增来源徽标展示，新增过滤选项，更新 `groupedLogs` 分组逻辑 |

#### 9.3.3 子对象查询 SQL 示例

```python
# product → versions
SELECT id FROM versions WHERE product_id = ?

# version → domains
SELECT id FROM domains WHERE version_id = ?

# version → business_objects  
SELECT id FROM business_objects WHERE version_id = ?

# business_objects → annotations
SELECT id FROM annotations WHERE target_type = 'business_object' AND target_id = ?

# roles → role_permissions
SELECT id FROM role_permissions WHERE role_id = ?

# business_objects → relationships (源端)
SELECT id FROM relationships WHERE source_bo_id = ?

# business_objects → relationships (目标端)  
SELECT id FROM relationships WHERE target_bo_id = ?
```

### 9.4 备选方案

| 方案 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| **A. 增强 fallback.py（选定）** | 最小改动，复用现有分页机制 | L3 查询需额外 SQL | ✅ 选定 |
| B. 新建专用端点 | 职责清晰 | 需新前端调用路径，改动大 | ❌ |
| C. 前端多次查询合并 | 后端零改动 | N+1 查询，分页困难 | ❌ |

### 9.5 实现计划

1. **Step 1**：增强 `fallback.py` — `AUDIT_CHILD_CONFIG` + L3 查询 + `_source` 标注
2. **Step 2**：同步增强 `audit_service.py` `get_object_history()` — `_source` 标注
3. **Step 3**：增强 `ObjectAuditLogVerifier` — 增加 `_source` 验证
4. **Step 4**：前端 `AuditLog.vue` 适配 — 来源徽标 + 过滤选项

### 9.6 测试策略

- 单元测试：`test_helpers/object_audit_verifier.py` 验证 `_source` 标注正确性
- 集成测试：通过 `useAuditLogs` 调用 BO v2 API 验证响应
- 回归测试：确保现有 `AuditLog.vue` 功能不受影响

---

## 10. TBD 列表

| ID | 项目 | 状态 |
|----|------|------|
| TBD-1 | product 子对象只包含 version | ✅ 已确认 |
| TBD-2 | 来源标记沿用 `al-cascade-from` 灰色文字风格 | ✅ 已确认 |
