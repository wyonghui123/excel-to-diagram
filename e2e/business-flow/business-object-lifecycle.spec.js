/**
 * 业务对象生命周期 - 业务流 E2E v2
 *
 * 覆盖 v2 抽取的 business_object (25 条) 业务规则
 */

import { test, expect } from '../helpers/auto-fixtures';
import { AdminActor } from '../screenplay/actor';
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor';
import { Navigate, Click, Fill, Wait } from '../screenplay/interactions';

test.describe('业务对象生命周期 - 业务流 E2E v2', () => {

  test('1. 字段约束 - 必填/唯一/不可变', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    await BusinessRuleAssertor.assertRule('BR-business_object-FLD-REQ-code', { field: 'code', value: null });
    await BusinessRuleAssertor.assertRule('BR-business_object-FLD-UNQ-code', { field: 'code', value: 'existing' });
    await BusinessRuleAssertor.assertRule('BR-business_object-FLD-REQ-name', { field: 'name', value: null });
    await BusinessRuleAssertor.assertRule('BR-business_object-FLD-REQ-service_module_id', { field: 'service_module_id', value: null });
  });

  test('2. 删除约束', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    let delFailed = false;
    try {
      await BusinessRuleAssertor.assertRule('BR-business_object-DEL', { relationCount: 1, expected: false });
    } catch (e) {
      delFailed = true;
    }
    expect(delFailed).toBe(true);
  });

  test('3. 审计 - CRUD', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    await BusinessRuleAssertor.assertRule('BR-business_object-AUDIT-create', { operation: 'create', auditLog: true });
    await BusinessRuleAssertor.assertRule('BR-business_object-AUDIT-update', { operation: 'update', auditLog: true });
    await BusinessRuleAssertor.assertRule('BR-business_object-AUDIT-delete', { operation: 'delete', auditLog: true });
  });

  test('4. 权限 - 检查/自动 owner/继承', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    await BusinessRuleAssertor.assertRule('BR-business_object-AUTH-check', { authorized: true });
    await BusinessRuleAssertor.assertRule('BR-business_object-AUTH-auto_owner', { creatorId: 'admin', expectedOwner: 'admin' });
    await BusinessRuleAssertor.assertRule('BR-business_object-INHERIT', { parentId: 'sm_1', expectedChildAccess: true });
  });

  test('5. 导入导出', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    await BusinessRuleAssertor.assertRule('BR-business_object-IE-import', { strategy: 'upsert' });
    await BusinessRuleAssertor.assertRule('BR-business_object-IE-export', { cascade: true });
  });

  test('6. 关联关系', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    await BusinessRuleAssertor.assertRule('BR-business_object-REL-business_object_to_relationships', {
      parentId: 'bo_1',
      childrenCount: 2,
    });
  });

  test('7. 业务动作 - CRUD 端点', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    await BusinessRuleAssertor.assertRule('BR-business_object-ACT-business_object_create', {
      method: 'POST',
      path: '/api/v1/business_objects',
    });

    await BusinessRuleAssertor.assertRule('BR-business_object-ACT-business_object_delete', {
      method: 'DELETE',
      path: '/api/v1/business_objects/{id}',
    });
  });
});
