# Spec 补充：FR-016 + TBD 决策更新

> 日期：2026-05-16 | 版本：v1.1
> 关联：[02_fr.md](./02_fr.md) | [06_rfc_impl_test_tbd.md](./06_rfc_impl_test_tbd.md)

---

## FR-016: PermissionConfigPanel 维度驱动UI适配

- **描述**: PermissionConfigPanel MUST在 M1 完成完整的UI流程重排。当前页面"菜单与功能权限"在上、"条件型权限"在下，用户先勾菜单再手动加条件规则。改造后**维度范围配置成为第一入口**，菜单和条件从维度自动推导。

- **优先级**: Must
- **类型**: 功能性需求
- **来源**: 用户确认（"角色详情中的权限管理页面的适配也考虑到了对吧"）+ FR-003/FR-015

### AC-016.1: Section 重排 — 维度范围成为第一Section

当前布局：
```
┌──────────────────────────┐
│  菜单与功能权限           │  ← Section 1 (先出现)
│  [MenuPermissionMatrix]   │
├──────────────────────────┤
│  条件型权限               │  ← Section 2 (后出现)
│  [ConditionRuleDialog]    │
└──────────────────────────┘
```

目标布局：
```
┌──────────────────────────┐
│  管理维度范围  【新增】    │  ← Section 1 (优先，维度入口)
│  [DimensionScopePanel]    │
├──────────────────────────┤
│  推荐菜单与功能权限        │  ← Section 2 (自动推导，可微调)
│  [MenuPermissionMatrix]   │
│  推导依据：维度范围内BO有数据│
├──────────────────────────┤
│  数据权限规则              │  ← Section 3 (自动推导，可微调)
│  [ConditionRuleList]      │
│  推导依据：维度范围展开      │
└──────────────────────────┘
```

### AC-016.2: DimensionScopePanel 交互设计

- [AC-016.2.1] 面板显示所有可用的管理维度的级联选择器
  - 第一行：产品选择 (单选下拉) — 从 `management_dimensions` where `code='product'`
  - 第二行：版本选择 (多选标签) — product 选中后，version 选项自动过滤 (级联)
  - 第三行：领域选择 (多选标签) — version 选中后，domain 选项自动过滤
  - 每行右侧有 `☑ 包含下级` 复选框 (如选 domain 含 sub_domain)
  
- [AC-016.2.2] 选择维度值后，面板底部实时显示"数据访问预览"
  - 显示：产品A × 版本V3.0 × 领域{核心领域,通用领域,华东领域} + 下级15个子领域
  - 预估数据量：领域3个、子领域15个、服务模块47个、业务对象200+个
  - 通过调用 `GET /api/v1/roles/{id}/derived-permissions` 获取实时预览

- [AC-016.2.3] 面板底部有按钮：
  - `[推导菜单和权限]` — 调用 DimensionScopeEngine.auto_sync_all() 预览
  - 推导结果自动填充到 Section 2 和 Section 3

### AC-016.3: 三Section联动机制

- [AC-016.3.1] 维度范围变更 → 自动触发 Section 2 和 Section 3 的重新推导
  - Section 2: 菜单列表更新（已勾选的菜单v.s.新推荐的菜单用不同颜色标注）
  - Section 3: 条件规则列表更新（新增/变更/不变的规则用不同标记）

- [AC-016.3.2] 管理员手动调整 Section 2 的菜单勾选 → Section 3 也自动联动
  - 新增菜单 → 自动补全该菜单关联 resource_type 的条件规则
  - 取消菜单 → 对应条件规则标记为"待清理"（不自动删除，管理员确认）

- [AC-016.3.3] 管理员手动调整 Section 3 的条件规则 → 不回写 Section 2
  - 条件规则的独立修改不影响菜单推荐
  - 但会在下次维度范围变更时被覆盖（因为重新推导）

### AC-016.4: 模式切换支持

- [AC-016.4.1] 页面顶部有模式切换 Tabs：
  - Tab 1: "维度驱动" (默认) — 显示维度范围 → 自动推导 → 微调
  - Tab 2: "菜单驱动" (保留) — 原有流程：直接勾选菜单 + 手动条件规则

- [AC-016.4.2] 两种模式共享同一套底层保存逻辑
  - 点击"保存全部权限" → 统一写入 role_permissions/role_menu_permissions/permission_rules/role_dimension_scopes
  - 数据一致：从"菜单驱动"切换到"维度驱动"时，尽可能反向解析已有的条件规则填充维度范围

### AC-016.5: 保存流程

- [AC-016.5.1] 点击"保存全部权限"后按以下顺序写入：
  1. `role_dimension_scopes` — 更新维度范围声明
  2. `role_menu_permissions` — 更新菜单分配
  3. `role_permissions` — 更新功能权限（从菜单 required_permissions 自动同步）
  4. `permission_rules` — 更新条件规则（从维度范围自动推导）

- [AC-016.5.2] 保存失败任一步骤回滚（同一事务）
- [AC-016.5.3] 保存成功提示"已保存 N 项菜单权限 + M 条数据规则"

---

## TBD 决策确认

| TBD | 问题 | 决策 | 理由 |
|-----|------|------|------|
| TBD-01 | 扩展 vs 替换 | **选B — 新建 `menus` 表** (BO化) | 元数据驱动纯粹性；改动面可控 |
| TBD-02 | 维度树M1 vs M4 | **推到 M4** | 当前仅一个确认的维度树；M1 不阻塞 |
| TBD-03 | action_group 枚举 | **固定枚举，M1不实现** | Could优先级；M1先逐个勾选跑通流 |
| TBD-04 | 诊断规则 | **M4 实现** | 不阻塞M1-M3 |
| TBD-05 | 派生角色UI | **M4 实现** | 不阻塞M1-M3 |
| TBD-06 | menuConfig.js 去留 | **localStorage缓存 + 首页兜底** | 零维护成本，API故障不停摆 |

---

## 受影响的文件清单（补充）

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `src/views/SystemManagement/RolePermissionCenter.vue` | 修改 | 增加维度Tabs，重排section顺序 |
| `src/views/SystemManagement/components/PermissionConfigPanel.vue` | **重构** | 增加 DimensionScopePanel section + 重排 |
| `src/views/SystemManagement/components/DimensionScopePanel.vue` | **新建** | 维度范围配置面板组件 |
| `src/views/SystemManagement/composables/useDimensionScopes.ts` | **新建** | 维度范围状态管理 |
| `meta/api/role_dimension_scope_api.py` | **新建** | 维度范围 CRUD + 推导预览API |
