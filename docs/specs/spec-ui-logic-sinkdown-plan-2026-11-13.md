# Spec: UI 层业务逻辑下沉 — 2026-11 通盘审查增量实施计划

> **版本**: v1.2.0
> **日期**: 2026-11-13
> **状态**: [TODO] 待排期（本文档只做规划，不含代码改动）
> **范围**: 前端全量 `src/`（views / components / composables / services / stores / utils / constants）+ 对应后端落点 `meta/api/`、`meta/services/`
> **审查方式**: 按 5 个域并行全量走查（非只读规则文件），覆盖约 300 个文件

---

## 0. 与历史文档的关系（重要）

本项目此前已有一轮 UI 逻辑下沉治理，成果记录在下列文档中。**本文档是 2026-11 的新增量审查，不重复历史已完成项。**

| 文档 | 版本/日期 | 本次如何处理 |
|---|---|---|
| [spec-ui-business-logic-downflow.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-ui-business-logic-downflow.md) | v3.1.2 / 2026-06-06 | 其中 FR-UI-001~013 已完成（httpClient / authService / keyTemplate / draftPersist / useMetaList 重构 / apiV1V2 / permissionService / conditionExpressionService / RolePermissionCenter / hierarchyService / diagramConfigStore / auditLogService / associationService）→ **不重列** |
| [spec-ui-business-logic-downflow-todos-v3.1.3.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-ui-business-logic-downflow-todos-v3.1.3.md) | 2026-06-07 | 剩余 7 项（centerScope 迁移、ESLint C1-C3、11 个子 spec、测试维持、M12、useExcelParser 增强、parent_spec_refs）→ **本文档只补充与之交叉的部分**（ESLint 防回流并入 B5，useExcelParser 并入 B3-7） |
| [spec-condition-rule-builder.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-condition-rule-builder.md) | 2026-11 | 上轮已实装（条件规则写路径收敛，commit 4cc00de0）→ **不重列** |

**因此本文档出现的问题，均为历史治理未覆盖或治理后新引入的（例如 `manage` 枚举漂移、三方密钥直连、无鉴权运维端点）。**

---

## 1. 审查覆盖面（证明"通盘"）

| 域 | 审计对象 | 规模 | 处理方式 |
|---|---|---|---|
| D1 交易单据类视图 | `src/views/` 下单据/列表/详情 | 62 个 `.vue`（约 1.57MB） | 全量走查 |
| D2 系统管理与权限类视图 | `src/views/SystemManagement/**` | 全量 | 全量走查 |
| D3 图表 / 报表 / 主应用 | `src/views/AADiagramApp/**`、`MetaReportPage`、`ComponentComparison` | 全量 | 全量走查 |
| D4 composables | `src/composables/` | 106 文件（1.0MB），30 个业务型逐审 / 29 个纯 UI 跳过 | 逐审业务型 |
| D5 services + stores + utils + constants + types | `src/services/` 74、`stores/` 12、`utils/` 12、其余 | 101 文件 | 逐审 |

**判定"该下沉"的标准**（四类，缺一不列）：

1. **决策类**：权限判定、状态流转、可执行动作、校验通过与否 → 必须后端决定，前端只渲染。
2. **计算类**：金额、统计、编码、diff、聚合 → 存在多消费方或涉及商业规则时必须后端。
3. **真源类**：枚举、标签映射、字段策略、限制阈值 → 只允许后端下发一份。
4. **安全类**：密钥、越权入口、fail-open 默认放行 → 必须后端收口。

**判定"不下沉"的**：纯渲染/几何布局（`useMermaid/*`、`groupModel/*` 20 文件、`hierarchyTree/*` 6 文件、`scaleGuard/*`、`autoGrouping/*`）、纯 UI 状态、动画与交互。已在文档 §2.5 列明，避免反复讨论。

---

## 2. 结论总览

| 优先级 | 项数 | 含义 |
|---|---:|---|
| **P0** | 7 | 安全或正确性缺陷，具备可证实利用路径 / 直接算错钱 / 越权入口 |
| **P1** | 约 25 | 单一真源缺失（枚举/标签/校验多份副本）、聚合与分页不合理 |
| **P2** | 若干 | 缓存职责分散、全量拉取、格式化重复、协议封装重复 |

> **行号说明**：本文档所有 `file:line` 基于 2026-11-13 磁盘快照。实施时若文件已变更，以当次磁盘为准，不要盲信行号。

---

## 3. P0 清单（7 项）

### P0-1 第三方密钥进入前端产物

| 项 | 内容 |
|---|---|
| 现象 | 智谱 / DeepSeek 的 API Key 用 `import.meta.env.VITE_*` 读取，Vite 会把 `VITE_` 前缀变量**打包进产物**；飞书 `app_secret` 由浏览器直接 POST 换 `tenant_access_token` |
| 证据 | `src/services/deepseekValidator.js:10`（`VITE_DEEPSEEK_API_KEY`）、`:144`（`Authorization: Bearer ...`）、`:159`（`max_tokens: 2000`）<br>`src/services/zhipuValidator.js:10`（`VITE_ZHIPU_API_KEY`）、`:197`、`:202`（`generateToken(ZHIPU_API_KEY)`）、`:208`（Bearer）<br>`src/services/feishuService.js:51`（`/auth/v3/tenant_access_token/internal`）、`:57-58`（body 传 `app_id` / `app_secret`）、`:64-66`（取 token）<br>`src/views/SystemManagement/SystemSettings.vue:369-370`（`VITE_FEISHU_APP_ID` / `VITE_FEISHU_APP_SECRET`）、`:381`（body 传 `app_secret`） |
| 后端现状 | `meta/` 全量 grep `feishu\|deepseek\|zhipu\|tenant_access_token` → **无任何命中**，即后端完全没有对应能力，前端直连是唯一实现 |
| 后端落点 | 新增 `meta/api/integration_api.py` + `meta/services/integration_credential_service.py`（密钥从环境变量 / 加密配置读，落库需加密；参考已有 `system_settings` 读取路径） |
| 接口契约 | `POST /api/v2/integrations/ai/validate` → `{ valid: bool, issues: [{level, message}] }`，请求体只传待校验内容，**不含 key**<br>`POST /api/v2/integrations/feishu/request` → 后端持 token 缓存后代理目标接口，前端不接触 secret<br>`GET /api/v2/system/settings/integrations` → `{ feishu: { app_id, has_secret: true, app_secret_masked: "******" }, ai: { provider, has_key: true } }` |
| 前端改动 | `deepseekValidator.js` / `zhipuValidator.js` / `feishuService.js` 改为调上述接口，删除所有 `import.meta.env.VITE_*KEY*`；`SystemSettings.vue` 只展示 masked 值，保存时"留空即不修改" |
| 验证 | ① `npm run build` 后 `grep -r "sk-\|Bearer \|app_secret" dist/` 必须 0 命中（构建产物无密钥）<br>② `python d:\filework\test.py --single meta/tests/api/test_integration_api.py`（新建）<br>③ vitest：`src/services/__tests__/` 对应 spec 改为 mock 新接口 |
| 风险 | 配置迁移：现网 `.env` 里的 `VITE_*` 需转为后端环境变量，漏迁会导致 AI 校验/飞书导入功能不可用 → 发布前逐个验证 |
| 依赖 | 无（可独立先做） |

### P0-2 权限与表达式 fail-open（默认放行）

| 项 | 内容 |
|---|---|
| 现象 | 权限查询/表达式求值抛异常时 `return true`，即"后端挂了 = 全放行" |
| 证据 | `src/composables/useMetaList.js`：`:1530`、`:1552`（`if (!action.permission) return true`）、`:1555`、`:1569`（`if (!condition) return true`）、`:1774-1780`（catch 后 `return true`）、`:1861`<br>`src/composables/useMenuPermissions.js:236-245`（catch 后 `return true`）<br>`src/services/conditionExpressionService.js:61-190`、`src/utils/safeExpression.js:40-120`（表达式求值失败降级为放行） |
| 后端现状 | 已有 `meta/services/condition_evaluator.py`、`permission_service.py`、`permission_set_service.py`、`permission_dimension_engine.py`、`dimension_scope_engine.py`、`action_policy.py`，能力齐备 |
| 后端落点 | 复用 `action_policy.py` 增加批量接口，前端不再本地求值 |
| 接口契约 | `POST /api/v2/bo/<bo_code>/actions/evaluate` → body `{ ids: [...], actions: [...] }` → `{ [id]: { [action]: { enabled: bool, reason: string, required_permission: string } } }`<br>`POST /api/v2/bo/<bo_code>/conditions/evaluate` → 同构，返回 `{ matched: bool, trace: [...] }`（trace 便于排查） |
| 前端改动 | 所有 `catch → return true` 改为 **fail-closed**：权限/表达式求值失败 → `false` + 上报一次错误；列表页按钮统一走 `actions/evaluate` 批量结果渲染 |
| 验证 | ① 新增单测覆盖"接口 500 → 按钮不出现"（vitest）<br>② `python d:\filework\test.py --single meta/tests/services/test_action_policy_batch.py`（新建）<br>③ 手工：断网后进入列表页，确认高危操作按钮全部不可见 |
| 风险 | 误伤：后端未实现的动作若也返回 false 会导致按钮消失 → 契约约定"后端不认识的动作返回 `enabled: false, reason: 'unsupported'`"，并在灰度期打日志对比前后差异 |
| 依赖 | 无 |

### P0-3 运维/授权端点缺鉴权（可越权触发）

| 项 | 内容 |
|---|---|
| 现象 | 调度器状态/立即执行端点**无任何装饰器**；权限规则与资源动作矩阵的写接口只有 `@_login_required`（登录即写，无权限校验）→ 任意登录用户可给自己提权 |
| 证据 | `meta/api/scheduler_api.py:54-55`（`GET /api/v2/schedulers/status`，无装饰器）、`:78-79`（`POST /api/v2/schedulers/<code>/run-now`，无装饰器）、`scheduler_bp` 在启动时无条件注册<br>`meta/api/permission_dimension_api.py:2215-2217`（`POST /roles/<id>/permission-rules`，仅 `@_login_required`）、`:2302-2305`（`PUT /resource-action-matrix`，仅 `@_login_required`） |
| 后端落点 | 统一鉴权装饰器（项目已有 `require_permission` / `_is_admin_user` 可复用） |
| 接口契约 | 不改 URL，只加装饰器：<br>`scheduler/status` → `@require_permission('system.scheduler.read')`<br>`scheduler/<code>/run-now` → `@require_permission('system.scheduler.execute')`<br>`POST permission-rules` / `PUT resource-action-matrix` → `@require_permission('system.permission_set.write')` + **禁止修改当前用户自身所属权限集**（自提权防护）+ 写操作记 `audit_service` |
| 前端改动 | 无（`SystemManagement` 相关页面本就只在管理员可见菜单内） |
| 验证 | ① `meta/tests/api/` 新增负向用例：普通用户调用返回 403<br>② `python d:\filework\test.py --single meta/tests/api/test_scheduler_auth.py`、`--single meta/tests/api/test_permission_dimension_auth.py`<br>③ 手工：普通账号 `curl.exe -X POST .../run-now -H "Cookie: ..."` 应 403 |
| 风险 | 部署环境若有用无权限账号调用 run-now 的运维脚本 → 需给脚本账号授予 `system.scheduler.execute` |
| 依赖 | 无（**建议第一个实施**） |

### P0-4 前端算钱 + 硬编码单价

