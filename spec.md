# Spec: 审计日志 P1 + P2 修复

> 2026-06-20 | Author: agent-audit-fix-p1p2 | Status: ✅ COMPLETED

## 背景

近 2 天审计日志业务视图分析发现两个 P1/P2 问题：
- **P1**: 12 条历史 user_name 残留 "Admin (admin)" 格式
- **P2**: transaction_id 覆盖率仅 7.1% (业务人员无法追踪事务边界)

## modified_files

- meta/api/_audit_helper.py
- meta/services/action_handlers.py
- meta/services/audit_interceptor.py
- meta/tests/test_audit_p1_p2_fix.py

## new_files

(无新增)

## deleted_files

(无删除)

## forbidden_files

(无)

## 完成标准

- [x] [P1] user_name LIKE '%(%' = 0
- [x] [P2-2d] tx_id 覆盖率 >= 95%
- [x] [P2-all] tx_id 全表覆盖率 >= 90%
- [x] E2E: C.1 (tx_id 共享) + D.2 (user_name 规范化) 生效
- [x] 数据修复: 12 条 P1 + 4914 条 P2 backfill

## 验证

```
verify_audit_fix.py → Overall: PASS
  [P1] user_name 残留 = 0:              PASS
  [P2-2d] tx_id 覆盖率 >= 95%:         PASS (100.0%)
  [P2-all] tx_id 全表覆盖率 >= 90%:    PASS (100.0%)

_e2e_c1_d2.py → PASS
  [OK] C.1 生效: 所有字段自动归到同一事务
  [OK] D.2 生效: user_name 是 'Admin' (规范化)
```

## 风险评估

- **Risk Level**: low (审计日志规范化, 不影响业务逻辑)
- **回滚方案**: git revert <commit> + re-run backfill script (idempotent)
- **PM 授权**: 主工作树 commit, 当时仅剩 main worktree (其他已合并)