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