| 项 | 内容 |
|---|---|
| 现象 | 报价模拟器在前端用硬编码单价计算许可费/实施费/培训费，折扣与税率也在前端乘算 |
| 证据 | `src/views/ComponentComparison.vue:3890/3894/3898`（模板 `simulator.licenseCount * 500`、`implDays * 3000`、`trainCount * 2000`）<br>同文件 `:5056-5058`（computed `simLicenseFee / simImplFee / simTrainFee` 同一套硬编码）<br>同文件 `:5046-5047`（`const price = base * (1 - discount) * (1 + tax)`）、`:5048` 附近 `'CNY ' + price.toLocaleString(...)` |
| 后端现状 | 已有 `meta/services/pricing_service.py`、`sales_order_pricing_service.py` |
| 后端落点 | 复用/扩展 `pricing_service.py`，单价落配置表（不与前端耦合） |
| 接口契约 | `POST /api/v2/pricing/simulate` → body `{ scenario, lines: [{ sku, qty, days }], discount, tax_rate }` → `{ lines: [{ sku, name, unit_price, qty, amount }], subtotal, discount_amount, tax_amount, total, currency }` |
| 前端改动 | 删除 `:5056-5058` 计算与 `:3890-3898` 模板内乘法，改为展示接口返回的 `lines/amount/total`；金额格式化统一走后端返回的 `formatted` 或共享 formatter（见 B5） |
| 验证 | ① 后端单测：折扣/税率/四舍五入边界（含 0.005 进位）<br>② 前端 vitest：模拟接口返回后 DOM 金额与接口一致<br>③ 手工比对：同一组输入，前后端金额完全相等 |
| 风险 | 单价是商业敏感数据，配置表需权限保护；历史演示数据中的 `manage` 等假数据应一并清理 |
| 依赖 | 建议在 B2（配置真源）之后做，避免单价又散落 |

### P0-5 变更单状态机 + 权限 + 标签全部前端拼装

| 项 | 内容 |
|---|---|
| 现象 | 可提交/可审批/可驳回/可编辑/可应用 五个布尔全部由前端 `status` + 前端权限函数计算；状态标签与颜色也是前端映射 |
| 证据 | `src/views/EngineeringChangeDetailPage.vue:322`（`can('engineering_change_approve', {...})`）、`:327`（`status = computed(...)`）、`:329-335`（`canSubmit/canApprove/canReject/canEdit/canApply` 全部 `status === 'x' && hasY`）、`:268-280`（`statusLabel()` / `statusTagType()` 本地映射）<br>`src/views/EngineeringChangeDiffPage.vue:413-427`（同类前端拼装） |
| 后端现状 | 已有 `meta/services/engineering_change_service.py`、`change_request_decision.py` |
| 后端落点 | 在 `engineering_change_service.py` 增 `get_available_actions(id)`，复用状态机 + `permission_service` |
| 接口契约 | `GET /api/v2/engineering-changes/<id>/actions` → `[{ code, label, enabled, reason, required_permission, style }]`（`style` 供标签颜色，避免前端第二份映射）<br>`GET /api/v2/engineering-changes/<id>/diff` → 后端生成差异结构 |
| 前端改动 | 五个 computed 全部删除，改为渲染 `actions`；`statusLabel/statusTagType` 删除，用后端返回 |
| 验证 | ① 后端单测覆盖 5 状态 × 4 角色矩阵（应允/应拒）<br>② E2E：`tests/e2e/` 变更单流程<br>③ 手工：用无审批权账号进入 in_review 单据，"审批"不出现 |
| 风险 | 状态机若后端与前端理解不一致，会出现按钮消失/多出 → 后端单测需覆盖全部状态迁移，且前端历史数据用同一状态枚举 |
| 依赖 | 需先完成状态枚举后端下发（B2） |

### P0-6 架构图统计四卡前端遍历全量 + 两套重复实现

| 项 | 内容 |
|---|---|
| 现象 | 统计卡片在前端遍历全量数据算计数；同一统计逻辑存在两套实现（图表页与转换层各一份） |
| 证据 | `src/views/AADiagramApp/composables/useDiagramData.js:1097`、`:1139-1290`（统计计算）、`:349-500`（同类逻辑另一处）<br>`src/services/archDataConverter.js:234-312`（转换层里的重复统计） |
| 后端现状 | 已有 `computation_service.py`、`list_service.py`、`query_service.py` |
| 后端落点 | `computation_service.py` 增架构统计聚合 |
| 接口契约 | `GET /api/v2/bo/architecture/stats?scope=<id>&filters=<json>` → `{ bo_count, sm_count, relation_count, domain_count, by_type: {...}, by_domain: [{domain,count}] }` |
| 前端改动 | 删除两处遍历，改为取接口；图表渲染仍用全量结构数据（渲染必须），但**统计数字不再前端算** |
| 验证 | ① 后端单测：造 3 组数据集比对计数<br>② 前端 vitest：mock 接口后四卡数值正确<br>③ 手工：1000+ 对象规模下切换过滤条件，四卡随接口变化 |
| 风险 | 统计口径必须与旧前端一致（是否计入注释节点/孤立节点）→ 接口实现前先固化口径文档 |
| 依赖 | 无（与 B3 其他项并行） |

### P0-7 前端生成关系编码

| 项 | 内容 |
|---|---|
| 现象 | 导入解析时若 Excel 未给关系编码，前端用 `${sourceCode}-${targetCode}` 拼，编码规则落在前端 |
| 证据 | `src/services/excelParser.js:229-230`（`const relationCode = extractedRelationCode \|\| \`${sourceCode}-${targetCode}\`;`），`:215-249` 上下文 |
| 后端现状 | 已有 `object_identity_service.py`、`import_export_service.py`、`async_import_service.py` |
| 后端落点 | 编码生成收敛到后端导入管道（优先），或提供批量解析接口 |
| 接口契约 | 方案 A（推荐）：导入预览/提交时由后端统一生成编码，前端不组装<br>方案 B：`POST /api/v2/relations/resolve-codes` → body `{ pairs: [{sourceCode,targetCode}] }` → `{ codes: [...] }` |
| 前端改动 | 删除本地拼接，改用后端返回 |
| 验证 | ① 后端单测：重复对、缺失一端、特殊字符、超长编码<br>② 导入 E2E：不含关系编码列的 Excel 导入后编码与后端规则一致 |
| 风险 | 历史数据已存在前端生成的编码，后端规则若不同会产生两套编码 → 需先比对现有 DB 中编码分布，确认可兼容 |
| 依赖 | 建议与 B3 导入管道改造一起做 |

---

## 4. P1 清单（约 25 项，按组）

### 4.1 枚举 / 规则表 / 标签多份副本（→ 后端下发唯一真源）

| # | 问题 | 前端证据 | 后端落点/接口 |
|---|---|---|---|
| P1-1 | **权限级别枚举漂移**：后端只有 `admin/write/read`，前端多处引入 `manage` | 后端真源 `meta/schemas/data_permission.yaml:37-41`（`admin/write/read`）、`:74`<br>前端 `src/views/SystemManagement/constants/permissionConstants.ts:52,60,69,76,89`（ActionGroupKey 含 manage，`manage: ['read','list','create','update','delete']`）<br>`src/views/SystemManagement/RoleDetailDrawer.vue:265`（`{ value: 'manage', label: '完全管理' }`）<br>`src/views/SystemManagement/components/ConditionRuleList.vue:48`、`src/views/SystemManagement/composables/useConditionRules.ts:9`（类型 `'none'\|'read'\|'write'\|'manage'`）<br>`src/views/SystemManagement/components/ResourceActionMatrix.vue:670`（`manage: '管理'`）<br>`src/services/permissionService.js:21,138,253`<br>`src/services/__tests__/permissionService.spec.js:94,139,155`（断言含 manage）<br>（注：`src/constants/permissionLevels.js` 本身无 manage，漂移点在上述文件） | `GET /api/v2/meta/enums/permission_level` → `{ items: [{value,label,level}] }`；同时清理前端 5 处副本与单测断言 |
| P1-2 | 动作→权限组映射表前端硬编码 | `permissionConstants.ts:52-89`、`ResourceActionMatrix.vue:670` | 并入 `GET /api/v2/meta/permission-matrix-schema` |
| P1-3 | 审计动作/对象标签 4 份副本 | `src/constants/auditLogMeta.js`、`src/services/auditLogService.js:24`、`src/utils/auditLogFormat.js:94`、`src/services/permissionService.js:132`、`ResourceActionMatrix.vue:663` | `GET /api/v2/meta/enums/audit_action`、`/audit_object_type` |
| P1-4 | 动作策略表前端实现 | `src/services/actionPolicyService.js:91-124`、`src/services/metaTransformService.js:463-486` | 复用 `meta/services/action_policy.py`，接口见 P0-2 |
| P1-5 | 任务状态/优先级标签与流转前端实现 | `src/services/taskService.js:23-70`、`src/views/.../TaskDetailDrawer.vue:71-83` | `GET /api/v2/meta/enums/task_status` + `GET /api/v2/tasks/<id>/actions` |
| P1-6 | 层级/组织维度枚举前端实现 | `src/services/hierarchyService.js:103-127`、`src/composables/useWorkspaceFilter.js:58-78` | 复用 `hierarchy_service.py`、`org_function_service.py` |
| P1-7 | 变更单状态枚举前端一份 | `src/views/EngineeringChangeListPage.vue:122-138` | 并入 P0-5 |

### 4.2 校验双份（前端自校验 + 后端无权威）

| # | 问题 | 前端证据 | 后端落点 |
|---|---|---|---|
| P1-8 | 字段策略校验前端实现 | `src/composables/useFieldPolicy.js:93-141`、`:194-236`、`:254-346` | 复用 `field_policy_engine.py` + `field_policy_validation.py`；接口 `POST /api/v2/bo/<code>/validate` 返回字段级错误 |
| P1-9 | BO 动作表单校验前端实现 | `src/composables/useBoActionForm.js:52-97` | 同上 |
| P1-10 | 数据校验器与字段提取器双份 | `src/services/dataValidator.js:220-300` + `src/utils/fieldExtractors.js` | 校验下沉；字段提取若只服务导入则随导入下沉（P0-7） |
| P1-11 | 选择上限前端可被 URL 抬高 | `src/composables/useSelectionConfig.js:38-137`（`?max_selection` 可抬到 `HARD_LIMIT=100000`） | 复用 `batch_selection_policy_service.py`；上限由后端读配置，忽略 URL 覆盖 |
| P1-12 | 维度范围/权限配置面板各自实现规则 | `src/views/SystemManagement/components/DimensionScopePanel.vue:269-340`、`PermissionConfigPanel.vue:782-866` | 复用 `dimension_scope_engine.py`、`permission_dimension_engine.py`；提供 `GET .../scope-preview` 返回"该范围能看到多少行" |

### 4.3 跨接口聚合 / 前端 join / 分页不合理

