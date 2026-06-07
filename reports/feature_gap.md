# E2E 功能层 Gap 分析报告 (L1)

> **生成时间**: 2026-06-07 18:04:37
> **生成工具**: scripts/feature\_gap\_analyzer.py
> **核心问题**: 11 个业务能力点的详细 case 是否覆盖?

***

## 一、总览

| 维度                       | 数字        |
| ------------------------ | --------- |
| 功能分类数                    | 12        |
| 代码中存在的功能 (category)      | 11        |
| 现有 spec 覆盖的功能 (category) | 7         |
| 业务对象数                    | 19        |
| 代码中 (object, feature) 对  | 136       |
| 代码有但 spec 完全没测的功能        | **4**     |
| 功能层覆盖度 (粗)               | **63.6%** |

## 二、12 大功能 × 存在性矩阵

| 功能                        | 代码中存在 | spec 覆盖 | 业务优先级 | 缺口状态             |
| ------------------------- | ----- | ------- | ----- | ---------------- |
| 排序 (Sort)                 | \[OK] | \[OK]   | P1    | \[OK] 覆盖         |
| 过滤 (Filter)               | \[OK] | \[OK]   | P1    | \[OK] 覆盖         |
| 组合过滤 (Filter Combination) | \[--] | \[--]   | P2    | \[OK] 覆盖         |
| 内联编辑 (Inline Edit)        | \[OK] | \[OK]   | P0    | \[WARN] 覆盖薄      |
| 批量操作 (Batch Ops)          | \[OK] | \[OK]   | P0    | \[OK] 覆盖         |
| 深插入 (Deep Insert)         | \[OK] | \[--]   | P1    | \[CRITICAL] 完全没测 |
| 计算字段 (Calculated Field)   | \[OK] | \[--]   | P1    | \[CRITICAL] 完全没测 |
| 分页 (Pagination)           | \[OK] | \[OK]   | P2    | \[WARN] 覆盖薄      |
| 导入导出 (Import/Export)      | \[OK] | \[OK]   | P1    | \[WARN] 覆盖薄      |
| 关联 (Association)          | \[OK] | \[OK]   | P1    | \[OK] 覆盖         |
| 表单验证 (Form Validation)    | \[OK] | \[--]   | P0    | \[CRITICAL] 完全没测 |
| 条件逻辑 (Conditional Logic)  | \[OK] | \[--]   | P1    | \[CRITICAL] 完全没测 |

## 三、业务对象 × 功能 矩阵

只显示代码中存在 (object, feature) 对。✅=已测 ⚠️=薄 ❌=完全没测

