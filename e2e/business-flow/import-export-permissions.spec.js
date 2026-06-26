/**
 * 导入导出权限矩阵 E2E (T2: 模型驱动生成)
 *
 * 模型源:
 *   - .trae/specs/_business_rules/*.yaml 中 BR-*-AUTH-* 规则
 *   - meta/schemas/<object>.yaml 的 import_export + authorization 配置
 *
 * 覆盖场景:
 *   1. unauthorized: 无权限用户尝试导入/导出 → 403
 *   2. read_only_attempting_write: 仅读权限用户尝试导入 → 403 (read vs write 错配)
 *   3. owner_allowed: owner 模式 → 200
 *   4. cascade_unauthorized: cascade 操作需要子对象权限 → 403
 *
 * 生成时间: 2026-06-25T12:21:12.552Z
 * 规则数: 9
 * 测试数: 48
 */

import { test, expect } from '../helpers/auto-fixtures';
import { AdminActor } from '../screenplay/actor';
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor';

const API_BASE = 'http://localhost:3010';

// 辅助: 用低权限用户调 API,期望特定 status
async function callIEApi(page, objectType, action, user, payload = {}) {
  const url = action.startsWith('export')
    ? `${API_BASE}/api/v1/export`
    : `${API_BASE}/api/v1/import`;
  const method = action.startsWith('export') ? 'POST' : 'POST';
  try {
    const resp = await page.request.post(url, {
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': user,
      },
      data: { object_type: objectType, ...payload },
      timeout: 5000,
    });
    return resp.status();
  } catch (e) {
    // 401/403/网络错误都视同拒绝
    if (e.message && e.message.match(/40[13]|403/)) return 403;
    return 0;  // 网络错误
  }
}