| # | 问题 | 前端证据 | 后端落点 |
|---|---|---|---|
| P1-13 | 报表页多次请求 + 前端聚合 | `src/views/MetaReportPage.vue:153-249` | 新增 `GET /api/v2/reports/<code>/rows?page=&page_size=&...`，服务端分页聚合 |
| P1-14 | 关系分类规则前端实现（约 400 行） | `src/services/relationClassifier.js:577-1000` | 后端 `relation` 分类服务；接口返回 `relation_type` |
| P1-15 | 架构数据转换/统计重复 | `archDataConverter.js:234-312`、`useDiagramData.js:349-560`、`:624-1095` | 见 P0-6 |
| P1-16 | 布局控制面板前端计算布局参数 | `src/views/AADiagramApp/.../LayoutControlPanel.vue:802-1190` | 纯渲染参数 → **保留**；仅把"布局合法性校验/上限"下沉 |
| P1-17 | 处理单元文档页前端聚合 | `src/views/.../HandlingUnitDocs.vue:162-186` | 复用 `handling_unit_service.py` 增聚合接口 |
| P1-18 | 权限元数据前端拼装 | `src/composables/usePermissionMeta.js:48-90` | `GET /api/v2/meta/permission-meta` |
| P1-19 | 级联查询前端编排 | `src/composables/useCascadeSelect.js:144-190` | 复用 `cascade_service.py`，提供 `GET .../cascade?parent_id=` 一次返回 |
| P1-20 | **批量循环无事务**（逐条 POST） | `SystemManagement/.../GroupRoleDialog.vue:109-117`、`OrgPermissionSetDialog.vue:118-126`、`AddPermissionDialog.vue:275-298`、`PermissionConfigPanel.vue:732-775` | 新增批量接口（见 B4），后端单事务 + 部分失败明细 |

### 4.4 表达式求值与解析

| # | 问题 | 前端证据 | 后端落点 |
|---|---|---|---|
| P1-21 | 条件表达式前端求值 | `src/services/conditionExpressionService.js:61-190` | 复用 `condition_evaluator.py`，接口见 P0-2 |
| P1-22 | 安全表达式失败放行 | `src/utils/safeExpression.js:40-120` | 随 P0-2 改 fail-closed |
| P1-23 | Excel 解析器前端规则 | `src/composables/useExcelParser.js:29-77` | 随 P0-7 导入管道下沉；此项与历史 T-FR-UI-014 交叉，历史标记 Won't，本次**仅做编码规则下沉，不做解析重构** |
| P1-24 | 飞书导入前端逐条处理 | `src/views/.../FeishuDataImport.vue:180-345` | 复用 `async_import_service.py`，前端只提交任务 id |
| P1-25 | 单据编号前端生成（若有） | 走查未见前端生成单号，**已由 `document_number_service.py` 收口** → 判定"已正确"，仅需补 E2E 防回流 | — |

---

## 5. P2 清单（收尾治理）

| # | 问题 | 证据 | 处理 |
|---|---|---|---|
| P2-1 | 缓存职责分散 | `permissionService` localStorage 5min、`enumService` LRU(100)、`associationService`、`useMetaCache`、`baseService`/`boService` 各自为政 | 统一 `useMetaCache` + 后端 ETag；元数据走 ETag，业务数据不缓存 |
| P2-2 | 全量拉取当"下拉选项" | `auditLogMeta` 用户下拉 `page_size=1000`、`GroupRoleDialog`/`OrgPermissionSetDialog` 100、`HandlingUnitDocs` 200、`RuleCenterPage` `limit:500` + 前端二次过滤 | 改远端搜索分页（`page_size<=50` + `keyword`） |
| P2-3 | 格式化重复 | `MetaReportPage.vue:176-211`、`StatsOverview.vue:123-137`、`src/utils/filterService.js:49-71`（拼 `23:59:59`） | 日期/金额/百分比格式化收敛到统一 formatter；**截止时间拼装必须后端**（时区风险） |
| P2-4 | 协议封装重复 | `graphqlClient.js:71-110`、`routeTemplate.js:1-23`、`columnOrderService.js:34-54`、`draftPersistService.js:44-94`、`scopeToFilter.js:29-54` | 合并到 httpClient 统一拦截器，去除各自重试/序列化 |

---

## 6. 批次计划（B1–B5）

### 依赖顺序

```
B1 安全止血（P0-1 / P0-2 / P0-3）        ← 独立，最先做
        │
        ├─→ B2 单一真源（P1-1~P1-12）    ← P0-5 的前置
        │        │
        │        ├─→ B3 计算与聚合下沉（P0-4 / P0-5 / P0-6 / P0-7 / P1-13~P1-20 的部分）
        │        │
        │        └─→ B4 事务化与批量接口（P1-20 + 权限矩阵三接口合并）
        │
        └─→ B5 收尾治理（P2 全量 + 表达式 fail-closed 复核 + ESLint 防回流）
```

### B1 安全止血（规模：小）

| 子项 | 内容 | 涉及文件 | 验收 |
|---|---|---|---|
| B1-1 | 三方密钥下沉 | 新增 `meta/api/integration_api.py`、`meta/services/integration_credential_service.py`；改 `src/services/deepseekValidator.js`、`zhipuValidator.js`、`feishuService.js`、`src/views/SystemManagement/SystemSettings.vue` | `dist/` 无密钥；新增后端单测通过 |
| B1-2 | 权限 fail-closed | `src/composables/useMetaList.js`、`useMenuPermissions.js`、`conditionExpressionService.js`、`safeExpression.js`；新增 `actions/evaluate` | 接口异常时按钮不可见；单测断言 `false` |
| B1-3 | 端点鉴权 | `meta/api/scheduler_api.py`、`meta/api/permission_dimension_api.py` | 普通用户 403 负向用例通过 |

> **B1 不含任何 UI 功能变更**，风险最低，可独立发布。

### B2 单一真源（规模：中）

| 子项 | 内容 |
|---|---|
| B2-1 | 后端新增 `meta/api/meta_enum_api.py`：`/enums/<name>`、`/permission-matrix-schema`、`/permission-meta`，数据源自 `meta/schemas/*.yaml`（避免又出现第二真源） |
| B2-2 | 前端删除 6 张表副本：`permissionService.js:16-139`、`permissionConstants.ts:52-89`、`RoleDetailDrawer.vue:265`、`ConditionRuleList.vue:48,70`、`useConditionRules.ts:9`、`ResourceActionMatrix.vue:670`。**`manage` 漂移 2026-11-13 决定：本轮不处理**（见 §10.2 TODO-1），B2 实施时跳过含 `manage` 的行/分支，其余 5 张表照常删除 |
| B2-3 | 审计/任务/层级/变更单枚举全部改接口下发 |
| B2-4 | 字段策略与动作表单校验改为调用 `POST /bo/<code>/validate` |
| B2-5 | 选择上限、维度范围改由后端校验（忽略 URL 覆盖） |

### B3 计算与聚合下沉（规模：中）

| 子项 | 内容 |
|---|---|
| B3-1 | 定价模拟接口（P0-4），删除 `ComponentComparison.vue` 计算与单价 |
| B3-2 | 变更单 `actions` + `diff` 接口（P0-5） |
| B3-3 | 架构统计接口（P0-6），删除两处遍历 |
| B3-4 | 关系编码后端生成（P0-7） |
| B3-5 | 报表服务端分页（P1-13）、级联一次返回（P1-19）、处理单元聚合（P1-17） |
| B3-6 | 关系分类下沉（P1-14）——**2026-11-13 决定：不实施**。已核实前端 Excel 解析链为死代码（证据见 §10.2 TODO-2），随死代码清理删除，不做下沉 |

### B4 事务化与批量接口（规模：中）

| 子项 | 内容 |
|---|---|
| B4-1 | 权限矩阵 / 菜单 / 维度范围三写接口合并为单事务提交（避免"矩阵成功、菜单失败"半成品） |
| B4-2 | 批量授权/批量关联接口：`POST /api/v2/permission-sets/<id>/rules:batch`，body 含 `operations[]`，返回 `{ succeeded, failed: [{index, reason}] }` |
| B4-3 | 前端 4 处逐条循环改单次批量调用（`GroupRoleDialog`、`OrgPermissionSetDialog`、`AddPermissionDialog`、`PermissionConfigPanel`） |

### B5 收尾治理（规模：大）

| 子项 | 内容 |
|---|---|
| B5-1 | 缓存收敛为 ETag + `useMetaCache` 单一入口（P2-1） |
| B5-2 | 全量拉取改远端搜索分页（P2-2） |
| B5-3 | 格式化收敛 + 截止时间拼装下沉（P2-3） |
| B5-4 | 协议封装去重（P2-4） |
| B5-5 | ESLint 防回流规则（与历史 T-NFR-UI-002 合并实施）：禁止 `.vue` 内 `fetch`、禁止 store 内 `fetch`、禁止 composable 内 >20 行纯计算函数、**禁止新增 `import.meta.env.VITE_.*KEY`** |

---

## 7. 统一约定（所有批次共用）

1. **鉴权装饰器统一**：新增端点一律 `@require_permission('<domain>.<resource>.<action>')`，`meta/api/` 内不允许出现"裸 `@_login_required` 即写"的端点。
2. **真源唯一**：枚举/标签只能来自 `meta/schemas/*.yaml` 或后端常量，前端不得再定义 `label` 映射表。
3. **fail-closed**：前端一切"权限/校验/表达式"默认值必须是"不可用"，只有后端明确返回 `true` 才可用。
4. **错误契约**：复用历史附录 A 的错误码枚举，新增 `UNSUPPORTED_ACTION`、`PERMISSION_DENIED`、`EVAL_FAILED`。
5. **金额与统计**：一律后端返回 `value + formatted`，前端不再做乘法与格式化。

---

## 8. 验证矩阵

| 层级 | 命令 | 适用批次 |
|---|---|---|
| 后端单测（唯一入口） | `python d:\filework\test.py --single meta/tests/<path>` | B1–B5 |
| 后端回归 | `python d:\filework\test.py --failed`（并发假失败需再串行确认） | 每次提交前 |
| 全量 | `python d:\filework\test.py --all --force` | 每批次收尾 |
| 前端单测 | `npx vitest run src/<path>/__tests__/` | B1–B5 |
| E2E | `python d:\filework\test.py --file tests/e2e/<spec>` | B1-3、B3-1/2/3 |
| 测试自查 | `python scripts/lint_tests.py` | 新增测试文件后 |
| 环境体检 | `python scripts/service_manager.py doctor` | 动手前后各一次 |

> **禁止** `pytest` / `python -m pytest`；PowerShell 中 `curl` 是别名，必须用 `curl.exe`。

---

## 9. 风险与禁改清单

### 9.1 严禁触碰（他人未提交 WIP）

| 文件 | 原因 |
|---|---|
| `meta/services/rule_config_publish_service.py` | 混入他人 WIP，未提交 |
| `src/composables/useConditionRuleDialog.js` | 同上 |

约束：**禁止 `git add -A` / `git add .`**，只按文件名精确暂存；禁止在主工作树 commit（多 Agent 必须独立 worktree）。

### 9.2 主要风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| `manage` 与 `admin` 口径不一致 | 权限判断全链路不一致 | 本轮不动 `manage`（TODO-1）；B2 删除副本时保留 `manage` 分支并加注释标记待收口 |
| B1-2 fail-closed 引发"按钮全消失" | 线上功能不可用 | 灰度期接口失败只记日志 + 保留后端开关，观察 1 天再切严格 |
| B2 删除前端副本时漏改单测 | vitest 大面积红 | 按文件清单逐个改，先跑 `npx vitest run` 局部 |
| B3 统计口径与旧前端不一致 | 报表数字对不上 | 接口实现前写死口径（是否含注释节点/孤立节点），并用历史数据对拍 |
| B4 事务化改动权限矩阵写路径 | 影响授权核心 | 必须先有负向用例 + 回滚预案 |
| B5 改动面大 | 回归风险 | 拆成 5 个独立 PR，每 PR 只做一件事 |

---

## 10. 决策记录与 TODO（2026-11-13）

### 10.1 决策结果

