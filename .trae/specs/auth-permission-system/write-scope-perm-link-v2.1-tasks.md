# -*- coding: utf-8 -*-
# Tasks: WriteScopeInterceptor 写权限 × Dim Scope 联动 (v2.1)

## Phase 1: 准备 (0.5 天)

- [ ] Task 1.1: 创建 `meta/tests/test_write_scope_v2_1.py` 单元测试 (8 个场景)
- [ ] Task 1.2: 跑基线 `python d:\filework\test.py --single meta/tests/test_write_scope_e2e.py`
- [ ] Task 1.3: 备份 `meta/core/interceptors/write_scope_interceptor.py` 到 `.bak_before_v2_1`

## Phase 2: 代码改造 (0.5 天)

- [ ] Task 2.1: 实现 `_role_has_perm(role_id, target_perm, user_perm_codes)` helper 方法
  - 检查顺序: `'*'` → `'{obj}:{act}'` → `'{obj}:*'` → `'{obj}'`
- [ ] Task 2.2: 实现 `_get_user_perm_codes(context, user_id)` helper 方法
  - per-request cache: g.user_perm_codes
- [ ] Task 2.3: 修改 `_check_dim_scope` 函数签名增加 `target_perm_suffix='update'` 参数
- [ ] Task 2.4: 在 `_check_dim_scope` 顶部 (role 循环前) 调 `_get_user_perm_codes` 一次
- [ ] Task 2.5: 在每个 role 循环顶部加 perm 前置检查
  - 无 perm → continue + roles_checked 记录 skipped='missing_functional_perm'
  - 有 perm → 继续 dim scope 派生
- [ ] Task 2.6: 修改 `_check_target` 调用 `_check_dim_scope` 处传 `target_perm_suffix`
  - action_to_perm = {'crud_create':'create', 'crud_update':'update', 'crud_delete':'delete', 'associate':'update', 'dissociate':'delete'}
- [ ] Task 2.7: 模块顶部加 `WRITE_SCOPE_V2_1_PERM_CHECK` 环境变量读取
- [ ] Task 2.8: 修改 `_log_reject` 支持 `decision: 'perm_missing_skipped'` 字段

## Phase 3: 测试 (0.5 天)

- [ ] Task 3.1: 跑 `python d:\filework\test.py --single meta/tests/test_write_scope_v2_1.py` 全部 8 个用例
- [ ] Task 3.2: 跑 `python d:\filework\test.py --single meta/tests/test_write_scope_e2e.py` 无回归
- [ ] Task 3.3: 跑 `python d:\filework\test.py --single meta/tests/test_cross_domain_relation_perm.py` 无回归
- [ ] Task 3.4: 跑 `python d:\filework\test.py --failed` 全过
- [ ] Task 3.5: 跑 `python d:\filework\test.py --all --force` 全量回归

## Phase 4: 文档同步 (0.3 天)

- [ ] Task 4.1: 更新 `write-scope-interceptor-spec.md` 加入 FR-014~FR-016 引用本 spec
- [ ] Task 4.2: 更新 `cross-domain-relationship-permission/spec.md` Requirement 2 标注 "已由 write-scope-perm-link-v2.1 关闭"
- [ ] Task 4.3: 更新 `docs/auth/write-scope-interceptor.md` 加入 v2.1 章节
- [ ] Task 4.4: 在 `docs/auth/role-migration-guide.md` 加入 "无 perm 角色" 迁移说明

## 总计

**预计 1.8 天完成 (Phase 1-4)**