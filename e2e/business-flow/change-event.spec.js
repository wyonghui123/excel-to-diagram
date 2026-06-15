/**
 * 变更事件 - 业务流 E2E v2
 */

import { test, expect } from '../helpers/auto-fixtures';
import { AdminActor } from '../screenplay/actor';
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor';
import { Navigate, Click, Wait } from '../screenplay/interactions';

test.describe('变更事件 - 业务流 E2E v2', () => {

  test('字段约束', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-change_event-FLD-REQ-event_type', { field: 'event_type', value: null });
    await BusinessRuleAssertor.assertRule('BR-change_event-FLD-REQ-object_id', { field: 'object_id', value: null });
    await BusinessRuleAssertor.assertRule('BR-change_event-FLD-REQ-object_type', { field: 'object_type', value: null });
  });

  test('审计 - CRUD', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-change_event-AUDIT-create', { operation: 'create', auditLog: true });
    await BusinessRuleAssertor.assertRule('BR-change_event-AUDIT-update', { operation: 'update', auditLog: true });
    await BusinessRuleAssertor.assertRule('BR-change_event-AUDIT-delete', { operation: 'delete', auditLog: true });
  });

  test('权限检查', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-change_event-AUTH-check', { authorized: true });
  });
});