| # | 事项 | 决策 | 对计划的影响 |
|---|---|---|---|
| D-1 | `manage` 权限枚举对齐方向 | **本轮不处理，转 TODO-1** | B2-2 跳过含 `manage` 的行；其余 5 张表照常删除；`manage` 收口不阻塞 B3/B4 |
| D-2 | B1 权限 fail-open 灰度 | **接受灰度**：接口失败先记日志不拦截，观察 1 天后切 fail-closed | B1-2 拆两步：① 记日志 + 保留后端开关；② 1 天后翻开关。验收仍以最终 fail-closed 行为为准 |
| D-3 | B3-6 关系分类（前端生成 `${source}-${target}`） | **不实施**；核实为死代码，随死代码清理删除 | B3-6 从批次中移出，转为 TODO-2（清理任务，不是下沉任务） |
| D-4 | 批次排期 | **B1 → B2 → B3 → B4 → B5** | 按 §6 依赖图顺序执行，B1 可独立发布 |

### 10.2 TODO（本轮不实施，登记待排期）

**TODO-1 `manage` 权限枚举收口**

- 结论：暂不处理，等业务侧确认"完全管理"是否需要成为独立权限级别。
- 影响面（漂移点已核实）：`src/views/SystemManagement/constants/permissionConstants.ts:52,60,69,76,89`、`RoleDetailDrawer.vue:265`、`ConditionRuleList.vue:48,70`、`useConditionRules.ts:9`、`ResourceActionMatrix.vue:670`、`src/services/permissionService.js:21,138,253`、`src/services/__tests__/permissionService.spec.js:94,139,155`。
- 注意：`src/constants/permissionLevels.js:10-12,19-21` 本身**只有** `read/write/admin`，不含 `manage`；`meta/schemas/data_permission.yaml:37,41,74` 同样只有 `admin/write/read`。即 `manage` 只存在于上列前端副本。
- 收口方向（任选其一，届时再定）：A 前端删除 `manage` 对齐 `admin`；B 后端扩枚举；C 明确 `manage` 仅 UI 分组不落库。

**TODO-2 前端 Excel 解析链路死代码清理（已核实为死代码）**

- 核实结论：**`src/services/excelParser.js` 无活跃调用方，整条链路已死。**
- 证据链：
  - `src/services/excelParser.js` 唯一被 `src/composables/useExcelParser.js:3-6` 引用；除此之外全仓无引用。
  - `useExcelParser` 仅两处消费者：
    - `src/views/AADiagramApp/composables/useDiagramData.js:278`（解构出 `previewData/rawData/handleFileUpload/clearData`），但 `previewData.value` 实际由后端数据构建（同文件 `:2354`、`:2556`、`:2580`）；`handleFileUpload` 仅在 `:2619` 被导出，**无任何视图消费**。
    - `src/components/AADiagramApp.vue:132,159`，该组件**未被 router 或任何 import 引用**（`src/router/modules/business.js:9` 指向的是 `views/AADiagramApp/index.vue`）；`src/components/DataPreview.vue` 内注释亦称其"已废弃"。
  - `src/views/AADiagramApp/index.vue:81` 只解构 `rawData`，**全文未使用**；该视图无上传控件（无 `el-upload` / `type="file"`）。
- 清理范围（建议独立小 PR）：删除 `src/services/excelParser.js`、`src/composables/useExcelParser.js`、`src/components/AADiagramApp.vue`、`src/services/__tests__/excelParser.spec.js`，并移除 `useDiagramData.js` 中的 `useExcelParser` 引入、`:278` 解构、`:2619` 导出，以及 `index.vue:81` 的 `rawData`。若 `DataPreview.vue` 本身也无引用，一并删除。
- 前置检查：删除后 `npx vitest run` 全绿；`grep -r "excelParser\|useExcelParser" src/` 为 0 命中。
- 不做的事：不把 Excel 解析下沉后端（后端已有 `import_export_service.py` / `async_import_service.py` 承接正式导入，前端这条旧链路无业务价值）。

---

## 11. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-11-13 | v1.0.0 | 初版：5 域通盘审查增量（P0 7 项 / P1 25 项 / P2 4 组），批次 B1–B5 |
| 2026-11-13 | v1.0.1 | 记录 4 项决策（manage 转 TODO-1、B1 接受灰度、B3-6 转 TODO-2 死代码清理、排期 B1→B2→B3→B4→B5）；核实 Excel 解析链路为死代码并补证据链；清除文档 Emoji |
| 2026-11-13 | v1.1.0 | 新增 §12「UI Pattern 通用化细化（B3+）」：头部产品二次对标（SAP Fiori / Salesforce / ServiceNow / 低代码平台）+ 四类元数据契约 + C-1~C-8 逐组件规格 + 抽象门槛与反例 + B3-UI-1~4 分批计划 + 验收矩阵与禁改清单 |
| 2026-11-13 | v1.2.0 | 新增 §13「实现方案（逐任务落地）」：T13-1~T13-9 任务编号与顺序、新建/修改文件清单、TS 类型定义、后端扩展点（models / yaml_loader / view_config_service / meta_api）、`ui-meta` 聚合端点与缓存/并发/fail-closed 细节、四个代码骨架、逐任务测试矩阵、双跑迁移与回滚点 |

---

## 12. UI Pattern 通用化细化（B3+，v1.1.0 新增）

> 本章回答一个问题：**在「元数据模型驱动」前提下，前端哪些 UI 模式值得抽成通用组件，抽到什么程度，以及依据是什么。**
> 本章与 §3~§5 的关系：§3~§5 解决「数据/规则该由谁算」，本章解决「同一套元数据如何驱动一片同类界面」，不重复下沉结论。

### 12.1 定位与边界

**模式化（pattern 化）的定义**（三条同时成立才算）：

1. 页面结构由**后端元数据**完整描述（列、分区、字段、动作、可见性），前端只做渲染映射。
2. 同一份元数据可被**多个对象**复用（换 `object_type` 即换页面，不改前端代码）。
3. 前端组件**不含业务分支**（不写 `if (objectType === 'sales_order')`），分支全部由元数据字段承载。

**不是模式化**（本章明确排除）：

- 纯视觉一致性（间距、字号、圆角）→ 走设计 token，不抽业务组件。
- 单点页面的一次性交互（如报价模拟器的滑块区）→ 保持页面内实现。
- 只有 1~2 处使用、且数据结构差异大的界面 → 不抽，避免「配置驱动」变成「配置地狱」。

**抽象门槛（硬性，写入 code review 检查项）**：
> 同类结构 **≥3 处** 且 **一份后端元数据能完整描述其差异** → 抽组件；
> 否则只抽 composable（复用逻辑、不锁 UI）。

### 12.2 头部产品二次对标与差距矩阵

本轮对 4 类产品做了二次研究（结论为「它们把什么放进了元数据」），用于校准我们的组件边界。

**（1）SAP Fiori elements（OData 注解驱动）**

| 能力 | 注解 | 我们的对应物 | 状态 |
|---|---|---|---|
| 列表列与顺序 | `UI.LineItem` | `list-view`（`<t>/list-view`） | 已有 |
| 详情页分区 | `UI.Facets` + `UI.FieldGroup` | `detail-view`（分区字段组） | 已有（但无 `col_span`/tabs） |
| 字段/列隐藏 | `UI.Hidden` | 字段 `visible` 静态标记 | 部分（无条件显隐） |
| 筛选栏字段 | `UI.SelectionFields` | `filter-config` + `filter-tree` | 已有 |
| 排序/初始可见列 | `UI.PresentationVariant` | `list-view` 内 default_sort | 部分 |
| 语义色（红黄绿） | `UI.Criticality` / `DataPoint` | 前端本地 `TAG_TYPE_MAP` / `STATUS_COLOR_TO_TYPE` | **缺失（前端第二份真源）** |
| 值帮助 | `Common.ValueList` | `value_help_api` + `EnumSearchHelp.vue` | 已有 |
| 字段联动/副作用 | `Common.SideEffects` | 无声明式接口 | **缺失** |
| 消费方式 | SmartTable / SmartForm / SmartFilterBar 通用控件，页面零代码 | `GenericObjectList` + `useMetaList` | 部分（列表已有，表单/详情无） |

**（2）Salesforce（Lightning 元数据 + Dynamic Forms）**

| 能力 | 实现 | 对我们的启示 |
|---|---|---|
| 字段级显隐 | `UiFormulaRule`（FlexiPage 元数据），可基于**当前记录字段值**、`$User` 字段、设备形态求值；每个字段是独立组件而非整块布局 | 这正是我们缺的「`visible_when`」层；且说明显隐规则要能在**字段粒度**声明，不能只在整表单粒度 |
| 分区可编排 | Dynamic Forms 的 `FieldSection`，可按 app/profile/record type 分配不同布局 | 我们的 `form.sections` 有分区但无「同一对象多套布局」概念，暂不引入（门槛未达） |
| 校验 | 校验规则在服务端（Validation Rule / 公式字段） | 与 §3 P0-2 一致：校验后端化，前端只渲染 `errors` |

**（3）ServiceNow（UI Builder）**

页面、组件、事件、数据资源全部是元数据记录（`sys_ux_*`），同一页面可按 audience/device 派生 variant。启示：**「页面 = 元数据实例」是可维护的**，但前提是有可视化编排器；我们没有编排器，因此只取其「数据资源与组件解耦」这一点 —— 前端组件只吃「已解析好的元数据」，不自己拼装多个端点（对应 C-2 `useUiMeta`）。

**（4）Retool / Appsmith / lowcode-asa（通用渲染器 + JSON Schema）**

核心结论有三条：① 用 JSON Schema 描述结构、渲染器与之解耦；② 组件注册表（registry）而非硬编码分支；③ 校验/权限/生命周期以**插件**形式挂在渲染管线，不与 UI 组件耦合。对应我们的做法：EnumTag/EnumSelect 走注册表，权限与可见性走 composable 插件式注入。

**差距矩阵（我们 vs 头部产品的「元数据完备度」）**

| 层 | 头部产品 | 我们（2026-11-13 盘点） | 差距等级 |
|---|---|---|---|
| 枚举/标签/语义色真源 | 注解 + Criticality | 后端 `enums/batch` 已有（B2 补齐 `meta/enums/<name>`）；语义色仍在**前端 6 处地图**（`auditLogFormat.js`、`permissionConstants.ts`、`MetaListPage.vue:1579`、`DetailPage.vue:596` 等） | 中（前端侧未收口） |
| 列表视图 | LineItem + PresentationVariant | `list-view` 完备；但前端仍需并发请求 list-view + filter-config + field-policies 三份，且 3 个页面手写表格 | 中 |
| 详情视图 | Facets + FieldGroup | `detail-view` 有分区；无 `col_span`、无 tabs | 中 |
| 表单视图 | SmartForm + UiFormulaRule | `form-view` 有 sections；**无字段级 `visible_when`、无 `col_span`、无 tabs** | **大（核心缺口）** |
| 动作/按钮 | 注解 + 服务端决策 | `actions/evaluate` 已有（P0-2 待批量）；按钮来源仍是 `ui-config.actions`，无动作栏聚合元数据 | 中小 |
| 值帮助 | Common.ValueList | `value_help_api` + 两个组件 | 小 |
| 字段联动 | SideEffects | 仅 `business_object.yaml` 有 `depends_on`；`visible_when` 只存在于**动作层** | 大 |

**结论**：后端已基本达到 SAP「注解层」水平；真正缺的是 Salesforce `UiFormulaRule` / `UI.Hidden` 对应的**可见性与布局声明层**，以及前端的**枚举语义色收口**。因此 B3 的重点不是「再造元数据接口」，而是「补齐可见性声明 + 让前端只消费一份元数据」。

### 12.3 四类元数据契约（前端消费面）