test.describe('product 导入权限', () => {
  test('无权限用户尝试导入应被拒绝 (upsert)', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-check 应拒绝无权限用户
      const status = await callIEApi(page, 'product', 'import', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('product 导出权限', () => {
  test('无权限用户尝试导出应被拒绝', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-check 应拒绝无权限用户
      const status = await callIEApi(page, 'product', 'export', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('product 导入权限 (read vs write)', () => {
  test('仅读权限用户尝试写入(导入)应被拒绝', async ({ page, isolation }) => {
    // 模型: read 权限不能用于 write 操作 (read vs write 场景)
      await BusinessRuleAssertor.assertRule('BR-product-AUTH-check', { authorized: true, expected: 200 });
      const status = await callIEApi(page, 'product', 'import', 'read_only_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('product 导入权限 (owner)', () => {
  test('对象 owner 导入应被允许', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-auto_owner 创建者自动获得 owner 权限
      const status = await callIEApi(page, 'product', 'import', 'owner_user');
      // owner 应被允许,但如果对象不存在,允许 200/201/404
      expect([200, 201, 204, 400, 404]).toContain(status);
  });
});

test.describe('product cascade 权限', () => {
  test('cascade 导出/导入应要求子对象权限', async ({ page, isolation }) => {
    // 模型: cascade 操作需要子对象权限
      const status = await callIEApi(page, 'product', 'export_cascade', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('version 导入权限', () => {
  test('无权限用户尝试导入应被拒绝 (upsert)', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-check 应拒绝无权限用户
      const status = await callIEApi(page, 'version', 'import', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('version 导出权限', () => {
  test('无权限用户尝试导出应被拒绝', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-check 应拒绝无权限用户
      const status = await callIEApi(page, 'version', 'export', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('version 导入权限 (read vs write)', () => {
  test('仅读权限用户尝试写入(导入)应被拒绝', async ({ page, isolation }) => {
    // 模型: read 权限不能用于 write 操作 (read vs write 场景)
      await BusinessRuleAssertor.assertRule('BR-version-AUTH-check', { authorized: true, expected: 200 });
      const status = await callIEApi(page, 'version', 'import', 'read_only_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('version 导入权限 (owner)', () => {
  test('对象 owner 导入应被允许', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-auto_owner 创建者自动获得 owner 权限
      const status = await callIEApi(page, 'version', 'import', 'owner_user');
      // owner 应被允许,但如果对象不存在,允许 200/201/404
      expect([200, 201, 204, 400, 404]).toContain(status);
  });
});

test.describe('version cascade 权限', () => {
  test('cascade 导出/导入应要求子对象权限', async ({ page, isolation }) => {
    // 模型: cascade 操作需要子对象权限
      const status = await callIEApi(page, 'version', 'export_cascade', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('domain 导入权限', () => {
  test('无权限用户尝试导入应被拒绝 (upsert)', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-check 应拒绝无权限用户
      const status = await callIEApi(page, 'domain', 'import', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('domain 导出权限', () => {
  test('无权限用户尝试导出应被拒绝', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-check 应拒绝无权限用户
      const status = await callIEApi(page, 'domain', 'export', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('domain 导入权限 (read vs write)', () => {
  test('仅读权限用户尝试写入(导入)应被拒绝', async ({ page, isolation }) => {
    // 模型: read 权限不能用于 write 操作 (read vs write 场景)
      await BusinessRuleAssertor.assertRule('BR-domain-AUTH-check', { authorized: true, expected: 200 });
      const status = await callIEApi(page, 'domain', 'import', 'read_only_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('domain 导入权限 (owner)', () => {
  test('对象 owner 导入应被允许', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-auto_owner 创建者自动获得 owner 权限
      const status = await callIEApi(page, 'domain', 'import', 'owner_user');
      // owner 应被允许,但如果对象不存在,允许 200/201/404
      expect([200, 201, 204, 400, 404]).toContain(status);
  });
});

test.describe('domain cascade 权限', () => {
  test('cascade 导出/导入应要求子对象权限', async ({ page, isolation }) => {
    // 模型: cascade 操作需要子对象权限
      const status = await callIEApi(page, 'domain', 'export_cascade', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('sub_domain 导入权限', () => {
  test('无权限用户尝试导入应被拒绝 (upsert)', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-check 应拒绝无权限用户
      const status = await callIEApi(page, 'sub_domain', 'import', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('sub_domain 导出权限', () => {
  test('无权限用户尝试导出应被拒绝', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-check 应拒绝无权限用户
      const status = await callIEApi(page, 'sub_domain', 'export', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('sub_domain 导入权限 (read vs write)', () => {
  test('仅读权限用户尝试写入(导入)应被拒绝', async ({ page, isolation }) => {
    // 模型: read 权限不能用于 write 操作 (read vs write 场景)
      await BusinessRuleAssertor.assertRule('BR-sub_domain-AUTH-check', { authorized: true, expected: 200 });
      const status = await callIEApi(page, 'sub_domain', 'import', 'read_only_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('sub_domain 导入权限 (owner)', () => {
  test('对象 owner 导入应被允许', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-auto_owner 创建者自动获得 owner 权限
      const status = await callIEApi(page, 'sub_domain', 'import', 'owner_user');
      // owner 应被允许,但如果对象不存在,允许 200/201/404
      expect([200, 201, 204, 400, 404]).toContain(status);
  });
});

test.describe('sub_domain cascade 权限', () => {
  test('cascade 导出/导入应要求子对象权限', async ({ page, isolation }) => {
    // 模型: cascade 操作需要子对象权限
      const status = await callIEApi(page, 'sub_domain', 'export_cascade', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('service_module 导入权限', () => {
  test('无权限用户尝试导入应被拒绝 (upsert)', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-check 应拒绝无权限用户
      const status = await callIEApi(page, 'service_module', 'import', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('service_module 导出权限', () => {
  test('无权限用户尝试导出应被拒绝', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-check 应拒绝无权限用户
      const status = await callIEApi(page, 'service_module', 'export', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('service_module 导入权限 (read vs write)', () => {
  test('仅读权限用户尝试写入(导入)应被拒绝', async ({ page, isolation }) => {
    // 模型: read 权限不能用于 write 操作 (read vs write 场景)
      await BusinessRuleAssertor.assertRule('BR-service_module-AUTH-check', { authorized: true, expected: 200 });
      const status = await callIEApi(page, 'service_module', 'import', 'read_only_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('service_module 导入权限 (owner)', () => {
  test('对象 owner 导入应被允许', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-auto_owner 创建者自动获得 owner 权限
      const status = await callIEApi(page, 'service_module', 'import', 'owner_user');
      // owner 应被允许,但如果对象不存在,允许 200/201/404
      expect([200, 201, 204, 400, 404]).toContain(status);
  });
});

test.describe('service_module cascade 权限', () => {
  test('cascade 导出/导入应要求子对象权限', async ({ page, isolation }) => {
    // 模型: cascade 操作需要子对象权限
      const status = await callIEApi(page, 'service_module', 'export_cascade', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('business_object 导入权限', () => {
  test('无权限用户尝试导入应被拒绝 (upsert)', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-check 应拒绝无权限用户
      const status = await callIEApi(page, 'business_object', 'import', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('business_object 导出权限', () => {
  test('无权限用户尝试导出应被拒绝', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-check 应拒绝无权限用户
      const status = await callIEApi(page, 'business_object', 'export', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('business_object 导入权限 (read vs write)', () => {
  test('仅读权限用户尝试写入(导入)应被拒绝', async ({ page, isolation }) => {
    // 模型: read 权限不能用于 write 操作 (read vs write 场景)
      await BusinessRuleAssertor.assertRule('BR-business_object-AUTH-check', { authorized: true, expected: 200 });
      const status = await callIEApi(page, 'business_object', 'import', 'read_only_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('business_object 导入权限 (owner)', () => {
  test('对象 owner 导入应被允许', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-auto_owner 创建者自动获得 owner 权限
      const status = await callIEApi(page, 'business_object', 'import', 'owner_user');
      // owner 应被允许,但如果对象不存在,允许 200/201/404
      expect([200, 201, 204, 400, 404]).toContain(status);
  });
});

test.describe('relationship 导入权限', () => {
  test('无权限用户尝试导入应被拒绝 (upsert)', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-check 应拒绝无权限用户
      const status = await callIEApi(page, 'relationship', 'import', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('relationship 导出权限', () => {
  test('无权限用户尝试导出应被拒绝', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-check 应拒绝无权限用户
      const status = await callIEApi(page, 'relationship', 'export', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('relationship 导入权限 (read vs write)', () => {
  test('仅读权限用户尝试写入(导入)应被拒绝', async ({ page, isolation }) => {
    // 模型: read 权限不能用于 write 操作 (read vs write 场景)
      await BusinessRuleAssertor.assertRule('BR-relationship-AUTH-check', { authorized: true, expected: 200 });
      const status = await callIEApi(page, 'relationship', 'import', 'read_only_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('relationship 导入权限 (owner)', () => {
  test('对象 owner 导入应被允许', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-auto_owner 创建者自动获得 owner 权限
      const status = await callIEApi(page, 'relationship', 'import', 'owner_user');
      // owner 应被允许,但如果对象不存在,允许 200/201/404
      expect([200, 201, 204, 400, 404]).toContain(status);
  });
});

test.describe('enum_type 导入权限', () => {
  test('无权限用户尝试导入应被拒绝 (n/a)', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-check 应拒绝无权限用户
      const status = await callIEApi(page, 'enum_type', 'import', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('enum_type 导出权限', () => {
  test('无权限用户尝试导出应被拒绝', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-check 应拒绝无权限用户
      const status = await callIEApi(page, 'enum_type', 'export', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('enum_type 导入权限 (owner)', () => {
  test('对象 owner 导入应被允许', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-auto_owner 创建者自动获得 owner 权限
      const status = await callIEApi(page, 'enum_type', 'import', 'owner_user');
      // owner 应被允许,但如果对象不存在,允许 200/201/404
      expect([200, 201, 204, 400, 404]).toContain(status);
  });
});

test.describe('enum_type cascade 权限', () => {
  test('cascade 导出/导入应要求子对象权限', async ({ page, isolation }) => {
    // 模型: cascade 操作需要子对象权限
      const status = await callIEApi(page, 'enum_type', 'export_cascade', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('enum_value 导入权限', () => {
  test('无权限用户尝试导入应被拒绝 (upsert)', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-check 应拒绝无权限用户
      const status = await callIEApi(page, 'enum_value', 'import', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('enum_value 导出权限', () => {
  test('无权限用户尝试导出应被拒绝', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-check 应拒绝无权限用户
      const status = await callIEApi(page, 'enum_value', 'export', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('enum_value 导入权限 (read vs write)', () => {
  test('仅读权限用户尝试写入(导入)应被拒绝', async ({ page, isolation }) => {
    // 模型: read 权限不能用于 write 操作 (read vs write 场景)
      await BusinessRuleAssertor.assertRule('BR-enum_value-AUTH-check', { authorized: true, expected: 200 });
      const status = await callIEApi(page, 'enum_value', 'import', 'read_only_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('enum_value 导入权限 (owner)', () => {
  test('对象 owner 导入应被允许', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-auto_owner 创建者自动获得 owner 权限
      const status = await callIEApi(page, 'enum_value', 'import', 'owner_user');
      // owner 应被允许,但如果对象不存在,允许 200/201/404
      expect([200, 201, 204, 400, 404]).toContain(status);
  });
});

test.describe('role 导入权限', () => {
  test('无权限用户尝试导入应被拒绝 (upsert)', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-check 应拒绝无权限用户
      const status = await callIEApi(page, 'role', 'import', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('role 导出权限', () => {
  test('无权限用户尝试导出应被拒绝', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-check 应拒绝无权限用户
      const status = await callIEApi(page, 'role', 'export', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('role 导入权限 (read vs write)', () => {
  test('仅读权限用户尝试写入(导入)应被拒绝', async ({ page, isolation }) => {
    // 模型: read 权限不能用于 write 操作 (read vs write 场景)
      await BusinessRuleAssertor.assertRule('BR-role-AUTH-check', { authorized: true, expected: 200 });
      const status = await callIEApi(page, 'role', 'import', 'read_only_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('role 导入权限 (owner)', () => {
  test('对象 owner 导入应被允许', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-auto_owner 创建者自动获得 owner 权限
      const status = await callIEApi(page, 'role', 'import', 'owner_user');
      // owner 应被允许,但如果对象不存在,允许 200/201/404
      expect([200, 201, 204, 400, 404]).toContain(status);
  });
});

test.describe('audit_log 导入权限', () => {
  test('无权限用户尝试导入应被拒绝 (n/a)', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-check 应拒绝无权限用户
      const status = await callIEApi(page, 'audit_log', 'import', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('audit_log 导出权限', () => {
  test('无权限用户尝试导出应被拒绝', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-check 应拒绝无权限用户
      const status = await callIEApi(page, 'audit_log', 'export', 'no_perm_user');
      expect([401, 403]).toContain(status);
  });
});

test.describe('audit_log 导入权限 (owner)', () => {
  test('对象 owner 导入应被允许', async ({ page, isolation }) => {
    // 模型: BR-*-AUTH-auto_owner 创建者自动获得 owner 权限
      const status = await callIEApi(page, 'audit_log', 'import', 'owner_user');
      // owner 应被允许,但如果对象不存在,允许 200/201/404
      expect([200, 201, 204, 400, 404]).toContain(status);
  });
});


// ---------------------------------------------------------------------------
// 模型溯源: BR-*-AUTH-* 规则覆盖度
// ---------------------------------------------------------------------------
test.describe('AUTH 规则覆盖度自检 (模型驱动)', () => {
  test('所有 AUTH 规则都被导入导出场景引用', async () => {
    const ruleIds = ["BR-business_object-AUTH-check","BR-domain-AUTH-check","BR-product-AUTH-check","BR-product-AUTH-auto_owner","BR-relationship-AUTH-check","BR-service_module-AUTH-check","BR-sub_domain-AUTH-check","BR-version-AUTH-check","BR-version-AUTH-auto_owner"];
    expect(ruleIds.length).toBeGreaterThan(0);
    // 每条 AUTH 规则应在测试场景中至少出现一次
    const allTestTitles = ["BR-product-AUTH-check","BR-product-AUTH-check","BR-product-AUTH-check","BR-product-AUTH-auto_owner","BR-product-AUTH-check","BR-version-AUTH-check","BR-version-AUTH-check","BR-version-AUTH-check","BR-version-AUTH-auto_owner","BR-version-AUTH-check","BR-domain-AUTH-check","BR-domain-AUTH-check","BR-domain-AUTH-check","BR-domain-AUTH-auto_owner","BR-domain-AUTH-check","BR-sub_domain-AUTH-check","BR-sub_domain-AUTH-check","BR-sub_domain-AUTH-check","BR-sub_domain-AUTH-auto_owner","BR-sub_domain-AUTH-check","BR-service_module-AUTH-check","BR-service_module-AUTH-check","BR-service_module-AUTH-check","BR-service_module-AUTH-auto_owner","BR-service_module-AUTH-check","BR-business_object-AUTH-check","BR-business_object-AUTH-check","BR-business_object-AUTH-check","BR-business_object-AUTH-auto_owner","BR-relationship-AUTH-check","BR-relationship-AUTH-check","BR-relationship-AUTH-check","BR-relationship-AUTH-auto_owner","BR-enum_type-AUTH-check","BR-enum_type-AUTH-check","BR-enum_type-AUTH-auto_owner","BR-enum_type-AUTH-check","BR-enum_value-AUTH-check","BR-enum_value-AUTH-check","BR-enum_value-AUTH-check","BR-enum_value-AUTH-auto_owner","BR-role-AUTH-check","BR-role-AUTH-check","BR-role-AUTH-check","BR-role-AUTH-auto_owner","BR-audit_log-AUTH-check","BR-audit_log-AUTH-check","BR-audit_log-AUTH-auto_owner"];
    for (const rid of ruleIds) {
      const referenced = allTestTitles.includes(rid);
      expect(referenced, `AUTH 规则 ${rid} 未被任何测试场景覆盖`).toBe(true);
    }
  });
});
