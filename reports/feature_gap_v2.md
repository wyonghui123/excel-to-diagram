# Feature Gap Analyzer v2 (4×3)

> **生成时间**: 2026-06-07 22:23:24
> **生成工具**: scripts/feature_gap_analyzer_v2.py
> **设计**: 4 数据源 × 3 分辨率 + Auto deep-dive

---

## 一、Executive Summary

| 指标 | 数值 |
|------|------|
| **整体覆盖度** | **83.3%** (10/12 category 充分覆盖) |
| Critical missing (SEC/COMP) | **0** |
| 薄覆盖 (thin) | 1 |
| 完全没测 (missing) | 1 |
| Spec 总数 | 56 |
| Spec 平均质量分 | 70.0 / 100 |
| v1 spec (需迁移) | 52 |
| v2 spec | 29 |
| soft-fail spec | 12 |
| API smoke spec (无 UI) | 0 |
| API 风险端点 | 31 |

## 二、4 数据源扫描结果

### DS1: 代码扫描
- 扫描文件: src/components + src/composables
- 发现功能 category: 11
- (object × feature) 对: 131

### DS2: Spec 质量评分

| 评分维度 | 数量 | 占比 |
|---------|------|------|
| v1 风格 | 52 | 93% |
| v2 风格 | 29 | 52% |
| soft-fail | 12 | 21% |
| API smoke (无 UI) | 0 | 0% |
| 质量分 < 50 | 4 | 7% |

**Top 5 低质量 spec** (需重写/迁移):

- `import-export.spec.js` - 分 31 (v1, soft-fail)
- `role-permission-center.spec.js` - 分 45 (v1, soft-fail)
- `useMetaList-21-keypath.spec.js` - 分 45 (ok)
- `ValueHelp-5-layer-link.spec.js` - 分 45 (ok)
- `arch-data-crud.spec.js` - 分 51 (v1)

### DS3: 业务规则 (meta/api)

| 风险等级 | API 文件数 |
|---------|-----------|
| 🟡 数据 (Data Integrity) | 4 |
| 🔴 安全 (Security) | 22 |
| 🔴 合规 (Compliance) | 3 |
| 🟢 UX | 2 |

**SEC/COMP 风险 API** (必须 E2E 覆盖):

- `association_api.py` (角色管理, 5 endpoints)
- `audit_api.py` (角色管理, 5 endpoints)
- `audit_management_api.py` (审计, 3 endpoints)
- `auth_api.py` (登录, 5 endpoints)
- `bo_action_api.py` (权限校验, 13 endpoints)
- `bo_api.py` (权限校验, 49 endpoints)
- `database_api.py` (权限校验, 9 endpoints)
- `data_permission_api.py` (权限校验, 4 endpoints)
- `decorators.py` (权限校验, 1 endpoints)
- `export_import_api.py` (数据范围, 9 endpoints)
- `intent_api.py` (权限校验, 7 endpoints)
- `management_dimension_api.py` (权限校验, 4 endpoints)
- `manage_api.py` (数据范围, 17 endpoints)
- `menu_permission_api.py` (权限校验, 9 endpoints)
- `meta_api.py` (权限校验, 14 endpoints)
- `permission_api.py` (权限校验, 2 endpoints)
- `permission_audit_api.py` (权限校验, 6 endpoints)
- `permission_bundle_api.py` (权限校验, 5 endpoints)
- `permission_rule_api.py` (权限校验, 10 endpoints)
- `permission_sync_api.py` (权限校验, 5 endpoints)
- `role_api.py` (权限校验, 12 endpoints)
- `role_dimension_scope_api.py` (角色管理, 3 endpoints)
- `role_menu_api.py` (角色管理, 3 endpoints)
- `user_api.py` (角色管理, 12 endpoints)
- `user_group_api.py` (权限校验, 19 endpoints)

### DS4: UI 模式 (Element UI)

| 组件 | 使用次数 |
|------|---------|
| `<el-button>` | 255 |
| `<el-input>` | 83 |
| `<el-table>` | 82 |
| `<el-form>` | 48 |
| `<el-select>` | 48 |
| `<el-dialog>` | 21 |
| `<el-menu>` | 17 |
| `<el-date-picker>` | 13 |
| `<el-pagination>` | 12 |
| `<el-tabs>` | 8 |

## 三、L1-c: Category 覆盖度矩阵 (12 × 4 DS)

