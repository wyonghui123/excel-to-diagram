# 权限安全 Backlog (2026-09-15 摸底)

> **生成方式**: 实测代码 + spec 对比, 不靠记忆
> **范围**: Spec 19 (M4 软删) + Spec 21 (action 对象级) + Spec 22 (state_transition action 池) + 通用安全
> **风险等级**: [P0-CRITICAL] P0 阻断 / [P1-HIGH] P1 紧迫 / [P2-MEDIUM] P2 排期

---

## TL;DR

| 类别 | 数量 | 关键缺口 |
|---|---|---|
| [P0-CRITICAL] P0 安全阻断 | 2 | **FR-005 全局管理员专属门禁未实施** + **FR-006 防提权硬规则缺审计** |
| [P1-HIGH] P1 安全紧迫 | 4 | **FR-007 委托预览未实施** + Spec 22 T-22-04 端点缺 + 前端整合半成品 + E2E 测试覆盖薄弱 |
| [P2-MEDIUM] P2 安全排期 | 5 | spec 22 T-22-11 E2E + TBD-2/3/5 + Spec 19 §10 长期项 |

---

## [P0-CRITICAL] P0：安全阻断 (本周处理)

### P0-1: FR-005 全局管理员专属门禁未实施

**spec 来源**: [Spec 19 §3 FR-005 L80-89](./19_org_admin_delegation.md)

> **敏感动作门禁（全局管理员专属）**: 受托管理员不能改 org 名称/标识符（受托范围可改结构不可改标识）、不能删 org（仅能冻结）

**实测现状**:
- `meta/services/org_service.py` [MISSING] 无 is_global_admin 检查
- `meta/services/` 全 grep `is_global_admin|sensitive_action` 0 命中
- `meta/core/interceptors/permission_interceptor.py` 仅 L264 注释 `[v2.1] 写 scope 拒绝 (FR-005)`

**风险**: 受托管理员可改/删 org 标识符, 破坏审计可追溯性

**实施内容**:
1. `_standard_actions.yaml` 加 `sensitive_action: true` 标记 (delete_org / rename_org / delete_user / freeze 等)
2. `PermissionInterceptor` 加 `_check_global_admin_for_sensitive(context)` 前置门
3. 受托管理员访问敏感 action → 403 `error_code: GLOBAL_ADMIN_ONLY`
4. 后端 pytest 测试 (≥6 用例)

**估算**: 1.5d

### P0-2: FR-006 防提权三硬规则缺审计

**spec 来源**: [Spec 19 §3 FR-006 L89-96](./19_org_admin_delegation.md)

> **防提权三硬规则**: 受托管理员 (a) 不能授 admin 权限集 (b) 不能给自身加权限集 (c) 不能改资源矩阵 admin 行

**实测现状**:
- `meta/services/permission_set_service.py` [MISSING] 无 is_global_admin 阻止授权 admin
- `meta/api/permission_set_api.py` [MISSING] 无"自身加权限集"拦截
- `meta/core/permission_spec.py` [MISSING] 无"改 admin 行"识别

**风险**: 受托管理员可提权为全局管理员 (横向越权最严重等级)

**实施内容**:
1. `PermissionSetService.assign_to_user(target_user, permission_set)` 加 global_admin 拦截
2. `UserApi.assign_permission_set` 加 "target_user == current_user" 拒绝
3. `PermissionSetMatrixApi.PUT` 加 "admin 行不可改" 拦截
4. 三处统一 raise `EscalationDenied` 异常 → 403 `error_code: ESCALATION_DENIED`
5. 完整 audit log (含原 target_user_id, attempted_permission_set_id, current_user_id)
6. 后端 pytest 测试 (≥9 用例, 3 类 × 3 种操作)

**估算**: 2d

---

## [P1-HIGH] P1：安全紧迫 (本月处理)

### P1-1: FR-007 委托结果预览未实施

**spec 来源**: [Spec 19 §3 FR-007 L96-100](./19_org_admin_delegation.md)

> **委托结果预览**: 显示授权前/后 diff (新增/移除的资源, 新增/移除的动作), 受托方可拒绝接受

**实测现状**:
- `meta/services/org_admin_scope_service.py` [MISSING] 无 preview / diff 方法
- `meta/api/` 全 grep `preview_diff|before_delegation|after_delegation` 0 命中

**实施内容**:
1. `OrgAdminScopeService.preview_delegation(target_user, proposed_rules)` → 返回 diff dict
2. `GET /api/v2/org/delegation-preview?user_id=X&scope=Y` endpoint
3. 前端 ResourceActionMatrix 加"预览"模式
4. 后端 pytest 测试 (≥4 用例)

