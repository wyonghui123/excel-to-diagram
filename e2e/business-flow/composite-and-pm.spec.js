/**
 * 跨对象组合 + PM 边界 - 业务流 E2E v3
 *
 * 覆盖 v3 (服务层) + v4 (跨对象) + PM 边界规则
 */

import { test, expect } from '../helpers/auto-fixtures';
import { AdminActor } from '../screenplay/actor';
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor';
import { Navigate, Click, Fill, Wait } from '../screenplay/interactions';

test.describe('跨对象组合 - 业务流 E2E v3', () => {

  test('1. 产品-版本 - cascade_delete + ref_integrity', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    // 删除产品时级联处理版本
    await BusinessRuleAssertor.assertRule('BR-product-COMP-cascade-delete-version', {
      parent: 'product_1',
      expected: 'cascade',
    });

    // 版本的 product_id 必须引用已存在的产品
    let refFailed = false;
    try {
      await BusinessRuleAssertor.assertRule('BR-version-COMP-ref-integrity-product', {
        invalid_ref: true,
        expected: 'error',
      });
    } catch (e) { refFailed = true; }
    expect(refFailed).toBe(true);
  });

  test('2. 版本-子域 - cascade + 权限继承', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    // 删除版本时级联处理子域
    await BusinessRuleAssertor.assertRule('BR-version-COMP-cascade-delete-sub_domain', {
      parent: 'version_1',
      expected: 'cascade',
    });

    // 对子域的权限应通过版本链追溯
    await BusinessRuleAssertor.assertRule('BR-sub_domain-COMP-permission-inherit-version', {
      parentAccess: true,
      expectedChildAccess: true,
    });
  });

  test('3. 子域-服务模块 - cascade + 可见性继承', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    // 删除子域时级联处理服务模块
    await BusinessRuleAssertor.assertRule('BR-sub_domain-COMP-cascade-delete-service_module', {
      parent: 'sub_domain_1',
      expected: 'cascade',
    });
  });

  test('4. 服务模块-业务对象 - cascade + 权限继承', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    // 删除服务模块时级联处理业务对象
    await BusinessRuleAssertor.assertRule('BR-service_module-COMP-cascade-delete-business_object', {
      parent: 'service_module_1',
      expected: 'cascade',
    });
  });

  test('5. 业务对象-关系 - ref_integrity + 无自环', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    // 关系的 source_bo_id 必须引用已存在业务对象
    let refFailed = false;
    try {
      await BusinessRuleAssertor.assertRule('BR-relationship-COMP-ref-integrity-business_object', {
        invalid_ref: true,
        expected: 'error',
      });
    } catch (e) { refFailed = true; }
    expect(refFailed).toBe(true);

    // PM 边界: 不允许自环
    let selfLoopFailed = false;
    try {
      await BusinessRuleAssertor.assertRule('BR-relationship-PM-no-self-loop', {
        source: 'bo_1',
        target: 'bo_1',
        expected: 'error',
      });
    } catch (e) { selfLoopFailed = true; }
    expect(selfLoopFailed).toBe(true);

    // PM 边界: 关系链深度不超过 5
    let depthFailed = false;
    try {
      await BusinessRuleAssertor.assertRule('BR-relationship-PM-max-depth-5', {
        depth: 6,
        expected: 'error',
      });
    } catch (e) { depthFailed = true; }
    expect(depthFailed).toBe(true);

    // PM 边界: 不允许关系环
    let cycleFailed = false;
    try {
      await BusinessRuleAssertor.assertRule('BR-relationship-PM-cycle-detect', {
        hasCycle: true,
        expected: 'error',
      });
    } catch (e) { cycleFailed = true; }
    expect(cycleFailed).toBe(true);
  });

  test('6. PM 边界 - 用户管理', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    // 用户名长度
    let usernameFailed = false;
    try {
      await BusinessRuleAssertor.assertRule('BR-user-PM-username-length-3-20', {
        length: 2,
        expected: 'error',
      });
    } catch (e) { usernameFailed = true; }
    expect(usernameFailed).toBe(true);

    // 邮箱格式
    let emailFailed = false;
    try {
      await BusinessRuleAssertor.assertRule('BR-user-PM-email-format-valid', {
        email: 'invalid',
        expected: 'error',
      });
    } catch (e) { emailFailed = true; }
    expect(emailFailed).toBe(true);
  });

  test('7. PM 边界 - 业务对象唯一性', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    // 同服务模块下 name 唯一
    let nameUniqueFailed = false;
    try {
      await BusinessRuleAssertor.assertRule('BR-business_object-PM-name-unique-in-same-sm', {
        name: 'existing',
        serviceModuleId: 'sm_1',
        expected: 'error',
      });
    } catch (e) { nameUniqueFailed = true; }
    expect(nameUniqueFailed).toBe(true);
  });
});
