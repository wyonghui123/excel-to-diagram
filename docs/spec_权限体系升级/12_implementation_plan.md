# Spec 12: 统一权限架构 — 实施计划

> 日期：2026-07-24 | 版本：v1.0 | 状态：待评审
> 依赖：Spec 10 (最终方案) + Spec 11 (实现分析)

---

## 1. 总体策略

### 1.1 核心原则

1. **渐进式**: 每个 Phase 独立可交付，Feature flag 控制新旧切换
2. **先内后外**: 先完成后端核心（Layer 1+2），再开放前端（Layer 3）
3. **先事实后配置**: 先建 role_effective_intents 事实表，推导管道写入后再改 UI
4. **零停机迁移**: 新旧系统并行，数据双向同步，灰度切换

### 1.2 Feature Flag 设计

```python
PERMISSION_FLAGS = {
    'effective_intents_enabled': False,    # Phase 1: 启用新求值引擎
    'derivation_pipeline_enabled': False,  # Phase 2: 启用推导管道
    'unified_permission_ui': False,        # Phase 3: 启用新UI
    'condition_structured': False,         # Phase 2: 结构化条件(替代自由文本)
    'action_independent': False,           # Phase 2: action独立性(废弃LEVEL_ORDER)
}
```

---

## 2. Phase 1: Layer 1 基础设施

> 目标：建立事实层，新旧并行

### 2.1 任务清单

| # | 任务 | FR | 产出 | 估时 |
|---|------|----|------|------|
| 1.1 | 新建 role_effective_intents 表 | FR-001 | migration + YAML schema | 0.5d |
| 1.2 | 新建 FieldMetadataRegistry | FR-004 | `field_metadata.py` + 配置生成器 | 1d |
| 1.3 | 新建 ConditionExpressionParser | FR-005 | `condition_parser.py` ({field,op,value}→SQL) | 1.5d |
| 1.4 | 新建 EffectiveIntentChecker | FR-002 | `effective_intent_checker.py` (Owner>Exclude>Include) | 2d |
| 1.5 | 新建 EffectiveIntentDAO | — | `effective_intent_dao.py` (CRUD) | 1d |
| 1.6 | derivation_mode 按维度类型区分 | FR-015 | FieldMetadata 扩展 | 0.5d |
| 1.7 | Feature flag 注入 | — | `permission_flags.py` | 0.5d |
| 1.8 | 单元测试 | — | test_effective_intents.py | 1d |

### 2.2 交付物

```
meta/
  migrations/add_effective_intents.py     ← 新表
  schemas/role_effective_intents.yaml     ← 新YAML
  core/
    effective_intent_checker.py           ← 新求值引擎
    effective_intent_dao.py               ← 新DAO
    condition_parser.py                   ← 条件→SQL
    field_metadata.py                     ← 字段元数据
    permission_flags.py                   ← Feature flag
  tests/
    test_effective_intents.py             ← 新测试
```

### 2.3 验收标准

- [ ] `role_effective_intents` 表创建成功，含 data_scope JSON + derivation_mode
- [ ] EffectiveIntentChecker 通过 4 种场景测试 (Owner/Exclude/Include/默认拒绝)
- [ ] ConditionExpressionParser 支持所有操作符 (=, !=, <, <=, >, >=, IN, NOT IN, CHILDREN_OF, ANCESTORS_OF)
- [ ] FieldMetadataRegistry 从 dimension_object_mapping.yaml 自动生成
- [ ] Feature flag 默认关闭，不影响现有系统

---

## 3. Phase 2: Layer 2 推导管道

> 目标：配置层统一，3源→推导管道→事实表

### 3.1 任务清单

