# Tasks：元数据驱动 UI — M0 地基

- 来源：`docs/specs/spec-meta-driven-ui-2026-11-16.md` §4.7（decision-complete）
- 原则：只加地基，不改任何现有页面行为；不 commit。
- 测试唯一入口：`python d:\filework\test.py --file <path> --force`

---

## T1 模型字段

- 文件：`meta/core/models_ui_config.py`、`meta/core/models_annotations.py`
- 改动：`UIListViewColumn` 增 `visible_when/roles`；`UIViewConfig` 增 `version/variants`；`UIAnnotation` 增 `readonly_when/roles`
- 完成：导入无循环依赖；默认值不改变现有序列化

## T2 YAML 加载透传

- 文件：`meta/core/yaml_loader.py`
- 函数：`parse_ui_list_view_column`、`parse_ui_annotation`、`parse_ui_view_config`
- 改动：读取可选新键；`variants` 非 dict 时忽略 + warning；不新增抛错路径（D4）
- 完成：现有 YAML 加载结果除新键默认值外完全一致

## T3 变体合并纯函数

- 文件：`meta/core/ui_config/variant_merge.py`（新建）
- 内容：`merge_patch`（深合并 + 稳定键数组 + `_remove` + 禁嵌套 variants）、`apply_variant`
- 完成：新增单测覆盖数组覆盖/追加/删除/嵌套 variants 拒绝

## T4 服务层接线

- 文件：`meta/services/view_config_service.py`
- 改动：`get_view_config` 支持 variants、失败回退 base；`get_available_views` 追加变体名
- 完成：无 variants 对象行为与现状一致；缓存键含 view

## T5 ui-meta 端点

- 文件：`meta/api/meta_api.py`
- 改动：`?view=`、`meta:{warnings,effective_view,schema_version}`、`?explain=1` → `meta.sources`；列/动作/表单/策略透传与降级 warning
- 完成：未知 view 回落 default + warning；`partial` 语义不变

## T6 lint R-UI-01..08

- 文件：`meta/tools/lint_metamodel.py`
- 改动：`lint_ui_config()` + `--ui-config` + 纳入 `--all`/默认
- 完成：现有 3 个资源页零违规；每规则各有正反用例

## T7 前端条件函数

- 文件：`src/services/metaResourceService.js`
- 内容：`evalCondition/isVisible/isActionVisible/isFieldReadonly/mergeFieldPolicies/setCurrentRoles/warnOnce`；`toFormControls` 接 `model/policies`
- 完成：未知条件形式返回 true；未注入角色不隐藏

## T8 前端接线

- 文件：`metaTransformService.js`、`useMetaList.js`、`metaService.js`、`MetaListPage.vue`、`MetaResourcePage.vue`
- 改动：透传新键、列/动作过滤、`getUiMeta({view})`、`viewName`/`view` 可选 prop
- 完成：不传 view / 无 `visible_when` 时行为与现状一致

## T9 测试

- 新增：`meta/tests/api/test_ui_meta_variants.py`、`test_ui_meta_conditions.py`、`test_lint_ui_config.py`、`src/services/__tests__/metaResourceService.conditions.spec.js`
- 扩展：`meta/tests/api/test_ui_meta_data_source.py`（不改既有断言）
- 完成：全部通过（`test.py --file ... --force`）

## T10 验证与汇报

- 顺序：后端测试 → `lint_metamodel.py --ui-config` → `--all` → eslint → `vite build` → Playwright 集成三页冒烟
- 判据：三页列/筛选/枚举/动作与改动前一致；无 console error
- 交付：汇报结果与差异，不 commit

---

## 阻塞/回滚

- 任一验证失败先修，不跳过；lint 与现有 YAML 冲突时只做行为等价修正
- 回滚：前端停止消费新键 + 后端无声明时输出不变，无需数据迁移

---

# Tasks：M1 audit_log 收敛

- 来源：`docs/specs/spec-meta-driven-ui-2026-11-16.md` §4.8（decision-complete）
- 原则：页面功能等价；不改后端端点；不 commit。

## [x] T11 声明式 fetch 基础设施

- 文件：`src/services/metaResourceService.js`
- 改动：导出 `resolveRequest(url, paramsMap)`（v1/v2 命名空间路由）；`applyOrderingBridge(params, paramsMap)`；`buildFetcher` 改用二者并在 total 取不到时回退 `result.total`；`resolveActionUrl/runAction` 改用 `resolveRequest`
- 完成：现有三页 URL/参数/行为零变化

## [x] T12 httpClient 透传 total

- 文件：`src/utils/httpClient.js`
- 改动：成功分支 `if (body.total !== undefined) result.total = body.total`
- 完成：仅新增可选字段，不覆盖已有键

## [x] T13 useMetaList 消费 data_source

- 文件：`src/composables/useMetaList.js`
- 改动：`loadList` 中 `config.fetcher || (metaConfig.list.data_source ? buildFetcher(...) : null)`
- 完成：显式 fetcher 优先；无 data_source 对象仍走 `boService.query`

## [x] T14 YAML 收敛

- 文件：`meta/schemas/audit_log.yaml`
- 改动：`ui_view_config.version: 2`；新增 `list.data_source`（§4.8.3）；删除 `log_category/log_level` 两列；不声明行级 `detail`（A10）
- 完成：`items_path: data`、`total_path: total`；列字段全部 ∈ schema

## [x] T15 死代码清理

- 删除：`src/views/SystemManagement/meta/auditLogMeta.js`、`src/views/SystemManagement/meta/__tests__/auditLogMeta.spec.js`
- 页面 `AuditLogManagement.vue` 不改（行点击抽屉保持现状）
- 完成：`grep auditLogMeta` 仅剩文档引用

