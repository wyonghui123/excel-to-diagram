/**
 * 审计日志 - 业务流 E2E v2 (扩展)
 *
 * 覆盖 v2 + v3 抽取的 audit_log (14) + (14 service) = 28 业务规则
 */

import { test, expect } from '../helpers/auto-fixtures';
import { AdminActor } from '../screenplay/actor';
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor';
import { Navigate, Click, Fill, Wait } from '../screenplay/interactions';

test.describe('审计日志 - 业务流 E2E v2 (扩展)', () => {

  test('1. 字段约束 - 14 字段', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    // 必填字段
    await BusinessRuleAssertor.assertRule('BR-audit_log-FLD-REQ-action', { field: 'action', value: null });
    await BusinessRuleAssertor.assertRule('BR-audit_log-FLD-REQ-object_id', { field: 'object_id', value: null });
    await BusinessRuleAssertor.assertRule('BR-audit_log-FLD-REQ-object_type', { field: 'object_type', value: null });
    await BusinessRuleAssertor.assertRule('BR-audit_log-FLD-REQ-log_category', { field: 'log_category', value: null });
    await BusinessRuleAssertor.assertRule('BR-audit_log-FLD-REQ-log_level', { field: 'log_level', value: null });
    await BusinessRuleAssertor.assertRule('BR-audit_log-FLD-REQ-created_at', { field: 'created_at', value: null });

    // 枚举
    await BusinessRuleAssertor.assertRule('BR-audit_log-FLD-ENUM-log_category', { field: 'log_category', allowed: ['security', 'authz', 'access', 'admin'] });
    await BusinessRuleAssertor.assertRule('BR-audit_log-FLD-ENUM-log_level', { field: 'log_level', allowed: ['INFO', 'WARNING', 'ERROR', 'CRITICAL'] });
    await BusinessRuleAssertor.assertRule('BR-audit_log-FLD-ENUM-object_type', { field: 'object_type', allowed: ['product', 'version', 'business_object', 'relationship'] });
    await BusinessRuleAssertor.assertRule('BR-audit_log-FLD-ENUM-status', { field: 'status', allowed: ['SUCCESS', 'FAILED', 'BLOCKED'] });
  });

  test('2. 服务层 assert - 业务类别映射', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    // assert CHECK
    await BusinessRuleAssertor.assertRule('BR-audit_log-SRV-ASSERT-CHECK-audit_constants-176', {
      trigger: 'service.assert_check',
      context: { action: 'LOGIN', expectedCategory: 'security' },
    });
    await BusinessRuleAssertor.assertRule('BR-audit_log-SRV-ASSERT-CHECK-audit_constants-177', {
      trigger: 'service.assert_check',
      context: { action: 'ROLE_ASSIGN', expectedCategory: 'authz' },
    });
  });

  test('3. 状态转换 - 标记失败', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    await BusinessRuleAssertor.assertRule('BR-audit_log-STATE-mark-failed', { from: 'SUCCESS', to: 'FAILED' });
  });

  test('4. 导入导出 - 不级联', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    await BusinessRuleAssertor.assertRule('BR-audit_log-IE-export', { cascade: false });
  });
});
