# T-2026-07-05-001 & T-2026-07-05-002

## T-001: ImportDialog 最小化按钮风格统一

### 1. 任务描述（一句话）

---

### 2. 改动文件白名单 (T-001)

```yaml
modified_files:
  # 冲突解决 (3)
  - meta/schemas/product.yaml
  - meta/schemas/version.yaml
  - meta/services/import_export_service.py
  # 部署文档固化 (2026-06-29 Python 兼容性扫描)
  - docs/DEPLOYMENT_STANDARDS.md
  - docs/SOP-USER-DEPLOYMENT.md
  # 部署脚本 (2026-06-30 PowerShell 打包脚本)
  - scripts/build-deploy-package.ps1
  # 上轮 worktree 遗留改动
  - src/services/relationClassifier.js
  # Phase 1 性能优化 - smChildCount 引用缓存
  - src/components/common/RelationScopeTree/RelationScopeTree.vue
  # [FIX 2026-07-04 deploy agent] 一键 6 类 BUG 健康检查 + MANIFEST 完整化
  - .gitignore
  - tools/deploy.sh
  - tools/status.sh
  - tools/restart.sh
  - tools/diagnose.sh
  - tools/precheck.sh
  - tools/lib/common.sh
  - tools/rebuild_zip.py
  - tools/rebuild_bundle.ps1
  - deploy_bundle/deploy.sh
  - deploy_bundle/status.sh
  - deploy_bundle/restart.sh
  - deploy_bundle/diagnose.sh
  - deploy_bundle/precheck.sh
  - deploy_bundle/lib/common.sh
  - deploy_bundle/README.txt
  - tests/test_deploy_e2e.py
  # 领域过滤器 originalId 碰撞修复 (2026-06-30)
  - src/services/hierarchyService.js
  # FIX 2026-07-02: hierarchy filter 命名空间隔离 + meta_obj NameError
  - src/composables/useMultiObjectPage.js
  - vite.config.js
  - waitress_server.py
  # Phase 1 性能优化 - refreshAll 并行化 (串行 await → Promise.all)
  - src/composables/useRefreshCoordinator.js
  # 自动合并 (9)
  - meta/core/action_executor.py
  - meta/core/interceptors/cascade_interceptor.py
  - meta/core/interceptors/data_permission_interceptor.py
  - meta/core/interceptors/owner_chain_interceptor.py
  - meta/core/interceptors/persistence_interceptor.py
  - meta/core/interceptors/write_scope_interceptor.py
  - meta/services/condition_permission_service.py
  - meta/services/manage_service.py
  - scripts/lint_msg_punct.py
  - e2e/screenplay/questions/BusinessRuleAssertor.js
  - src/components/bo/ActionExecutor.vue
  - src/components/common/ObjectPage/AssociationSection.vue
  # [FIX BUG-V044 2026-07-04 dev agent] importDataAsync 路径未清 list cache, 关闭弹窗后 list 显示旧数据
  - src/components/common/ImportDialog/ImportDialog.vue

new_files:
  # 部署脚本 (2026-06-30 one-shot deploy + rollback)
  - docs/deploy-full-v20260630_001.sh
  - docs/deploy-rollback-v20260630_001.sh
  - docs/DEPLOY-MANUAL-20260630_001.md
  - docs/DEPLOY-CHEATSHEET-20260630_001.txt
  # 部署 bundle 说明 (2026-06-30)
  - README_BUNDLE.txt
  # [FIX 2026-07-04 deploy agent] 一键 6 类 BUG 健康检查
  - tools/lib/check_deploy_health.sh
  - deploy_bundle/lib/check_deploy_health.sh
  - deploy_bundle/smoke_test.sh
  - deploy_bundle/deploy-v20260703_005.zip
  - deploy_bundle/deploy-v20260703_006.zip
  - tests/check_health_local.py
  - tests/test_manifest_alignment.py
  - tests/test_export_no_annotation.py
  # IE 智能体的 e2e 测试 (21)
  - e2e/business-flow/bmrd-rule-validation.spec.js
  - e2e/business-flow/bug-v010-owner-trace.spec.js
  - e2e/business-flow/bug-v011-cascade-delete.spec.js
  - e2e/business-flow/bug-v012-transitive-cascade.spec.js
  - e2e/business-flow/bug-v013-owner-rls-exception.spec.js
  - e2e/business-flow/bug-v014-investigation.spec.js
  - e2e/business-flow/cascade-side-effect.spec.js
  - e2e/business-flow/composite-business-rules.spec.js
  - e2e/business-flow/deep-cascade.spec.js
  - e2e/business-flow/dimension-permission-test888-333.spec.js
  - e2e/business-flow/import-export-permissions.spec.js
  - e2e/business-flow/import-template.spec.js
  - e2e/business-flow/import-validation.spec.js
  - e2e/business-flow/key-template.spec.js
  - e2e/business-flow/owner-visibility-permission.spec.js
  - e2e/business-flow/parent-child-deletability.spec.js
  - e2e/business-flow/parent-child-transaction.business.spec.js
  - e2e/business-flow/parent-child-transaction.spec.js
  - e2e/business-flow/parent-child-transaction.technical.spec.js
  - e2e/business-flow/pm-boundary.spec.js
  - e2e/business-flow/update-delete-permission.spec.js
  # IE 智能体的测试生成器 (16)
  - scripts/generate-bmrd-rule-validation.js
  - scripts/generate-bug-v010-regression.js
  - scripts/generate-bug-v011-regression.js
  - scripts/generate-bug-v012-regression.js
  - scripts/generate-bug-v013-regression.js
  - scripts/generate-bug-v014-investigation.js
  - scripts/generate-cascade-side-effect.js
  - scripts/generate-cascade-tests.js
  - scripts/generate-composite-business-rules.js
  - scripts/generate-deletability.js
  - scripts/generate-excel-format-tests.js
  - scripts/generate-import-template.js
  - scripts/generate-import-validation.js
  - scripts/generate-key-template.js
  - scripts/generate-owner-visibility-permission.js
  - scripts/generate-parent-child-transaction.js
  - scripts/generate-permission-matrix.js
  - scripts/generate-pm-boundary.js
  - scripts/generate-test888-333-permission.js
  - scripts/generate-update-delete-permission.js
  # SOP 端到端演练器 (2026-07-03)
  - tools/e2e_sop_drill.py
  - tools/_test_v4_startup.py
  # 远端堡垒机一键部署脚本 (2026-07-03)
  - tools/deploy.sh
  - tools/rollback.sh
  - tools/lib/common.sh
  - tools/unified_server.py
  - tools/serve_frontend.py
  - tools/test_deploy_generalized.py
  # 部署前 precheck + 部署后 smoke test (2026-07-03)
  - tools/precheck.sh
  - tools/smoke_test.sh
  - tools/test_precheck_smoke.py
  # 基础设施 SOP 文档 + 自动化 (2026-07-03)
  - README.md
  - DEPLOYMENT.md
  - TROUBLESHOOTING.md
  - tools/rebuild_bundle.py
  # 失败时一键诊断 (2026-07-03)
  - tools/diagnose.sh
  - tools/test_diagnose.py
  # IE 其他新文件 (2)
  - meta/tests/test_excel_format.py
  - scripts/test_ie_assertor.js
  # T-002 E2E 真实流程验证 (2026-07-05, 验证 fetchProducts fix 生效)
  - test_t002_v9_real.py

deleted_files: []
```