**估算**: 1.5d

### P1-2: Spec 22 T-22-04 state-transition-actions endpoint 缺

**spec 来源**: [Spec 22 §2 FR-005](./22_state_transition_action_pool.md)

> **GET /api/v2/bo/{type}/state-transition-actions**: 返回该对象类型所有 state_transition action_ref + 启用状态

**实测现状** (2026-09-16 修正):
- [OK] **`meta/api/bo_api.py` 已有 endpoint**: commit `62d8b445` (V061 staging 2026-09-13) 实施, line 2145 `get_state_transition_actions(object_type)`, 含登录装饰器 + 对象级 404 + 字段契约 (id/name/actionRef/label/icon/highlight/stateField/toState)
- [OK] **路由顺序正确**: 已在 `/<path:obj_id>` 之前注册 (沿用 §6.8 fix 路径, 避免贪婪匹配)
- [OK] **前端已对接**: `boService.getStateTransitionActions(rt)` ([boService.js:156](file:///d:/filework/excel-to-diagram/src/services/boService.js#L156-L161)) + `usePermissionMeta.loadStateTransitionActions` ([usePermissionMeta.js:70](file:///d:/filework/excel-to-diagram/src/composables/usePermissionMeta.js#L70-L91)) + `supportedActions` computed 自动合并
- [?] **后端 pytest**: 15 用例覆盖 FR-001/002/004/007/路由顺序, **未覆盖 endpoint 行为** (新增 endpoint 行为测试建议)

**[OK] P1-2 实际状态: 已实施完成**, 之前 P1-2 backlog 条目描述"endpoint 缺"是 2026-09-13 摸底时的过期快照, V061 staging 已捎带 commit

**[P3-MEDIUM] 子项: endpoint 行为测试 + 前端 lastError 暴露 (0.5d)**

**风险**: endpoint 已上线但 0 个 pytest 用例覆盖, 未来重构 (e.g. 改去重逻辑、改字段名) 无回归保护

**实施内容**:
1. `test_spec22_state_transition_action_pool.py` 加 5 用例: 基础返回 / 同 action_ref 去重 / 404 未知类型 / 空 action_ref 跳过 / 字段契约
2. `usePermissionMeta.loadStateTransitionActions` 失败时改为暴露 `lastError {code: STATE_TRANSITION_ACTIONS_PARTIAL_FAIL, message: 含失败 rt}` 而非 console.warn 静默吞错 (UI 可感知后端问题)

**估算**: 0.5d

### P1-3: Spec 22 §6.8 复用债 (半成品)

**spec 来源**: [Spec 22 §6.8 复用债治理](./22_state_transition_action_pool.md)

**现状** (2026-09-16 更新):
- [OK] §6.8.3 已 commit (`b76dfee`): usePermissionMeta 单一真源
- [OK] §6.8.4 已 commit (ConditionRuleDialog composable)
- [OK] **子项 C 已 commit (`8499eb3` 2026-09-16)**: ResourceActionMatrix.vue JS → TS 迁移 (1d 完成)
  - 14 个 props + 4 个 emits 类型化 → TS `defineProps<Props>` + `defineEmits<Emits>`
  - 类型定义收敛到 `../constants/permissionConstants.ts` (单一真源, 跨组件共享)
  - 内部分 15 个 interface / type: ActionType / ActionMetaItem / MatrixCell / MatrixRow / MatrixPayload / ScopeMatrixEntry / ScopeMatrix / DimensionItem / ContextMenu / ResourceHierarchyEntry / ResourceTypeLabels / ActionLabels / ActionHints / SupportedActionsMap / ExternalResourceFilters / ExternalResourceFilterMode / ResourceActionMatrixEmits
  - 内部 ~80 个 ref/computed/function 保持 JS（务实分层, 收益不抵成本）
  - vite build 通过 (4289 modules, 0 error)
- [DEFERED] **子项 A**: scopeMatrix 平铺逻辑抽取 → P2 backlog (等第二个调用方出现)
- [DEFERED] **子项 B**: DetailPage section.type 分发器重构 → P3 独立专项 (与权限无关, 转 UI 前端组长)

**风险**: 子项 C 完成后徽标"不同步"风险已收敛到 `useMenuPermission.ts:209-214` 的 `recalcBoGroupStatus` 模块级函数 (原 useMenuPermission 与 MenuPermissionMatrix 各维护一份逐行同构的实现, 现收敛为此唯一实现)。

**已实施** (2026-09-16 commit `8499eb3`):
1. ResourceActionMatrix.vue JS → TS 迁移 (1d 完成)
2. 类型定义收敛到 permissionConstants.ts
3. vite build 验证 (0 error)

**仍需 PM 决策**:
- A 是否维持 [DEFERED]: 等触发条件 (第二个 scopeMatrix 调用方出现) 自动立项
- B 是否独立专项: 不应混在权限 backlog, 转 UI 前端组长

**原 1d 估算**: 实际 1d 完成 (子项 C), A/B 维持 DEFERED。

### P1-4: Spec 22 E2E Playwright 测试覆盖薄弱

**spec 来源**: [Spec 22 §5 T-22-11](./22_state_transition_action_pool.md)

**实测现状**:
- 后端 pytest: [OK] 15 用例 (`test_spec22_state_transition_action_pool.py`)
- 前端 vitest: [?] 待查 (本任务未深入前端目录)
- **E2E Playwright: [MISSING] 0 文件**

**风险**: state_transition action_ref 拦截器**已上线无 E2E 验证**, 集成风险未知

**实施内容**:
1. E2E 场景 1: 非管理员用户改 user.status 走 state_transition rule → 403 (无 action_ref 权限)
2. E2E 场景 2: 同上但用户持有 unlock action → 200
3. E2E 场景 3: admin 通配符放行 → 200
4. E2E 场景 4: 自定义 rule 无 action_ref 走 allowed_roles 兜底 → 200
5. E2E 场景 5: action_ref 空字符串走 allowed_roles → 200

**估算**: 1.5d

---

## [P2-MEDIUM] P2：安全排期 (下季度)

### P2-1: Spec 22 TODO-1~4 (PM 反馈第十六次, audit_log row_snapshot + restore)

**spec 来源**: [Spec 22 §6.6 L1017-1020](./22_state_transition_action_pool.md)

| TODO | 内容 | 优先级 |
|---|---|---|
| TODO-1 | `audit_log.yaml` 加 row_snapshot (json) + snapshot_version (string) 字段 | P1 |
| TODO-2 | AuditInterceptor.before_action 在 DELETE 时序列化全行到 row_snapshot | P1 |
| TODO-3 | POST /api/v2/audit_log/{id}/restore endpoint, 独立权限码 audit_log:restore (仅 admin) | P1 |
| TODO-4 | 文档化「长期不活跃场景用 deactivate + frozen」决策 | P2 |

**风险**: TODO-3 是新 endpoint + 新权限码, **未实施直接生产风险** (无 restore, archive/restore 撤销后遗留空白)

**建议**: TODO-1+2 (1d) + TODO-3 (1d) + TODO-4 (0.5d)

### P2-2: Spec 22 §6.5.8 同步 TODO (其他 yaml status 同步)

**spec 来源**: [Spec 22 §6.5.8 L957-961](./22_state_transition_action_pool.md)

| TODO | 内容 |
|---|---|
| 同步 permission_set.yaml / product.yaml 扩 4 状态 | 当前仅 user 扩 |
| list filter widget 同步加 frozen 选项 | |
| reset_password 走 BoActionRegistry | 当前未走, 在 endpoint 层 |

**估算**: 0.5d

### P2-3: Spec 19 TBD-3/5

**spec 来源**: [Spec 19 §10 TBD L466-471](./19_org_admin_delegation.md)

| TBD | 内容 |
|---|---|
| TBD-3 | 受托管理员登录首页导航适配 (M2 UI 实现时定) |
| TBD-5 | FR-013 L3 门禁清单集中呈现 (随 M3 排期) |

### P2-4: Spec 19 TBD-6

**spec 来源**: [Spec 19 §10 TBD L471](./19_org_admin_delegation.md)

> TBD-6: 实例级有效权限树 (Azure Check access 式: BO 实例节点 + Inherited 来源徽标, 懒加载限范围)

**风险**: 这是 Spec 14/15/17 多次遗留的"为什么我能/不能操作这个实例"可解释性终极方案

**估算**: 3d (立项到 v1)

### P2-5: Spec 21 FR-002 敏感动作未配范围警示

**spec 来源**: [Spec 21 §4.2 L530-536](./21_action_object_instance_scope_clarification.md)

> 勾 delete + 无数据范围 → 行左侧出现 [WARN] 警示; hover 显示已开放的敏感动作清单

**实测现状**: 验收清单全 ☐, 未实施

**风险**: **配置员容易误授权**敏感动作 (delete/export) 到全实例, 无警示

**估算**: 1d

---

## 跨规格安全缺口

### X-1: 受托管理员操作 audit log 完整性

**现状**:
- Spec 19 M2 已通过 NFR-003 (审计完整性) 验收
- 但 FR-005/006/007 未实施, 等于"防御代码缺位 + 审计也记录不到攻击尝试"

**建议**: P0-1 + P0-2 实施时一并加 attack-attempt audit log

### X-2: 矩阵 cell "配置未保存" 状态 UI 不可见

**现状**:
- Spec 21 §3.2.4 已设计但未实施
- 配置员误以为已保存实际未保存 → 误授权

**风险等级**: 中 (业务错误, 非安全攻击, 但影响授权合规)

**估算**: 0.5d (在 Spec 21 P2 backlog)

### X-3: 数据导出 (export) 全实例未配范围 = 真实泄露路径

**现状**:
- Spec 21 §1.2 明确指出 "16 个 BO 中**所有默认状态下**矩阵 cell 勾选 + 数据范围未配置 → 用户实际拥有该类对象的所有实例的操作权"
- **敏感动作 (delete / export / import) 尤其危险**

**风险等级**: [P0-CRITICAL] 实际泄露路径

**建议**: 优先 P2-5 (敏感动作警示) + P0-1 (FR-005 全局管理员专属)

---

### P2-A: [OK 已完成] SearchHelpDialog 元数据驱动 (移除 DIMENSION_LABEL_MAP 硬编码)

**实测现状** (2026-09-16, commit `3a2b53b`):
- 删除 `SearchHelpDialog.vue` 硬编码 `DIMENSION_LABEL_MAP` (5 BO 名: product/version/domain/sub_domain/service_module)
- 改用 `permissionService.getResourceLabel(targetBo)` (后端 `/permission_dimension/meta` 优先, fallback 常量 `RESOURCE_LABELS`, 未知 key 原样返回)
- `dialogTitle` 计算保持"选择XX"语义, 新 BO 名自动从元数据获取
- 移除 `externalSelectedItems` watcher 两个 `console.log` 调试代码

**风险消除**: 新增 BO 时无需修改前端, 后端 `permission_dimension` metaCache + 后端 `RESOURCE_LABELS` 常量是单一真理源

**估时**: 0.2d (实测 <1h)

### P2-D: [OK 已完成] 移除 SearchHelp L4 死代码封装

**实测调研** (2026-09-16):
- `src/components/common/SearchHelp/` 4 个 L4 封装 (`SearchHelpListSingle/ListMulti/TreeSingle/TreeMulti`) 没有任何外部调用方
- 仅在 `components/common/index.js` 中导出 (3 处)
- `src/` 全 grep `SearchHelp(ListSingle|ListMulti|TreeSingle|TreeMulti)`: 0 个 import 命中
- 真正常用的是 `SearchHelpDialog` (L2) + `ValueHelpField/ConditionRuleBuilder` (L3)

**改动**:
- 删除整个 `SearchHelp/` 目录 (4 vue + index.js)
- `components/common/index.js` 清理 3 处导出
- 减 4 文件 + ~190 行死代码

**YAGNI**: 元数据驱动的"语义化门面"如无需求不保留抽象

**估时**: 0.5d (实测 <1h)

### P2-X: [OK 已完成] ConditionRuleDialog 业务逻辑下放 composable (C 方案)

**实测现状** (2026-09-16, commits `ba37864` + `2d2efa9`):
- `useConditionRuleDialog.js` 升级为 dialog 完整业务逻辑封装 (102 → 599 行, +26 个新接口)
- `ConditionRuleDialog.vue` 846 → 460 行 (-45%), 仅保留模板 + props/emits + 解构 composable + readonly dialogTitle 重写 + init watch
- 下放覆盖: form reactive + scopeMode 互映 / Rule Builder state (customRules/treeRef/showAdvanced/customCondition) / syncCustomRules (含 v57 pureBizKeyIn) / loadFieldMetadata + fetchOverlapWarnings / preview state + doPreview (debounce 600ms) / handleSave (Spec 20 v5 L4 + v6 display) / buildRuleFromParsed + hydratePickerNames (含 /codes 端点) / init(rule) 替代 onMounted

**BUG fix**: `2d2efa9` 修 TDZ (customCondition 在 watch 前声明)

**风险消除**:
- dialog 业务逻辑可独立单元测试 (无需 mount 完整 SFC)
- 调用方 (PermissionConfigPanel + ReadonlyAggregateSection) 无改动 — P1-2 接口已对齐

**估时**: 2d (实测 <2h)

### P2-Y: [DEFERED] HierarchicalTreePicker dimension 硬编码收敛 (B 方案)

**spec 来源**: 二次检查 search-help + condition 配置通用组件讨论 (2026-09-16)

**实施内容**:
- `SearchHelpDialog.vue:313-314` `HierarchicalTreePicker` dimension 硬编码 (`/api/v2/bo/permission_dimension/{dim}/tree`, rootType='product')
- 改走 `metaService` 元数据 + 通用自引用 BO 路径 (`value-help` + `extra.parent_id`)

**估算**: 1d

### P2-Z: [DEFERED] ConditionRuleDialog 瘦身 (E 方案)

**spec 来源**: 二次检查 search-help + condition 配置通用组件讨论 (2026-09-16)

**实施内容**:
- 1450 行 dialog, 拆分出独立 RuleEditor / FieldPicker / RulePreview 3 个子组件
- 配合 P2-X composable 下放

**估算**: 1.5d

---

## 总估算

| 类别 | 任务数 | 总天数 | 优先顺序 |
|---|---|---|---|
| [P0-CRITICAL] P0 | 2 | 3.5d | 本周 (PM 确认后立即启动) |
| [P1-HIGH] P1 | 4 | 4.5d | 本月 (与 P0 并行或接续) |
| [P2-MEDIUM] P2 | 5+ (A/D 完成) | 6d+ (4.5d 净) | 排期 (下季度) |
| **合计** | **11+** | **14d+** | — |

---

## 启动建议

**PM 决策三选** (借鉴 v088/v089 流程):

| # | 决策点 | 推荐 | 理由 |
|---|---|---|---|
| 1 | P0-1 + P0-2 是否同周启动? | **分两周** | 风险不同 (门禁 vs 防提权), 拆开便于回滚 |
| 2 | P0-1 是否带 `sensitive_action: true` yaml 标记先做? | **YES** | 数据层先行, 跟 v088 软删模式一致 |
| 3 | P1-2 (state-transition-actions endpoint) 是否依赖 P0-1? | **不依赖** | Spec 22 是独立的, 可并行 (注: 2026-09-16 实测 endpoint 已实施, 仅剩测试 + lastError 子项) |
| 4 | P2-5 (敏感动作警示) 是否复用 P0-1 的 sensitive_action 标记? | **YES** | 一举两得, 配置源统一 |

**实施顺序建议**:

```
Week 1: P0-1 (FR-005 全局管理员专属门禁)
   └─ Day 1-2: _standard_actions.yaml 加 sensitive_action 标记
   └─ Day 2-3: PermissionInterceptor 加门禁
   └─ Day 3-4: 后端 pytest 6 用例 + audit log 增强
   └─ Day 5: 数据摸底 + 部署 runbook

Week 2: P0-2 (FR-006 防提权三硬规则)
   └─ Day 1-2: PermissionSetService.assign_to_user 拦截
   └─ Day 2-3: UserApi.assign_permission_set 自我拦截
   └─ Day 3-4: PermissionSetMatrixApi admin 行拦截
   └─ Day 4-5: 后端 pytest 9 用例 + 部署 runbook

Week 3-4: P1-1~P1-4 并行
   └─ P1-1 FR-007 委托预览 (1.5d)
   └─ **P1-2 [OK 已完成] endpoint 实施 (2026-09-13 62d8b445)** + 子项: 行为测试 + lastError 暴露 (0.5d)
   └─ **P1-3 [OK 子项 C 完成 8499eb3] ResourceActionMatrix TS 迁移 (1d)** + A/B 维持 DEFERED
   └─ P1-4 E2E Playwright 5 场景 (1.5d)

Q1 2027: P2 全部 + v09x DROP COLUMN
```

---

## 附录: 实施所需工具

| 工具 | 路径 | 用途 |
|---|---|---|
| `v19_p2_audit_remote.py` | `tools/v19_p2_audit_remote.py` | 数据摸底 (待复用) |
| `v19_p2_preflight_backup.py` | `tools/v19_p2_preflight_backup.py` | cold backup (复用 v088) |
| `v19_v089_legacy_safety_audit.py` | `tools/v19_v089_legacy_safety_audit.py` | 校验新表覆盖 (复用 v089) |
| `v19_*_preflight_backup.py` | (新建) | P0-1/2 部署前摸底 |
| `_standard_actions.yaml` | `meta/schemas/_standard_actions.yaml` | action 池 (加 sensitive_action 字段) |

---

**生成时间**: 2026-09-15
**生成依据**: 实测代码 grep + spec 文档对比
**下一步**: PM 决策 → 立项 → 拆票 (T-P0-1-XX 等)