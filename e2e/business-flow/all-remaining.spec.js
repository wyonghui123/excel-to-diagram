/**
 * AI 异步任务 - 业务流 E2E v2
 */

import { test, expect } from '../helpers/auto-fixtures';
import { AdminActor } from '../screenplay/actor';
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor';
import { Navigate, Click, Wait } from '../screenplay/interactions';

test.describe('AI 异步任务 - 业务流 E2E v2', () => {
  test('字段约束', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-ai_async_task-FLD-REQ-request', { field: 'request', value: null });
    await BusinessRuleAssertor.assertRule('BR-ai_async_task-FLD-REQ-task_type', { field: 'task_type', value: null });
  });
  test('枚举', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-ai_async_task-FLD-ENUM-status', { field: 'status', allowed: ['PENDING', 'RUNNING', 'SUCCESS', 'FAILED'] });
    await BusinessRuleAssertor.assertRule('BR-ai_async_task-FLD-ENUM-task_type', { field: 'task_type', allowed: ['GENERATE', 'EXPLAIN', 'SUGGEST'] });
  });
  test('审计 - CRUD', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-ai_async_task-AUDIT-create', { operation: 'create', auditLog: true });
    await BusinessRuleAssertor.assertRule('BR-ai_async_task-AUDIT-update', { operation: 'update', auditLog: true });
  });
});

test.describe('定时任务 - 业务流 E2E v2', () => {
  test('字段约束', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-scheduled_task-FLD-REQ-name', { field: 'name', value: null });
    await BusinessRuleAssertor.assertRule('BR-scheduled_task-FLD-REQ-cron', { field: 'cron', value: null });
  });
  test('审计 - CRUD', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-scheduled_task-AUDIT-create', { operation: 'create', auditLog: true });
    await BusinessRuleAssertor.assertRule('BR-scheduled_task-AUDIT-update', { operation: 'update', auditLog: true });
  });
});

test.describe('菜单 + 菜单权限 - 业务流 E2E v2', () => {
  test('菜单 - 字段约束', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-menu-FLD-REQ-code', { field: 'code', value: null });
    await BusinessRuleAssertor.assertRule('BR-menu-FLD-REQ-name', { field: 'name', value: null });
  });
  test('菜单 - 审计', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-menu-AUDIT-create', { operation: 'create', auditLog: true });
  });
  test('菜单权限 - 字段约束', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-menu_permission-FLD-REQ-menu_id', { field: 'menu_id', value: null });
    await BusinessRuleAssertor.assertRule('BR-menu_permission-FLD-REQ-role_id', { field: 'role_id', value: null });
  });
  test('菜单权限 - 审计', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-menu_permission-AUDIT-create', { operation: 'create', auditLog: true });
  });
});

test.describe('角色数据权限/维度/权限授予 - 业务流 E2E v2', () => {
  test('角色数据权限 - 审计', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-role_data_permission-AUDIT-create', { operation: 'create', auditLog: true });
  });
  test('角色维度 - 审计', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-role_dimension_scope-AUDIT-create', { operation: 'create', auditLog: true });
  });
  test('角色权限授予 - 审计', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-role_permission-AUDIT-create', { operation: 'create', auditLog: true });
  });
});

test.describe('数据权限 + 过滤器变体 - 业务流 E2E v2', () => {
  test('数据权限 - 字段约束', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-data_permission-FLD-REQ-name', { field: 'name', value: null });
  });
  test('数据权限 - 审计', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-data_permission-AUDIT-create', { operation: 'create', auditLog: true });
  });
  test('过滤器变体 - 审计', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-filter_variant-AUDIT-create', { operation: 'create', auditLog: true });
  });
});

test.describe('用户组成员 - 业务流 E2E v2', () => {
  test('用户组成员 - 字段约束', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-user_group_member-FLD-REQ-user_id', { field: 'user_id', value: null });
  });
  test('用户组成员 - 审计', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-user_group_member-AUDIT-create', { operation: 'create', auditLog: true });
  });
});

test.describe('任务队列 + 任务执行 - 业务流 E2E v2', () => {
  test('任务队列 - 字段约束', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-task_queue-FLD-REQ-name', { field: 'name', value: null });
  });
  test('任务队列 - 审计', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-task_queue-AUDIT-create', { operation: 'create', auditLog: true });
  });
  test('任务执行 - 字段约束', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-task_execution-FLD-REQ-task_id', { field: 'task_id', value: null });
  });
  test('任务执行 - 审计', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-task_execution-AUDIT-create', { operation: 'create', auditLog: true });
  });
});

test.describe('维度映射 - 业务流 E2E v2', () => {
  test('审计 - CRUD', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-dimension_object_mapping-AUDIT-create', { operation: 'create', auditLog: true });
  });
});

test.describe('员工数据范围 - 业务流 E2E v2', () => {
  test('字段约束', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-employee_data_scope-FLD-REQ-emp_id', { field: 'emp_id', value: null });
  });
  test('审计 - CRUD', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-employee_data_scope-AUDIT-create', { operation: 'create', auditLog: true });
  });
});

test.describe('测试对象 + 测试表 - 业务流 E2E v2', () => {
  test('审计 - CRUD', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-test_objects-AUDIT-create', { operation: 'create', auditLog: true });
  });
  test('测试表 - 字段约束', async ({ page, isolation }) => {
    const admin = AdminActor(page, { isolation });
    await BusinessRuleAssertor.assertRule('BR-test_table-FLD-REQ-name', { field: 'name', value: null });
  });
});
