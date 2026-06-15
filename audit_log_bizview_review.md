# Audit Log 业务人员视角审查报告

**审查日期**：2026-06-15
**审查范围**：操作日志 Tab（List + Detail Drawer）
**审查角色**：业务人员（非技术）
**已修复的 P0/P2**：operation log tab 整体设计已业务化（操作类型 → 业务化文案、字段变更 → before/after、关联操作 → +/- 目标对象）

---

## 📋 总体评价

✅ **列表页**（AuditLog.vue）：**80% 业务化**，核心体验已经做到位
❌ **详情弹窗**（AuditLogDetail.vue）：**40% 业务化**，暴露了大量技术性字段
❌ **字段后端值**：**多个内部技术术语**（`object_type` / `_record` / `DELETE_BLOCKED`）暴露给业务人员

---

## 🔍 详情弹窗 (AuditLogDetail.vue) 技术性内容清单

**截图为证**：[domain_683_bizview_detail.png](file:///d:/filework/excel-to-diagram/domain_683_bizview_detail.png)、[sub_domain_68_bizview_detail1.png](file:///d:/filework/excel-to-diagram/sub_domain_68_bizview_detail1.png)、[relationship_35_bizview_detail1.png](file:///d:/filework/excel-to-diagram/relationship_35_bizview_detail1.png)、[user_group_8217_bizview_detail1.png](file:///d:/filework/excel-to-diagram/user_group_8217_bizview_detail1.png)

### ❌ 1. **IP** 127.0.0.1（4/4 详情页都出现）

**位置**：[AuditLogDetail.vue:35-38](file:///d:/filework/excel-to-diagram/src/components/common/AuditLogDetail/AuditLogDetail.vue#L35-L38)

```vue
<div class="ald-info-row" v-if="log.ip_address">
  <span class="ald-label">IP</span>
  <span class="ald-value ald-cascade-source">{{ log.ip_address }}</span>
</div>
```

**问题**：
- 业务人员**完全不需要** IP
- 127.0.0.1 是**本地回环**，暴露给业务人员毫无意义
- 真实生产 IP 反而是**安全风险**（暴露内网拓扑）
- `ald-cascade-source` 用了 tertiary 颜色让业务人员忽略，但**字段名 IP 还是直白显示**

**建议**：
- 业务视图：**完全隐藏 IP 字段**
- 管理员/审计员视图：通过 `?show_tech_info=true` 启用

---

### ❌ 2. **Trace** UUID（4/4 详情页都出现）

**位置**：[AuditLogDetail.vue:39-42](file:///d:/filework/excel-to-diagram/src/components/common/AuditLogDetail/AuditLogDetail.vue#L39-L42)

```vue
<div class="ald-info-row" v-if="log.trace_id">
  <span class="ald-label">Trace</span>
  <span class="ald-value ald-cascade-source">{{ log.trace_id }}</span>
</div>
```

**问题**：
- `Trace` 是**内部可观测性概念**（OpenTelemetry/分布式追踪）
- UUID 格式 `3e220831-ffa5-4419-b2cf-07c552937f5e` 业务人员看不懂
- 字段名 Trace 直白显示
- **业务价值**为 0（业务人员用不到）

**建议**：
- 业务视图：**完全隐藏**
- 运维视图：通过参数启用

---

### ❌ 3. **对象类型** annotation / sub_domain / relationship / user_group（4/4 详情页都出现）

**位置**：[AuditLogDetail.vue:23-26](file:///d:/filework/excel-to-diagram/src/components/common/AuditLogDetail/AuditLogDetail.vue#L23-L26)

```vue
<div class="ald-info-row" v-if="log.object_type">
  <span class="ald-label">对象类型</span>
  <span class="ald-value">{{ log.object_type }}</span>
</div>
```

**问题**：
- 业务人员**已经在详情页**，知道自己看的是哪个对象
- 显示 `annotation` / `sub_domain` 是**内部模型名**（不是业务术语）
- 业务人员期待看到的是"领域" / "子领域" / "业务关系" / "用户组" / "备注"（来自 yaml 的 `name` 字段）

**建议**：
- **翻译**：通过 `metaObjectMap[log.object_type]?.name` 查 yaml 的 `name` 字段
  - `annotation` → 备注
  - `sub_domain` → 子领域
  - `domain` → 领域
  - `relationship` → 业务关系
  - `user_group` → 用户组
  - `business_object` → 业务对象
  - `permission_rule` → 权限规则
- 或者**完全删除**（业务人员在详情页，重复信息）

---

### ❌ 4. **对象ID** 5 / 68 / 35 / 8217（4/4 详情页都出现）

**位置**：[AuditLogDetail.vue:27-30](file:///d:/filework/excel-to-diagram/src/components/common/AuditLogDetail/AuditLogDetail.vue#L27-L30)

```vue
<div class="ald-info-row" v-if="log.object_id">
  <span class="ald-label">对象ID</span>
  <span class="ald-value">{{ log.object_id }}</span>
</div>
```

**问题**：
- 业务人员已经在详情页 URL 看到 ID
- 显示 5/68/35/8217 业务人员**不知道对应什么**（子领域 68 = "TEST600"，但业务人员看到 ID 68 也反应不过来）
- **业务价值**为 0

**建议**：
- **完全删除**对象 ID 行
- 或者改成对象名称（通过 object_type + object_id 二次查询）但**性能成本高**

---

## 🔍 列表页 (AuditLog.vue) 技术性内容清单

### ❌ 5. **未知**（action 翻译缺失）

**位置**：[AuditLog.vue:521-523](file:///d:/filework/excel-to-diagram/src/components/common/AuditLog/AuditLog.vue#L521-L523)

```js
function formatAction(action) {
  const actionMap = {
    'CREATE': '创建', 'UPDATE': '更新', 'DELETE': '删除',
    'LOGIN': '登录', 'LOGOUT': '登出',
    'ASSOCIATE': '添加关联', 'DISSOCIATE': '移除关联',
    'ASSIGN': '分配', 'REVOKE': '撤销'
  }
  if (!action) return '未知'
  return actionMap[action] || '未知'  // ❌ 任何未在 map 里的 action 都显示"未知"
}
```

**问题**：
- 当 action 是 `DELETE_BLOCKED` / `AUDIT_WRITE_FAILED` / `LOGIN_FAILED` / `EXPORT` / `IMPORT` / `RESTORE` / `CASCADE_DELETE` / `BATCH_CREATE` / `BATCH_UPDATE` / `EXECUTE` 时，列表显示"未知"
- 截图证据：2026年6月15日 16:26 Admin (admin) **未知** 2 项变更
- 业务人员看到"未知"以为系统出错

**建议**：
- 扩展 actionMap：
  - `DELETE_BLOCKED` → "删除已阻止"
  - `EXPORT` → "导出"
  - `IMPORT` → "导入"
  - `RESTORE` → "恢复"
  - `CASCADE_DELETE` → "级联删除"
  - `BATCH_CREATE` → "批量创建"
  - `BATCH_UPDATE` → "批量更新"
  - `EXECUTE` → "执行"
- 或者**后端 audit_api 写日志时用业务化 action 名**

---

### ❌ 6. **_record** 字段名暴露

**位置**：audit_logs 表写入逻辑（[manage_service.py:114](file:///d:/filework/excel-to-diagram/meta/services/manage_service.py#L114)）

**问题**：
- 截图证据：`_record: (空) → DELETE_BLOCKED`
- `_record` 是**内部聚合字段名**（代表整个对象的 cud summary）
- 业务人员看到 `_record` 不知道是啥
- 显示 `(空) → DELETE` 也不直观

**建议**：
- **方案 A（推荐）**：列表页对 `field_name='_record'` 的项**整体隐藏**（业务上 "创建记录" 已经在 group header 表明）
- **方案 B**：翻译为 `变更摘要` / `记录级别`
- **方案 C**：删除时显示 "记录已删除" 而不是 `(空) → DELETE`

---

## 🔍 字段后端值问题

### ❌ 7. **`object_type` 后端值是英文模型名**（不是 yaml 的 name）

**数据证据**：
| 后端存 | 业务术语 | 用户看到 |
|--------|----------|----------|
| `annotation` | 备注 | annotation |
| `sub_domain` | 子领域 | sub_domain |
| `domain` | 领域 | domain |
| `relationship` | 业务关系 | relationship |
| `user_group` | 用户组 | user_group |
| `business_object` | 业务对象 | business_object |
| `permission_rule` | 权限规则 | permission_rule |
| `enum_type` | 枚举类型 | enum_type |

**建议**：
- 前端在显示前通过 `metaObjectMap` 翻译为 yaml `name` 字段
- 或者后端 audit_logs 表新增 `object_type_display` 列（写日志时直接存业务名）

---

### ❌ 8. **`user_name` 显示 "system" 而不是业务名**

**截图证据**：`2026年6月15日 16:16 system 更新 content: ...`

**位置**：audit_logs 表写入时 user_name 字段（[audit_service.py](file:///d:/filework/excel-to-diagram/meta/services/audit_service.py)）

**问题**：
- 后端写入的 user_name 是 "system"（系统操作，没有具体用户时）
- 业务人员看到 "system" 不知道是 AI/系统/脚本/批处理

**建议**：
- 业务化映射：
  - "system" → "系统" / "自动"
  - "admin" → 保留（实际用户）
  - "[REDACTED]" → 隐藏
- 或者通过 user_id 二次查询 display_name

---

### ❌ 9. **JSON 字符串原样显示**

**截图证据**：`content: {"value": "del@test.com"}` / `groups: {"target_type": "user_group", "target_id": 8217}`

**位置**：[AuditLogDetail.vue](file:///d:/filework/excel-to-diagram/src/components/common/AuditLogDetail/AuditLogDetail.vue) `parseTargetDisplay` 函数

**问题**：
- `old_value` / `new_value` 在数据库存的是 JSON 字符串 `{"value": "..."}`
- 业务人员看到 JSON 字符串看不懂
- 应当**展开 JSON 字段**为表格

**建议**：
- `parseTargetDisplay` 应处理：
  - `{"value": "xxx"}` → 显示 "xxx"
  - `{"target_display": "xxx", "target_type": "用户", "target_id": 1123}` → 显示 "xxx (用户)"
  - 已实现部分，但**未实现 `{"value": "..."}` 包装**（`[{"field": "value", "old": "x", "new": "y"}]` 也是）

---

## 🛠️ 改进建议（按优先级）

### P1 - 立即修复（影响业务人员理解）

| # | 建议 | 工作量 | 影响 |
|---|------|--------|------|
| 1 | **隐藏 IP 和 Trace 字段**（详情弹窗） | 0.5h | 4/4 详情页 |
| 2 | **翻译 `object_type` 英文**为 yaml `name`（详情弹窗 + 列表） | 1h | 4/4 详情页 + 列表 |
| 3 | **删除"对象ID" 行**（详情弹窗） | 0.2h | 4/4 详情页 |
| 4 | **扩展 actionMap** 处理 `DELETE_BLOCKED`/`EXPORT`/`IMPORT`/`RESTORE` 等 | 0.5h | 列表所有页 |
| 5 | **隐藏 `_record` 字段条目**（列表页） | 0.2h | 列表所有页 |

### P2 - 重要改进

| # | 建议 | 工作量 | 影响 |
|---|------|--------|------|
| 6 | **JSON 字符串展开**（`{"value": "..."}` → 业务值） | 1h | 列表 + 详情 |
| 7 | **user_name 业务化**（"system" → "系统"） | 0.3h | 所有页 |
| 8 | **添加 "技术信息" 折叠区** 给管理员/审计员 | 1h | 详情弹窗 |

### P3 - 体验优化

| # | 建议 | 工作量 | 影响 |
|---|------|--------|------|
| 9 | **空值友好显示**（`(空) → DELETE` → "记录已删除"） | 0.5h | 列表 |
| 10 | **添加字段说明 tooltip**（hover 显示字段业务含义） | 1h | 列表字段 |

---

## 📐 设计原则建议

### 1. **业务视图 vs 技术视图分离**

```
操作日志 Tab
├─ 业务人员视图（默认）
│   ├─ 时间
│   ├─ 操作人（业务名）
│   ├─ 操作（业务动词：创建/更新/添加关联）
│   ├─ 变更内容（业务字段 + 业务值）
│   └─ 折叠展开
│
└─ 技术信息（折叠或"详细信息"按钮，admin 可见）
    ├─ 对象类型（内部名）
    ├─ 对象ID
    ├─ IP
    ├─ Trace
    ├─ 事务ID
    └─ 错误信息
```

### 2. **后端写日志时即业务化**

不依赖前端翻译，**在 audit_logs 表新增 `object_type_display` / `action_display` 列**，写日志时直接存业务名：
- `object_type='annotation'` + `object_type_display='备注'`
- `action='DELETE_BLOCKED'` + `action_display='删除已阻止'`

**优点**：后端是 single source of truth，API/导出/列表/详情自动一致

### 3. **列表优先 + 详情补充**

- 列表 80% 业务人员能直接看懂
- 详情弹窗只展示**列表展开看不到的补充信息**，不要重复

---

## 📂 审查证据

- **截图（列表）**：
  - [domain_683_bizview.png](file:///d:/filework/excel-to-diagram/domain_683_bizview.png) — 领域 683 列表 ✅ 业务化
  - [sub_domain_68_bizview.png](file:///d:/filework/excel-to-diagram/sub_domain_68_bizview.png) — 子领域 68 列表 ✅ 业务化
  - [relationship_35_bizview.png](file:///d:/filework/excel-to-diagram/relationship_35_bizview.png) — 关系 35 列表 ✅ 业务化
- **截图（详情弹窗 - 含技术性内容）**：
  - [domain_683_bizview_detail.png](file:///d:/filework/excel-to-diagram/domain_683_bizview_detail.png) — IP + Trace + annotation + ID 5
  - [sub_domain_68_bizview_detail1.png](file:///d:/filework/excel-to-diagram/sub_domain_68_bizview_detail1.png) — IP + Trace + sub_domain + ID 68
  - [relationship_35_bizview_detail1.png](file:///d:/filework/excel-to-diagram/relationship_35_bizview_detail1.png) — IP + Trace + relationship + ID 35
  - [user_group_8217_bizview_detail1.png](file:///d:/filework/excel-to-diagram/user_group_8217_bizview_detail1.png) — IP + Trace + user_group + ID 8217

## 📊 修复后预估效果

| 修复后 | 业务人员能否理解 | 备注 |
|--------|----------------|------|
| 详情弹窗: 隐藏 IP/Trace/对象ID | ✅ 100% | 信息冗余，删除即可 |
| 详情弹窗: 翻译 object_type | ✅ 100% | 翻译为 yaml name |
| 列表: 扩展 actionMap | ✅ 95% | DELETE_BLOCKED 等业务化 |
| 列表: 隐藏 _record 字段 | ✅ 100% | 已在 group header 显示 |
| 详情: JSON 展开 | ✅ 90% | 业务值替代 JSON 字符串 |