| # | 任务 | FR | 产出 | 估时 |
|---|------|----|------|------|
| 2.1 | 新建 permission_rules_v2 表 | FR-001 | migration + YAML | 0.5d |
| 2.2 | 条件结构化转换 | — | condition 自由文本→[{field,op,value}] 迁移脚本 | 1.5d |
| 2.3 | 新建 PermissionDerivationPipeline | FR-003 | `derivation_pipeline.py` (8步) | 3d |
| 2.4 | 维度展开适配 | FR-003 | DimensionScopeEngine 输出改为 conditions | 1d |
| 2.5 | 级别展开 (LEVEL_BUNDLES) | FR-003 | LEVEL_BUNDLES 定义 + 展开逻辑 | 1d |
| 2.6 | action 独立性切换 | — | LEVEL_ORDER→LEVEL_BUNDLES, Feature flag 控制 | 1d |
| 2.7 | exclude 替代 is_denied | — | is_denied→exclude_conditions 迁移 | 0.5d |
| 2.8 | 菜单反向推导 | FR-011 | MenuBOLinker 扩展 | 0.5d |
| 2.9 | 配置源优先级 | FR-013 | manual>template>derived 冲突解决 | 0.5d |
| 2.10 | 重推导触发 | FR-014 | stale 标记 + 手动/定时触发 | 1d |
| 2.11 | role_dimension_scopes 数据迁移 | — | 迁移到 permission_rules_v2 | 1d |
| 2.12 | 拦截器适配 (读) | — | DataPermissionInterceptor 读取 effective_intents | 2d |
| 2.13 | 拦截器适配 (写) | — | WriteScopeInterceptor 调用 EffectiveIntentChecker | 3d |
| 2.14 | API 适配 | — | permission_rule_v2 端点适配新表 | 1d |
| 2.15 | 回归测试 | — | 40个测试文件全量回归 | 2d |

### 3.2 推导管道详细设计

```python
class PermissionDerivationPipeline:
    """Layer 2 → Layer 1 推导管道"""

    def derive(self, role_id: int) -> DerivationResult:
        # Step 1: 加载3个配置源
        rules = self._load_permission_rules(role_id)
        menus = self._load_role_menus(role_id)
        manual_intents = self._load_manual_intents(role_id)

        # Step 2: 加载对象基线 (可选)
        owd = self._load_object_owd()

        # Step 3: 统一展开 (核心步骤)
        intents = self._unified_expand(rules)

        # Step 4: 维度→菜单推导
        derived_menus = self._derive_menus_from_dimensions(intents)

        # Step 5: 菜单→BO actions 推导 + 反向建议
        menu_intents = self._derive_intents_from_menus(menus)
        reverse_suggestions = self._suggest_menus_for_intents(intents)

        # Step 6: 冲突解决
        resolved = self._resolve_conflicts(intents, menu_intents, manual_intents)

        # Step 7: 合并 → 写入 role_effective_intents
        self._write_effective_intents(role_id, resolved)

        # Step 8: 标记 stale
        self._mark_stale_intents(role_id, resolved)

        return DerivationResult(
            intents=resolved,
            derived_menus=derived_menus,
            reverse_suggestions=reverse_suggestions,
            completeness=self._check_completeness(resolved),
        )
```

### 3.3 数据迁移计划

```
迁移顺序 (零停机):

1. 新建 permission_rules_v2 表 (空表, 不影响现有)
2. 迁移 role_dimension_scopes → permission_rules_v2
   - dimension_code + scope_mode + dimension_values
   - → include_conditions: [{field: dim+"_id", op: scope_mode, value: values}]
3. 迁移 data_permission_rules → permission_rules_v2
   - condition 自由文本 → [{field, op, value}] (条件结构化转换)
   - is_denied=1 → exclude_conditions
   - rule_type='dimension' 的记录合并到 Step 2 的结果
4. 启用 Feature flag 'derivation_pipeline_enabled'
5. 推导管道首次运行, 生成 role_effective_intents
6. 验证: 新旧系统输出一致
7. 切换拦截器读取 effective_intents
8. 废弃旧表 (permission_rules legacy)
```

### 3.4 交付物

```
meta/
  migrations/
    add_permission_rules_v2.py          ← 新表
    migrate_dimension_scopes_to_v2.py   ← 维度迁移
    migrate_rules_to_v2.py              ← 条件迁移
    migrate_is_denied_to_exclude.py     ← deny→exclude
  services/
    derivation_pipeline.py              ← 新推导管道
    condition_converter.py              ← 自由文本→结构化
  core/
    level_bundles.py                    ← LEVEL_BUNDLES 定义
  tests/
    test_derivation_pipeline.py         ← 新测试
    test_derivation_e2e.py              ← E2E测试
```

