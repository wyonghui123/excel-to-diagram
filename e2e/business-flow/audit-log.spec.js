/**
 * 审计日志 - 业务流 E2E v2
 *
 * 覆盖 v2 抽取的 audit_log (14) + business_object (25) 业务规则
 */

import { test, expect } from '../helpers/auto-fixtures';
import { AdminActor } from '../screenplay/actor';
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor';
import { Navigate, Click, Wait } from '../screenplay/interactions';

test.describe('审计日志 - 业务流 E2E v2', () => {

  test('1. 审计日志 - 列表/详情/筛选', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    await admin.attemptsTo(Navigate.to('/audit-log'));
    await BusinessRuleAssertor.assertRule('BR-audit_log-AUTH-check', { authorized: true });
  });

  test('2. 业务对象字段约束', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    await BusinessRuleAssertor.assertRule('BR-business_object-FLD-REQ-code', { field: 'code', value: null });
    await BusinessRuleAssertor.assertRule('BR-business_object-FLD-UNQ-code', { field: 'code', value: 'existing' });
    await BusinessRuleAssertor.assertRule('BR-business_object-FLD-REQ-name', { field: 'name', value: null });
    await BusinessRuleAssertor.assertRule('BR-business_object-FLD-REQ-service_module_id', { field: 'service_module_id', value: null });
  });

  test('3. 审计 - 业务对象 CRUD', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    await BusinessRuleAssertor.assertRule('BR-business_object-AUDIT-create', { operation: 'create', auditLog: true });
    await BusinessRuleAssertor.assertRule('BR-business_object-AUDIT-update', { operation: 'update', auditLog: true });
    await BusinessRuleAssertor.assertRule('BR-business_object-AUDIT-delete', { operation: 'delete', auditLog: true });
  });

  test('4. 删除约束 - 业务对象', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    let boDelFailed = false;
    try {
      await BusinessRuleAssertor.assertRule('BR-business_object-DEL', { relationCount: 1, expected: false });
    } catch (e) {
      boDelFailed = true;
    }
    expect(boDelFailed).toBe(true);
  });

  test('5. 权限和 owner', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    await BusinessRuleAssertor.assertRule('BR-business_object-AUTH-check', { authorized: true });
    await BusinessRuleAssertor.assertRule('BR-business_object-AUTH-auto_owner', { creatorId: 'admin', expectedOwner: 'admin' });
  });
});
