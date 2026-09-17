# 二次全面审查报告 (2026-08-29)

> 审查对象: Spec 16 全 Plan (A → B → C → D) 实施结果
> 审查方法: 抽样核查 + 关键路径 grep + Plan B/Phase 4 报告比对
> Worktree: `feat/permission-set-refactor`

## 总体评估

**实施完成度**: 约 **55-60%** (Phase 4 report 自评 70%, 经二次审查下调)

**核心问题**: Plan A/B/C 三阶段的 subagent 实施**未达到 spec 16 完整迁移要求**,
Phase 4 final report 里列出的"已知残留"实际只是冰山一角。

---

## �� P0 严重问题 (必须立即处理)

### 1. **schema YAML 文件完全未迁移** (Plan A 核心交付物缺失)

**位置**: `meta/schemas/role.yaml`, `meta/schemas/user_group.yaml`

**现状**:
```yaml
# meta/schemas/role.yaml (仍是旧)
id: role
name: 角色
table_name: roles
```

**spec 16 要求** (§3.1, line 161):
```
| meta/schemas/role.yaml | 删除（或归档），引用全部改 permission_set.yaml |
| meta/schemas/user_group.yaml | 删除，改 org.yaml |
```

**未交付**: `permission_set.yaml`, `org.yaml` 不存在.

**影响**: 
- metadata-driven 注册系统仍按旧 schema 工作
- 业务规则 yaml (`BR-xxx-FLD-REQ-role_id`) 引用旧字段名
- 前端 metadata 加载会拿到旧 objectType

**修复**: 立即 Plan A 第二轮 — git mv + 内容改造

---

### 2. **前端 boService 旧 objectType 调用未迁移** (Plan C Task 7/8 漏改)

**位置**: 3 个文件, 7 处

```javascript
// OrgPermissionSetDialog.vue:95
const result = await boService.query('role', { page: 1, page_size: 100 })

// OrgPermissionSetDialog.vue:120, 124
await boService.associate('user_group', props.groupId, 'roles', roleId, 'role')
await boService.dissociate('user_group', props.groupId, 'roles', roleId, 'role')

// PermissionSetDetailContent.vue:257, 259
result = await boService.create('role', saveData)
result = await boService.update('role', roleId.value, saveData)

// PermissionSetDetail.vue:229, 231
result = await boService.create('role', saveData)
result = await boService.update('role', roleId.value, saveData)
```

**影响**:
- 用户打开"权限集编辑"页面 → `boService.update('role', ...)` 会调用旧 API
- 实际请求会命中 `/api/v1/roles/{id}` 旧路径（如果后端还有兼容）
- 或者 404（新 schema 不识别 'role' objectType）

**修复**: Plan C 第二轮, 把 7 处 `'role'` → `'permission_set'`, `'user_group'` → `'org'`

---

### 3. **UI 文案大量未迁移** (Plan C Task 9 验证是假的)

**位置**: components + dialog 文件

**已 grep 出残留** (UI 显示给用户的字符串):
- `DimensionScopePanel.vue:15` — "配置角色的数据权限范围"
- `PermissionConfigPanel.vue:59` — "角色 ID 是否已保存为数字 ID"
- `PermissionConfigPanel.vue:107` — "体检是角色 object 的 validation action"
- `ResourceActionMatrix.vue:313, 316, 319` — "元数据未就绪：请检查角色是否已保存"
- `ResourceActionMatrix.vue:319` — "当前角色" (实际 props 已叫 `permission_set_id`, 但 UI 仍说"角色")
- `OrgPermissionSetDialog.vue:127` — "成功关联 N 个角色" (应改为"权限集")
- `useNavigation.js:104, 107, 110` — breadcrumb 父级标题 "用户与权限管理" (需评估)

**i18n 文件确实干净**, 但**组件硬编码字符串未清理**。

**影响**: 用户能看到 "角色" / "用户组" 等旧术语, 与新 schema 不一致.

**修复**: Plan C 第二轮, 文案迁移

---

## �� P1 中等问题 (重要但不阻塞)

### 4. 后端 service 方法签名仍用 `role_id` 参数名

**位置**: 15 个 service 文件

```python
# dimension_scope_engine.py
def expand_dimension_values(self, role_id: int) -> Dict[str, Set[int]]:
    scopes = self._load_scopes(role_id)

def derive_data_conditions(self, role_id: int) -> Dict[str, str]:
    expanded = self.expand_dimension_values(role_id)
```

**Phase 2 报告 (subagent 写) 已承认**: "部分大文件 (import_export_service.py 8211 lines) 未单独审查"

**修复**: 内部方法签名统一改为 `permission_set_id` (低风险, IDE 一次性 rename)

---

### 5. 后端 API blueprint 函数参数仍用 `role_id`

**位置**: `meta/api/org_api.py`, `permission_set_dimension_scope_api.py`, `_deprecation.py`

```python
# org_api.py
def add_group_role(org_id, role_id):       # ← 参数名应改 permission_set_id
def remove_group_role(org_id, role_id):
```

**影响**: HTTP 请求参数名是否仍为 `role_id`? 需后端验证; 前端发什么参数决定。

**修复**: API blueprint 内部参数 rename + request 参数名同步

---

### 6. 业务规则 yaml 未迁移

**位置**: `.trae/specs/_business_rules/*.yaml` (6 文件)

```yaml
# permission_rule.yaml
- id: BR-permission_rule-FLD-REQ-role_id
  field: role_id
  source: schema:permission_rule.yaml:fields[role_id].required
```