> 以下契约描述**前端消费的形状**；后端端点已存在或按 §12.4 标注新增。原则：一次页面加载只发**一次**元数据聚合请求。

**（A）EnumContract**

```
GET /api/v2/meta/enums/<name>        → { name, items: [{ value, label, color?, category? }] }
GET /api/v1/meta/enums/batch?names=a,b → { [name]: [{ value, label, color? }] }
```

- `label`：唯一文案真源，前端不得再写中文映射表。
- `color`：语义色（`success | warning | danger | info | primary`），前端只做 class 映射。
- `category`：分组标签（用于 `el-option-group`），替代 `actionOptionsGrouped` 这类本地拼装。

**（B）ViewContract**

```
GET /api/v2/bo/<t>/ui-meta  (新增聚合端点)
→ {
    object_type, label,
    list:  { columns: [{ field, label, width, sortable, filterable, tag_enum? }], default_sort, page_size, actions: [...] },
    detail:{ sections: [{ key, label, columns(1|2), fields: [...] }] },
    form:  { sections: [{ key, label, columns, col_span_map, tabs?: [{key,label}] }],
             fields: [{ key, label, widget, required, readonly, visible, visible_when?, enum_type?, value_help?, depends_on? }] },
    filters: [...],
    field_policies: {...},
    actions: [...]
  }
```

- 由现有的 `list-view` / `detail-view` / `form-view` / `filter-config` / `field-policies` / `ui-config` 在**后端**合并下发，避免前端 4~6 个并发请求（当前 `useMetaList` 已有该问题）。
- 元数据带 `schema_version`（已有端点 `schema-version`），前端缓存按 version 失效。

**（C）ActionContract**

```
GET  /api/v2/bo/<t>/actions/evaluate  (P0-2 扩展为批量)
POST /api/v2/bo/<t>/actions/evaluate  body { ids:[...], actions:[...] }
→ { [id]: { [action]: { enabled, reason, required_permission, style } } }
```

- `style` 直接给按钮/标签语义色，前端不再维护第二份映射。
- `reason` 用于 tooltip（灰化原因），`enabled=false` 时按钮仍渲染但禁用（可发现性优于消失）。

**（D）VisibilityContract（新增，本批次核心）**

在 `form-view` / `detail-view` 字段上新增三个声明式键，语义对齐 Salesforce `UiFormulaRule` 与 SAP `UI.Hidden`：

| 键 | 类型 | 语义 | 求值方 |
|---|---|---|---|
| `visible_when` | 表达式字符串，如 `status IN ('draft','rejected') AND amount > 0` | 字段是否渲染 | **前端本地求值**（仅用于 UI 显隐，不承载权限语义） |
| `col_span` | 1~4 整数（相对栅格） | 字段占宽，替代纯 `columns:1|2` 的整表单粒度 | 前端 |
| `tabs` | `[{key,label,section_keys[]}]` | 分区归组到 tab；缺省则平铺 | 前端 |

**红线**：`visible_when` **不得**用于权限控制（权限只看 `field-policies` + 服务端）。表达式求值失败时 **隐藏字段并上报一次错误**（fail-closed，与 P0-2 口径一致）。

### 12.4 组件清单与逐项规格

优先级：C-1 / C-2 / C-3 为 P0（重复最重、收益最高）；C-5 / C-6 / C-7 为 P1（依赖 VisibilityContract）；C-4 / C-8 为 P1（收编类，需逐个页面评估）。

---

#### C-1 `EnumTag`（+ `useEnumMeta`）— P0

| 项 | 规格 |
|---|---|
| 职责 | 把「枚举值」渲染为带语义色的标签；**不**接受任何中文 label 入参 |
| Props | `enumName: string`、`value: string|number`、`size?: 'sm'|'default'`、`effect?: 'light'|'plain'`、`showDot?: boolean` |
| 数据源 | `GET /api/v2/meta/enums/<enumName>`（模块级缓存，同 C-2 的 `enumCache`） |
| 行为 | 命中 → 渲染 `label` + `color → el-tag type` 映射；未命中 → 渲染**原始 code** 并 `console.warn` 一次（不隐藏，便于发现元数据缺项） |
| 替换目标 | `auditLogFormat.js:48/239/294/473/484/577`（OBJECT_TYPE / FIELD / FIELD_VALUE / LOG_CATEGORY / LOG_LEVEL / USER_NAME）、`permissionConstants.ts:23/75`（SOURCE_LABELS / BADGE_LABELS）、`EngineeringChangeDetailPage.vue:268-280`（statusLabel/statusTagType）、`EngineeringChangeDiffPage.vue:259`（LINE_TYPE_LABELS）、`MetaListPage.vue:1579`（TAG_TYPE_MAP）、`DetailPage.vue:596`（STATUS_COLOR_TO_TYPE）、`taskService.js:25`（BUCKET_LABELS）、`ObjectOwdPanel.vue:57/63` |
| 规模依据 | 全量 `el-tag` 82 处 / 20 文件；`tagType` 类辅助函数 14 处；当前**不存在**任何 StatusTag/EnumTag 组件（仅有 EnumSelect / EnumSearchHelp） |
| 验收 | ① 上述 8 处地图删除，全局 grep 中文枚举映射 0 命中（白名单：`i18n` 文案）<br>② 标签文案与后端 `enums` 逐项一致（穷举所有枚举值 diff 为 0）<br>③ 未知值渲染 code 而非空白 |
| 测试 | `src/components/__tests__/EnumTag.spec.js`：命中 / 未命中 / 空值 / 缓存复用 4 例 |

#### C-2 `useUiMeta(objectType, view?)` — P0

| 项 | 规格 |
|---|---|
| 职责 | 页面元数据的**唯一入口**：一次请求拿到 list/detail/form/filters/actions/field_policies，按 `schema_version` 缓存 |
| 输入 | `objectType: string`、`view?: 'list'|'detail'|'form'`、`options?: { force?: boolean }` |
| 返回 | `{ meta, loading, error, reload(), enumOf(name) }`；`meta` 结构见 §12.3(B) |
| 数据源 | 新增 `GET /api/v2/bo/<t>/ui-meta`（后端合并现有 6 个端点；旧端点保留兼容一个版本） |
| 约束 | 组件内**禁止**再直接 `apiV2.get('/bo/.../list-view')`；`useMetaList` 改为内部调用 `useUiMeta`（对外接口不变，避免大改） |
| 替换目标 | `useMetaList.js` 中的多端点并发段；`SystemManagement/*` 与 `ObjectPage` 系列页面中的散装 `meta` 请求 |
| 验收 | ① 任一列表页首屏元数据请求数从 N（≥3）降到 1（DevTools Network 断言）<br>② 切对象/切视图时命中缓存不发请求<br>③ `schema-version` 变更后自动重取 |
| 测试 | `src/composables/__tests__/useUiMeta.spec.js`：聚合解析 / 缓存命中 / version 失效 / 错误态 4 例 |

#### C-3 `ActionBar` — P0

| 项 | 规格 |
|---|---|
| 职责 | 渲染对象级/实例级动作按钮组；按钮可用性来自后端批量求值结果 |
| Props | `actions: ActionMeta[]`、`evaluations?: { [id]: {...} }`、`context: 'list'|'detail'|'batch'`、`layout?: 'inline'|'dropdown'` |
| 数据源 | `ui-meta.actions`（按钮定义：code/label/style/scope）+ `POST actions/evaluate`（批量可用性） |
| 行为 | `enabled=false` → 禁用 + tooltip 显示 `reason`；`context='batch'` 时未选中任何行则整组禁用 |
| 替换目标 | `EngineeringChangeDetailPage.vue:329-335`（canSubmit/canApprove/canReject/canEdit/canApply 五个 computed）、列表页顶部按钮区（`useMetaList` 内联渲染） |
| 验收 | ① 上述 5 个 computed 删除；<br>② 断网/500 时动作全部禁用（fail-closed）；<br>③ 无审批权账号在 in_review 单据上看不到「审批」；<br>④ 批量按钮在 0 选中时禁用 |
| 测试 | `src/components/__tests__/ActionBar.spec.js` + 后端 `test_action_policy_batch.py` |

#### C-4 手写列表页收编 — P1

现状：仅剩 3 个页面仍手写「表格 + 筛选 + 分页」——`EngineeringChangeListPage.vue`、`RuleCenterPage.vue`、`MetaReportPage.vue`；其余已走 `useMetaList`。

| 页面 | 结论 | 理由 |
|---|---|---|
| `EngineeringChangeListPage.vue` | **收编**到 `useMetaList` + `ui-meta.list` | 列/筛选/动作均可由变更单元数据描述，无独有交互 |
| `MetaReportPage.vue` | **收编**（列表部分） | 报表列表同构；报表渲染区保留页面私有 |
| `RuleCenterPage.vue` | **不收编**（见 §12.5 反例） | 左侧规则树 + 规则编辑器是独有结构，强行套用会让 `useMetaList` 长出业务分支 |

验收：收编后这两个页面 `.vue` 行数下降 ≥40%，且无新增 `if (objectType === ...)` 分支。

#### C-5 `MetaForm`（元数据驱动表单）— P1

| 项 | 规格 |
|---|---|
| 职责 | 按 `form.sections` + `fields` 渲染表单，支持 `col_span`、`tabs`、`visible_when`、`required/readonly`、`widget` 选择、`value_help` |
| Props | `objectType`、`mode: 'create'|'edit'|'view'`、`modelValue`、`errors?`、`disabled?` |
| 数据源 | `ui-meta.form` + `ui-meta.field_policies`；提交校验走 `POST /bo/<t>/validate`（B2-4 已实装） |
| 依赖 | **必须先补 VisibilityContract**（§12.3 D）：`form-view` 增 `visible_when` / `col_span` / `tabs` 三个键，并在后端 `form-view` 序列化处下发 |
| 明确不做 | 不内置业务计算（金额合计等走后端）；不做拖拽式布局编辑（无编排器需求） |
| 替换目标 | `UseBoActionForm` 相关弹窗表单（`useBoActionForm.js` + 各业务弹窗）中重复的 `el-form-item` 手写段；**不替换**复杂定制表单（如报价模拟器） |
| 验收 | ① 至少 2 个对象的 create/edit 表单由同一组件渲染；② `visible_when` 在表单值变化时即时生效；③ 校验错误定位到字段（`field_name` → form-item）；④ 与后端 `validate` 结果 100% 一致 |
| 测试 | `MetaForm.spec.js`：col_span 布局 / tabs 切换 / visible_when 联动 / 必填错误 / 只读态 5 例 |

#### C-6 字段联动声明（`FieldLinkage`）— P1

| 项 | 规格 |
|---|---|
| 职责 | 把「字段 A 变化 → 字段 B 的选项/只读/必填/值变化」改为**元数据声明**，而非页面内 `watch` |
| 数据源 | `form.fields[].depends_on: [{ field, effect: 'options'|'readonly'|'required'|'reset'|'reload_value_help', source?: 'enum'|'value_help' }]` |
| 现状依据 | 目前 `depends_on` 仅出现在 `business_object.yaml`；字段→控件联动散落在页面 `watch` 与 `useBoActionForm` 内 |
| 门槛 | 先盘点：若全项目同类联动 <3 处，则**只做 composable `useFieldLinkage`**，不做声明式键（避免为 2 处引入解析器） |
| 验收 | 若落地：至少 1 个对象的联动由元数据驱动；删除对应页面 `watch` |

#### C-7 `DetailSection`（详情分区渲染）— P1