| 对象 \ 功能               | sort | filter | filter | inline | batch\_ | deep\_i | calcul | pagina | export | associ | form\_v | condit |
| --------------------- | ---- | ------ | ------ | ------ | ------- | ------- | ------ | ------ | ------ | ------ | ------- | ------ |
| `business_object`     | ⚠️   | ⚠️     | ·      | ⚠️     | ⚠️      | ·       | ❌      | ⚠️     | ⚠️     | ⚠️     | ❌       | ·      |
| `user`                | ⚠️   | ⚠️     | ·      | ⚠️     | ⚠️      | ❌       | ·      | ⚠️     | ⚠️     | ⚠️     | ❌       | ·      |
| `role`                | ⚠️   | ⚠️     | ·      | ⚠️     | ⚠️      | ❌       | ·      | ⚠️     | ⚠️     | ⚠️     | ❌       | ❌      |
| `user_group`          | ⚠️   | ⚠️     | ·      | ⚠️     | ·       | ❌       | ·      | ⚠️     | ⚠️     | ⚠️     | ❌       | ·      |
| `product`             | ⚠️   | ⚠️     | ·      | ⚠️     | ⚠️      | ❌       | ·      | ⚠️     | ⚠️     | ⚠️     | ❌       | ❌      |
| `version`             | ⚠️   | ⚠️     | ·      | ⚠️     | ⚠️      | ❌       | ❌      | ⚠️     | ⚠️     | ⚠️     | ❌       | ❌      |
| `relationship`        | ⚠️   | ⚠️     | ·      | ⚠️     | ⚠️      | ❌       | ·      | ⚠️     | ⚠️     | ⚠️     | ❌       | ❌      |
| `enum_type`           | ⚠️   | ⚠️     | ·      | ⚠️     | ⚠️      | ❌       | ·      | ⚠️     | ⚠️     | ⚠️     | ❌       | ·      |
| `permission`          | ⚠️   | ⚠️     | ·      | ⚠️     | ⚠️      | ❌       | ❌      | ⚠️     | ⚠️     | ⚠️     | ❌       | ❌      |
| `audit_log`           | ⚠️   | ⚠️     | ·      | ⚠️     | ⚠️      | ❌       | ·      | ⚠️     | ⚠️     | ⚠️     | ❌       | ❌      |
| `menu`                | ⚠️   | ⚠️     | ·      | ⚠️     | ⚠️      | ❌       | ❌      | ⚠️     | ⚠️     | ⚠️     | ❌       | ·      |
| `diagram`             | ⚠️   | ⚠️     | ·      | ⚠️     | ·       | ·       | ❌      | ⚠️     | ⚠️     | ⚠️     | ❌       | ·      |
| `import_export`       | ⚠️   | ⚠️     | ·      | ⚠️     | ⚠️      | ❌       | ·      | ⚠️     | ⚠️     | ⚠️     | ❌       | ·      |
| `draft`               | ⚠️   | ⚠️     | ·      | ⚠️     | ⚠️      | ❌       | ·      | ⚠️     | ⚠️     | ⚠️     | ❌       | ·      |
| `filter_variant`      | ·    | ⚠️     | ·      | ·      | ·       | ·       | ·      | ·      | ⚠️     | ·      | ❌       | ·      |
| `change_event`        | ·    | ·      | ·      | ·      | ·       | ·       | ·      | ·      | ·      | ·      | ·       | ·      |
| `change_subscription` | ·    | ·      | ·      | ·      | ·       | ·       | ·      | ·      | ·      | ·      | ·       | ·      |
| `scheduled_task`      | ·    | ·      | ·      | ·      | ·       | ·       | ·      | ·      | ·      | ·      | ·       | ·      |
| `ai_async_task`       | ·    | ·      | ·      | ·      | ·       | ·       | ·      | ·      | ·      | ·      | ·       | ·      |

图例: ✅ 已测 | ⚠️ 代码有但 spec 只间接提 | ❌ 代码有 spec 完全没 | · 代码无此组合

## 四、详细缺口清单 + 建议 test cases

按业务优先级排序:

### P0 内联编辑 (Inline Edit)

_核心产品能力,影响所有 BO 编辑_

**状态**: \[WARN] 覆盖薄 (spec 仅 1 处提及)
**已测关键词**: inline

**建议 test cases** (11 个 variant):

- [ ] **create\_row**: create row 场景验证
- [ ] **edit\_row**: edit row 场景验证
- [ ] **delete\_row**: delete row 场景验证
- [ ] **save\_row**: save row 场景验证
- [ ] **cancel\_row**: cancel row 场景验证
- [ ] **visibility\_logic**: visibility logic 场景验证
- [ ] **readonly\_logic**: readonly logic 场景验证
- [ ] **quick\_mode**: quick mode 场景验证
- [ ] **direct\_mode**: direct mode 场景验证
- [ ] **validation\_inline**: validation inline 场景验证
- [ ] **tab\_navigation**: tab navigation 场景验证

### P0 表单验证 (Form Validation)

_数据正确性底线_

**状态**: \[CRITICAL] 完全没测 (代码中 257 处实现)
**代码位置 (前 5)**:

- `src\components\common\ConfirmDialog.vue:68`
- `src\components\common\EmptyState.vue:25`
- `src\components\common\EnumSearchHelp.vue:66`
- `src\components\common\EnumSelect.vue:72`
- `src\components\common\FilterVariantSelector.vue:104`

**建议 test cases** (7 个 variant):

- [ ] **required**: required 场景验证
- [ ] **format**: format 场景验证
- [ ] **range**: range 场景验证
- [ ] **unique**: unique 场景验证
- [ ] **custom\_rule**: custom rule 场景验证
- [ ] **async\_validation**: async validation 场景验证
- [ ] **cross\_field\_validation**: cross field validation 场景验证