### 3.5 验收标准

- [ ] 推导管道 8 步全部通过单元测试
- [ ] role_dimension_scopes 数据 100% 迁移到 permission_rules_v2
- [ ] data_permission_rules 数据迁移, 条件结构化转换无丢失
- [ ] 推导管道输出 → role_effective_intents 写入正确
- [ ] 笛CARTESIAN积语义保留 (AC-008 回归通过)
- [ ] DataPermissionInterceptor 读取 effective_intents, 结果与旧系统一致
- [ ] WriteScopeInterceptor 调用 EffectiveIntentChecker, 结果与旧系统一致
- [ ] 40 个测试文件全量回归通过

---

## 4. Phase 3: Layer 3 交互

> 目标：前端统一权限配置体验

### 4.1 任务清单

| # | 任务 | FR | 产出 | 估时 |
|---|------|----|------|------|
| 3.1 | UnifiedPermissionPanel (双模式) | FR-006/007/019 | 新Vue组件 | 3d |
| 3.2 | ConditionEditor (结构化) | FR-005 | {field,op,value} 编辑器 | 2d |
| 3.3 | EffectiveIntentTable (细粒度) | FR-007 | Intent编辑表 | 1.5d |
| 3.4 | DerivationChainViewer | FR-008 | 推导链可视化 | 1.5d |
| 3.5 | SqlPreviewPanel | FR-009 | SQL预览+资源预估 | 1d |
| 3.6 | CompletenessIndicator | FR-017 | 红黄绿灯 | 0.5d |
| 3.7 | RoleDiffViewer | FR-018 | 角色对比 | 1d |
| 3.8 | PermissionSimulator | FR-016 | 访问模拟 | 1d |
| 3.9 | 高效模式 Step 1-6 流程 | FR-006 | 模板+维度+级别+条件+菜单+预览 | 2d |
| 3.10 | 权限级别提示 | — | 选择级别时显示包含actions | 0.5d |
| 3.11 | 前端测试 | — | Vitest + E2E | 1d |

### 4.2 交付物

```
src/
  views/SystemManagement/
    components/
      UnifiedPermissionPanel.vue        ← 新主面板
      ConditionEditor.vue               ← 结构化条件编辑
      EffectiveIntentTable.vue          ← 细粒度编辑
      DerivationChainViewer.vue         ← 推导链
      SqlPreviewPanel.vue               ← SQL预览
      CompletenessIndicator.vue         ← 红黄绿灯
      RoleDiffViewer.vue                ← 角色对比
      PermissionSimulator.vue           ← 访问模拟
    composables/
      usePermissionRules.ts             ← 新composable
      useDerivationPipeline.ts          ← 推导管道
      useEffectiveIntents.ts            ← Intent管理
```

### 4.3 验收标准

- [ ] 高效模式 6 步流程完整可用
- [ ] 细粒度模式直接编辑 Intent 事实
- [ ] 高效↔细粒度同页 Tab 无缝切换, 修改不丢失
- [ ] ConditionEditor 支持 {field, op, value} 结构化编辑
- [ ] 推导链可视化: 维度→菜单→actions 可点击查看来源
- [ ] SQL预览实时更新
- [ ] 完整性指示: 🔴🟡🟢 正确显示
- [ ] 角色对比: 差异高亮

---

## 5. Phase 4: 迁移兼容与收尾

> 目标：灰度切换全量上线 + 清理旧代码

### 5.1 任务清单

| # | 任务 | 产出 | 估时 |
|---|------|------|------|
| 4.1 | 灰度切换: 5%→25%→50%→100% | 灰度配置 | 0.5d |
| 4.2 | 线上验证: 新旧系统输出对比 | 对比脚本 | 1d |
| 4.3 | 性能测试: 推导管道+求值引擎 | 性能报告 | 1d |
| 4.4 | 废弃旧表: permission_rules (legacy) | 迁移+删除 | 0.5d |
| 4.5 | 废弃旧代码清理 | 代码删除 | 1d |
| 4.6 | 文档更新 | 开发者文档 | 0.5d |

### 5.2 灰度切换策略