| 项 | 规格 |
|---|---|
| 职责 | 按 `detail-view.sections` 渲染分区标题 + 字段网格；字段值按类型走 formatter；枚举字段走 C-1 |
| Props | `sections`、`record`、`fieldPolicies`、`columns?: 1|2` |
| 替换目标 | `DetailPage.vue` 与各单据详情页中重复的 `<el-descriptions>` / 手写分区段 |
| 复用 | 与 C-5 共享 `fieldFormatters`（金额/日期/布尔/空值 `—`），避免详情与表单各写一份格式化 |
| 验收 | ① ≥2 个详情页由同一组件渲染；② 空值统一渲染 `—`；③ 金额/日期格式与列表页一致（同一 formatter） |

#### C-8 `DiffView`（变更差异渲染）— P1

| 项 | 规格 |
|---|---|
| 职责 | 渲染「字段 before/after + 行级差异」；差异结构由后端生成（§3 P0-5 的 `/diff` 端点） |
| 现状 | `EngineeringChangeDiffPage.vue:259` 有本地 `LINE_TYPE_LABELS`，`:413-427` 有前端拼装的状态动作 |
| 数据源 | `GET /api/v2/engineering-changes/<id>/diff` → `{ lines: [{ type, field, before, after }] }` |
| 验收 | ① 前端不再计算差异，只渲染；② `LINE_TYPE_LABELS` 删除，标签来自后端；③ diff 行色语义与 `style` 字段一致 |

### 12.5 抽象门槛与反例（明确「不抽」）

| 对象 | 结论 | 原因（对应门槛） |
|---|---|---|
| `RuleCenterPage.vue` | 不抽 | 规则树 + 编辑器是独有交互；套用通用列表会让 `useMetaList` 增加 `objectType` 业务分支（违反 §12.1 第 3 条） |
| `ComponentComparison.vue` | 不抽 | 报价模拟器是单点营销页，交互与数据结构唯一；按 §3 P0-4 仅把**算钱**下沉后端，UI 保持页面内 |
| 权限矩阵（`ResourceActionMatrix`） | 不抽成通用表格 | 行列双向勾选 + 三态/灰化/来源标签是权限域专有语义；已高度组件化（自身即组件），再抽象无复用方 |
| `MetaReportPage` 报表渲染区 | 不抽 | 报表类型差异大，元数据描述成本高于收益 |
| 纯视觉样式（间距/字号/圆角） | 不抽组件 | 走设计 token，非业务模式 |

### 12.6 分批计划（B3-UI）

| 批次 | 内容 | 后端依赖 | 前置 | 完成判据 |
|---|---|---|---|---|
| **B3-UI-1** | C-1 EnumTag + `useEnumMeta` 缓存；C-2 `useUiMeta` 前端骨架（先对接现有 6 端点，聚合端点可后置） | 无（`enums/batch` 已有） | B2 完成 | 8 处中文枚举地图删除；列表页元数据请求收敛 |
| **B3-UI-2** | C-3 ActionBar + `actions/evaluate` 批量化 + `ui-meta.actions` 聚合 | `POST actions/evaluate` 批量 | B3-UI-1；P0-2 fail-closed 口径 | 5 个状态 computed 删除；断网全禁用 |
| **B3-UI-3** | VisibilityContract 后端补齐（`visible_when`/`col_span`/`tabs`）→ C-5 MetaForm → C-7 DetailSection → C-6 FieldLinkage（先盘点再决定是否声明式） | `form-view` / `detail-view` 序列化扩展 | B3-UI-2 | ≥2 个对象表单同组件渲染；visible_when 生效 |
| **B3-UI-4** | C-4 收编 2 个手写列表页；C-8 DiffView（依赖 P0-5 的 `/diff`） | `/diff` 端点 | B3-UI-3；P0-5 | 两页行数 −40%；无新增业务分支 |

> 排期建议：B3-UI-1 可与 §6 的 B2 尾巴并行（纯前端，不动端点）；B3-UI-3 必须在 P0-2 完成后做，否则 `visible_when` 会与 fail-open 混淆。

### 12.7 验收矩阵 + 风险与禁改

**全局验收矩阵**

| 编号 | 断言 | 方式 |
|---|---|---|
| A-UI-1 | 前端不再存在「枚举 code → 中文」的本地映射表 | `Grep` 白名单校验（8 个目标文件） |
| A-UI-2 | 单页面元数据请求数 = 1 | DevTools Network / `useUiMeta` 单测 |
| A-UI-3 | 权限/可见性求值失败 → 隐藏或禁用（fail-closed） | 断网手工 + 单测 |
| A-UI-4 | 同一对象在列表/详情/表单中的标签与颜色完全一致 | 三页截图比对 + 枚举穷举单测 |
| A-UI-5 | 新增组件无 `objectType ===` 业务分支 | ESLint 自定义规则或 code review 清单 |
| A-UI-6 | 抽出的组件均有对应 `.spec.js`，且 `npx vitest run <spec>` 通过 | 前端测试 |
| A-UI-7 | 后端新增/扩展端点有 `test.py --single` 用例 | 后端测试 |

**风险与禁改**

| 风险 | 影响 | 对策 |
|---|---|---|
| 聚合端点 `ui-meta` 体积过大 | 首屏元数据 100KB+ 拖慢加载 | 按 `view` 参数裁剪（`?view=list` 只返列表相关）；gzip 后仍超 50KB 则拆分 |
| `visible_when` 表达式解析前端实现 | 表达式能力不一致导致显隐错乱 | 复用后端 `condition_evaluator` 的**同一套语法子集**，并加「语法不支持即报错并隐藏」 |
| 声明式表单降低定制能力 | 复杂表单（报价/图表配置）无法表达 | 明确 MetaForm 只覆盖「标准对象表单」；定制表单白名单保留 |
| EnumTag 全量替换面大（82 处） | 回归面广 | 分批替换（按文件目录），每批跑该目录 vitest；保留 1 个版本的旧辅助函数并标 `@deprecated` |
| 元数据缓存 stale | 改配置后前端不生效 | 缓存键含 `schema_version`；提供 `force` 参数与「刷新元数据」入口（已有 `meta/reload`） |

**禁改清单（本章新增）**

1. 不得在 `visible_when` 中承载权限语义（权限只走 `field-policies` + 服务端）。
2. 不得为追求通用性给 `useMetaList` / `MetaForm` 增加对象级 `if` 分支。
3. 不得在未达「≥3 处」门槛时新增声明式元数据键。
4. 不得让前端重新计算 §3 P0 清单中的任何金额/统计/状态判定。
5. 不得删除旧端点前未确认前端全量切换（保留一个版本双跑）。

### 12.8 参考来源（二次对标）

- SAP Fiori elements — OData V4 注解（`UI.LineItem` / `UI.Facets` / `UI.FieldGroup` / `UI.Hidden` / `UI.SelectionFields` / `UI.PresentationVariant` / `UI.Criticality` / `Common.SideEffects`）与 Smart 控件消费方式：<https://ui5.sap.com/tools/feature-showcase.html>、<https://help.sap.com/docs/SAP_FIORI_ELEMENTS>
- Salesforce — Dynamic Forms 与 `UiFormulaRule`（字段级可见性可基于记录字段、`$User` 字段、设备形态）：<https://help.salesforce.com/s/articleView?id=sf.dynamic_forms_overview.htm>、Lightning Web Components `lightning-record-edit-form` / FlexiPage 元数据文档
- ServiceNow — UI Builder 全元数据页面（`sys_ux_page` / 组件 / 数据资源 / variant）：<https://docs.servicenow.com/bundle/xanadu-application-development/page/build/ui-builder/concept/ui-builder-overview.html>
- 低代码通用渲染器 — JSON Schema 驱动 + 组件注册表 + 插件化校验/权限/生命周期（Retool / Appsmith 公开架构文档与 lowcode-asa 实践总结）：<https://docs.retool.com/>、<https://docs.appsmith.com/>

> 备注：上述链接为对标依据的分类入口，用于支撑「哪些能力应由元数据声明」的判断；本文不引用其实现细节代码。

---

## 13. 实现方案（逐任务落地，v1.2.0 新增）

> 本章把 §12 的组件规格落成可执行任务。所有路径相对仓库根 `d:\filework\excel-to-diagram`；行号基于 2026-11-13 快照，实施以当次磁盘为准。

### 13.1 任务编号与落地顺序

**实施顺序与编号顺序不同**：先有元数据（后端），再有基础设施（前端），最后才是组件与收编。

| 步骤 | 任务 | 对应批次 | 交付物 | 前置依赖 |
|---:|---|---|---|---|
| 1 | T13-5 | B3-UI-1 | 后端 `GET /api/v2/bo/<t>/ui-meta` 聚合端点 | 无 |
| 2 | T13-1 | B3-UI-1 | 枚举 batch 端点补齐 `color` / `category` + 前端缓存收口 | 无 |
| 3 | T13-2 | B3-UI-1 | `src/types/uiMeta.ts` 类型定义 + `metaService.getUiMeta` | T13-5 |
| 4 | T13-3 | B3-UI-1 | `useUiMeta` / `useEnumMeta` composable（缓存 + 并发去重 + 降级） | T13-2 |
| 5 | T13-4 | B3-UI-1 | `EnumTag` 组件（替代各处状态/枚举映射表） | T13-3 |
| 6 | T13-6 | B3-UI-2 | `ActionBar` + `POST actions/evaluate` 批量求值 | T13-3 |
| 7 | T13-7 | B3-UI-3 | VisibilityContract 后端扩展 + `visibilityEvaluator` | T13-5 |
| 8 | T13-8 | B3-UI-3 | `MetaForm` / `DetailSection`（消费 `visible_when` / `col_span` / `tabs`） | T13-7 |
| 9 | T13-9 | B3-UI-4 | 列表页收编（`useMetaList` 换源）+ `DiffView` | T13-3 / T13-6 |

> 任务粒度按「可独立验证 + 可独立回滚」切分；T13-5 与 T13-1 可并行，T13-4 与 T13-6 可并行。

### 13.2 文件级改动清单

**新建**

| 文件 | 说明 |
|---|---|
| `src/types/uiMeta.ts` | 四类契约的 TS 类型（§13.3），唯一类型真源 |
| `src/composables/useEnumMeta.js` | 枚举加载 / 缓存 / 并发去重，供 `EnumTag` 与筛选器消费 |
| `src/composables/useUiMeta.js` | `ui-meta` 单次加载 + `form`/`detail` 索引 + schema_version 失效 |
| `src/composables/useBatchActions.js` | 批量 `actions/evaluate` 请求合并（50ms 窗口）+ 结果索引 |
| `src/utils/visibilityEvaluator.js` | `visible_when` 求值封装（复用 `safeExpression.evaluateCondition`） |
| `src/components/meta/EnumTag.vue` | 枚举/状态标签，唯一颜色映射点 |
| `src/components/meta/ActionBar.vue` | 工具栏/行内/批量动作渲染，`enabled=false` 灰化 + tooltip |
| `src/components/meta/MetaForm.vue` | 元数据驱动表单（含 `visible_when` / `col_span` / `tabs`） |
| `src/components/meta/DetailSection.vue` | 详情分区渲染（1/2 列 + 字段级 `col_span`） |
| `src/components/meta/DiffView.vue` | 变更差异渲染（数据来自后端 `diff` 结构） |
| `src/components/meta/__tests__/*.spec.js` | 组件单测（§13.7） |
| `src/composables/__tests__/useUiMeta.spec.js` | 缓存 / 去重 / 失败降级 |
| `src/utils/__tests__/visibilityEvaluator.spec.js` | 表达式子集 + fail-closed |
| `meta/tests/api/test_ui_meta_api.py` | 聚合端点形状 / 局部缺失 / 鉴权 |
| `meta/tests/services/test_view_config_visibility.py` | `col_span` 越界、`tabs` 引用校验、schema_version 变化 |

