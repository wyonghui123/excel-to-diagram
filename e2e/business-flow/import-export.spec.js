/**
 * 导入导出 - 业务流 E2E v2
 *
 * 覆盖 v2 抽取的业务对象和产品的 import_export 规则
 */

import { test, expect } from '../helpers/auto-fixtures';
import { AdminActor } from '../screenplay/actor';
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor';
import { Navigate, Click, Wait } from '../screenplay/interactions';

test.describe('导入导出 - 业务流 E2E v2', () => {

  test('1. 业务对象导入导出 - upsert/级联', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    await BusinessRuleAssertor.assertRule('BR-business_object-IE-import', { strategy: 'upsert' });
    await BusinessRuleAssertor.assertRule('BR-business_object-IE-export', { cascade: true });
  });

  test('2. 产品导入导出 - code 冲突键', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    await BusinessRuleAssertor.assertRule('BR-product-IE-import', { strategy: 'upsert', conflictKey: 'code' });
    await BusinessRuleAssertor.assertRule('BR-product-IE-export', { cascade: true });
  });

  test('3. 权限检查', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    await BusinessRuleAssertor.assertRule('BR-business_object-AUTH-check', { authorized: true });
  });
});