## [x] T16 lint 白名单

- 文件：`meta/tools/lint_metamodel.py`
- 改动：`UI_PARAMS_ALLOWED` 追加 `action/user_name/created_at_start/created_at_end/sort_field/sort_direction`
- 完成：`--ui-config` 零违规，R-UI-03 仍硬校验

## [x] T17 测试与验证

- 新增：`meta/tests/api/test_ui_meta_audit_log.py`、`src/services/__tests__/metaResourceService.dataSource.spec.js`
- 顺序：新增后端 → 既有后端 → `lint --ui-config` → vitest → eslint 改动文件 → `vite build` → Playwright 审计页冒烟
- 完成：§4.8.4 全绿；汇报结果，不 commit

---

# Tasks：M2 task_run 收敛

- 来源：`docs/specs/spec-meta-driven-ui-2026-11-16.md` §4.9（decision-complete）
- 范围修正：`handling_unit` / `print_template` 本里程碑不动（§4.9.3）
- 原则：页面行为等价；唯一预期差异 = 行级动作由「隐藏」变「置灰」
- 测试唯一入口：`python d:\filework\test.py --file <path> --force`

## [x] T18 task_run YAML 声明

- 文件：`meta/schemas/task_run.yaml`
- 改动：`ui_view_config.list` 追加 `data_source`（§4.9.4-A 原文）与 `actions`（cancel `in: [pending, claimed, running]`、retry `in: [failed, dead, cancelled]`，`refresh: true`）；列/筛选/详情不动
- 完成：YAML 可解析；占位符 `{row.id}`（`run_id` 为响应别名，`{row.id}` 才过 R-UI-05）；动作顺序 cancel → retry

## [x] T19 lint 白名单

- 文件：`meta/tools/lint_metamodel.py`
- 改动：`UI_PARAMS_ALLOWED` 追加 `job_code/status/source/from/to`
- 完成：`lint_metamodel.py --ui-config` 零违规（实测退出码 0）

## [x] T20 buildFetcher 透传 meta

- 文件：`src/services/metaResourceService.js`
- 改动：仅当响应含 `result.data.meta` 时在 `data` 内附加 `meta` 键
- 完成：既有 dataSource 断言零改动通过（11 passed）

## [x] T21 TaskRuns 接线

- 文件：`src/views/TaskCenter/TaskRuns.vue`
- 改动：按 §4.9.4-E 六条执行（data_source fetcher + 降级 fetchRuns、rowActions 渲染、`run_id → id` 归一后 executeRowAction、filtersMeta 改取 `data.meta.filters`）
- 完成：`retryRun/cancelRun` 导入已删；`onCancel/onRetry/readableError/runAction` 已移除；FilterBar/轮询/`?run=` 深链/详情抽屉保留；eslint 与 `vite build` 通过

## [x] T22 测试

- 新增：`meta/tests/api/test_ui_meta_task_run.py`（5 passed）
- 扩展：`src/services/__tests__/metaResourceService.dataSource.spec.js` 新增 meta 透传/无 meta 两用例
- 完成：两条用例独立通过

## [x] T23 验证与汇报

- 顺序：§4.9.5 的 1–6 → 冒烟 7
- 结果：新增后端 5 passed、既有 data_source 后端通过、lint 0 违规、vitest 11 passed、eslint 通过、`vite build` 成功、Playwright 冒烟通过（ui-meta 契约 + 列表首屏 data_source 请求 + 无 console error）
- 交付：汇报差异，提交前征询用户

---

# Tasks：M3 列表个性化

- 来源：`docs/specs/spec-meta-driven-ui-2026-11-16.md` §4.10（decision-complete）
- 范围：仅 §4.5；§4.6 explain 已由 M0 覆盖，不扩后端/YAML

## [x] T24 useListPreferences

- 文件：`src/composables/useListPreferences.js`（新建）
- 内容：`buildStorageKey/createDefaultPreferences/normalizePreferences/applyColumnOrder/filterHiddenColumns/resolvePageSize/useListPreferences`
- 完成：纯函数无 Vue 依赖可单测；composable 仅 `page` 模式读写；仓储异常静默降级

## [x] T25 MetaListPage 接线

- 文件：`src/components/common/MetaListPage/MetaListPage.vue`
- 改动：`preferredColumns` 替换 `tableColumns/cardPrimaryColumn/cardColumns/hasBusinessKeyColumn` 的列源；`getColumnWidth` 优先保存宽度；`@header-dragend` 写回；storageKey watch 恢复 pageSize/filters 并补一次 `loadList`；pageSize/filters 变化持久化
- 完成：无存量偏好时行为与现状逐项一致（列集合/宽度/首屏请求数不变）

## [x] T26 列设置入口

- 文件：`src/components/common/MetaListPage/MetaListPage.vue`
- 改动：`isPageMode && !hideToolbar` 时工具栏右侧新增「列设置」popover（显示/隐藏、上下移序、恢复默认）
- 完成：embedded/dialog 不渲染；隐藏最后一列被阻止；恢复默认清空 order/hidden/width

## [x] T27 单测

- 文件：`src/composables/__tests__/useListPreferences.spec.js`（新建）
- 完成：§4.10.2-C 全部用例通过（10 tests）

## [x] T28 验证与汇报

- 顺序：§4.10.4 的 1–3 → 冒烟 4
- 结果：vitest 10 passed；MetaListPage 既有回归 92 passed；eslint 新增文件 0 error（MetaListPage 仅存量 error/warn，已用 HEAD 基线比对）；`vite build` 成功；Playwright smoke 4 passed（隐藏列刷新后保持 / 恢复默认 / embedded 无入口）
- 交付：汇报结果，提交前征询用户