| Category | 风险 | DS1代码 | DS2 spec (分) | DS3 API | DS4 UI | 状态 |
|----------|------|---------|--------------|---------|--------|------|
| 排序 (Sort) | 🟢UX | ✅ (141) | 5 (72.0) | · | el-table / el-p | ✅ |
| 过滤 (Filter) | 🟢UX | ✅ (582) | 31 (66.5) | 1 | el-table / el-p | ✅ |
| 组合过滤 (Filter Combination) | 🟢UX | · (0) | · | · | el-table / el-p | ❌ |
| 内联编辑 (Inline Edit) | 🟡数据 ( | ✅ (107) | 3 (58.7) | · | el-table (inlin | ⚠️ |
| 批量操作 (Batch Ops) | 🟡数据 ( | ✅ (104) | 4 (62.5) | · | 通用 Element UI | ✅ |
| 深插入 (Deep Insert) | 🟡数据 ( | ✅ (106) | 1 (88.0) | · | ObjectChildSect | ✅ |
| 计算字段 (Calculated Field) | 🟡数据 ( | ✅ (1) | 1 (88.0) | · | 通用 Element UI | ✅ |
| 分页 (Pagination) | 🟢UX | ✅ (268) | 6 (61.5) | · | el-table / el-p | ✅ |
| 导入导出 (Import/Export) | 🟡数据 ( | ✅ (939) | 55 (70.5) | 1 | el-upload | ✅ |
| 关联 (Association) | 🟡数据 ( | ✅ (144) | 5 (62.4) | 1 | el-dialog / el- | ✅ |
| 表单验证 (Form Validation) | 🟡数据 ( | ✅ (257) | 2 (93.0) | · | el-form / el-se | ✅ |
| 条件逻辑 (Conditional Logic) | 🔴合规 ( | ✅ (29) | 1 (88.0) | · | el-form / el-se | ✅ |

## 四、Auto Deep-Dive (P0/P1 + missing/thin)

> 每个 deep-dive 包含: 4 DS 证据 + scenarios + 推荐的 test cases

### 🟢 [P2] 过滤 (Filter) ✅

**4 数据源证据**:
- DS1 代码: 582 处
- DS2 spec: 31 个, 平均分 66.5
- DS3 API: 1 个相关 (filter_variant_api.py)
- DS4 UI 组件: el-table / el-pagination

**Scenarios (L1-s)**:

- · **text_search**: 未覆盖
- · **exact_match**: 未覆盖
- · **date_range**: 未覆盖
- · **date_relative**: 未覆盖
- · **number_range**: 未覆盖
- · **multi_select**: 未覆盖
- · **calculated_field**: 未覆盖
- · **single_criteria**: 未覆盖
- · **multi_criteria_AND**: 未覆盖
- · **multi_criteria_OR**: 未覆盖

**推荐 test cases (L1-r)**: 10 个

- [P1] **text_search**
- [P1] **exact_match**
- [P1] **date_range**
- [P1] **date_relative**
- [P1] **number_range**
- [P1] **multi_select**
- [P1] **calculated_field**
- [P1] **single_criteria**
- ... +2 more

### 🟢 [P2] 组合过滤 (Filter Combination) ❌

**4 数据源证据**:
- DS1 代码: ❌ 无
- DS2 spec: ❌ 完全没测
- DS3 API: 0 个相关 (无)
- DS4 UI 组件: el-table / el-pagination

**Scenarios (L1-s)**:

- · **multi_select_plus_text_plus_sort**: 未覆盖
- · **cascading_filters**: 未覆盖
- · **saved_filter_variant**: 未覆盖

**推荐 test cases (L1-r)**: 3 个

- [P1] **multi_select_plus_text_plus_sort**
- [P1] **cascading_filters**
- [P1] **saved_filter_variant**

### 🟡 [P1] 内联编辑 (Inline Edit) ⚠️

**4 数据源证据**:
- DS1 代码: 107 处
- DS2 spec: 3 个, 平均分 58.7
- DS3 API: 0 个相关 (无)
- DS4 UI 组件: el-table (inline cell)

**Scenarios (L1-s)**:

- · **create_row**: 未覆盖
- · **edit_row**: 未覆盖
- · **delete_row**: 未覆盖
- · **save_row**: 未覆盖
- · **cancel_row**: 未覆盖
- · **visibility_logic**: 未覆盖
- · **readonly_logic**: 未覆盖
- · **quick_mode**: 未覆盖
- · **direct_mode**: 未覆盖
- · **validation_inline**: 未覆盖
- · **tab_navigation**: 未覆盖

**推荐 test cases (L1-r)**: 11 个

- [P1] **create_row**
- [P1] **edit_row**
- [P1] **delete_row**
- [P1] **save_row**
- [P1] **cancel_row**
- [P1] **visibility_logic**
- [P1] **readonly_logic**
- [P1] **quick_mode**
- ... +3 more

### 🟡 [P1] 批量操作 (Batch Ops) ✅

**4 数据源证据**:
- DS1 代码: 104 处
- DS2 spec: 4 个, 平均分 62.5
- DS3 API: 0 个相关 (无)
- DS4 UI 组件: 通用 Element UI

**Scenarios (L1-s)**:

- · **batch_add**: 未覆盖
- · **batch_delete**: 未覆盖
- · **batch_update**: 未覆盖
- · **select_all**: 未覆盖
- · **select_page**: 未覆盖
- · **selection_count**: 未覆盖

**推荐 test cases (L1-r)**: 6 个

- [P1] **batch_add**
- [P1] **batch_delete**
- [P1] **batch_update**
- [P1] **select_all**
- [P1] **select_page**
- [P1] **selection_count**

### 🟢 [P2] 分页 (Pagination) ✅

**4 数据源证据**:
- DS1 代码: 268 处
- DS2 spec: 6 个, 平均分 61.5
- DS3 API: 0 个相关 (无)
- DS4 UI 组件: el-table / el-pagination

**Scenarios (L1-s)**:

- · **page_size**: 未覆盖
- · **jump_to_page**: 未覆盖
- · **first_last_page**: 未覆盖
- · **total_count**: 未覆盖

**推荐 test cases (L1-r)**: 4 个

- [P1] **page_size**
- [P1] **jump_to_page**
- [P1] **first_last_page**
- [P1] **total_count**

### 🟡 [P1] 关联 (Association) ✅

**4 数据源证据**:
- DS1 代码: 144 处
- DS2 spec: 5 个, 平均分 62.4
- DS3 API: 1 个相关 (association_api.py)
- DS4 UI 组件: el-dialog / el-cascader / search-help

**Scenarios (L1-s)**:

- · **m2m_add**: 未覆盖
- · **m2m_remove**: 未覆盖
- · **fk_select**: 未覆盖
- ⚙️ **search_help**: 代码有 (src\components\common\SearchHelpDialog.vue:12)
- · **recent_items**: 未覆盖
- · **inline_create_child**: 未覆盖
- · **deep_link**: 未覆盖
- · **batch_add**: 未覆盖
- · **batch_remove**: 未覆盖
- ✅ **validation**: 已测 (form-validation.spec.js)

**推荐 test cases (L1-r)**: 9 个

- [P1] **m2m_add**
- [P1] **m2m_remove**
- [P1] **fk_select**
- [P1] **search_help**
- [P1] **recent_items**
- [P1] **inline_create_child**
- [P1] **deep_link**
- [P1] **batch_add**
- ... +1 more

### 🔴 [P0] 条件逻辑 (Conditional Logic) ✅

**4 数据源证据**:
- DS1 代码: 29 处
- DS2 spec: 1 个, 平均分 88.0
- DS3 API: 0 个相关 (无)
- DS4 UI 组件: el-form / el-select

**Scenarios (L1-s)**:

- · **visible_when**: 未覆盖
- · **readonly_when**: 未覆盖
- · **required_when**: 未覆盖
- · **value_when**: 未覆盖
- ⚙️ **cascade_select**: 代码有 (src\composables\useCascadeSelect.js:11)
- · **dependent_field**: 未覆盖
- · **permission_based_visibility**: 未覆盖

**推荐 test cases (L1-r)**: 7 个

- [P0] **visible_when**
- [P0] **readonly_when**
- [P0] **required_when**
- [P0] **value_when**
- [P0] **cascade_select**
- [P0] **dependent_field**
- [P0] **permission_based_visibility**

## 五、最终优先级 (Risk × Coverage)

| 排序 | Category | 风险 | 状态 | 推荐 ROI | 优先级 |
|------|----------|------|------|---------|--------|
| 1 | 组合过滤 (Filter Combination) | 🟢UX | ❌ | 高 | P1 |
| 2 | 内联编辑 (Inline Edit) | 🟡DATA | ⚠️ | 中 | P2 |
| 3 | 排序 (Sort) | 🟢UX | ✅ | 中 | P2 |
| 4 | 过滤 (Filter) | 🟢UX | ✅ | 中 | P2 |
| 5 | 批量操作 (Batch Ops) | 🟡DATA | ✅ | 中 | P2 |
| 6 | 深插入 (Deep Insert) | 🟡DATA | ✅ | 中 | P2 |
| 7 | 计算字段 (Calculated Field) | 🟡DATA | ✅ | 中 | P2 |
| 8 | 分页 (Pagination) | 🟢UX | ✅ | 中 | P2 |
| 9 | 导入导出 (Import/Export) | 🟡DATA | ✅ | 中 | P2 |
| 10 | 关联 (Association) | 🟡DATA | ✅ | 中 | P2 |
| 11 | 表单验证 (Form Validation) | 🟡DATA | ✅ | 中 | P2 |
| 12 | 条件逻辑 (Conditional Logic) | 🔴COMP | ✅ | 中 | P2 |

## 六、附录: Spec 质量详情 (15 spec)

| Spec | tests | v1/v2 | soft-fail | smoke | 分 |
|------|------:|------|-----------|-------|----:|
| `import-export.spec.js` | 2 | v1 | ⚠️ | · | **31** |
| `role-permission-center.spec.js` | 27 | v1 | ⚠️ | · | **45** |
| `useMetaList-21-keypath.spec.js` | 21 | ? | · | · | **45** |
| `ValueHelp-5-layer-link.spec.js` | 15 | ? | · | · | **45** |
| `arch-data-crud.spec.js` | 2 | v1 | · | · | **51** |
| `arch-data-filter-scope.spec.js` | 2 | v1 | · | · | **51** |
| `relation-scope-field.spec.js` | 2 | v1 | · | · | **51** |
| `condition-rule-dialog-spec-v14.spec.js` | 9 | v1 | · | · | **53** |
| `audit-log-objects-p1.spec.js` | 11 | v1 | · | · | **55** |
| `audit-log.spec.js` | 3 | v1 | · | · | **61** |
| `business-object-crud.spec.js` | 2 | v1 | · | · | **61** |
| `diagram.spec.js` | 2 | v1 | · | · | **61** |
| `enum-management.spec.js` | 3 | v2 | ⚠️ | · | **61** |
| `fk-filter-debug.spec.js` | 1 | v1 | · | · | **61** |
| `fk-filter-issue.spec.js` | 2 | v1 | · | · | **61** |
| `fk-filter-search.spec.js` | 1 | v1 | · | · | **61** |
| `overlap-warning.spec.js` | 1 | v2 | ⚠️ | · | **61** |
| `product-crud.spec.js` | 2 | v1 | · | · | **61** |
| `role-intents.spec.js` | 4 | v2 | ⚠️ | · | **61** |
| `user-group-filter.spec.js` | 2 | v1 | · | · | **61** |
| `user-permission.spec.js` | 2 | v1 | · | · | **61** |
| `value-help-dialog.spec.js` | 1 | v1 | · | · | **61** |
| `value-help-filter.spec.js` | 3 | v1 | · | · | **61** |
| `workspace.spec.js` | 2 | v1 | · | · | **61** |
| `audit-log-actions.spec.js` | 7 | v1 | · | · | **63** |
| `audit-log-base.spec.js` | 5 | v1 | · | · | **63** |
| `audit-log-filter.spec.js` | 7 | v1 | · | · | **63** |
| `audit-log-levels.spec.js` | 6 | v1 | · | · | **63** |
| `audit-log-objects-p0.spec.js` | 5 | v1 | · | · | **63** |
| `relation-scope-tree.spec.js` | 6 | v1 | · | · | **63** |
| `audit-log-embedded-access.spec.js` | 14 | v2 | ⚠️ | · | **70** |
| `condition-rule-dialog.spec.js` | 2 | v2 | ⚠️ | · | **71** |
| `intent-apis.spec.js` | 4 | v2 | ⚠️ | · | **71** |
| `permission-explainer.spec.js` | 3 | v2 | ⚠️ | · | **71** |
| `user-group-detail.spec.js` | 1 | v2 | ⚠️ | · | **71** |
| `user-role.spec.js` | 3 | v2 | ⚠️ | · | **71** |
| `audit-log-grouping-detail.spec.js` | 10 | v2 | ⚠️ | · | **75** |
| `fk-filter.spec.js` | 2 | v2 | · | · | **81** |
| `menu-bo-linker.spec.js` | 3 | v2 | · | · | **81** |
| `association-crud.spec.js` | 4 | v2 | · | · | **86** |
| `batch-ops.spec.js` | 4 | v2 | · | · | **86** |
| `deep-insert.spec.js` | 3 | v2 | · | · | **86** |
| `filter-combination.spec.js` | 3 | v2 | · | · | **86** |
| `inline-edit.spec.js` | 4 | v2 | · | · | **86** |
| `product-version.spec.js` | 3 | v2 | · | · | **86** |
| `calculated-field.spec.js` | 5 | v2 | · | · | **88** |
| `conditional-logic.spec.js` | 7 | v2 | · | · | **88** |
| `pagination.spec.js` | 5 | v2 | · | · | **88** |
| `data-permission-config.spec.js` | 3 | v2 | · | · | **91** |
| `debug-column-config.spec.js` | 1 | v2 | · | · | **91** |
| `arch-data-crud-v2.spec.js` | 1 | v2 | · | · | **96** |
| `auto-business-object.spec.js` | 3 | v2 | · | · | **96** |
| `auto-product.spec.js` | 2 | v2 | · | · | **96** |
| `filter-ux.spec.js` | 4 | v2 | · | · | **96** |
| `sort-ux.spec.js` | 3 | v2 | · | · | **96** |
| `form-validation.spec.js` | 7 | v2 | · | · | **98** |

---

_本报告由 scripts/feature_gap_analyzer_v2.py (4×3 设计) 自动生成_