### 5. 完成标准 (T-001)

```yaml
acceptance_criteria:
  - 50 个改动文件在白名单内
  - 没有改动黑名单文件
  - 0 conflict markers 残留
  - Python 语法 OK (3 个文件 + 5 个 interceptor)
  - YAML 语法 OK (product + version)
  - ImportExportService._build_permission_filter 完整
  - V010-V014 修复存在
  - commit message 含铁律声明
```

### 6. 风险评估 (T-001)

```yaml
risk_level: low
```

### 7. 工作日志 (T-001)

```yaml
decisions:
  - 2026-07-05 03:50: 决定去掉 link + type="primary"，
    让"最小化"按钮回归普通 el-button 样式与"关闭"按钮对齐。
    依据: YON_EP_GUIDE.md 规定 Link 按钮仅用于表格操作列 (详情/编辑/删除)，
    弹窗底部按钮应为填充样式。
```

---

## T-002: 切换产品/版本下拉不显示新创建的数据

### 1. 任务描述

修复 admin 创建新产品/版本后，架构数据管理页面"切换产品/版本"弹窗下拉中找不到新数据。

### 2. 根因

`useVersionContext.js` 是单例, `products`/`versions` 仅在 `init()` 首次调用时 fetch 一次。GlobalToolbar 下拉/弹窗都直接读单例, 外部数据变更不感知。