### P1 深插入 (Deep Insert)

_嵌套数据建模关键_

**状态**: \[CRITICAL] 完全没测 (代码中 115 处实现)
**代码位置 (前 5)**:

- `src\components\common\AuditLog\AuditLog.vue:144`
- `src\components\common\AuditLog\AuditLog.vue:838`
- `src\components\common\AuditLogDetail\AuditLogDetail.vue:33`
- `src\components\common\AuditLogDetail\AuditLogDetail.vue:37`
- `src\components\common\AuditLogDetail\AuditLogDetail.vue:41`

**建议 test cases** (3 个 variant):

- [ ] **create\_with\_children**: create with children 场景验证
- [ ] **cascade\_save**: cascade save 场景验证
- [ ] **rollback\_on\_child\_error**: rollback on child error 场景验证

### P1 计算字段 (Calculated Field)

_数据展示核心_

**状态**: \[CRITICAL] 完全没测 (代码中 6 处实现)
**代码位置 (前 5)**:

- `src\composables\useMenuPermissions.js:37`
- `src\composables\useMenuPermissions.js:60`
- `src\composables\useMenuPermissions.js:37`
- `src\composables\useMenuPermissions.js:60`
- `src\composables\__tests__\useHierarchyList.spec.js:321`

**建议 test cases** (5 个 variant):

- [ ] **auto\_compute**: auto compute 场景验证
- [ ] **sort\_by\_calc**: sort by calc 场景验证
- [ ] **filter\_by\_calc**: filter by calc 场景验证
- [ ] **display\_in\_table**: display in table 场景验证
- [ ] **display\_in\_form**: display in form 场景验证

### P1 导入导出 (Import/Export)

_运营必备_

**状态**: \[WARN] 覆盖薄 (spec 仅 2 处提及)
**已测关键词**: export, import

**建议 test cases** (5 个 variant):

- [ ] **export\_csv**: export csv 场景验证
- [ ] **export\_excel**: export excel 场景验证
- [ ] **import\_file**: import file 场景验证
- [ ] **import\_validation**: import validation 场景验证
- [ ] **import\_rollback**: import rollback 场景验证

### P1 条件逻辑 (Conditional Logic)

_业务规则核心_

**状态**: \[CRITICAL] 完全没测 (代码中 31 处实现)
**代码位置 (前 5)**:

- `src\components\common\ObjectPage\ObjectPageContent.vue:262`
- `src\components\common\ObjectPage\ObjectPageContent.vue:263`
- `src\composables\useCascadeSelect.js:11`
- `src\composables\useCascadeSelect.js:231`
- `src\composables\useCascadeSelect.js:11`

**建议 test cases** (6 个 variant):

- [ ] **visible\_when**: visible when 场景验证
- [ ] **readonly\_when**: readonly when 场景验证
- [ ] **required\_when**: required when 场景验证
- [ ] **value\_when**: value when 场景验证
- [ ] **cascade\_select**: cascade select 场景验证
- [ ] **dependent\_field**: dependent field 场景验证

### P2 组合过滤 (Filter Combination)

_高级用户需求_

**状态**: \[CRITICAL] 完全没测 (代码中 0 处实现)

**建议 test cases** (3 个 variant):

- [ ] **multi\_select\_plus\_text\_plus\_sort**: multi select plus text plus sort 场景验证
- [ ] **cascading\_filters**: cascading filters 场景验证
- [ ] **saved\_filter\_variant**: saved filter variant 场景验证

### P2 分页 (Pagination)

_基础功能,但实现简单_

**状态**: \[WARN] 覆盖薄 (spec 仅 2 处提及)
**已测关键词**: pagesize, pagination

**建议 test cases** (4 个 variant):

- [ ] **page\_size**: page size 场景验证
- [ ] **jump\_to\_page**: jump to page 场景验证
- [ ] **first\_last\_page**: first last page 场景验证
- [ ] **total\_count**: total count 场景验证

## 五、推荐执行顺序 (按 ROI)