**关联**: e2e 测试通过 `BusinessRuleAssertor.assertRule(...)` 调用这些 BR ID

**影响**: 一旦 schema 改了 (问题 #1), 这些 BR ID 失效, 6 个 e2e 业务流 spec 全失败

**修复**: Plan D Tasks 2-5 (我跳过的范围)

---

## �� P2 已知问题 (Phase 4 已记录但需要明确优先级)

### 7. Plan D Tasks 1-7 (35 测试文件 + 3 spec 文件) 完全未执行

**当前状态**: 这些文件里 `role_id`/`user_group_id` 仍是字面量

**影响**:
- 跑 `pytest meta/tests/` → 大批 false negative
- 跑 `npm run test:unit` → 同上
- CI 无法绿

**修复**: Plan D 第二轮 (Task 2-5 + Task 7)

---

### 8. `useConditionRules.ts` query param `role_id` 未迁移

```typescript
// src/views/SystemManagement/composables/useConditionRules.ts:32, 60
role_id: roleId.value
```

**影响**: 取决于后端是否已迁移接收参数名. 需验证后端 API 蓝图.

---

### 9. ConditionRuleDialog `roleId` prop 保留 (向后兼容)

```typescript
// src/views/SystemManagement/ConditionRuleDialog.vue
const props = defineProps({
  roleId: { type: [String, Number], required: true },  // [Plan C 2026-08-29] 暂保留
```

**Plan C 决策**: 加注释说明, 后续 Plan D 统一. 但 Plan D 我没做.

**修复**: Plan C/D 后续轮, prop 统一改为 permissionSetId

---

## �� P3 低优先级 / 文档

### 10. debug 脚本 + 根目录脚本未清理

- `create_missing_tables.py` 等含旧 column 名 (`role_id INTEGER`)
- e2e/business-flow/*.spec.js (除业务规则文件) 含测试数据硬编码

**修复**: 独立清理任务

---

### 11. Plan D Tasks 1-7 spec 中 sed 规则风险

Plan D Task 3 的 `sed -i "s/\brole\b/permission_set/g"` 会破坏以下:
- 包含 "role" 但语义不是数据 schema 的内容（如 SQL 字符串、注释、函数名）
- v1_backup 旧表名（不应被改）

**修复**: Plan D 第二轮, sed 规则需更精确 (限定 schema 上下文)

---

## 已正确完成的工作 (无问题)

- ✅ Plan A v070-v073 SQL migration 脚本 (DB column rename)
- ✅ Plan B 13 commits 后端 service 重命名 (user_group_service → org_service)
- ✅ Plan B API blueprint 重命名 (role_api → permission_set_api)
- ✅ Plan B e2e 双轨对账测试 (test_2026_08_28_backend_dual_track.py)
- ✅ Plan B server.py Blueprint 注册
- ✅ Plan C Task 2 文件 git mv (9 文件)
- ✅ Plan C Task 3 useMenuPermission.ts 迁移
- ✅ Plan C Task 4 permissionService.js API path 迁移
- ✅ Plan C Task 5 objectTypeService FK 配置
- ✅ Plan C Task 6 router/menu 路由迁移
- ✅ Plan C Task 8 (PermissionConfigPanel 等 4 个) 变量名迁移
- ✅ Plan C Task 9 i18n 文件干净
- ✅ Plan C Task 10 OrgFunctionPanel 新建
- ✅ Plan C Task 11 audit/nav/guard 5 文件 label 迁移
- ✅ Plan C Task 12 graphqlClient.js 注释示例
- ✅ Plan D Task 8 历史 lessons pre-refactor 标记
- ✅ Plan D Task 9 permission_flags.py 清理

---

## 修复优先级建议

### 必须立即 (本周内)
1. **P0-1**: schema YAML 迁移 (Plan A 第二轮) — 1-2 小时
2. **P0-2**: 前端 boService 旧 objectType 调用 (Plan C 第二轮) — 30 min
3. **P0-3**: UI 硬编码字符串清理 (Plan C 第二轮) — 1 小时

### 重要 (本周内)
4. **P1-4**: 后端 service 方法签名 rename — 2-3 小时
5. **P1-5**: API blueprint 参数 rename — 1-2 小时
6. **P1-6**: 业务规则 yaml 迁移 — 1 小时

### 次要 (下周)
7. **P2-7**: Plan D Tasks 2-5 测试文件迁移 — 3-4 小时
8. **P2-8**: useConditionRules.ts query param — 30 min
9. **P2-9**: ConditionRuleDialog prop 统一 — 30 min

### 文档/清理 (后续)
10. **P3-10/11**: debug 脚本 + sed 规则精细化

---

## 与 Phase 4 Final Report 的差异

**Phase 4 Report (我写)** 标称:
- 后端 56 文件全量迁移 ✅
- 前端 29 文件全量迁移 ✅
- 总体变更 101 文件

**二次审查修正**:
- 后端 service 内部 rename 不完整 (15 文件残留)
- 前端 boService 调用不完整 (3 文件 7 处残留)
- UI 文案迁移不完整 (~15 处硬编码字符串)
- schema YAML 完全未迁移 (核心交付物缺失)
- **实质完成度**: 约 55-60%, 而非 Phase 4 报告暗示的 ~95%

---

## 结论

**Spec 16 完整执行**未达成。当前状态适合:
- 演示新路由/新组件 (OrgFunctionPanel)
- 单元测试