**修改**

| 文件 | 改动点 |
|---|---|
| `meta/core/models.py` | `UIAnnotation` 增 `visible_when` / `col_span`；`UIFormSection` / `UIDetailFacet` 增 `key` / `columns` / `col_span_map`；`UIFormViewConfig` / `UIDetailViewConfig` 增 `tabs` |
| `meta/core/yaml_loader.py` | `parse_ui_annotation` 提取两个新键（缺省不写）；解析 `form.tabs` / `detail.tabs` |
| `meta/services/view_config_service.py` | `build_form_view_from_fields`（约 345 行）与 `build_detail_view_from_fields`（约 303 行）补 `key` / `columns`；`get_or_build_view_config`（约 385 行）输出 `schema_version` |
| `meta/api/meta_api.py` | 新增 `/<object_type>/ui-meta`，内部复用 `get_or_build_view_config`，不复制逻辑 |
| `meta/api/meta_enum_api.py` | `enums/batch` 的每项补 `color` / `category`；`enums/<name>` 保持单数形状 |
| `src/services/metaService.js` | 新增 `getUiMeta(objectType)`（含 `schema_version` 缓存 + inflight 去重）；旧 `getViewConfig` 保留 |
| `src/services/metaEnumService.js` | 改为消费 batch 端点；本地映射表只删不增；batch 请求按 **name 级 inflight 合并**（不同 name 集合并发时，已被在途批次覆盖的 name 不再重复请求） |
| `src/services/boService.js` | 复用既有 `evaluateActions(...)` 承载批量语义（见下方命名偏差记录），不新增 `evaluateActionsBatch` 别名 |
| `src/composables/useMetaList.js` | 约 1172 行 `metaService.getViewConfig` 换 `getUiMeta`；约 1122 行单条 `evaluateActions` 换批量；`catch → return true` 全部改 fail-closed |

> 目录选择：新组件放 `src/components/meta/`（业务组件层），不复用 `src/components/` 顶层的页面级历史组件，也不混入 `src/components/app/` 的纯 UI 基础层。

> **命名偏差记录（T13-9 实测）**：本文档早期写作 `boService.evaluateActionsBatch(...)`，实际实现为 `boService.evaluateActions(objectType, ids, actions)`，已支持 ids 数组入参与批量返回结构，行为与文档契约一致。为不改动既有调用方，**不新增 `evaluateActionsBatch` 别名**，以本条记录为准。

### 13.3 类型定义（`src/types/uiMeta.ts`）

```ts
export type EnumColor = 'success' | 'warning' | 'danger' | 'info' | 'primary'

export interface EnumItem {
  value: string | number | boolean
  label: string
  color?: EnumColor
  category?: string
}

export interface UiColumnMeta {
  field: string
  label: string
  width?: number
  sortable?: boolean
  filterable?: boolean
  tag_enum?: string
}

export interface UiFieldMeta {
  key: string
  label: string
  widget: string
  required?: boolean
  readonly?: boolean
  visible?: boolean
  visible_when?: string
  col_span?: 1 | 2 | 3 | 4
  enum_type?: string
  value_help?: unknown
  depends_on?: string[]
}

export interface UiSectionMeta {
  key: string
  label: string
  columns?: 1 | 2
  fields: string[]
  col_span_map?: Record<string, 1 | 2 | 3 | 4>
}

export interface UiTabMeta {
  key: string
  label: string
  section_keys: string[]
}

export interface UiActionMeta {
  id: string
  label: string
  icon?: string
  style?: EnumColor
  position?: 'toolbar' | 'row' | 'batch'
  confirm?: string
  enabled?: boolean
  reason?: string
  required_permission?: string
}

export interface UiMeta {
  schema_version: string
  object_type: string
  label: string
  partial?: boolean
  list: {
    columns: UiColumnMeta[]
    default_sort?: string
    page_size?: number
    actions: UiActionMeta[]
  }
  detail: { sections: UiSectionMeta[]; tabs?: UiTabMeta[] }
  form: {
    sections: UiSectionMeta[]
    tabs?: UiTabMeta[]
    fields: UiFieldMeta[]
    layout?: 'vertical' | 'horizontal'
  }
  filters: unknown[]
  field_policies: Record<string, { editable?: boolean; visible?: boolean; readonly?: boolean }>
  actions: UiActionMeta[]
}

export type ActionEvaluateResult = Record<
  string,
  Record<string, { enabled: boolean; reason?: string; required_permission?: string; style?: EnumColor }>
>
```

字段命名红线：前端类型字段名与后端 JSON **逐字一致**（`snake_case`），不在前端做驼峰转换，避免 `col_span` / `visible_when` 两套叫法。

### 13.4 后端扩展点

**（1）模型层** `meta/core/models.py`

```python
@dataclass
class UIAnnotation:
    ...
    visible_when: Optional[str] = None   # 仅 UI 显隐，不承载权限
    col_span: Optional[int] = None       # 1..4，越界在加载期忽略并 warning

@dataclass
class UIFormSection:
    title: str
    fields: List[str]
    key: Optional[str] = None
    columns: int = 2
    col_span_map: Dict[str, int] = field(default_factory=dict)

@dataclass
class UITabConfig:
    key: str
    label: str
    section_keys: List[str]
```

- `UIFormViewConfig` / `UIDetailViewConfig` 增 `tabs: List[UITabConfig] = field(default_factory=list)`。
- `col_span` 校验放在**反序列化处**（`yaml_loader`），非法值降级为 `None` + 一条 warning 日志，不抛异常阻断启动。

**（2）加载层** `meta/core/yaml_loader.py`

- `parse_ui_annotation` 增加两个键的提取（参考现有 `hidden_in_form` 的提取路径；漏提取会表现为「YAML 写了不生效」）。
- `tabs` 解析后做引用校验：`section_keys` 中不存在的 key → 丢弃该 tab 并 warning，其余照常。

**（3）服务层** `meta/services/view_config_service.py`

- `build_form_view_from_fields`：`UIFormSection` 增加 `key=slugify(group_name)`、`columns=2`；`col_span_map` 由字段的 `ui.col_span` 汇总。
- `build_detail_view_from_fields`：同上，`UIDetailFacet` 补 `key` / `columns`。
- `get_or_build_view_config`：返回值加 `schema_version`，取值优先级：
  1. 已有 `schema-version` 端点返回的版本（复用，不新增算法）；
  2. 退化方案：`sha1(object_type + json(config, sort_keys=True) + 字段 UI 注解摘要)[:12]`。

**（4）接口层** `meta/api/meta_api.py`

```python
@meta_bp.route('/<object_type>/ui-meta', methods=['GET'])
@<沿用相邻 list-view 路由的鉴权装饰器>
def get_ui_meta(object_type):
    config = svc.get_or_build_view_config(object_type)      # 已有兜底逻辑
    view = svc.get_view_config(object_type)                 # 显式配置（可为空）
    blocks, partial = {}, False
    for name, builder in (('list', _list_block), ('detail', _detail_block),
                          ('form', _form_block), ('filters', _filters_block),
                          ('field_policies', _policies_block)):
        try:
            blocks[name] = builder(object_type, config, view)
        except Exception:
            logger.exception('ui-meta block failed: %s/%s', object_type, name)
            blocks[name] = _empty_block(name)
            partial = True
    return jsonify(success=True, data={
        'schema_version': config.schema_version,
        'object_type': object_type,
        'label': registry.get(object_type).name,
        'partial': partial,
        'actions': _merge_actions(config.list, config.detail),
        **blocks,
    })
```

契约要点：

- **单块失败不整体 500**：返回 `partial: true` + 空块，前端按「局部降级」渲染并上报一次错误（与 fail-closed 口径区分：显隐失败隐藏字段，元数据缺失只降级区域）。
- 旧 3 个端点保留，内部同样走 `get_or_build_view_config`，保证新旧同源。
- `ui-meta` 不返回任何权限判定结果，只返回声明；`enabled` 只来自 `actions/evaluate`。

### 13.5 关键实现细节

| 关注点 | 方案 |
|---|---|
| 缓存键 | `metaService` 内 `key = object_type`，值 `{ schema_version, data }`；命中时比对 version，不一致即重取并整块替换 |
| 并发去重 | `inflight: Map<key, Promise>`；同 key 并发只发一次，完成后 `finally` 清理 |
| 枚举缓存 | 与 `ui-meta` 共享 `schema_version`；`meta/reload` 后自动失效（无需手工清表） |
| 请求次数 | 一个页面加载 = 1 次 `ui-meta` + 1 次 `enums/batch`（按需）+ 1 次 `actions/evaluate`（有选中行时） |
| `visible_when` 求值 | 复用 `src/utils/safeExpression.js` 的 `evaluateCondition`；语法子集：比较运算 / `IN` / `AND` / `OR` / `NOT` / 字段直引 / 字面量 |
| 求值失败 | `fail-closed`：`visible=false`，同 `(object_type, field, expr)` 仅上报一次错误，避免刷屏 |
| 显隐触发 | `computed` 依赖当前记录值；编辑态用表单当前值，详情态用后端记录值，两者不混用 |
| 栅格 | `MetaForm` 固定 4 列；字段 `col_span` 缺省 = `section.columns === 1 ? 4 : 2` |
| 批量求值 | 同一 `object_type` 的 50ms 窗口内请求合并为一次；**请求未返回前动作默认 `enabled=false, reason='pending'`**，禁止先放行后回填 |
| 成功率上报 | `ui-meta` 的 `partial=true`、`evaluate` 的 `unsupported` 两类事件计数上报，用于灰度期对比 |

### 13.6 代码骨架

**`useUiMeta`**

```js
import { ref, shallowRef, computed } from 'vue'
import metaService from '@/services/metaService'

export function useUiMeta(objectTypeRef) {
  const meta = shallowRef(null)
  const loading = ref(false)
  const error = ref(null)

  async function load(force = false) {
    const type = unref(objectTypeRef)
    if (!type) return null
    loading.value = true
    error.value = null
    try {
      meta.value = await metaService.getUiMeta(type, { force })
      return meta.value
    } catch (e) {
      error.value = e
      meta.value = null            // 不提供残缺兜底，交给调用方降级
      return null
    } finally {
      loading.value = false
    }
  }

  const fieldIndex = computed(() =>
    Object.fromEntries((meta.value?.form?.fields || []).map(f => [f.key, f]))
  )
  const sectionIndex = computed(() =>
    Object.fromEntries([...(meta.value?.form?.sections || []), ...(meta.value?.detail?.sections || [])]
      .map(s => [s.key, s]))
  )
  return { meta, loading, error, load, fieldIndex, sectionIndex }
}
```

**`useEnumMeta`**

```js
const cache = new Map()        // name -> { schemaVersion, items, byValue }
const inflight = new Map()

export function useEnumMeta() {
  const loading = ref(false)

  async function load(name, schemaVersion) {
    const hit = cache.get(name)
    if (hit && hit.schemaVersion === schemaVersion) return hit
    if (inflight.has(name)) return inflight.get(name)
    const p = metaEnumService.getEnum(name, { schemaVersion })
      .then(items => {
        const entry = { schemaVersion, items, byValue: new Map(items.map(i => [String(i.value), i])) }
        cache.set(name, entry)
        return entry
      })
      .finally(() => inflight.delete(name))
    inflight.set(name, p)
    return p
  }

  function getItem(name, value) {
    return cache.get(name)?.byValue.get(String(value)) || null
  }
  return { load, getItem, loading }
}
```