| 优先级 | 功能                        | 推荐场景数 | 业务价值       | 实施难度                       |
| --- | ------------------------- | ----- | ---------- | -------------------------- |
| P0  | 表单验证 (Form Validation)    | 5     | 高 (数据正确性)  | 中 (需新 spec)                |
| P0  | 内联编辑 (Inline Edit)        | 6     | 高 (核心编辑能力) | 高 (新建 spec)                |
| P0  | 批量操作 (Batch Ops)          | 4     | 高 (批量管理)   | 中 (可基于现有 spec 扩展)          |
| P1  | 排序 (Sort)                 | 4     | 高 (UX)     | 低 (可在现有 spec 加 test)       |
| P1  | 过滤 (Filter)               | 6     | 高 (UX)     | 低 (可扩展现有 fk-filter)        |
| P1  | 关联 (Association)          | 5     | 高 (M2M)    | 中 (需 spec)                 |
| P1  | 导入导出 (Import/Export)      | 4     | 中          | 低 (import-export.spec 已存在) |
| P2  | 组合过滤 (Filter Combination) | 3     | 中          | 高 (复杂场景)                   |

## 六、下一步 (推荐)

### L2: 生成 test skeleton (3-4 小时)

- 用 L3 工具 (`auto_gen_v2_spec.py`) 为每个 P0/P1 功能生成 spec 骨架
- 用 `dataFinder` + `isolation` 自动构造测试数据
- 11 个 spec × 5-10 test = 55-110 test

### L3: 闭环 (1 天)

- feature\_gap\_analyzer.py 集成到 CI
- 每周自动跑
- 输出覆盖率趋势 + PR 评论

***

## 七、3 大领域深度查证 (2026-06-07)

> 本章节针对用户提出的 3 个高价值领域,做**精确查证**而非粗略统计

### 7.1 现有相关 spec 真实状态 (15 个 spec)

| Spec                           | tests | desc | 风格 | soft-fail | skip | 实际测什么             |
| ------------------------------ | ----: | ---: | -- | --------- | ---- | ----------------- |
| value-help-filter.spec.js      |     3 |    1 | v1 | ✅         | ❌    | 弹窗布局              |
| value-help-dialog.spec.js      |     1 |    1 | v1 | ❌         | ❌    | **只测分页**          |
| ValueHelp-5-layer-link.spec.js |    15 |    1 | v1 | ❌         | ✅    | 5 层链路架构 (非 C/D)   |
| relation-scope-field.spec.js   |     2 |    1 | v1 | ✅         | ✅    | 字段级 scope         |
| relation-scope-tree.spec.js    |     6 |    1 | v1 | ❌         | ❌    | 树形 scope          |
| menu-bo-linker.spec.js         |     3 |    1 | v1 | ❌         | ❌    | BO 链接             |
| role-permission-center.spec.js |    27 |    1 | v1 | ✅         | ❌    | 权限中心              |
| permission-explainer.spec.js   |     3 |    1 | v1 | ✅         | ❌    | explain API (软失败) |
| data-permission-config.spec.js |     3 |    1 | v1 | ❌         | ❌    | owner\_aspect     |
| user-permission.spec.js        |     2 |    1 | v1 | ❌         | ❌    | -                 |
| role-intents.spec.js           |     4 |    1 | v1 | ❌         | ❌    | -                 |
| intent-apis.spec.js            |     4 |    1 | v1 | ✅         | ❌    | -                 |
| user-role.spec.js              |     3 |    1 | v1 | ✅         | ❌    | -                 |
| overlap-warning.spec.js        |     1 |    1 | v1 | ✅         | ❌    | -                 |
| condition-rule-dialog.spec.js  |     2 |    1 | v1 | ✅         | ❌    | -                 |

**3 个关键发现**:

1. **15 个 spec,每个只有 1 个 describe block** = 都是聚焦测试
2. **100% 是 v1 风格** (login + setAdminPermissions) = 跟 v2 规范脱节
3. **`grep "add association\|remove association\|batch add\|batch delete"`** **→ 0 命中** = 关联 C/D 完全没测

***

### 7.2 🔴 Q1: Association C/D 是不是覆盖全了?

**答案: ❌ 完全没覆盖**

