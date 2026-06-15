/**
 * 变更订阅 - 业务流 E2E v2
 */

import { test, expect } from '../helpers/auto-fixtures';
import { AdminActor } from '../screenplay/actor';
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor';
import { Navigate, Click, Wait } from '../screenplay/interactions';

test.describe('变更订阅 - 业务流 E2E v2', () => {

  test('字段约束', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-change_subscription-FLD-REQ-subscriber_id', { field: 'subscriber_id', value: null });
    await BusinessRuleAssertor.assertRule('BR-change_subscription-FLD-REQ-object_type', { field: 'object_type', value: null });
  });

  test('审计 - CRUD', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-change_subscription-AUDIT-create', { operation: 'create', auditLog: true });
    await BusinessRuleAssertor.assertRule('BR-change_subscription-AUDIT-update', { operation: 'update', auditLog: true });
    await BusinessRuleAssertor.assertRule('BR-change_subscription-AUDIT-delete', { operation: 'delete', auditLog: true });
  });
});
