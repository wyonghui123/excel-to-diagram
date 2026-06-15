/**
 * 权限规则 + 权限包 - 业务流 E2E v2
 */

import { test, expect } from '../helpers/auto-fixtures';
import { AdminActor } from '../screenplay/actor';
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor';
import { Navigate, Click, Wait } from '../screenplay/interactions';

test.describe('权限规则 - 业务流 E2E v2', () => {
  test('字段约束', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-permission_rule-FLD-REQ-code', { field: 'code', value: null });
    await BusinessRuleAssertor.assertRule('BR-permission_rule-FLD-REQ-name', { field: 'name', value: null });
  });
  test('审计 - CRUD', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-permission_rule-AUDIT-create', { operation: 'create', auditLog: true });
    await BusinessRuleAssertor.assertRule('BR-permission_rule-AUDIT-delete', { operation: 'delete', auditLog: true });
  });
  test('权限检查', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-permission_rule-AUTH-check', { authorized: true });
  });
});

test.describe('权限包 - 业务流 E2E v2', () => {
  test('字段约束', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-permission_bundle-FLD-REQ-code', { field: 'code', value: null });
    await BusinessRuleAssertor.assertRule('BR-permission_bundle-FLD-REQ-name', { field: 'name', value: null });
  });
  test('审计 - CRUD', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-permission_bundle-AUDIT-create', { operation: 'create', auditLog: true });
    await BusinessRuleAssertor.assertRule('BR-permission_bundle-AUDIT-delete', { operation: 'delete', auditLog: true });
  });
});

test.describe('数据权限组 - 业务流 E2E v2', () => {
  test('字段约束', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-group_data_permission-FLD-REQ-name', { field: 'name', value: null });
  });
  test('审计 - CRUD', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-group_data_permission-AUDIT-create', { operation: 'create', auditLog: true });
    await BusinessRuleAssertor.assertRule('BR-group_data_permission-AUDIT-delete', { operation: 'delete', auditLog: true });
  });
});

test.describe('用户组 - 业务流 E2E v2', () => {
  test('字段约束', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-user_group-FLD-REQ-name', { field: 'name', value: null });
  });
  test('审计 - CRUD', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-user_group-AUDIT-create', { operation: 'create', auditLog: true });
    await BusinessRuleAssertor.assertRule('BR-user_group-AUDIT-delete', { operation: 'delete', auditLog: true });
  });
});
