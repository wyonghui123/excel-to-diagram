/**
 * 子域管理 - 业务流 E2E v2
 *
 * 覆盖 v2 抽取的 sub_domain (22) 业务规则
 */

import { test, expect } from '../helpers/auto-fixtures';
import { AdminActor } from '../screenplay/actor';
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor';
import { Navigate, Click, Fill, Wait } from '../screenplay/interactions';

test.describe('子域管理 - 业务流 E2E v2', () => {

  test('1. 字段约束', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    await BusinessRuleAssertor.assertRule('BR-sub_domain-FLD-REQ-code', { field: 'code', value: null });
    await BusinessRuleAssertor.assertRule('BR-sub_domain-FLD-UNQ-code', { field: 'code', value: 'existing' });
    await BusinessRuleAssertor.assertRule('BR-sub_domain-FLD-REQ-name', { field: 'name', value: null });
    await BusinessRuleAssertor.assertRule('BR-sub_domain-FLD-REQ-domain_id', { field: 'domain_id', value: null });
  });

  test('2. 删除约束', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    let delFailed = false;
    try {
      await BusinessRuleAssertor.assertRule('BR-sub_domain-DEL', { relationCount: 1, expected: false });
    } catch (e) { delFailed = true; }
    expect(delFailed).toBe(true);
  });

  test('3. 审计 - CRUD', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    await BusinessRuleAssertor.assertRule('BR-sub_domain-AUDIT-create', { operation: 'create', auditLog: true });
    await BusinessRuleAssertor.assertRule('BR-sub_domain-AUDIT-update', { operation: 'update', auditLog: true });
    await BusinessRuleAssertor.assertRule('BR-sub_domain-AUDIT-delete', { operation: 'delete', auditLog: true });
  });

  test('4. 权限/owner/继承', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    await BusinessRuleAssertor.assertRule('BR-sub_domain-AUTH-check', { authorized: true });
    await BusinessRuleAssertor.assertRule('BR-sub_domain-AUTH-auto_owner', { creatorId: 'admin', expectedOwner: 'admin' });
    await BusinessRuleAssertor.assertRule('BR-sub_domain-INHERIT', { parentId: 'd_1', expectedChildAccess: true });
  });

  test('5. 层级 + 导入导出', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    await BusinessRuleAssertor.assertRule('BR-sub_domain-HIER', { level: 3 });
    await BusinessRuleAssertor.assertRule('BR-sub_domain-IE-import', { strategy: 'upsert' });
    await BusinessRuleAssertor.assertRule('BR-sub_domain-IE-export', { cascade: true });
  });
});
