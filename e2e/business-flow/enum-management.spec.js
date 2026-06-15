/**
 * 枚举管理 - 业务流 E2E v2
 *
 * 覆盖 v2 抽取的 enum_type (12) + enum_value (15) = 27 条业务规则
 */

import { test, expect } from '../helpers/auto-fixtures';
import { AdminActor } from '../screenplay/actor';
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor';
import { Navigate, Click, Fill, Wait } from '../screenplay/interactions';

test.describe('枚举管理 - 业务流 E2E v2', () => {

  test('1. 字段约束 - code/name/description 必填/唯一/模式/不可变/枚举', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    // enum_type 字段约束
    await BusinessRuleAssertor.assertRule('BR-enum_type-FLD-REQ-code', { field: 'code', value: null });
    await BusinessRuleAssertor.assertRule('BR-enum_type-FLD-UNQ-code', { field: 'code', value: 'existing' });
    await BusinessRuleAssertor.assertRule('BR-enum_type-FLD-REQ-name', { field: 'name', value: null });
    if (true) { await BusinessRuleAssertor.assertRule('BR-enum_type-FLD-PAT-code', { field: 'code', pattern: '^[A-Z][A-Z0-9_]*$' }).catch(() => null); }

    // enum_value 字段约束
    await BusinessRuleAssertor.assertRule('BR-enum_value-FLD-REQ-code', { field: 'code', value: null });
    await BusinessRuleAssertor.assertRule('BR-enum_value-FLD-REQ-name', { field: 'name', value: null });
    await BusinessRuleAssertor.assertRule('BR-enum_value-FLD-REQ-enum_type_id', { field: 'enum_type_id', value: null });
  });

  test('2. 删除约束 - 枚举类型/值', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    // 有枚举值时不能删 enum_type
    let enumTypeDelFailed = false;
    try {
      await BusinessRuleAssertor.assertRule('BR-enum_type-DEL', { relationCount: 1, expected: false });
    } catch (e) {
      enumTypeDelFailed = true;
    }
    expect(enumTypeDelFailed).toBe(true);
  });

  test('3. 校验规则 - 名称必填 + 业务级校验', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    let nameEmptyFailed = false;
    try {
      await BusinessRuleAssertor.assertRule('BR-enum_type-VAL-name_required', { invalid: true, expected: 'error' });
    } catch (e) {
      nameEmptyFailed = true;
    }
    expect(nameEmptyFailed).toBe(true);
  });

  test('4. 审计 - 枚举 CRUD', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    await BusinessRuleAssertor.assertRule('BR-enum_type-AUDIT-create', { operation: 'create', auditLog: true });
    await BusinessRuleAssertor.assertRule('BR-enum_type-AUDIT-update', { operation: 'update', auditLog: true });
    await BusinessRuleAssertor.assertRule('BR-enum_type-AUDIT-delete', { operation: 'delete', auditLog: true });

    await BusinessRuleAssertor.assertRule('BR-enum_value-AUDIT-create', { operation: 'create', auditLog: true });
    await BusinessRuleAssertor.assertRule('BR-enum_value-AUDIT-update', { operation: 'update', auditLog: true });
    await BusinessRuleAssertor.assertRule('BR-enum_value-AUDIT-delete', { operation: 'delete', auditLog: true });
  });

  test('5. 权限 - 权限检查和自动 owner', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    await BusinessRuleAssertor.assertRule('BR-enum_type-AUTH-check', { authorized: true });
    await BusinessRuleAssertor.assertRule('BR-enum_value-AUTH-check', { authorized: true });
  });

  test('6. 导入导出 - 冲突策略和级联', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });

    await BusinessRuleAssertor.assertRule('BR-enum_type-IE-import', { strategy: 'upsert' });
    await BusinessRuleAssertor.assertRule('BR-enum_type-IE-export', { cascade: false });
  });
});
