---
# Integration Task Spec - RBAC + IE merge

> **Task ID**: T-INTEGRATION-RBAC-IE-2026-06-26
> **协调者**: coordinator agent
> **Worktree**: d:/filework/integration-worktree/
> **风险等级**: medium
> **目标**: 把 IE 智能体的 23 个 commits (feat/ie-model-driven) 整合到 RBAC 智能体的分支

---

## 1. 任务描述

> 协调者分析显示 IE 智能体的 V010-V014 修复对 RBAC 智能体不可替代, 需安全整合
> 验证: 整合后 0 conflict markers, 0 syntax errors, 5 个核心修复保留

---

## 2. 改动文件白名单 (50 个文件)

```yaml
modified_files:
  # 冲突解决 (3)
  - meta/schemas/product.yaml
  - meta/schemas/version.yaml
  - meta/services/import_export_service.py
  # 部署文档固化 (2026-06-29 Python 兼容性扫描)
  - docs/DEPLOYMENT_STANDARDS.md
  - docs/SOP-USER-DEPLOYMENT.md
  # 上轮 worktree 遗留改动
  - src/services/relationClassifier.js
  # Phase 1 性能优化 - smChildCount 引用缓存
  - src/components/common/RelationScopeTree/RelationScopeTree.vue
  # Phase 1 性能优化 - refreshAll 并行化 (串行 await → Promise.all)
  - src/composables/useRefreshCoordinator.js
  # Bug fix 2026-06-30 - enum_types.mutability 字段错值 (fully_editable → fullEditable)
  - meta/scripts/migrate_enums.py
  - meta/core/enums/secure_admin.py
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

new_files:
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
  # IE 其他新文件 (2)
  - meta/tests/test_excel_format.py
  - scripts/test_ie_assertor.js
  # Bug fix 2026-06-30 - enum_types.mutability 一次性 DB 修复脚本
  - fix_enum_mutability_db.py

deleted_files: []
```

---

## 3. 禁止改文件黑名单

```yaml
forbidden_files:
  - .agent-status.json
  - service_manager.ps1
  - scripts/agent_bootstrap.ps1
  - .git/hooks/pre-commit
  - healthy-baseline-2026-06-17
  - multi-agent-coordination.md
  - meta/server.py
  - vite.config.js
  - stats.html
```

---

## 4. 依赖关系

```yaml
depends_on:
  - branch: fix/export-import-rbac (HEAD d85c61b)
  - branch: feat/ie-model-driven (HEAD ff79092)
  - merge-base: 8d6ebeb
```

---

## 5. 完成标准

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

---

## 6. 风险评估

```yaml
risk_level: medium

reason: |
  - 3 个手动解决冲突, 选 IE 注释 + HEAD 逻辑
  - 11 处 mojibake 是 IE 智能体原数据问题
  - 自动合并文件未人工审查
  - 整合 worktree 隔离, 主分支不受影响

mitigation:
  - 回滚: git reset --hard refs/backup/integration-pre-merge-2026-06-26
  - 测试: IE 自己的 21 个 e2e spec
  - 隔离: integration-worktree 独立
  - 验证: 8 项验证 (markers / YAML / Python / function)
```

---

## 7. 工作日志

```yaml
decisions:
  - 协调者分析 3 个活跃分支, 决定整合 RBAC + IE
  - 创建 integration-worktree
  - merge --no-commit 发现 3 个冲突, 全部解决
  - 8 项验证全部 PASS
  - pre-commit 拦截 GBK mojibake, 修复 11 处
  - pre-commit 拦截 spec.md 白名单, 更新本 spec

blockers: []

insights:
  - RBAC 智能体已包含 IE 的 V010 修复 (context.extra dict) - 自动合并
  - IE 的 V014 是 no-op 调查 - 无代码改动
  - RBAC 的 V013 ≠ IE 的 V013 - 不同 BUG
```

---

## 8. 完成后 Checklist

- [x] spec.md 已填写完整
- [x] 所有 acceptance_criteria 已勾选
- [ ] commit 成功推送
- [ ] 通知用户 ready for review T-INTEGRATION-RBAC-IE-2026-06-26