```
灰度阶段:
  5%:  仅 admin 用户使用新系统
  25%: 随机 1/4 用户使用新系统
  50%: 随机 1/2 用户使用新系统
  100%: 全量切换

每个阶段:
  1. 运行 24h, 监控错误率
  2. 对比新旧系统输出 (抽样 100 条请求)
  3. 错误率 < 0.1% → 进入下一阶段
  4. 错误率 ≥ 0.1% → 回退, 分析原因
```

---

## 6. 风险与缓解

| # | 风险 | 概率 | 影响 | 缓解 |
|---|------|------|------|------|
| 1 | WriteScopeInterceptor 重构影响写操作 | 高 | 严重 | Phase 2 分两步: 先适配接口不改逻辑, 再优化内部 |
| 2 | 条件结构化转换丢失语义 | 中 | 严重 | 迁移脚本+人工抽查+对比测试 |
| 3 | LEVEL_ORDER→action独立 影响现有权限检查 | 高 | 严重 | Feature flag 控制, 灰度切换 |
| 4 | 推导管道性能 (首次全量推导) | 中 | 中 | 增量推导+缓存+预热 |
| 5 | 前端重构影响用户体验 | 中 | 中 | 新UI与旧UI并行, Feature flag切换 |

---

## 6.1 Phase 1 执行记录 (2026-07-24)

> 状态：✅ 已完成 | 35/35 测试通过

### 已交付文件

