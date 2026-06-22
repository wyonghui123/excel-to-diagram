# -*- coding: utf-8 -*-
# Checklist: WriteScopeInterceptor 写权限 × Dim Scope 联动 (v2.1)

> 实施完成前逐项勾选 ✅

## Phase 1: 准备阶段

- [ ] **1.1** 创建 `meta/tests/test_write_scope_v2_1.py` 单元测试 (8 个场景)
  - [ ] test_v2_1_role_perm_missing_denies_write
  - [ ] test_v2_1_role_perm_present_allows_dim_scope_match
  - [ ] test_v2_1_admin_wildcard_bypasses_perm_check
  - [ ] test_v2_1_owner_chain_priority_over_perm_check
  - [ ] test_v2_1_target_perm_suffix_by_action
  - [ ] test_v2_1_wildcard_perm_patterns
  - [ ] test_v2_1_legacy_v118_compatibility
  - [ ] test_v2_1_audit_log_records_perm_skip
- [ ] **1.2** 跑 `python d:\filework\test.py --single meta/tests/test_write_scope_e2e.py` 建立基线
- [ ] **1.3** 备份现有 `meta/core/interceptors/write_scope_interceptor.py` 到 `.bak_before_v2_1`

## Phase 2: 代码改造

- [ ] **2.1** 实现 `_role_has_perm(role_id, target_perm, user_perm_codes)` helper
- [ ] **2.2** 实现 `_get_user_perm_codes(context, user_id)` helper (含 g.user_perm_codes 缓存)
- [ ] **2.3** 修改 `_check_dim_scope` 增加 `target_perm_suffix` 参数
- [ ] **2.4** 在 `_check_dim_scope` 顶部增加 perm 前置检查逻辑
- [ ] **2.5** 修改 `_check_target` 调用处根据 `context.action` 传 `target_perm_suffix`
- [ ] **2.6** 增加 `WRITE_SCOPE_V2_1_PERM_CHECK` 环境变量读取 (默认 false)
- [ ] **2.7** 修改 `_log_reject` 支持 `decision: 'perm_missing_skipped'` 新增字段

## Phase 3: 验证

- [ ] **3.1** 跑 `python d:\filework\test.py --single meta/tests/test_write_scope_v2_1.py` - 8 个用例全过
- [ ] **3.2** 跑 `python d:\filework\test.py --failed` - 无预期外失败
- [ ] **3.3** 跑 `python d:\filework\test.py --single meta/tests/test_write_scope_e2e.py` - 现有 E2E 不回归
- [ ] **3.4** 跑 `python d:\filework\test.py --single meta/tests/test_cross_domain_relation_perm.py` - 跨域 spec 不回归
- [ ] **3.5** 验证 TEST333 实测: 编辑 domain=706 SM → 403, 编辑 domain=703 SM → 200

## Phase 4: 文档同步

- [ ] **4.1** 更新 `write-scope-interceptor-spec.md` 加入 FR-014~FR-016 引用本 spec
- [ ] **4.2** 更新 `cross-domain-relationship-permission/spec.md` Requirement 2 标注 "已由 write-scope-perm-link-v2.1 关闭"
- [ ] **4.3** 更新 `docs/auth/write-scope-interceptor.md` 加入 v2.1 章节
- [ ] **4.4** 在 `docs/auth/role-migration-guide.md` 加入 "无 perm 角色" 迁移说明

## 完成判定

- [ ] 所有 Phase 1-4 勾选
- [ ] 8 个新单元测试通过
- [ ] 现有 write_scope_e2e + cross_domain_relation_perm 测试通过
- [ ] TEST333 实测符合预期 (越权拒绝, 同域通过)
- [ ] 无新增调试日志, 无 # [WIP] 标记残留