**`EnumTag.vue`（核心逻辑）**

```vue
<template>
  <el-tag v-if="item" :type="tagType" size="small" disable-transitions>
    {{ item.label }}
  </el-tag>
  <span v-else class="enum-tag--unknown">{{ value ?? '-' }}</span>
</template>

<script setup>
const props = defineProps({ enumName: String, value: [String, Number, Boolean] })
const { item, tagType } = useEnumTag(props)   // tagType: color -> EP type，未知 color 用 'info'
</script>
```

- 颜色映射只在此组件内维护一份 `EnumColor -> el-tag type`，其他页面禁止再写 `statusTagType()`。
- 未知枚举值：显示原值 + `info` 色，不隐藏（可发现性）。

**`ActionBar.vue`（核心逻辑）**

```js
const visibleActions = computed(() => props.actions.filter(a => a.position !== 'batch'))
function onClick(a) {
  if (a.enabled === false) return
  if (a.confirm && !window.confirm(a.confirm)) return
  emit('action', a.id)
}
```

- `enabled === false` 时按钮渲染但禁用，`el-tooltip` 显示 `reason`；`enabled === undefined` 视为未求值，按钮禁用（fail-closed）。
- `style` 只映射到 `AppButton` 的 `variant`，不在组件内做业务判断。

**`visibilityEvaluator.js`**

```js
import { evaluateCondition } from '@/utils/safeExpression'

const reported = new Set()

export function evaluateVisible(expr, record, ctx = {}) {
  if (!expr || !expr.trim()) return true
  try {
    return Boolean(evaluateCondition(expr, record))
  } catch (e) {
    const key = `${ctx.objectType || ''}:${ctx.field || ''}:${expr}`
    if (!reported.has(key)) {
      reported.add(key)
      console.error('[visible_when] evaluation failed, field hidden (fail-closed)', key, e)
    }
    return false
  }
}
```

### 13.7 逐任务测试矩阵

| 任务 | 测试文件 | 必覆盖用例 |
|---|---|---|
| T13-1 | `meta/tests/api/test_meta_enum_batch.py` | batch 缺 `names` 返回空对象；未知 name 不报 500；`color` 非法值被过滤 |
| T13-5 | `meta/tests/api/test_ui_meta_api.py` | 形状完整；单块异常 → `partial:true` 且其余块正常；未登录/无权限按现有路由口径；旧 `form-view` 与新端点 `form` 逐字段一致 |
| T13-2/T13-3 | `src/composables/__tests__/useUiMeta.spec.js` | 单次请求；同 key 并发只发一次；`schema_version` 变化触发重取；接口失败 → `meta=null` 且 `error` 有值 |
| T13-4 | `src/components/meta/__tests__/EnumTag.spec.js` | `label`/`color` 正确；未知值显示原值；值为 `0`/`false` 不被当空；缓存命中不重复请求 |
| T13-6 | `src/components/meta/__tests__/ActionBar.spec.js` | `enabled:false` 禁用且 tooltip 显示 `reason`；`style` 映射；批量请求合并为一次；未求值默认禁用 |
| T13-7 | `src/utils/__tests__/visibilityEvaluator.spec.js` | 比较 / `IN` / `AND` / `OR` / 空表达式；非法表达式 → `false` 且只上报一次；`test_view_config_visibility.py` 覆盖 `col_span` 越界忽略、`tabs` 引用缺失丢弃 |
| T13-8 | `src/components/meta/__tests__/MetaForm.spec.js` | `col_span` 生效（1/2/4）；`visible_when=false` 不渲染；`readonly` 不渲染输入框；`tabs` 按 `section_keys` 分组 |
| T13-9 | 既有列表页 spec + `tests/e2e/` | 列表列/动作与旧端点一致；断开后端时动作全部禁用（fail-closed）；DOM 中无本地状态映射残留 |

执行入口：后端 `python d:\filework\test.py --single <path>`；前端 `npx vitest run <spec>`。禁止 `pytest`。

### 13.8 迁移与兼容

| 项 | 策略 |
|---|---|
| 端点双跑 | `ui-meta` 内部复用 `get_or_build_view_config`，旧 3 端点不删；前端切换由开关 `uiMeta.enabled`（默认 `false`）控制，灰度先开单页 |
| 前端回退 | `getUiMeta` 失败时回退旧 3 端点（仅迁移期），并打一次 warn；开关关闭后此回退代码一并删除 |
| YAML 兼容 | 新键缺省不落盘；`col_span` 越界/`tabs` 引用缺失均降级 warning，不阻断 `meta/reload` |
| 枚举映射 | 前端本地映射表按「先删调用、后删常量」两步走；未迁移枚举用 `label` 直传兜底，禁止保留第二份中文映射 |
| 旧端点弃用 | 加 `@deprecated` 注释（含替代端点）；连续 2 个版本无调用后再删除，删除前先 grep 全仓确认 |
| 数据库 | 本次不新增表；若后续把 `tabs` 持久化到 DB，必须走 `batch_save`，禁止直写 `meta/architecture.db` |
| 字段名 | 全链路 `snake_case`，后端不改名、前端不转换，避免同一语义两套 key |

### 13.9 回滚点与验收证据

| 任务 | 回滚方式 | 验收证据 |
|---|---|---|
| T13-5 | 关 `uiMeta.enabled` → 旧 3 端点；新 route 可独立下线 | `curl.exe` 取 `ui-meta` 样例 JSON + 与旧端点 diff 为空 |
| T13-1 | 枚举 batch 端点独立下线，前端回到单数端点 | 单测输出 + Network 面板请求数 |
| T13-2/T13-3 | 删除新增文件即可（无其他模块引用） | `useUiMeta.spec.js` 全绿 |
| T13-4 | 组件替换点逐个回退（按页面） | `grep -rn "statusTagType\|DEFAULT_.*LABEL" src/` 计数下降 |
| T13-6 | 恢复单条 `evaluateActions` | 断网用例：按钮全部禁用 |
| T13-7/T13-8 | 仅删 YAML 中的新键即回到旧行为，无需代码回滚 | `test_view_config_visibility.py` + 页面截图 |
| T13-9 | 换回 `metaService.getViewConfig` | 列表页回归 spec + E2E smoke |

每次任务结束必须留下：测试命令与结果、关键请求样例、删除的映射表条目数（grep 计数），作为「已下沉」的可验证证据。

### 13.10 页面接线落地状态与剩余细化方案（T13-10）

> 二次检查发现 T13 系列只交付了组件/服务，缺少真实页面消费方。本节记录已接线项与剩余项的可执行方案。

**已接线**

| 组件 | 落点 | 说明 |
|---|---|---|
| `EnumTag` | `src/views/EngineeringChangeListPage.vue` 状态列 | 删除 `statusLabelMap` / `statusTagMap` / `statusLabel()` / `statusTagType()`；label/color 全部由枚举接口下发，页面仅保留筛选项 |
| `DiffView` | `src/components/meta/DiffView.vue` | 只读差异预览（add/modify/remove + 字段变化），数据源 `engineeringChangeService.diffStructures`；供后续 diff 页收编或详情页内嵌使用 |

**剩余项细化方案（按依赖排序）**

1. **ActionBar 接线（依赖后端先行）**
   - 后端新增 `GET /api/v2/engineering-changes/<id>/actions`，返回 `[{ code, label, enabled, reason, required_permission, style }]`；状态机与权限判定复用 `engineering_change_service.py` + `permission_service.py`，前端不再保留 5 个 computed。
   - `ActionBar` 增加可选 `dataTest` 字段透传，保证既有 `[data-test="ec-action-*"]` 选择器不变；`enabled===false` 渲染禁用 + tooltip 显示 `reason`（fail-closed）。
   - 验收：后端 5 状态 × 4 角色矩阵用例（应允/应拒各一组）；前端 spec 由“断言 computed”改为“断言 actions 渲染”；无审批权账号在 `in_review` 单据上看不到“审批”。
   - 风险：后端若漏返回某个 action 会导致按钮消失，灰度期记录前后差异日志。

2. **DetailSection 接线（需先定目标容器）**
   - `src/components/common/DetailPage/DetailPage.vue` 已通过 `ObjectPageContent` 消费 ui-meta 的 `form.sections` 渲染详情分区，与新组件职责重叠。
   - 因此接线不是“替换某个页面的一段模板”，而是迁移 `ObjectPageContent` 的分区渲染到 `DetailSection`；需先建立选择器/视觉基线（2155 行共用组件，影响全部对象详情页）。
   - 在此之前不改 `EngineeringChangeDetailPage.vue`：该文件当前存在并行会话的未提交改动，改动会混入无关 diff。
   - 验收：`DetailSection.spec.js` + `DetailPage` 既有 spec 全绿；`grep -rn "el-descriptions" src/views` 计数下降。

3. **MetaForm 接线（缺少宿主页面）**
   - 工程变更创建流程当前走 diff 页（选来源/目标结构 → 勾选行 → 填标题/类型/生效日/原因），没有独立创建表单页；直接套 `MetaForm` 会改变交互。
   - 方案：新增 `EngineeringChangeCreatePage.vue`（路由 `/master-data/engineering-change/create`），表单区由 `MetaForm` 按 ui-meta `form` 渲染，提交仍调用既有 `createChange`。
   - 验收：`MetaForm.spec.js` + 新页面 spec；创建成功后详情页字段与表单一致。

4. **MetaReportPage 收编（待确认数据源）**
   - 若其列表数据来自 `meta` 视图配置，可优先改为 `useMetaList`（自动获得 ui-meta 列/动作/fail-closed）；若来自报表专用接口，则仅接入 `EnumTag`，不强行套 `useMetaList`。

**T13-9 E2E 冒烟与端口真源修复（已完成）**

| 项 | 内容 |
|---|---|
| 用例 | `e2e/smoke/ui-meta-enum.smoke.spec.js`：① `ui-meta` 契约（`success` / `schema_version` / `list` / `form` / `detail`）② `enums/batch` 的 `color` 白名单 ③ 工程变更列表首屏（`ec-table` / `ec-status-filter` / `ec-search` / `ec-pagination`） |
| 首次失败根因 | `e2e/helpers/auth.js` 将 `appUrl` 硬编码为 `http://localhost:3004`，与 `scripts/ports.json`（FE=3006）漂移 → `page.goto` `ERR_CONNECTION_REFUSED`；`scripts/service_manager.ps1` 的 `$vitePort` 同样回落 3004 |
| 修复 | `auth.js` / `service_manager.ps1` 统一读 `scripts/ports.json`（`APP_URL` / `VITE_DEV_PORT` 仍可覆盖），不再使用历史 3004 兜底 |
| 结果 | `npx playwright test e2e/smoke/ui-meta-enum.smoke.spec.js --project=smoke --retries=0` → 4 passed（含 setup）；`npx vitest run src/components/meta/__tests__ src/services/__tests__/metaEnumService.spec.js src/views/__tests__/EngineeringChangeListPage.spec.js` → 7 files / 46 tests passed |
| 注意 | 后端新增的 `ui-meta` 路由需重启 Waitress 才生效（不热加载）；重启前若 `ui-meta` 返回 404，属陈旧进程而非代码缺失 |

**执行约束**：以上 1-4 每项独立 worktree + 独立提交；`DetailPage.vue`、`EngineeringChangeDetailPage.vue` 改动前先确认无并行未提交改动；E2E 用 `scripts/service_manager.py` 起服务，禁止 `npm run dev`。

> 备注：本章只给实现方案与落点，不改任何业务代码；实际改动按 T13-x 独立提交，提交前需 PM 授权。