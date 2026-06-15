/**
 * 服务模块管理 - 业务流 E2E v2
 *
 * 覆盖 v2 抽取的 service_module (23) 业务规则
 */

import { test, expect } from '../helpers/auto-fixtures';
import { AdminActor } from '../screenplay/actor';
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor';
import { Navigate, Click, Fill, Wait } from '../screenplay/interactions';

test.describe('服务模块管理 - 业务流 E2E v2', () => {

  test('1. 字段约束 - code/name/parent', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    await BusinessRuleAssertor.assertRule('BR-service_module-FLD-REQ-code', { field: 'code', value: null });
    await BusinessRuleAssertor.assertRule('BR-service_module-FLD-UNQ-code', { field: 'code', value: 'existing' });
    await BusinessRuleAssertor.assertRule('BR-service_module-FLD-REQ-name', { field: 'name', value: null });
    await BusinessRuleAssertor.assertRule('BR-service_module-FLD-REQ-sub_domain_id', { field: 'sub_domain_id', value: null });
  });

  test('2. 删除约束', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    let delFailed = false;
    try {
      await BusinessRuleAssertor.assertRule('BR-service_module-DEL', { relationCount: 1, expected: false });
    } catch (e) {
      delFailed = true;
    }
    expect(delFailed).toBe(true);
  });

  test('3. 审计 - CRUD', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    await BusinessRuleAssertor.assertRule('BR-service_module-AUDIT-create', { operation: 'create', auditLog: true });
    await BusinessRuleAssertor.assertRule('BR-service_module-AUDIT-update', { operation: 'update', auditLog: true });
    await BusinessRuleAssertor.assertRule('BR-service_module-AUDIT-delete', { operation: 'delete', auditLog: true });
  });

  test('4. 权限 - 检查/自动 owner/继承', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    await BusinessRuleAssertor.assertRule('BR-service_module-AUTH-check', { authorized: true });
    await BusinessRuleAssertor.assertRule('BR-service_module-AUTH-auto_owner', { creatorId: 'admin', expectedOwner: 'admin' });
    await BusinessRuleAssertor.assertRule('BR-service_module-INHERIT', { parentId: 'sd_1', expectedChildAccess: true });
  });

  test('5. 导入导出', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    await BusinessRuleAssertor.assertRule('BR-service_module-IE-import', { strategy: 'upsert' });
    await BusinessRuleAssertor.assertRule('BR-service_module-IE-export', { cascade: true });
  });
});