### 3. 改动白名单

```yaml
modified_files:
  - src/components/common/GlobalToolbar/GlobalToolbar.vue
```

### 4. 修复

`handleDropdownCommand` 改 async, 打开弹窗前:
- 切换产品 → `await fetchProducts()`
- 切换版本 → `await fetchVersions(selectedProductId.value)`

### 5. 完成标准

```yaml
acceptance_criteria:
  - [x] handleDropdownCommand async 化
  - [x] changeProduct 分支 await fetchProducts()
  - [x] changeVersion 分支 await fetchVersions()
  - [x] vite build 通过
  - [x] commit message 含铁律声明
```

### 6. 风险

```yaml
risk_level: low
mitigation:
  - 回滚: revert commit
  - 失败: dialog 用旧数据打开, 不崩
```

### 7. 工作日志

```yaml
decisions:
  - 选择"打开弹窗时刷新"而非 TTL/路由监听, 触发点最精确
insights:
  - 紧凑下拉 (line 23-60) 同样读单例, 暂不修以避免无谓 API 请求
```

---

## T-003: 导入进度显示 0/5 (行级回调覆盖类型级)

### 1. 任务描述

多对象类型导入时, 第 5 个类型 (业务对象) 进度显示 "正在导入 业务对象 (0/5)" 但实际 4 个类型已导入完成.

### 2. 根因

`meta/services/import_export_service.py` L6317-6329 `_import_sheet` 的行级进度回调**硬编码**了:
```python
'total_types': 0,
'current_index': 0,
```

外层主循环 (L5041-5064) 计算的真实 `current_index` (1-5) **没有传**进 `_import_sheet`. 当后端切到行级进度时, 回调中的 0/0 覆盖了前端缓存的 4/5, 导致显示 (0/5).

### 3. 改动 (Frontend 防御性修复)

```yaml
modified_files:
  - src/components/common/ImportDialog/ImportDialog.vue
```

在 `pollImportProgress` 中, 收到 `total_types === 0` 的回调时**不更新** `currentIndex` (这是行级进度信号, 不是类型级).

```js
if (data.total_types && data.total_types > 0) {
  currentIndex.value = data.current_index || 0
}
```

### 4. 可选的后端彻底修复 (待用户决定)

在 `_import_sheet` 接收 `current_index` 和 `total_types` 参数, 行级回调也使用真实值 (见 backend L5069 + L6325-6326).

### 5. 完成标准

```yaml
acceptance_criteria:
  - [x] pollImportProgress 中加 total_types > 0 守卫
  - [x] vite build 通过
  - [x] commit message 含铁律声明
```

### 6. 风险

```yaml
risk_level: low
mitigation:
  - 回滚: revert commit
```

### 7. 工作日志

```yaml
decisions:
  - 选择前端防御性修复, 不动后端 (历史教训: export_import_api.py 误改被纠正)
  - 前端守卫语义清晰: total_types=0 即行级进度
insights:
  - 59% 与 4/5 (80%) 不符, 是后端进度计算策略 (基于行而非类型), 不在 T-003 范围
```
