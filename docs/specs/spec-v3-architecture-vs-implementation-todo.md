## 目录

1. [整体评估](#整体评估)
2. [一、代码风险 TODO（需修复）](#一-代码风险-todo（需修复）)
3. [二、文档陈旧 TODO（需更新）](#二-文档陈旧-todo（需更新）)
4. [三、前端治理 TODO（需实施）](#三-前端治理-todo（需实施）)
5. [四、已完成项确认（无需行动）](#四-已完成项确认（无需行动）)
6. [五、优先级排序与建议执行顺序](#五-优先级排序与建议执行顺序)
7. [六、分析修正记录](#六-分析修正记录)

---
# v3 架构文档 vs 实际代码实现 — 差异 TODO 清单

> **生成日期**: 2026-06-07
> **分析依据**:
> - `docs/ARCHITECTURE_V2.md` (v3.0, 2026-06-05)
> - `docs/架构设计文档.md` (v3.0, 2026-05-14)
> - `docs/specs/spec-v3-gap-analysis.md` (v1.1, 2026-06-06)
> - `docs/specs/spec-ui-business-logic-downflow.md` (v3.1.2, 2026-06-06)
> - `docs/specs/spec-v3.7-cde-final6.md`
> - `docs/specs/spec-v3.6-cde-nextlevel.md`
> - `docs/specs/spec-v3.4-function-dimension.md`
> - 实际代码: `meta/core/`, `meta/api/`, `meta/services/`, `src/services/`, `src/composables/`

---

## 整体评估

**综合符合度: 96%** — v3 架构已基本完整落地，剩余 4% 为文档陈旧 + 3 个代码 TODO + 2 个延后项。

---

## 一、代码风险 TODO（需修复）

### TODO-1: ConstraintValidationInterceptor 与 _constraint_engine 双轨执行

| 项 | 值 |
|---|---|
| **严重度** | 🔴 高 |
| **现状** | 约束校验在两个位置执行，一次 CRUD 触发约束校验**两次** |

**双轨执行链路追踪**：

```
用户请求 → bo_framework.execute()
  │
  ├─ [轨道1] bo_framework.py:110-115（_execute_core 前置校验）
  │    self._constraint_engine.validate(context)  ← 第1次
  │    if violations → return ActionResult(success=False)
  │
  ├─ [轨道2] 拦截器链 _dispatch_interceptors()
  │    → ConstraintValidationInterceptor.before_action()  ← 第2次
  │       engine = ConstraintEngine()  ← 新实例！
  │       engine.validate(context)
  │       if violations → raise ValidationFailedError
  │
  └─ 两条轨道使用**不同的 ConstraintEngine 实例**
       轨道1: self._constraint_engine（bo_framework.__init__ 创建，L44）
       轨道2: ConstraintEngine()（拦截器内每次 new，L32）
```

**关键差异**：

| 维度 | 轨道1 (bo_framework._constraint_engine) | 轨道2 (ConstraintValidationInterceptor) |
|------|---------------------------------------|---------------------------------------|
| 实例 | `self._constraint_engine`（bo_framework 初始化时创建） | `ConstraintEngine()`（每次请求新建） |
| 位置 | [bo_framework.py:44](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L44) + [bo_framework.py:111](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L111) | [constraint_validation_interceptor.py:32](file:///d:/filework/excel-to-diagram/meta/core/interceptors/constraint_validation_interceptor.py#L32) |
| 错误处理 | `return ActionResult(success=False)` | `raise ValidationFailedError` |
| 错误格式 | `'; '.join(messages)` | `ValidationDetail` + `i18n_key`（更丰富） |
| 触发时机 | `_execute_core` 之前 | 拦截器链 P42 位置 |

**风险评估**：
- **性能**：每次写操作校验两次，约束规则越多开销越大
- **一致性**：两个实例理论上结果一致（同一 ConstraintEngine 类），但如果未来有状态扩展可能不一致
- **错误格式不统一**：轨道1 返回 `ActionResult`，轨道2 抛 `ValidationFailedError`（含 i18n_key）

| **文档标注** | ARCHITECTURE_V2.md §5.3 行 790: "约束双轨执行风险...TODO: 二选一,移除重复" |
|---|---|

**修复方案**：

| 方案 | 改动 | 优点 | 缺点 |
|------|------|------|------|
| **A: 删除 ConstraintValidationInterceptor** | 删除 `constraint_validation_interceptor.py` + 删除 `app_builder.py:158-159` + 删除 `server.py:388-389` | 最小改动，保留 framework 层校验 | 丢失 i18n_key / ValidationDetail 格式 |
| **B: 删除 bo_framework._constraint_engine** | 删除 `bo_framework.py:44` + `bo_framework.py:110-115` | 统一拦截器模式，错误格式更丰富（i18n_key） | 需确认拦截器链在校验失败时能正确阻断 |
| **C（推荐）: 删除 bo_framework._constraint_engine + 保留拦截器** | 同 B，但需将拦截器的 `ValidationFailedError` 错误格式回传到 framework | 统一拦截器模式 + 保留丰富错误格式 + 消除双实例风险 | 需验证 `ValidationFailedError` 在 `bo_framework.execute()` 的 except 链中能被正确捕获（已确认：[bo_framework.py:152-158](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L152) 有 `ValidationFailedError` 处理） |

**推荐方案 C**，理由：
1. 拦截器模式统一（其他校验/权限都走拦截器）
2. `ValidationFailedError` 已在 `bo_framework.execute()` 的 except 链中被正确捕获
3. 拦截器提供更丰富的错误格式（i18n_key + ValidationDetail）
4. 消除双实例风险

| **工作量** | ~1h（含测试验证） |
|---|---|
| **验证** | `python d:\filework\test.py --failed` + 手动创建违反约束的记录确认只校验一次 |

---

### TODO-2: KeyTemplateInterceptor(45) vs HierarchyValidationInterceptor(45) 注册顺序

| 项 | 值 |
|---|---|
| **严重度** | 🔴 高 |
| **现状** | KeyTemplate(45) 先注册 → 先生成 code；HierarchyValidation(45) 后注册 → 后校验父级 |

**注册顺序追踪**（两处注册，顺序一致）：

**app_builder.py** ([L163-169](file:///d:/filework/excel-to-diagram/meta/core/app_builder.py#L163)):
```python
# L163-165: KeyTemplate 先注册
_kt_engine = KeyTemplateEngine(ds)
_kt_interceptor = KeyTemplateInterceptor(engine=_kt_engine)
bo_framework.register_interceptor(_kt_interceptor)  # ← 第1个 P45

# L168-169: HierarchyValidation 后注册
bo_framework.register_interceptor(LockInterceptor())        # P20
bo_framework.register_interceptor(HierarchyValidationInterceptor())  # ← 第2个 P45
```

**server.py** ([L393-399](file:///d:/filework/excel-to-diagram/meta/server.py#L393)):
```python
# L393-395: KeyTemplate 先注册
_kt_engine = KeyTemplateEngine(data_source)
_kt_interceptor = KeyTemplateInterceptor(engine=_kt_engine)
bo_framework.register_interceptor(_kt_interceptor)  # ← 第1个 P45

# L398-399: HierarchyValidation 后注册
bo_framework.register_interceptor(LockInterceptor())
bo_framework.register_interceptor(HierarchyValidationInterceptor())  # ← 第2个 P45
```

**执行时序问题**：

```
创建 sub_domain（domain_id 指向不存在的 domain）:
  │
  ├─ P45-1: KeyTemplateInterceptor.before_action()
  │    → 检测到 code 为空 + auto_suggest=true
  │    → 生成 code = "DOM-001-SUB-001"  ← 已生成！
  │    → context.params['code'] = "DOM-001-SUB-001"
  │
  ├─ P45-2: HierarchyValidationInterceptor.before_action()
  │    → 检查 domain_id 是否存在
  │    → 不存在！→ context.result = ActionResult(success=False)
  │
  └─ 结果：code 已生成但父级校验失败
       → 如果事务回滚 → 无影响（code 不会持久化）
       → 如果事务未包裹 → 孤儿 code 写入 DB ⚠️
```

**实际风险等级评估**：

| 场景 | 是否有事务保护 | 孤儿 code 风险 |
|------|:----------:|:----------:|
| 标准创建（走 bo_framework.execute） | ✅ 有（[bo_framework.py:120-145](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L120) 自动事务） | 🟢 低（事务回滚） |
| DISABLE_AUTO_TRANSACTION=true | ❌ 无 | 🔴 高（孤儿 code） |
| 拦截器链异常中断（非 ValidationFailedError） | 取决于异常类型 | 🟡 中 |

**修复方案**：

| 方案 | 改动 | 优点 | 缺点 |
|------|------|------|------|
| **A: 调整注册顺序** | 交换 `app_builder.py:163-165` 和 `app_builder.py:168-169` 的顺序 + 同步 `server.py:393-399` | 最小改动，先校验后生成 | 同优先级执行顺序仍依赖注册顺序，未来维护者可能不知道 |
| **B: 调整优先级** | HierarchyValidation 改为 P43（在 ConstraintValidation P42 之后、KeyTemplate P45 之前） | 语义更清晰，不依赖注册顺序 | 改优先级可能影响其他拦截器 |

**推荐方案 A**，理由：
1. 最小改动（仅交换 2 处注册顺序）
2. 不改变优先级体系
3. ARCHITECTURE_V2.md §5.3 行 788 已说明"同优先级共存，执行顺序取决于注册顺序"

| **工作量** | ~15min |
|---|---|
| **验证** | 创建父级不存在的子对象，确认先校验后生成 code；`python d:\filework\test.py --failed` |

---

### TODO-3: PermissionInterceptor 孤儿状态

| 项 | 值 |
|---|---|
| **严重度** | 🟡 中（功能无影响，但维护成本增加） |
| **现状** | PermissionInterceptor 代码已实现且功能完整（含 M11 YAML 集成），但**未在 app_builder.py 中注册**；同时 `require_permission` 装饰器在 API 层广泛使用 |

**双轨并行追踪**：

| 机制 | 位置 | 作用范围 | 使用量 |
|------|------|---------|--------|
| **PermissionInterceptor** | [permission_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/permission_interceptor.py) | BO 框架层（所有 CRUD 操作） | **未注册**（app_builder.py 无注册行） |
| **require_permission 装饰器** | [auth_middleware.py](file:///d:/filework/excel-to-diagram/meta/services/auth_middleware.py) → [decorators.py](file:///d:/filework/excel-to-diagram/meta/api/decorators.py) | API 层（特定端点） | 15+ 处使用（user_group_api / role_api / permission_rule_api 等） |

**关键发现**：PermissionInterceptor **已在 server.py 中注册**！

```python
# server.py:385（v1 路径，非 app_builder）
bo_framework.register_interceptor(PermissionInterceptor())  # ← 已注册！
```

但 **app_builder.py 中未注册**（app_builder.py:153-177 无 PermissionInterceptor 行）。

**这意味着**：
- 走 `server.py` 初始化路径 → PermissionInterceptor **生效**（与 require_permission 双重校验）
- 走 `app_builder.py` 初始化路径 → PermissionInterceptor **不生效**（仅 require_permission 校验）

**修复方案**：

| 方案 | 改动 | 优点 | 缺点 |
|------|------|------|------|
| **A: 删除 PermissionInterceptor + 清理 server.py 注册** | 删除 `permission_interceptor.py` + 删除 `server.py:385` | 消除双轨，统一走装饰器 | 丢失 M11 YAML 集成（`_check_yaml_permission` / `_apply_yaml_field_masks` / `inject_ai_agent_role`） |
| **B: 在 app_builder.py 中也注册 PermissionInterceptor + 删除 require_permission 装饰器** | 添加 `app_builder.py` 注册 + 逐个替换 15+ 处装饰器 | 统一拦截器模式 | 工作量大，装饰器粒度更细（特定端点 vs 全局 CRUD） |
| **C（推荐）: 保留 PermissionInterceptor + 在 app_builder.py 中也注册 + 保留 require_permission** | 添加 `app_builder.py` 注册行 | 双重保护（拦截器覆盖全局 CRUD + 装饰器覆盖特定端点），M11 YAML 集成生效 | 仍有双重校验（但 PermissionInterceptor 和 require_permission 作用范围不同，不冲突） |

**推荐方案 C**，理由：
1. PermissionInterceptor 已含 M11 YAML 集成（`_check_yaml_permission` / `inject_ai_agent_role` / `_apply_yaml_field_masks`），删除会丢失这些功能
2. 两种机制作用范围不同：拦截器覆盖 BO 框架层 CRUD，装饰器覆盖 API 层特定端点，**不冲突**
3. 最小改动（仅添加 1 行注册）

| **工作量** | ~15min（添加注册行 + 测试验证） |
|---|---|
| **验证** | `python d:\filework\test.py --failed` |

---

## 二、文档陈旧 TODO（需更新）

### TODO-4: ARCHITECTURE_V2.md §4.1 架构图数量声明滞后

| 项 | 值 |
|---|---|
| **严重度** | 🟡 中 |
| **现状** | 文档内部多处数量声明不一致 |

**不一致清单**（全部在 ARCHITECTURE_V2.md 中）：

| 位置 | 行号 | 声明内容 | 实际值 | 偏差 |
|------|------|---------|--------|------|
| §1.3 摘要 | L5 | 18 拦截器 · 35+ 引擎 · 61 服务 · 49 API | 18 / 35+ / 61 / 49 | ✅ 正确 |
| §1.3 表格 | L60 | 18 拦截器 | 18 | ✅ 正确 |
| §4.1 架构图 | L510 | **16**拦截器 · **25+**引擎 · **57**服务 · **35** API Blueprint | 18 / 35+ / 61 / 49 | ❌ 严重滞后 |
| §4.1 架构图 | L540 | BO Framework — **16**拦截器 + **25+**引擎 | 18 + 35+ | ❌ 严重滞后 |
| §4.1 数据流 | L577-585 | **16**拦截器链执行 | 18 | ❌ 严重滞后 |
| §5.1 模式1 | L92 | **16**拦截器优先级链 | 18 | ❌ 滞后 |
| §5.1 模式1 | L94 | （**16**个具体拦截器） | 18 | ❌ 滞后 |
| §5.1 模式1 | L126 | 所有**16**个拦截器 | 18 | ❌ 滞后 |
| §5.3 表格 | L768-778 | 18 个拦截器（含新增 2 个） | 18 | ✅ 正确 |
| 版本记录 | L2705 | **16**拦截器/25+引擎/57服务/35API | 18/35+/61/49 | ❌ 历史记录 |
| 版本记录 | L2733 | 18 拦截器 / 35+ 引擎 / 61 服务 | 18/35+/61 | ✅ 正确 |

**根因**：§4.1 和 §5.1 是 v2.4.0（2026-05-23）写的，当时只有 16 个拦截器；§5.3 表格和版本记录在 v3.0.0（2026-06-05）更新时已修正，但 §4.1/§5.1 遗漏。

| **修复方案** | 全局替换 §4.1 + §5.1 中的 "16拦截器" → "18拦截器"，"25+引擎" → "35+引擎"，"57服务" → "61服务"，"35 API" → "49 API" |
|---|---|
| **工作量** | ~30min |

### TODO-5: ARCHITECTURE_V2.md §5.3 注册位置行号过期

| 项 | 值 |
|---|---|
| **严重度** | 🟢 低 |
| **现状** | §5.3 引用 "注册位置: meta/core/app_builder.py:L102-L125"，实际在 L153-L177 |
| **位置** | `docs/ARCHITECTURE_V2.md` §5.3 行 780 |
| **修复方案** | 更新行号引用 |
| **工作量** | ~15min |

### TODO-6: ARCHITECTURE_V2.md §2.5 "五层权限" 与 Owner 模型未对齐

| 项 | 值 |
|---|---|
| **严重度** | 🟡 中 |
| **现状** | 文档描述"五层权限"（认证/授权/数据权限/审计/基础设施），但实际代码含 Owner 模型（Phase 21），形成 6 层。Owner 是数据权限子层还是独立层未明确 |
| **位置** | `docs/ARCHITECTURE_V2.md` §2.5 行 312-320 |
| **修复方案** | 明确 Owner 模型在权限层级中的位置，更新文档 |
| **工作量** | ~30min |

### TODO-7: spec-ui-business-logic-downflow.md 附录 B.2 状态与主表不一致

| 项 | 值 |
|---|---|
| **严重度** | 🟡 中 |
| **现状** | 附录 B.2 标注 M10 "📋 spec 完成待实施"、M11 "📋 规划中"、M13 "📋 规划中"、M14 "📋 规划中"，但主状态快照表已全部标 "✅ 完成" |
| **位置** | `docs/specs/spec-ui-business-logic-downflow.md` 附录 B.2 行 1014-1021 |
| **修复方案** | 同步 B.2 至主表最新状态 |
| **工作量** | ~15min |

---

## 三、前端治理 TODO（需实施）

### TODO-8: ESLint C1-C3 约束强制规则 — ⚠️ 已部分实施

| 项 | 值 |
|---|---|
| **严重度** | 🟡 中 |
| **现状** | **C2/C3/C4 已实施，C1 已实施但阈值不同** |

**已实施的规则**（[eslint.config.js](file:///d:/filework/excel-to-diagram/eslint.config.js)）：

| 约束 | spec 定义 | ESLint 实现 | 状态 |
|------|---------|------------|:----:|
| C1 | composable 内禁止 >20 行纯函数业务逻辑 | `max-lines-per-function: ['warn', { max: 50 }]`（L123-136） | ⚠️ 阈值不同（spec 20 行 vs ESLint 50 行），且为 `warn` 非 `error` |
| C2 | Pinia store 内禁止 `fetch()` | `no-restricted-globals: ['error', { name: 'fetch' }]`（L95-107） | ✅ 已实施 |
| C3 | .vue 文件内禁止 `fetch()` | `no-restricted-globals: ['error', { name: 'fetch' }]`（L81-93） | ✅ 已实施 |
| C4 | composable 层禁止 `fetch()` | `no-restricted-globals: ['error', { name: 'fetch' }]`（L109-121） | ✅ 已实施（spec 未定义 C4，但 ESLint 已实现） |
| service 层豁免 | — | `no-restricted-globals: 'off'`（L138-144） | ✅ 已实施 |
| graphqlClient 豁免 | — | `ignores: ['src/services/graphqlClient.js']`（L15） | ✅ 已实施 |

**待完善项**：

| 项 | 当前 | 建议 |
|----|------|------|
| C1 阈值 | `max: 50`（warn） | 改为 `max: 20`（与 spec 一致）或接受 50（composable 编排逻辑通常 >20 行） |
| C1 严重度 | `warn` | 考虑改为 `error`（CI 卡点） |
| CI 集成 | 无 | 添加 `npm run lint` 到 CI pipeline |

| **关联 PR** | spec-ui-business-logic-downflow.md PR 15（状态 🟢） |
|---|---|
| **工作量** | ~30min（调整阈值 + CI 集成） |
| **验证** | 故意在 composable 中写 >50 行函数 → ESLint 报错 |

### TODO-9: FR-UI-011 diagramConfigStore centerScope 迁移

| 项 | 值 |
|---|---|
| **严重度** | 🟢 低 |
| **现状** | diagramDataStore.js 已删除，diagramConfigStore 确认零 fetch，但 centerScope / centerScopeMarkers 迁移到 useDiagramData **待后续** |
| **位置** | `src/stores/diagramConfigStore.js` → `src/composables/useDiagramData.js` |
| **文档标注** | spec-ui-business-logic-downflow.md §8.2 行 859 |
| **工作量** | ~0.5d |

### TODO-10: graphqlClient.js httpClient 迁移

| 项 | 值 |
|---|---|
| **严重度** | 🟢 低 |
| **现状** | `src/services/graphqlClient.js:40` 仍有 1 处 raw fetch。GraphQL 为 POC 阶段，0 调用方 |
| **位置** | `src/services/graphqlClient.js` |
| **文档标注** | spec-v3-gap-analysis FR-GAP-009 标注 ⏸ 暂缓 |
| **修复方案** | GraphQL 正式启用时再迁移 |
| **工作量** | ~30min（迁移时） |

---

## 四、已完成项确认（无需行动）

以下项经代码验证已 100% 符合设计，无需额外工作：

| # | 项目 | 证据 |
|---|------|------|
| 1 | 18 拦截器链全部注册 | `app_builder.py:153-177` 与 ARCHITECTURE_V2.md §5.3 表格 100% 一致 |
| 2 | httpClient 统一 | bo/ 子服务 0 处 raw fetch，httpClient 支持 FormData/Blob/download |
| 3 | 旧 @deprecated 文件删除 | boAssociationService.js / boHierarchyService.js 已物理删除 |
| 4 | M10/M13/M14 Blueprint 注册 | server.py:649-658 + app_builder.py:289-293 |
| 5 | SSE 进度流 | bo_action_api.py:338 `/_chain_stream` 已实现 |
| 6 | BOAction 统一端点 | bo_action_api.py:91 + trace_id + X-Trace-Id |
| 7 | M8 Query Engine | m8_api.py + m8_utils.py，6 个 P0 能力 |
| 8 | M9 GraphQL | graphql.py 端点已注册 |
| 9 | M10 MCP Server | mcp/server.py，20 tools，JSON-RPC 2.0 |
| 10 | M11 RLS | DataPermissionInterceptor(P30)，155 rls 测试 PASS |
| 11 | M13 Schema Dashboard | schema_api.py，65 schema 测试 PASS |
| 12 | M14 Telemetry | telemetry/api.py，39 telemetry 测试 PASS |
| 13 | AsyncInterceptorEngine | bo_framework.py:21 env var 切换 |
| 14 | BOF 持久化事务三层架构 | WriteQueue + ds.transaction() + SAVEPOINT |
| 15 | vitest isolate:true | PR-TestFix-16 已实施（之前分析错误，已修正） |
| 16 | 测试治理 337→0 | PR-TestFix-1~18 全部完成，2147 passed |
| 17 | 49 API Blueprint | server.py + app_builder.py 注册 49 个 |
| 18 | 31 composables | src/composables/ 下 31 个 |
| 19 | 35+ 引擎 | SchemaGenerator/AssociationEngine/BOEngine/KeyTemplateEngine 等 |
| 20 | Cookie+Token 双认证 | dev-login + httpOnly cookie + Token Service 三件套 |
| 21 | 五层安全防线 | 认证/授权/数据权限/审计/基础设施 |
| 22 | KeyTemplate 引擎 | key_template_engine.py + KeyTemplateInterceptor(45) |
| 23 | 14 FR 中 13 个完成 | FR-UI-001~010/012/013 ✅，FR-UI-011 🟡，FR-UI-014 🟢可裁剪 |

---

## 五、优先级排序与建议执行顺序

| 优先级 | TODO | 工作量 | ROI |
|:-----:|------|:-----:|:---:|
| 🔴 P0 | TODO-1: Constraint 双轨消除 | 1h | 高（消除重复校验 + 数据一致性风险） |
| 🔴 P0 | TODO-2: KeyTemplate/Hierarchy 注册顺序 | 15min | 高（消除孤儿 code 风险） |
| 🟡 P1 | TODO-3: 删除 PermissionInterceptor 孤儿 | 15min | 中（减少维护成本） |
| 🟡 P1 | TODO-4: §4.1 架构图同步 | 30min | 中（文档一致性） |
| 🟡 P1 | TODO-6: 五层权限 Owner 定位 | 30min | 中（架构清晰度） |
| 🟡 P1 | TODO-7: B.2 状态同步 | 15min | 中（文档一致性） |
| 🟡 P1 | TODO-8: ESLint C1-C3 规则 | 2h | 中（自动化约束保护） |
| 🟢 P2 | TODO-5: 行号引用更新 | 15min | 低（文档细节） |
| 🟢 P2 | TODO-9: centerScope 迁移 | 0.5d | 低（功能完善） |
| 🟢 P3 | TODO-10: graphqlClient 迁移 | 30min | 低（暂缓，0 调用方） |

**建议 P0 批次**: TODO-1 + TODO-2 一起修，总计 ~1.25h，消除两个数据一致性风险。

---

## 六、分析修正记录

| # | 原分析结论 | 修正后 | 修正原因 |
|---|----------|-------|---------|
| 1 | vitest isolate 未实施 | **已实施**（PR-TestFix-16） | spec-ui-business-logic-downflow.md §6.6.4.11 记录了 `isolate: true` + `singleThread: true` 修改 |
| 2 | useMetaList 1716 行 | spec 记录 1800 行（2412→1800, -25.4%） | 需重新确认实际行数，可能后续有增量 |
| 3 | 未覆盖 spec-ui-business-logic-downflow.md | **已补充审阅** | 该 spec 是 UI 层业务逻辑下沉的核心文档，14 FR + Phase B + M9-M14 进度 + 18 个 PR-TestFix 均已确认 |
| 4 | ESLint C1-C3 未实施 | **C2/C3/C4 已实施，C1 已实施但阈值不同** | [eslint.config.js](file:///d:/filework/excel-to-diagram/eslint.config.js) 已含 `no-restricted-globals` 规则（C2/C3/C4 error 级）+ `max-lines-per-function`（C1 warn 50 行） |
| 5 | PermissionInterceptor 未注册 | **server.py 已注册，app_builder.py 未注册** | [server.py:385](file:///d:/filework/excel-to-diagram/meta/server.py#L385) 有注册行，但 [app_builder.py:153-177](file:///d:/filework/excel-to-diagram/meta/core/app_builder.py#L153) 无。两条初始化路径行为不一致 |
| 6 | PermissionInterceptor 应删除 | **应保留并在 app_builder.py 中也注册** | PermissionInterceptor 已含 M11 YAML 集成（`_check_yaml_permission` / `inject_ai_agent_role` / `_apply_yaml_field_masks`），删除会丢失这些功能 |
| 7 | TODO-2 孤儿 code 风险为"高" | **标准路径风险低（有事务保护），DISABLE_AUTO_TRANSACTION 路径风险高** | [bo_framework.py:120-145](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L120) 自动事务包裹，孤儿 code 会被回滚 |