| 证据                                          | 说明                                          |
| ------------------------------------------- | ------------------------------------------- |
| `value-help-dialog.spec.js` (1 test)        | 只测**分页** (`VHD-01: Value Help Dialog 分页验证`) |
| `value-help-filter.spec.js` (3 tests)       | 只测**过滤布局**                                  |
| `ValueHelp-5-layer-link.spec.js` (15 tests) | 只测**5 层架构链路**,**不测 C/D 操作**                 |
| 搜 "add association"                         | 0 命中                                        |
| 搜 "remove association"                      | 0 命中                                        |
| 搜 "batch add" / "batch delete"              | 0 命中                                        |
| 搜 "m2m add" / "m2m remove"                  | 0 命中                                        |

**漏测的场景清单** (基于 [ObjectChildSection.vue](file:///d:/filework/excel-to-diagram/src/components/common/ObjectChildSection/ObjectChildSection.vue) + [InlineEditCell.vue](file:///d:/filework/excel-to-diagram/src/components/common/MetaListPage/InlineEditCell.vue) 实际能力):

- [ ] **单条添加 association** (打开 dialog → 搜索 → 选中)
- [ ] **批量添加** (选多行 + 确认)
- [ ] **单条删除**
- [ ] **批量删除**
- [ ] **行内编辑修改关联** (InlineEditCell)
- [ ] **取消关联** (with confirm dialog)
- [ ] **关联最近使用** (Recent Items,代码有 [SearchHelpDialog.vue:12-29](file:///d:/filework/excel-to-diagram/src/components/common/SearchHelpDialog.vue#L12-L29) 实现)
- [ ] **Search help 弹窗的 sort/filter**
- [ ] **Cascade 5-layer chain** 的 add/remove
- [ ] **关联数据校验** (FK 引用完整性)

***

### 7.3 🟡 Q2: Value Help 是不是覆盖全了 (sorting, 创建, 编辑)?

**答案: ⚠️ 部分覆盖 (30%)**

| 能力                                    | 状态    | 测的 spec                         | test 数 |
| ------------------------------------- | ----- | ------------------------------- | -----: |
| 打开弹窗                                  | ✅     | value-help-filter, 5-layer-link |      4 |
| 分页                                    | ✅     | value-help-dialog               |      1 |
| 文本搜索                                  | ✅     | value-help-filter, 5-layer-link |      6 |
| 弹窗布局                                  | ✅     | value-help-filter               |      3 |
| 5 层架构链路                               | ✅     | ValueHelp-5-layer-link          |     15 |
| **Sort 排序**                           | ❌     | 0 spec 测 VH 列表的 sort            |      0 |
| **Create 新建**                         | ❌     | 0 spec 测 VH 弹窗内"+"按钮            |      0 |
| **Edit 编辑**                           | ❌     | 0 spec 测 VH 选中后编辑               |      0 |
| **Recent Items**                      | ❌     | 0 spec                          |      0 |
| **Multi-mode (flat/tree/tree\_flat)** | ⚠️ 间接 | 5-layer-link 测了模式但不是交互          |      - |
| **Cascade 5-layer chain**             | ✅     | 5-layer-link                    |      5 |

**漏测的核心场景**:

- [ ] **VH 列表列排序** (asc/desc/calculated field)
- [ ] **VH 内新建数据** (弹窗里"+"按钮)
- [ ] **VH 选中后编辑已选数据**
- [ ] **Recent Items 显示与点击** ([SearchHelpDialog.vue:12-29](file:///d:/filework/excel-to-diagram/src/components/common/SearchHelpDialog.vue#L12-L29) 实现)
- [ ] **VH 列表的多选 + 批量确认**
- [ ] **VH 列表日期/数字范围过滤**
- [ ] **VH 列表 calculated field 显示**
- [ ] **VH 选中后联动回填** (5-layer chain 数据回填)

***

### 7.4 🟡 Q3: 4 大权限 (菜单/功能/数据/owner) 是不是覆盖全了?

**答案: ⚠️ 部分覆盖 (40%)**

| 权限类型                  | 状态         | 测的 spec                           | 实际深度                                    |
| --------------------- | ---------- | --------------------------------- | --------------------------------------- |
| **功能权限 (functional)** | ⚠️ 薄       | role-permission-center (27 tests) | 测了**配置**,**不测运行时**                      |
| **数据权限 (data)**       | ⚠️ 薄       | data-permission-config (3 tests)  | owner\_aspect + visibility draft,API 测试 |
| **Owner 权限**          | ⚠️ 薄       | data-permission-config (3 tests)  | owner\_id 字段验证                          |
| **菜单权限 (menu)**       | ❌ **完全没测** | 0 专门 spec                         | 仅 menu-bo-linker.spec.js 测 BO 链接        |

#### 7.4.1 关键证据:permission-explainer.spec.js

```javascript
// C01: 后端 explain API 5 步验证 (软失败兼容 v1/v2)
// C02: check API 快速检查 (兼容 v1/v2)
// C03: check_intent API FR-017 (兼容 v1/v2)
// 全部都是: 软失败模式 (WARN),不真正 fail
```

#### 7.4.2 关键证据:data-permission-config.spec.js

```javascript
// C01: aspect scope 表达式求值
// C02: BO has owner_id 字段
// C03: visibility draft 模式 scope 表达式
// 全是 API smoke,不是用户场景 E2E
```

#### 7.4.3 漏测的核心场景

- [ ] **菜单权限**: 不同角色登录后,看到的菜单是否不同 (0 测试)
- [ ] **功能权限运行时**: 角色 A 不能"删除"按钮,角色 B 能 (仅测了配置,不测运行时)
- [ ] **数据权限运行时**: 普通用户只能看自己 owner 的 BO (仅测了 scope 表达式)
- [ ] **Owner 权限切换**: 转移 owner 后,前 owner 看不到 (0 测试)
- [ ] **跨角色对比**: 同一操作,admin/普通用户/只读用户的差异化 (0 测试)
- [ ] **权限拒绝提示**: 无权限时是否给清晰错误
- [ ] **多角色合并**: 一个用户有多个角色时的权限并集
- [ ] **权限缓存失效**: 角色权限变更后,登录用户是否立即生效

***

## 八、真实业务风险评估

如果这些 gap 不补,实际会造成什么业务问题?

| Gap                       | 真实风险                       | 严重度        |
| ------------------------- | -------------------------- | ---------- |
| Association C/D 没测        | 批量添加/删除如果出 bug,**生产数据会出错** | 🔴 高       |
| Value Help Sort/Create 没测 | 用户实际高频使用,**UX 差但没人发现**     | 🟡 中       |
| **菜单权限 0 测**              | 任何用户登录**可能看到不该看的菜单**       | 🔴 严重 (安全) |
| **功能权限运行时 0 测**           | 普通用户**可能能点删除按钮**,数据泄露      | 🔴 严重 (安全) |
| **数据权限 0 测**              | A 部门用户**可能看到 B 部门数据**      | 🔴 严重 (合规) |
| **Owner 权限 0 测**          | 离职员工仍可见原 owner 数据          | 🟡 中       |

***

## 九、更新后的执行顺序 (按业务风险)

> 基于 §7-§8 深度查证,优先级从"功能 gap"重新排序为"业务风险"

### 立即补 (0.5-1 天,\~P0 安全底线)

| # | 任务                                 | 业务价值  | 工作量   |
| - | ---------------------------------- | ----- | ----- |
| 1 | **菜单权限 E2E** (admin/普通/只读 登录后菜单对比) | 🔴 安全 | 0.5 天 |
| 2 | **功能权限运行时** (按钮可见性跨角色对比)           | 🔴 安全 | 0.5 天 |

### 中期补 (1-2 天,\~P1)

| # | 任务                                    | 业务价值     | 工作量   |
| - | ------------------------------------- | -------- | ----- |
| 3 | **Association C/D 完整测试** (单/批 增/删/编辑) | 🔴 数据正确性 | 1 天   |
| 4 | **Value Help Sort/Create/Edit**       | 🟡 UX    | 0.5 天 |
| 5 | **Data 权限运行时** (跨部门数据隔离)              | 🔴 合规    | 0.5 天 |

### 长期补 (1 天,\~P2)

| # | 任务                           | 业务价值 | 工作量   |
| - | ---------------------------- | ---- | ----- |
| 6 | **Owner 权限切换场景** (转移/离职/接手)  | 🟡 中 | 0.5 天 |
| 7 | **跨角色对比** (admin/普通/只读 同一操作) | 🟡 中 | 0.5 天 |

### 不建议做 (过度工程)

- ❌ `filter_combination` 的多选+text+sort 组合场景 (实施复杂,业务使用频次低)
- ❌ 批量迁移 v1→v2 (v1 工作正常)
- ❌ 升级 L3 工具 (已够用)

***

## 十、最终建议与总结

### 10.1 真实优先级 (按"业务风险 × 实施 ROI")

| 排序     | 任务                          | 风险    | 实施 ROI | 总时间   |
| ------ | --------------------------- | ----- | ------ | ----- |
| **#1** | 菜单权限 E2E                    | 🔴 严重 | 极高     | 0.5 天 |
| **#2** | 功能权限运行时                     | 🔴 严重 | 极高     | 0.5 天 |
| **#3** | Data 权限运行时                  | 🔴 严重 | 高      | 0.5 天 |
| **#4** | Association C/D             | 🔴 高  | 中      | 1 天   |
| **#5** | Value Help Sort/Create/Edit | 🟡 中  | 中      | 0.5 天 |
| #6     | Owner 权限切换                  | 🟡 中  | 低      | 0.5 天 |
| #7     | 跨角色对比                       | 🟡 中  | 低      | 0.5 天 |
| #8     | Form Validation 补全          | 🟢 低  | 高      | 0.5 天 |
| #9     | Inline Edit 加深              | 🟢 低  | 中      | 0.5 天 |

**优先做 #1-#3** (1.5 天) - 解决 3 个**安全/合规**风险
**次之 #4-#5** (1.5 天) - 解决数据正确性 + UX
**最后 #6-#9** (2 天) - 完善覆盖

### 10.2 实施路径 (L2 升级)

```
Phase 1: 补 3 个安全/合规 spec (~1.5 天)
  - 菜单权限 (admin/普通/只读 对比)
  - 功能权限 (按钮可见性)
  - Data 权限 (跨部门)

Phase 2: 补 Association C/D + VH 完善 (~1.5 天)
  - association-add-remove.spec.js (10 test)
  - value-help-sort-create.spec.js (6 test)
  - 把现有 5-layer-link.spec.js 升级 v2

Phase 3: Owner + 跨角色 + Form Validation (~2 天)
  - owner-transfer.spec.js
  - role-matrix.spec.js (admin/普通/只读 跨场景)
  - form-validation.spec.js
```

### 10.3 自动化补充建议

| 工具                                | 作用                      | 状态            |
| --------------------------------- | ----------------------- | ------------- |
| `feature_gap_analyzer.py`         | 扫代码 + spec,输出功能层 gap    | ✅ 已建 (本报告)    |
| `ai_discover_e2e_gaps.py`         | 扫路由 + schemas,输出对象层 gap | ✅ 已建          |
| `auto_gen_v2_spec.py`             | URL → v2 spec 自动生成      | ✅ 已建          |
| `check_bo_id_ui.py`               | UI 端 bug 验证 (id=NULL 等) | ✅ 已建          |
| **`permission_matrix_tester.py`** | 跨角色权限对比自动测试             | ❌ 建议建 (0.5 天) |
| **`association_crud_tester.py`**  | Association C/D 自动遍历    | ❌ 建议建 (0.5 天) |

***

## 十一、补充:15 spec 风格统计

| 风格指标                                | 数量        | 占比   |
| ----------------------------------- | --------- | ---- |
| v1 风格 (login + setAdminPermissions) | **15/15** | 100% |
| v2 风格 (auto-fixtures.js)            | **0/15**  | 0%   |
| 使用 soft-fail (WARN)                 | 8/15      | 53%  |
| 使用 test.skip                        | 2/15      | 13%  |
| 单 describe block                    | 15/15     | 100% |

**结论**: 这 15 个 spec **全部需要迁移到 v2** 才能纳入 v2 合规检查;同时半数使用 soft-fail 模式 = 测试弱保证。

***

_本报告由 scripts/feature\_gap\_analyzer.py 自动生成 + 人工深度查证补全 (2026-06-07)_