| # | 文件 | 职责 | 测试覆盖 |
|---|------|------|---------|
| 1 | [add_effective_intents.py](file:///d:/filework/worktrees/release-prep/meta/migrations/add_effective_intents.py) | Migration: role_effective_intents 表 | — |
| 2 | [role_effective_intents.yaml](file:///d:/filework/worktrees/release-prep/meta/schemas/role_effective_intents.yaml) | YAML schema 定义 | — |
| 3 | [condition_parser.py](file:///d:/filework/worktrees/release-prep/meta/core/condition_parser.py) | {field,op,value}→SQL WHERE 解析器 | 10 个测试 |
| 4 | [field_metadata.py](file:///d:/filework/worktrees/release-prep/meta/core/field_metadata.py) | 字段元数据注册表 | 5 个测试 |
| 5 | [effective_intent_dao.py](file:///d:/filework/worktrees/release-prep/meta/core/effective_intent_dao.py) | role_effective_intents CRUD | 6 个测试 |
| 6 | [effective_intent_checker.py](file:///d:/filework/worktrees/release-prep/meta/core/effective_intent_checker.py) | 求值引擎 Owner>Exclude>Include | 9 个测试 |
| 7 | [permission_flags.py](file:///d:/filework/worktrees/release-prep/meta/core/permission_flags.py) | Feature flag 控制 | 3 个测试 |
| 8 | [test_effective_intents.py](file:///d:/filework/worktrees/release-prep/meta/tests/test_effective_intents.py) | TDD 测试 (35 个用例) | — |

### 测试结果

```
35 passed in 0.70s

TestConditionExpressionParser::         10/10 PASSED
TestFieldMetadataRegistry::              5/5  PASSED
TestEffectiveIntentDAO::                 6/6  PASSED
TestEffectiveIntentChecker::             9/9  PASSED
TestDerivationMode::                     2/2  PASSED
TestPermissionFlags::                    3/3  PASSED
```

### 关键设计决策 (执行中确认)

1. **_is_owner 只检查 owner_id**：不检查 created_by，created_by 是普通字段可用于 include 条件
2. **include 不匹配 → default_deny**：source 标记为 `default_deny` 而非 `include`
3. **CHILDREN_OF 子查询**：通过 `_DIM_CHILD_TABLES` 映射字段→子表，生成 `IN (SELECT ...)` 子查询
4. **derivation_mode 默认值**：domain_id/sub_domain_id → dynamic，product_id/version_id → static
5. **Feature flag 环境变量覆盖**：`PERMISSION_FLAG_<NAME>=1` 可运行时覆盖

### 零影响验证

- Feature flag 默认关闭 → 不影响现有系统
- 全新文件 → 不修改任何现有代码
- 独立测试 DB → 不污染主数据库

---

## 7. 时间线与里程碑

```
Phase 1 (Layer 1 基础设施):     7.5d  ← 可独立交付
  ├─ 1.1~1.3 表+元数据+解析!解析器       3d
  ├─ 1.4~1.5 求值引擎+DAO               3d
  └─ 1.6~1.8 derivation+flag+测试       1.5d

Phase 2 (Layer 2 推导管道):     20d   ← 核心阶段
  ├─ 2.1~2.3 新表+条件转换+管道         5d
  ├─ 2.4~2.7 维度适配+级别+action+exclude 3d
  ├─ 2.8~2.11 反向推导+优先级+重推导+迁移 3d
  ├─ 2.12~2.13 拦截器适配(读+写)        5d
  ├─ 2.14 API适配                       1d
  └─ 2.15 回归测试                       3d

Phase 3 (Layer 3 交互):         15d   ← 前端重构
  ├─ 3.1~3.3 主面板+条件编辑+Intent表   6.5d
  ├─ 3.4~3.8 推导链+SQL+完整性+对比+模拟 5d
  └─ 3.9~3.11 高效模式+级别提示+测试    3.5d

Phase 4 (迁移兼容):             4.5d  ← 收尾
  └─ 4.1~4.6 灰度+验证+性能+清理       4.5d

总计: ~47d
```

### 7.1 关键里程碑

| 里程碑 | 时间点 | 标志 |
|--------|--------|------|
| M1: Layer 1 可用 | Phase 1 完成后 | EffectiveIntentChecker 通过所有测试 |
| M2: 推导管道可用 | Phase 2 Step 2.3 完成后 | 3源→effective_intents 写入正确 |
| M3: 拦截器切换 | Phase 2 Step 2.13 完成后 | 新旧系统输出对比一致 |
| M4: 前端可用 | Phase 3 完成后 | 新UI功能完整+旧UI仍可用 |
| M5: 全量上线 | Phase 4 灰度100% | 错误率<0.1%持续7天 |

---

## 8. Could 级需求 (Phase 5+, 按需排期)

| FR | 描述 | 估时 | 优先条件 |
|----|------|------|---------|
| FR-010 | 冲突检测 | 1d0 | Phase 3 上线后 |
| FR-012 | 对象基线共享 (OWD) | 2d | 多角色合并场景复杂化后 |
| FR-016 | 访问模拟 | 1d | 审计合规需求 |
| FR-021 | 角色互斥约束 | 1d | 互斥业务场景出现 |
| FR-022 | 配置变更版本化 | 2d | 配置回滚需求 |

---

## 9. 与现有代码的对接点

### 9.1 Phase 1 不修改的文件 (零影响)

- `condition_permission_service.py` — 不改, 新建 effective_intent_checker
- `dimension_scope_engine.py` — 不改, Phase 2 再适配
- `data_permission_interceptor.py` — 不改, Phase 2 再适配
- `write_scope_interceptor.py` — 不改, Phase 2 再适配
- 所有前端组件 — 不改, Phase 3 再重构

### 9.2 Phase 2 需修改的文件 (有影响但兼容)

| 文件 | 修改方式 | 兼容策略 |
|------|---------|---------|
| `dimension_scope_engine.py` | 输出改为 conditions | Feature flag: 旧输出/新输出 |
| `data_permission_interceptor.py` | 读取 effective_intents | Feature flag: 旧路径/新路径 |
| `write_scope_interceptor.py` | 调用 EffectiveIntentChecker | Feature flag: 旧逻辑/新逻辑 |
| `bo_api.py` (permission_rule_v2) | 适配新表 | 双写: 新表+旧表 |

### 9.3 Phase 3 需修改的前端文件

| 文件 | 修改方式 |
|------|---------|
| `PermissionConfigPanel.vue` | 替换为 UnifiedPermissionPanel |
| `DimensionScopePanel.vue` | 合并到 UnifiedPermissionPanel |
| `ConditionRuleList.vue` | 合并到 UnifiedPermissionPanel |
| `ConditionRuleDialog.vue` | 替换为 ConditionEditor |
| `useConditionRules.ts` | 替换为 usePermissionRules |
