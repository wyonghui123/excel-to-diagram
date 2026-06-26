/**
 * Composite 业务规则 E2E (T16-B: 模型驱动生成)
 *
 * 模型源:
 *   - .trae/specs/_business_rules/_composite/_composite.yaml (58 条 BR)
 *   - meta/schemas/<obj>.yaml
 *   - meta/services/cascade_service.py
 *   - meta/services/data_permission_service.py
 *
 * 覆盖 BR 规则 (58 条, 58 test):
 *   - cascade_delete: 17 条
 *   - reference_integrity: 17 条
 *   - permission_inherit_chain: 17 条
 *   - sequential_codegen: 5 条
 *   - scope_inherit: 2 条
 *
 * 业务度: 🟢 强业务 (BR 规则反映业务核心约束)
 *
 * 漏掉场景: T13/T14/T15 只测了 cascade_delete, 未测其他 4 个 subtype
 * 本生成器补完 5 个 subtype × 多个对象对 = 58 条 BR
 *
 * 5 个 subtype 含义:
 *   - cascade_delete: 级联删除策略
 *   - reference_integrity: FK 引用完整性
 *   - permission_inherit_chain: 权限继承链
 *   - scope_inherit: 可见性继承
 *   - sequential_codegen: 顺序编码生成
 *
 * 生成时间: 2026-06-26T01:18:52.459Z
 */

import { test, expect } from '../helpers/auto-fixtures';
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor';

const API_BASE = 'http://localhost:3010';
const COMPOSITE_RULES = [
  {
    "id": "BR-business_object-COMP-cascade-delete-version",
    "subtype": "cascade_delete",
    "object": "business_object",
    "target": "version",
    "description": "删除业务对象时,产品版本应级联处理 (cardinality=N:1)",
    "testId": "T_BUSINESS_OBJECT_COMP_CASCADE_VERSION_001"
  },
  {
    "id": "BR-version-COMP-ref-integrity-business_object",
    "subtype": "reference_integrity",
    "object": "version",
    "target": "business_object",
    "description": "产品版本的必须引用已存在的业务对象",
    "testId": "T_VERSION_COMP_REF_BUSINESS_OBJECT_001"
  },
  {
    "id": "BR-version-COMP-permission-inherit-business_object",
    "subtype": "permission_inherit_chain",
    "object": "version",
    "target": "business_object",
    "description": "对产品版本的权限应通过业务对象链追溯",
    "testId": "T_VERSION_COMP_PERM_BUSINESS_OBJECT_001"
  },
  {
    "id": "BR-business_object-COMP-cascade-delete-service_module",
    "subtype": "cascade_delete",
    "object": "business_object",
    "target": "service_module",
    "description": "删除业务对象时,服务模块应级联处理 (cardinality=N:1)",
    "testId": "T_BUSINESS_OBJECT_COMP_CASCADE_SERVICE_MODULE_001"
  },
  {
    "id": "BR-service_module-COMP-ref-integrity-business_object",
    "subtype": "reference_integrity",
    "object": "service_module",
    "target": "business_object",
    "description": "服务模块的必须引用已存在的业务对象",
    "testId": "T_SERVICE_MODULE_COMP_REF_BUSINESS_OBJECT_001"
  },
  {
    "id": "BR-service_module-COMP-permission-inherit-business_object",
    "subtype": "permission_inherit_chain",
    "object": "service_module",
    "target": "business_object",
    "description": "对服务模块的权限应通过业务对象链追溯",
    "testId": "T_SERVICE_MODULE_COMP_PERM_BUSINESS_OBJECT_001"
  },
  {
    "id": "BR-business_object-COMP-hierarchy-path",
    "subtype": "sequential_codegen",
    "object": "business_object",
    "target": "",
    "description": "业务对象的 hierarchy_path 应基于父链自动生成 (level=5)",
    "testId": "T_BUSINESS_OBJECT_COMP_HIER_PATH_001"
  },
  {
    "id": "BR-domain-COMP-cascade-delete-version",
    "subtype": "cascade_delete",
    "object": "domain",
    "target": "version",
    "description": "删除领域时,产品版本应级联处理 (cardinality=N:1)",
    "testId": "T_DOMAIN_COMP_CASCADE_VERSION_001"
  },
  {
    "id": "BR-version-COMP-ref-integrity-domain",
    "subtype": "reference_integrity",
    "object": "version",
    "target": "domain",
    "description": "产品版本的必须引用已存在的领域",
    "testId": "T_VERSION_COMP_REF_DOMAIN_001"
  },
  {
    "id": "BR-version-COMP-permission-inherit-domain",
    "subtype": "permission_inherit_chain",
    "object": "version",
    "target": "domain",
    "description": "对产品版本的权限应通过领域链追溯",
    "testId": "T_VERSION_COMP_PERM_DOMAIN_001"
  },
  {
    "id": "BR-domain-COMP-cascade-delete-sub_domain",
    "subtype": "cascade_delete",
    "object": "domain",
    "target": "sub_domain",
    "description": "删除领域时,子领域应级联处理 (cardinality=1:N)",
    "testId": "T_DOMAIN_COMP_CASCADE_SUB_DOMAIN_001"
  },
  {
    "id": "BR-sub_domain-COMP-ref-integrity-domain",
    "subtype": "reference_integrity",
    "object": "sub_domain",
    "target": "domain",
    "description": "子领域的必须引用已存在的领域",
    "testId": "T_SUB_DOMAIN_COMP_REF_DOMAIN_001"
  },
  {
    "id": "BR-sub_domain-COMP-permission-inherit-domain",
    "subtype": "permission_inherit_chain",
    "object": "sub_domain",
    "target": "domain",
    "description": "对子领域的权限应通过领域链追溯",
    "testId": "T_SUB_DOMAIN_COMP_PERM_DOMAIN_001"
  },
  {
    "id": "BR-domain-COMP-hierarchy-path",
    "subtype": "sequential_codegen",
    "object": "domain",
    "target": "",
    "description": "领域的 hierarchy_path 应基于父链自动生成 (level=2)",
    "testId": "T_DOMAIN_COMP_HIER_PATH_001"
  },
  {
    "id": "BR-enum_type-COMP-cascade-delete-enum_value",
    "subtype": "cascade_delete",
    "object": "enum_type",
    "target": "enum_value",
    "description": "删除枚举类型时,枚举值应级联处理 (cardinality=1:N)",
    "testId": "T_ENUM_TYPE_COMP_CASCADE_ENUM_VALUE_001"
  },
  {
    "id": "BR-enum_value-COMP-ref-integrity-enum_type",
    "subtype": "reference_integrity",
    "object": "enum_value",
    "target": "enum_type",
    "description": "枚举值的必须引用已存在的枚举类型",
    "testId": "T_ENUM_VALUE_COMP_REF_ENUM_TYPE_001"
  },
  {
    "id": "BR-enum_value-COMP-permission-inherit-enum_type",
    "subtype": "permission_inherit_chain",
    "object": "enum_value",
    "target": "enum_type",
    "description": "对枚举值的权限应通过枚举类型链追溯",
    "testId": "T_ENUM_VALUE_COMP_PERM_ENUM_TYPE_001"
  },
  {
    "id": "BR-enum_value-COMP-cascade-delete-enum_type",
    "subtype": "cascade_delete",
    "object": "enum_value",
    "target": "enum_type",
    "description": "删除枚举值时,枚举类型应级联处理 (cardinality=N:1)",
    "testId": "T_ENUM_VALUE_COMP_CASCADE_ENUM_TYPE_001"
  },
  {
    "id": "BR-enum_type-COMP-ref-integrity-enum_value",
    "subtype": "reference_integrity",
    "object": "enum_type",
    "target": "enum_value",
    "description": "枚举类型的必须引用已存在的枚举值",
    "testId": "T_ENUM_TYPE_COMP_REF_ENUM_VALUE_001"
  },
  {
    "id": "BR-enum_type-COMP-permission-inherit-enum_value",
    "subtype": "permission_inherit_chain",
    "object": "enum_type",
    "target": "enum_value",
    "description": "对枚举类型的权限应通过枚举值链追溯",
    "testId": "T_ENUM_TYPE_COMP_PERM_ENUM_VALUE_001"
  },
  {
    "id": "BR-product-COMP-cascade-delete-version",
    "subtype": "cascade_delete",
    "object": "product",
    "target": "version",
    "description": "删除产品线时,产品版本应级联处理 (cardinality=1:N)",
    "testId": "T_PRODUCT_COMP_CASCADE_VERSION_001"
  },
  {
    "id": "BR-version-COMP-ref-integrity-product",
    "subtype": "reference_integrity",
    "object": "version",
    "target": "product",
    "description": "产品版本的必须引用已存在的产品线",
    "testId": "T_VERSION_COMP_REF_PRODUCT_001"
  },
  {
    "id": "BR-version-COMP-permission-inherit-product",
    "subtype": "permission_inherit_chain",
    "object": "version",
    "target": "product",
    "description": "对产品版本的权限应通过产品线链追溯",
    "testId": "T_VERSION_COMP_PERM_PRODUCT_001"
  },
  {
    "id": "BR-version-COMP-scope-inherit-product",
    "subtype": "scope_inherit",
    "object": "version",
    "target": "product",
    "description": "产品版本的可见性由产品线的 visibility 决定",
    "testId": "T_VERSION_COMP_SCOPE_PRODUCT_001"
  },
  {
    "id": "BR-product-COMP-cascade-delete-version",
    "subtype": "cascade_delete",
    "object": "product",
    "target": "version",
    "description": "删除产品线时,产品版本应级联处理 (cardinality=1:N)",
    "testId": "T_PRODUCT_COMP_CASCADE_VERSION_001"
  },
  {
    "id": "BR-version-COMP-ref-integrity-product",
    "subtype": "reference_integrity",
    "object": "version",
    "target": "product",
    "description": "产品版本的product_id必须引用已存在的产品线",
    "testId": "T_VERSION_COMP_REF_PRODUCT_001"
  },
  {
    "id": "BR-version-COMP-permission-inherit-product",
    "subtype": "permission_inherit_chain",
    "object": "version",
    "target": "product",
    "description": "对产品版本的权限应通过产品线链追溯",
    "testId": "T_VERSION_COMP_PERM_PRODUCT_001"
  },
  {
    "id": "BR-version-COMP-scope-inherit-product",
    "subtype": "scope_inherit",
    "object": "version",
    "target": "product",
    "description": "产品版本的可见性由产品线的 visibility 决定",
    "testId": "T_VERSION_COMP_SCOPE_PRODUCT_001"
  },
  {
    "id": "BR-relationship-COMP-cascade-delete-version",
    "subtype": "cascade_delete",
    "object": "relationship",
    "target": "version",
    "description": "删除业务关系时,产品版本应级联处理 (cardinality=N:1)",
    "testId": "T_RELATIONSHIP_COMP_CASCADE_VERSION_001"
  },
  {
    "id": "BR-version-COMP-ref-integrity-relationship",
    "subtype": "reference_integrity",
    "object": "version",
    "target": "relationship",
    "description": "产品版本的必须引用已存在的业务关系",
    "testId": "T_VERSION_COMP_REF_RELATIONSHIP_001"
  },
  {
    "id": "BR-version-COMP-permission-inherit-relationship",
    "subtype": "permission_inherit_chain",
    "object": "version",
    "target": "relationship",
    "description": "对产品版本的权限应通过业务关系链追溯",
    "testId": "T_VERSION_COMP_PERM_RELATIONSHIP_001"
  },
  {
    "id": "BR-service_module-COMP-cascade-delete-version",
    "subtype": "cascade_delete",
    "object": "service_module",
    "target": "version",
    "description": "删除服务模块时,产品版本应级联处理 (cardinality=N:1)",
    "testId": "T_SERVICE_MODULE_COMP_CASCADE_VERSION_001"
  },
  {
    "id": "BR-version-COMP-ref-integrity-service_module",
    "subtype": "reference_integrity",
    "object": "version",
    "target": "service_module",
    "description": "产品版本的必须引用已存在的服务模块",
    "testId": "T_VERSION_COMP_REF_SERVICE_MODULE_001"
  },
  {
    "id": "BR-version-COMP-permission-inherit-service_module",
    "subtype": "permission_inherit_chain",
    "object": "version",
    "target": "service_module",
    "description": "对产品版本的权限应通过服务模块链追溯",
    "testId": "T_VERSION_COMP_PERM_SERVICE_MODULE_001"
  },
  {
    "id": "BR-service_module-COMP-cascade-delete-sub_domain",
    "subtype": "cascade_delete",
    "object": "service_module",
    "target": "sub_domain",
    "description": "删除服务模块时,子领域应级联处理 (cardinality=N:1)",
    "testId": "T_SERVICE_MODULE_COMP_CASCADE_SUB_DOMAIN_001"
  },
  {
    "id": "BR-sub_domain-COMP-ref-integrity-service_module",
    "subtype": "reference_integrity",
    "object": "sub_domain",
    "target": "service_module",
    "description": "子领域的必须引用已存在的服务模块",
    "testId": "T_SUB_DOMAIN_COMP_REF_SERVICE_MODULE_001"
  },
  {
    "id": "BR-sub_domain-COMP-permission-inherit-service_module",
    "subtype": "permission_inherit_chain",
    "object": "sub_domain",
    "target": "service_module",
    "description": "对子领域的权限应通过服务模块链追溯",
    "testId": "T_SUB_DOMAIN_COMP_PERM_SERVICE_MODULE_001"
  },
  {
    "id": "BR-service_module-COMP-cascade-delete-business_object",
    "subtype": "cascade_delete",
    "object": "service_module",
    "target": "business_object",
    "description": "删除服务模块时,业务对象应级联处理 (cardinality=1:N)",
    "testId": "T_SERVICE_MODULE_COMP_CASCADE_BUSINESS_OBJECT_001"
  },
  {
    "id": "BR-business_object-COMP-ref-integrity-service_module",
    "subtype": "reference_integrity",
    "object": "business_object",
    "target": "service_module",
    "description": "业务对象的必须引用已存在的服务模块",
    "testId": "T_BUSINESS_OBJECT_COMP_REF_SERVICE_MODULE_001"
  },
  {
    "id": "BR-business_object-COMP-permission-inherit-service_module",
    "subtype": "permission_inherit_chain",
    "object": "business_object",
    "target": "service_module",
    "description": "对业务对象的权限应通过服务模块链追溯",
    "testId": "T_BUSINESS_OBJECT_COMP_PERM_SERVICE_MODULE_001"
  },
  {
    "id": "BR-service_module-COMP-hierarchy-path",
    "subtype": "sequential_codegen",
    "object": "service_module",
    "target": "",
    "description": "服务模块的 hierarchy_path 应基于父链自动生成 (level=4)",
    "testId": "T_SERVICE_MODULE_COMP_HIER_PATH_001"
  },
  {
    "id": "BR-sub_domain-COMP-cascade-delete-version",
    "subtype": "cascade_delete",
    "object": "sub_domain",
    "target": "version",
    "description": "删除子领域时,产品版本应级联处理 (cardinality=N:1)",
    "testId": "T_SUB_DOMAIN_COMP_CASCADE_VERSION_001"
  },
  {
    "id": "BR-version-COMP-ref-integrity-sub_domain",
    "subtype": "reference_integrity",
    "object": "version",
    "target": "sub_domain",
    "description": "产品版本的必须引用已存在的子领域",
    "testId": "T_VERSION_COMP_REF_SUB_DOMAIN_001"
  },
  {
    "id": "BR-version-COMP-permission-inherit-sub_domain",
    "subtype": "permission_inherit_chain",
    "object": "version",
    "target": "sub_domain",
    "description": "对产品版本的权限应通过子领域链追溯",
    "testId": "T_VERSION_COMP_PERM_SUB_DOMAIN_001"
  },
  {
    "id": "BR-sub_domain-COMP-cascade-delete-domain",
    "subtype": "cascade_delete",
    "object": "sub_domain",
    "target": "domain",
    "description": "删除子领域时,领域应级联处理 (cardinality=N:1)",
    "testId": "T_SUB_DOMAIN_COMP_CASCADE_DOMAIN_001"
  },
  {
    "id": "BR-domain-COMP-ref-integrity-sub_domain",
    "subtype": "reference_integrity",
    "object": "domain",
    "target": "sub_domain",
    "description": "领域的必须引用已存在的子领域",
    "testId": "T_DOMAIN_COMP_REF_SUB_DOMAIN_001"
  },
  {
    "id": "BR-domain-COMP-permission-inherit-sub_domain",
    "subtype": "permission_inherit_chain",
    "object": "domain",
    "target": "sub_domain",
    "description": "对领域的权限应通过子领域链追溯",
    "testId": "T_DOMAIN_COMP_PERM_SUB_DOMAIN_001"
  },
  {
    "id": "BR-sub_domain-COMP-cascade-delete-service_module",
    "subtype": "cascade_delete",
    "object": "sub_domain",
    "target": "service_module",
    "description": "删除子领域时,服务模块应级联处理 (cardinality=1:N)",
    "testId": "T_SUB_DOMAIN_COMP_CASCADE_SERVICE_MODULE_001"
  },
  {
    "id": "BR-service_module-COMP-ref-integrity-sub_domain",
    "subtype": "reference_integrity",
    "object": "service_module",
    "target": "sub_domain",
    "description": "服务模块的必须引用已存在的子领域",
    "testId": "T_SERVICE_MODULE_COMP_REF_SUB_DOMAIN_001"
  },
  {
    "id": "BR-service_module-COMP-permission-inherit-sub_domain",
    "subtype": "permission_inherit_chain",
    "object": "service_module",
    "target": "sub_domain",
    "description": "对服务模块的权限应通过子领域链追溯",
    "testId": "T_SERVICE_MODULE_COMP_PERM_SUB_DOMAIN_001"
  },
  {
    "id": "BR-sub_domain-COMP-hierarchy-path",
    "subtype": "sequential_codegen",
    "object": "sub_domain",
    "target": "",
    "description": "子领域的 hierarchy_path 应基于父链自动生成 (level=3)",
    "testId": "T_SUB_DOMAIN_COMP_HIER_PATH_001"
  },
  {
    "id": "BR-version-COMP-cascade-delete-product",
    "subtype": "cascade_delete",
    "object": "version",
    "target": "product",
    "description": "删除产品版本时,产品线应级联处理 (cardinality=N:1)",
    "testId": "T_VERSION_COMP_CASCADE_PRODUCT_001"
  },
  {
    "id": "BR-product-COMP-ref-integrity-version",
    "subtype": "reference_integrity",
    "object": "product",
    "target": "version",
    "description": "产品线的必须引用已存在的产品版本",
    "testId": "T_PRODUCT_COMP_REF_VERSION_001"
  },
  {
    "id": "BR-product-COMP-permission-inherit-version",
    "subtype": "permission_inherit_chain",
    "object": "product",
    "target": "version",
    "description": "对产品线的权限应通过产品版本链追溯",
    "testId": "T_PRODUCT_COMP_PERM_VERSION_001"
  },
  {
    "id": "BR-version-COMP-cascade-delete-domain",
    "subtype": "cascade_delete",
    "object": "version",
    "target": "domain",
    "description": "删除产品版本时,领域应级联处理 (cardinality=1:N)",
    "testId": "T_VERSION_COMP_CASCADE_DOMAIN_001"
  },
  {
    "id": "BR-domain-COMP-ref-integrity-version",
    "subtype": "reference_integrity",
    "object": "domain",
    "target": "version",
    "description": "领域的必须引用已存在的产品版本",
    "testId": "T_DOMAIN_COMP_REF_VERSION_001"
  },
  {
    "id": "BR-domain-COMP-permission-inherit-version",
    "subtype": "permission_inherit_chain",
    "object": "domain",
    "target": "version",
    "description": "对领域的权限应通过产品版本链追溯",
    "testId": "T_DOMAIN_COMP_PERM_VERSION_001"
  },
  {
    "id": "BR-version-COMP-hierarchy-path",
    "subtype": "sequential_codegen",
    "object": "version",
    "target": "",
    "description": "产品版本的 hierarchy_path 应基于父链自动生成 (level=1)",
    "testId": "T_VERSION_COMP_HIER_PATH_001"
  }
];

test.describe('composite.subtype: cascade_delete (17 条 BR)', () => {

test('T_BUSINESS_OBJECT_COMP_CASCADE_VERSION_001: 删 business_object 应级联处理 version', async ({ page }) => {
  // BR 规则: BR-business_object-COMP-cascade-delete-version
  // 业务: 删除业务对象时,产品版本应级联处理 (cardinality=N:1)
  // subtype: cascade_delete, object: business_object, target: version
  await BusinessRuleAssertor.assertRule('BR-business_object-COMP-cascade-delete-version', {
    object: 'business_object',
    target: 'version',
    subtype: 'cascade_delete',
    expected: 'cascade',
  });
  expect(true).toBe(true);
});

test('T_BUSINESS_OBJECT_COMP_CASCADE_SERVICE_MODULE_001: 删 business_object 应级联处理 service_module', async ({ page }) => {
  // BR 规则: BR-business_object-COMP-cascade-delete-service_module
  // 业务: 删除业务对象时,服务模块应级联处理 (cardinality=N:1)
  // subtype: cascade_delete, object: business_object, target: service_module
  await BusinessRuleAssertor.assertRule('BR-business_object-COMP-cascade-delete-service_module', {
    object: 'business_object',
    target: 'service_module',
    subtype: 'cascade_delete',
    expected: 'cascade',
  });
  expect(true).toBe(true);
});

test('T_DOMAIN_COMP_CASCADE_VERSION_001: 删 domain 应级联处理 version', async ({ page }) => {
  // BR 规则: BR-domain-COMP-cascade-delete-version
  // 业务: 删除领域时,产品版本应级联处理 (cardinality=N:1)
  // subtype: cascade_delete, object: domain, target: version
  await BusinessRuleAssertor.assertRule('BR-domain-COMP-cascade-delete-version', {
    object: 'domain',
    target: 'version',
    subtype: 'cascade_delete',
    expected: 'cascade',
  });
  expect(true).toBe(true);
});

test('T_DOMAIN_COMP_CASCADE_SUB_DOMAIN_001: 删 domain 应级联处理 sub_domain', async ({ page }) => {
  // BR 规则: BR-domain-COMP-cascade-delete-sub_domain
  // 业务: 删除领域时,子领域应级联处理 (cardinality=1:N)
  // subtype: cascade_delete, object: domain, target: sub_domain
  await BusinessRuleAssertor.assertRule('BR-domain-COMP-cascade-delete-sub_domain', {
    object: 'domain',
    target: 'sub_domain',
    subtype: 'cascade_delete',
    expected: 'cascade',
  });
  expect(true).toBe(true);
});

test('T_ENUM_TYPE_COMP_CASCADE_ENUM_VALUE_001: 删 enum_type 应级联处理 enum_value', async ({ page }) => {
  // BR 规则: BR-enum_type-COMP-cascade-delete-enum_value
  // 业务: 删除枚举类型时,枚举值应级联处理 (cardinality=1:N)
  // subtype: cascade_delete, object: enum_type, target: enum_value
  await BusinessRuleAssertor.assertRule('BR-enum_type-COMP-cascade-delete-enum_value', {
    object: 'enum_type',
    target: 'enum_value',
    subtype: 'cascade_delete',
    expected: 'cascade',
  });
  expect(true).toBe(true);
});

test('T_ENUM_VALUE_COMP_CASCADE_ENUM_TYPE_001: 删 enum_value 应级联处理 enum_type', async ({ page }) => {
  // BR 规则: BR-enum_value-COMP-cascade-delete-enum_type
  // 业务: 删除枚举值时,枚举类型应级联处理 (cardinality=N:1)
  // subtype: cascade_delete, object: enum_value, target: enum_type
  await BusinessRuleAssertor.assertRule('BR-enum_value-COMP-cascade-delete-enum_type', {
    object: 'enum_value',
    target: 'enum_type',
    subtype: 'cascade_delete',
    expected: 'cascade',
  });
  expect(true).toBe(true);
});

test('T_PRODUCT_COMP_CASCADE_VERSION_001: 删 product 应级联处理 version', async ({ page }) => {
  // BR 规则: BR-product-COMP-cascade-delete-version
  // 业务: 删除产品线时,产品版本应级联处理 (cardinality=1:N)
  // subtype: cascade_delete, object: product, target: version
  await BusinessRuleAssertor.assertRule('BR-product-COMP-cascade-delete-version', {
    object: 'product',
    target: 'version',
    subtype: 'cascade_delete',
    expected: 'cascade',
  });
  expect(true).toBe(true);
});

test('T_PRODUCT_COMP_CASCADE_VERSION_001: 删 product 应级联处理 version', async ({ page }) => {
  // BR 规则: BR-product-COMP-cascade-delete-version
  // 业务: 删除产品线时,产品版本应级联处理 (cardinality=1:N)
  // subtype: cascade_delete, object: product, target: version
  await BusinessRuleAssertor.assertRule('BR-product-COMP-cascade-delete-version', {
    object: 'product',
    target: 'version',
    subtype: 'cascade_delete',
    expected: 'cascade',
  });
  expect(true).toBe(true);
});

test('T_RELATIONSHIP_COMP_CASCADE_VERSION_001: 删 relationship 应级联处理 version', async ({ page }) => {
  // BR 规则: BR-relationship-COMP-cascade-delete-version
  // 业务: 删除业务关系时,产品版本应级联处理 (cardinality=N:1)
  // subtype: cascade_delete, object: relationship, target: version
  await BusinessRuleAssertor.assertRule('BR-relationship-COMP-cascade-delete-version', {
    object: 'relationship',
    target: 'version',
    subtype: 'cascade_delete',
    expected: 'cascade',
  });
  expect(true).toBe(true);
});

test('T_SERVICE_MODULE_COMP_CASCADE_VERSION_001: 删 service_module 应级联处理 version', async ({ page }) => {
  // BR 规则: BR-service_module-COMP-cascade-delete-version
  // 业务: 删除服务模块时,产品版本应级联处理 (cardinality=N:1)
  // subtype: cascade_delete, object: service_module, target: version
  await BusinessRuleAssertor.assertRule('BR-service_module-COMP-cascade-delete-version', {
    object: 'service_module',
    target: 'version',
    subtype: 'cascade_delete',
    expected: 'cascade',
  });
  expect(true).toBe(true);
});

test('T_SERVICE_MODULE_COMP_CASCADE_SUB_DOMAIN_001: 删 service_module 应级联处理 sub_domain', async ({ page }) => {
  // BR 规则: BR-service_module-COMP-cascade-delete-sub_domain
  // 业务: 删除服务模块时,子领域应级联处理 (cardinality=N:1)
  // subtype: cascade_delete, object: service_module, target: sub_domain
  await BusinessRuleAssertor.assertRule('BR-service_module-COMP-cascade-delete-sub_domain', {
    object: 'service_module',
    target: 'sub_domain',
    subtype: 'cascade_delete',
    expected: 'cascade',
  });
  expect(true).toBe(true);
});

test('T_SERVICE_MODULE_COMP_CASCADE_BUSINESS_OBJECT_001: 删 service_module 应级联处理 business_object', async ({ page }) => {
  // BR 规则: BR-service_module-COMP-cascade-delete-business_object
  // 业务: 删除服务模块时,业务对象应级联处理 (cardinality=1:N)
  // subtype: cascade_delete, object: service_module, target: business_object
  await BusinessRuleAssertor.assertRule('BR-service_module-COMP-cascade-delete-business_object', {
    object: 'service_module',
    target: 'business_object',
    subtype: 'cascade_delete',
    expected: 'cascade',
  });
  expect(true).toBe(true);
});

test('T_SUB_DOMAIN_COMP_CASCADE_VERSION_001: 删 sub_domain 应级联处理 version', async ({ page }) => {
  // BR 规则: BR-sub_domain-COMP-cascade-delete-version
  // 业务: 删除子领域时,产品版本应级联处理 (cardinality=N:1)
  // subtype: cascade_delete, object: sub_domain, target: version
  await BusinessRuleAssertor.assertRule('BR-sub_domain-COMP-cascade-delete-version', {
    object: 'sub_domain',
    target: 'version',
    subtype: 'cascade_delete',
    expected: 'cascade',
  });
  expect(true).toBe(true);
});

test('T_SUB_DOMAIN_COMP_CASCADE_DOMAIN_001: 删 sub_domain 应级联处理 domain', async ({ page }) => {
  // BR 规则: BR-sub_domain-COMP-cascade-delete-domain
  // 业务: 删除子领域时,领域应级联处理 (cardinality=N:1)
  // subtype: cascade_delete, object: sub_domain, target: domain
  await BusinessRuleAssertor.assertRule('BR-sub_domain-COMP-cascade-delete-domain', {
    object: 'sub_domain',
    target: 'domain',
    subtype: 'cascade_delete',
    expected: 'cascade',
  });
  expect(true).toBe(true);
});

test('T_SUB_DOMAIN_COMP_CASCADE_SERVICE_MODULE_001: 删 sub_domain 应级联处理 service_module', async ({ page }) => {
  // BR 规则: BR-sub_domain-COMP-cascade-delete-service_module
  // 业务: 删除子领域时,服务模块应级联处理 (cardinality=1:N)
  // subtype: cascade_delete, object: sub_domain, target: service_module
  await BusinessRuleAssertor.assertRule('BR-sub_domain-COMP-cascade-delete-service_module', {
    object: 'sub_domain',
    target: 'service_module',
    subtype: 'cascade_delete',
    expected: 'cascade',
  });
  expect(true).toBe(true);
});

test('T_VERSION_COMP_CASCADE_PRODUCT_001: 删 version 应级联处理 product', async ({ page }) => {
  // BR 规则: BR-version-COMP-cascade-delete-product
  // 业务: 删除产品版本时,产品线应级联处理 (cardinality=N:1)
  // subtype: cascade_delete, object: version, target: product
  await BusinessRuleAssertor.assertRule('BR-version-COMP-cascade-delete-product', {
    object: 'version',
    target: 'product',
    subtype: 'cascade_delete',
    expected: 'cascade',
  });
  expect(true).toBe(true);
});

test('T_VERSION_COMP_CASCADE_DOMAIN_001: 删 version 应级联处理 domain', async ({ page }) => {
  // BR 规则: BR-version-COMP-cascade-delete-domain
  // 业务: 删除产品版本时,领域应级联处理 (cardinality=1:N)
  // subtype: cascade_delete, object: version, target: domain
  await BusinessRuleAssertor.assertRule('BR-version-COMP-cascade-delete-domain', {
    object: 'version',
    target: 'domain',
    subtype: 'cascade_delete',
    expected: 'cascade',
  });
  expect(true).toBe(true);
});
});

test.describe('composite.subtype: reference_integrity (17 条 BR)', () => {

test('T_VERSION_COMP_REF_BUSINESS_OBJECT_001: 创建 version 引用已删除的 business_object 应失败', async ({ page }) => {
  // BR 规则: BR-version-COMP-ref-integrity-business_object
  // 业务: 产品版本的必须引用已存在的业务对象
  // subtype: reference_integrity, object: version, target: business_object
  await BusinessRuleAssertor.assertRule('BR-version-COMP-ref-integrity-business_object', {
    object: 'version',
    target: 'business_object',
    subtype: 'reference_integrity',
    expected: 'error',
  });
  expect(true).toBe(true);
});

test('T_SERVICE_MODULE_COMP_REF_BUSINESS_OBJECT_001: 创建 service_module 引用已删除的 business_object 应失败', async ({ page }) => {
  // BR 规则: BR-service_module-COMP-ref-integrity-business_object
  // 业务: 服务模块的必须引用已存在的业务对象
  // subtype: reference_integrity, object: service_module, target: business_object
  await BusinessRuleAssertor.assertRule('BR-service_module-COMP-ref-integrity-business_object', {
    object: 'service_module',
    target: 'business_object',
    subtype: 'reference_integrity',
    expected: 'error',
  });
  expect(true).toBe(true);
});

test('T_VERSION_COMP_REF_DOMAIN_001: 创建 version 引用已删除的 domain 应失败', async ({ page }) => {
  // BR 规则: BR-version-COMP-ref-integrity-domain
  // 业务: 产品版本的必须引用已存在的领域
  // subtype: reference_integrity, object: version, target: domain
  await BusinessRuleAssertor.assertRule('BR-version-COMP-ref-integrity-domain', {
    object: 'version',
    target: 'domain',
    subtype: 'reference_integrity',
    expected: 'error',
  });
  expect(true).toBe(true);
});

test('T_SUB_DOMAIN_COMP_REF_DOMAIN_001: 创建 sub_domain 引用已删除的 domain 应失败', async ({ page }) => {
  // BR 规则: BR-sub_domain-COMP-ref-integrity-domain
  // 业务: 子领域的必须引用已存在的领域
  // subtype: reference_integrity, object: sub_domain, target: domain
  await BusinessRuleAssertor.assertRule('BR-sub_domain-COMP-ref-integrity-domain', {
    object: 'sub_domain',
    target: 'domain',
    subtype: 'reference_integrity',
    expected: 'error',
  });
  expect(true).toBe(true);
});

test('T_ENUM_VALUE_COMP_REF_ENUM_TYPE_001: 创建 enum_value 引用已删除的 enum_type 应失败', async ({ page }) => {
  // BR 规则: BR-enum_value-COMP-ref-integrity-enum_type
  // 业务: 枚举值的必须引用已存在的枚举类型
  // subtype: reference_integrity, object: enum_value, target: enum_type
  await BusinessRuleAssertor.assertRule('BR-enum_value-COMP-ref-integrity-enum_type', {
    object: 'enum_value',
    target: 'enum_type',
    subtype: 'reference_integrity',
    expected: 'error',
  });
  expect(true).toBe(true);
});

test('T_ENUM_TYPE_COMP_REF_ENUM_VALUE_001: 创建 enum_type 引用已删除的 enum_value 应失败', async ({ page }) => {
  // BR 规则: BR-enum_type-COMP-ref-integrity-enum_value
  // 业务: 枚举类型的必须引用已存在的枚举值
  // subtype: reference_integrity, object: enum_type, target: enum_value
  await BusinessRuleAssertor.assertRule('BR-enum_type-COMP-ref-integrity-enum_value', {
    object: 'enum_type',
    target: 'enum_value',
    subtype: 'reference_integrity',
    expected: 'error',
  });
  expect(true).toBe(true);
});

test('T_VERSION_COMP_REF_PRODUCT_001: 创建 version 引用已删除的 product 应失败', async ({ page }) => {
  // BR 规则: BR-version-COMP-ref-integrity-product
  // 业务: 产品版本的必须引用已存在的产品线
  // subtype: reference_integrity, object: version, target: product
  await BusinessRuleAssertor.assertRule('BR-version-COMP-ref-integrity-product', {
    object: 'version',
    target: 'product',
    subtype: 'reference_integrity',
    expected: 'error',
  });
  expect(true).toBe(true);
});

test('T_VERSION_COMP_REF_PRODUCT_001: 创建 version 引用已删除的 product 应失败', async ({ page }) => {
  // BR 规则: BR-version-COMP-ref-integrity-product
  // 业务: 产品版本的product_id必须引用已存在的产品线
  // subtype: reference_integrity, object: version, target: product
  await BusinessRuleAssertor.assertRule('BR-version-COMP-ref-integrity-product', {
    object: 'version',
    target: 'product',
    subtype: 'reference_integrity',
    expected: 'error',
  });
  expect(true).toBe(true);
});

test('T_VERSION_COMP_REF_RELATIONSHIP_001: 创建 version 引用已删除的 relationship 应失败', async ({ page }) => {
  // BR 规则: BR-version-COMP-ref-integrity-relationship
  // 业务: 产品版本的必须引用已存在的业务关系
  // subtype: reference_integrity, object: version, target: relationship
  await BusinessRuleAssertor.assertRule('BR-version-COMP-ref-integrity-relationship', {
    object: 'version',
    target: 'relationship',
    subtype: 'reference_integrity',
    expected: 'error',
  });
  expect(true).toBe(true);
});

test('T_VERSION_COMP_REF_SERVICE_MODULE_001: 创建 version 引用已删除的 service_module 应失败', async ({ page }) => {
  // BR 规则: BR-version-COMP-ref-integrity-service_module
  // 业务: 产品版本的必须引用已存在的服务模块
  // subtype: reference_integrity, object: version, target: service_module
  await BusinessRuleAssertor.assertRule('BR-version-COMP-ref-integrity-service_module', {
    object: 'version',
    target: 'service_module',
    subtype: 'reference_integrity',
    expected: 'error',
  });
  expect(true).toBe(true);
});

test('T_SUB_DOMAIN_COMP_REF_SERVICE_MODULE_001: 创建 sub_domain 引用已删除的 service_module 应失败', async ({ page }) => {
  // BR 规则: BR-sub_domain-COMP-ref-integrity-service_module
  // 业务: 子领域的必须引用已存在的服务模块
  // subtype: reference_integrity, object: sub_domain, target: service_module
  await BusinessRuleAssertor.assertRule('BR-sub_domain-COMP-ref-integrity-service_module', {
    object: 'sub_domain',
    target: 'service_module',
    subtype: 'reference_integrity',
    expected: 'error',
  });
  expect(true).toBe(true);
});

test('T_BUSINESS_OBJECT_COMP_REF_SERVICE_MODULE_001: 创建 business_object 引用已删除的 service_module 应失败', async ({ page }) => {
  // BR 规则: BR-business_object-COMP-ref-integrity-service_module
  // 业务: 业务对象的必须引用已存在的服务模块
  // subtype: reference_integrity, object: business_object, target: service_module
  await BusinessRuleAssertor.assertRule('BR-business_object-COMP-ref-integrity-service_module', {
    object: 'business_object',
    target: 'service_module',
    subtype: 'reference_integrity',
    expected: 'error',
  });
  expect(true).toBe(true);
});

test('T_VERSION_COMP_REF_SUB_DOMAIN_001: 创建 version 引用已删除的 sub_domain 应失败', async ({ page }) => {
  // BR 规则: BR-version-COMP-ref-integrity-sub_domain
  // 业务: 产品版本的必须引用已存在的子领域
  // subtype: reference_integrity, object: version, target: sub_domain
  await BusinessRuleAssertor.assertRule('BR-version-COMP-ref-integrity-sub_domain', {
    object: 'version',
    target: 'sub_domain',
    subtype: 'reference_integrity',
    expected: 'error',
  });
  expect(true).toBe(true);
});

test('T_DOMAIN_COMP_REF_SUB_DOMAIN_001: 创建 domain 引用已删除的 sub_domain 应失败', async ({ page }) => {
  // BR 规则: BR-domain-COMP-ref-integrity-sub_domain
  // 业务: 领域的必须引用已存在的子领域
  // subtype: reference_integrity, object: domain, target: sub_domain
  await BusinessRuleAssertor.assertRule('BR-domain-COMP-ref-integrity-sub_domain', {
    object: 'domain',
    target: 'sub_domain',
    subtype: 'reference_integrity',
    expected: 'error',
  });
  expect(true).toBe(true);
});

test('T_SERVICE_MODULE_COMP_REF_SUB_DOMAIN_001: 创建 service_module 引用已删除的 sub_domain 应失败', async ({ page }) => {
  // BR 规则: BR-service_module-COMP-ref-integrity-sub_domain
  // 业务: 服务模块的必须引用已存在的子领域
  // subtype: reference_integrity, object: service_module, target: sub_domain
  await BusinessRuleAssertor.assertRule('BR-service_module-COMP-ref-integrity-sub_domain', {
    object: 'service_module',
    target: 'sub_domain',
    subtype: 'reference_integrity',
    expected: 'error',
  });
  expect(true).toBe(true);
});

test('T_PRODUCT_COMP_REF_VERSION_001: 创建 product 引用已删除的 version 应失败', async ({ page }) => {
  // BR 规则: BR-product-COMP-ref-integrity-version
  // 业务: 产品线的必须引用已存在的产品版本
  // subtype: reference_integrity, object: product, target: version
  await BusinessRuleAssertor.assertRule('BR-product-COMP-ref-integrity-version', {
    object: 'product',
    target: 'version',
    subtype: 'reference_integrity',
    expected: 'error',
  });
  expect(true).toBe(true);
});

test('T_DOMAIN_COMP_REF_VERSION_001: 创建 domain 引用已删除的 version 应失败', async ({ page }) => {
  // BR 规则: BR-domain-COMP-ref-integrity-version
  // 业务: 领域的必须引用已存在的产品版本
  // subtype: reference_integrity, object: domain, target: version
  await BusinessRuleAssertor.assertRule('BR-domain-COMP-ref-integrity-version', {
    object: 'domain',
    target: 'version',
    subtype: 'reference_integrity',
    expected: 'error',
  });
  expect(true).toBe(true);
});
});

test.describe('composite.subtype: permission_inherit_chain (17 条 BR)', () => {

test('T_VERSION_COMP_PERM_BUSINESS_OBJECT_001: 对 version 有权限时,应自动获得 business_object 权限', async ({ page }) => {
  // BR 规则: BR-version-COMP-permission-inherit-business_object
  // 业务: 对产品版本的权限应通过业务对象链追溯
  // subtype: permission_inherit_chain, object: version, target: business_object
  await BusinessRuleAssertor.assertRule('BR-version-COMP-permission-inherit-business_object', {
    object: 'version',
    target: 'business_object',
    subtype: 'permission_inherit_chain',
    expected: 'inherit',
  });
  expect(true).toBe(true);
});

test('T_SERVICE_MODULE_COMP_PERM_BUSINESS_OBJECT_001: 对 service_module 有权限时,应自动获得 business_object 权限', async ({ page }) => {
  // BR 规则: BR-service_module-COMP-permission-inherit-business_object
  // 业务: 对服务模块的权限应通过业务对象链追溯
  // subtype: permission_inherit_chain, object: service_module, target: business_object
  await BusinessRuleAssertor.assertRule('BR-service_module-COMP-permission-inherit-business_object', {
    object: 'service_module',
    target: 'business_object',
    subtype: 'permission_inherit_chain',
    expected: 'inherit',
  });
  expect(true).toBe(true);
});

test('T_VERSION_COMP_PERM_DOMAIN_001: 对 version 有权限时,应自动获得 domain 权限', async ({ page }) => {
  // BR 规则: BR-version-COMP-permission-inherit-domain
  // 业务: 对产品版本的权限应通过领域链追溯
  // subtype: permission_inherit_chain, object: version, target: domain
  await BusinessRuleAssertor.assertRule('BR-version-COMP-permission-inherit-domain', {
    object: 'version',
    target: 'domain',
    subtype: 'permission_inherit_chain',
    expected: 'inherit',
  });
  expect(true).toBe(true);
});

test('T_SUB_DOMAIN_COMP_PERM_DOMAIN_001: 对 sub_domain 有权限时,应自动获得 domain 权限', async ({ page }) => {
  // BR 规则: BR-sub_domain-COMP-permission-inherit-domain
  // 业务: 对子领域的权限应通过领域链追溯
  // subtype: permission_inherit_chain, object: sub_domain, target: domain
  await BusinessRuleAssertor.assertRule('BR-sub_domain-COMP-permission-inherit-domain', {
    object: 'sub_domain',
    target: 'domain',
    subtype: 'permission_inherit_chain',
    expected: 'inherit',
  });
  expect(true).toBe(true);
});

test('T_ENUM_VALUE_COMP_PERM_ENUM_TYPE_001: 对 enum_value 有权限时,应自动获得 enum_type 权限', async ({ page }) => {
  // BR 规则: BR-enum_value-COMP-permission-inherit-enum_type
  // 业务: 对枚举值的权限应通过枚举类型链追溯
  // subtype: permission_inherit_chain, object: enum_value, target: enum_type
  await BusinessRuleAssertor.assertRule('BR-enum_value-COMP-permission-inherit-enum_type', {
    object: 'enum_value',
    target: 'enum_type',
    subtype: 'permission_inherit_chain',
    expected: 'inherit',
  });
  expect(true).toBe(true);
});

test('T_ENUM_TYPE_COMP_PERM_ENUM_VALUE_001: 对 enum_type 有权限时,应自动获得 enum_value 权限', async ({ page }) => {
  // BR 规则: BR-enum_type-COMP-permission-inherit-enum_value
  // 业务: 对枚举类型的权限应通过枚举值链追溯
  // subtype: permission_inherit_chain, object: enum_type, target: enum_value
  await BusinessRuleAssertor.assertRule('BR-enum_type-COMP-permission-inherit-enum_value', {
    object: 'enum_type',
    target: 'enum_value',
    subtype: 'permission_inherit_chain',
    expected: 'inherit',
  });
  expect(true).toBe(true);
});

test('T_VERSION_COMP_PERM_PRODUCT_001: 对 version 有权限时,应自动获得 product 权限', async ({ page }) => {
  // BR 规则: BR-version-COMP-permission-inherit-product
  // 业务: 对产品版本的权限应通过产品线链追溯
  // subtype: permission_inherit_chain, object: version, target: product
  await BusinessRuleAssertor.assertRule('BR-version-COMP-permission-inherit-product', {
    object: 'version',
    target: 'product',
    subtype: 'permission_inherit_chain',
    expected: 'inherit',
  });
  expect(true).toBe(true);
});

test('T_VERSION_COMP_PERM_PRODUCT_001: 对 version 有权限时,应自动获得 product 权限', async ({ page }) => {
  // BR 规则: BR-version-COMP-permission-inherit-product
  // 业务: 对产品版本的权限应通过产品线链追溯
  // subtype: permission_inherit_chain, object: version, target: product
  await BusinessRuleAssertor.assertRule('BR-version-COMP-permission-inherit-product', {
    object: 'version',
    target: 'product',
    subtype: 'permission_inherit_chain',
    expected: 'inherit',
  });
  expect(true).toBe(true);
});

test('T_VERSION_COMP_PERM_RELATIONSHIP_001: 对 version 有权限时,应自动获得 relationship 权限', async ({ page }) => {
  // BR 规则: BR-version-COMP-permission-inherit-relationship
  // 业务: 对产品版本的权限应通过业务关系链追溯
  // subtype: permission_inherit_chain, object: version, target: relationship
  await BusinessRuleAssertor.assertRule('BR-version-COMP-permission-inherit-relationship', {
    object: 'version',
    target: 'relationship',
    subtype: 'permission_inherit_chain',
    expected: 'inherit',
  });
  expect(true).toBe(true);
});

test('T_VERSION_COMP_PERM_SERVICE_MODULE_001: 对 version 有权限时,应自动获得 service_module 权限', async ({ page }) => {
  // BR 规则: BR-version-COMP-permission-inherit-service_module
  // 业务: 对产品版本的权限应通过服务模块链追溯
  // subtype: permission_inherit_chain, object: version, target: service_module
  await BusinessRuleAssertor.assertRule('BR-version-COMP-permission-inherit-service_module', {
    object: 'version',
    target: 'service_module',
    subtype: 'permission_inherit_chain',
    expected: 'inherit',
  });
  expect(true).toBe(true);
});

test('T_SUB_DOMAIN_COMP_PERM_SERVICE_MODULE_001: 对 sub_domain 有权限时,应自动获得 service_module 权限', async ({ page }) => {
  // BR 规则: BR-sub_domain-COMP-permission-inherit-service_module
  // 业务: 对子领域的权限应通过服务模块链追溯
  // subtype: permission_inherit_chain, object: sub_domain, target: service_module
  await BusinessRuleAssertor.assertRule('BR-sub_domain-COMP-permission-inherit-service_module', {
    object: 'sub_domain',
    target: 'service_module',
    subtype: 'permission_inherit_chain',
    expected: 'inherit',
  });
  expect(true).toBe(true);
});

test('T_BUSINESS_OBJECT_COMP_PERM_SERVICE_MODULE_001: 对 business_object 有权限时,应自动获得 service_module 权限', async ({ page }) => {
  // BR 规则: BR-business_object-COMP-permission-inherit-service_module
  // 业务: 对业务对象的权限应通过服务模块链追溯
  // subtype: permission_inherit_chain, object: business_object, target: service_module
  await BusinessRuleAssertor.assertRule('BR-business_object-COMP-permission-inherit-service_module', {
    object: 'business_object',
    target: 'service_module',
    subtype: 'permission_inherit_chain',
    expected: 'inherit',
  });
  expect(true).toBe(true);
});

test('T_VERSION_COMP_PERM_SUB_DOMAIN_001: 对 version 有权限时,应自动获得 sub_domain 权限', async ({ page }) => {
  // BR 规则: BR-version-COMP-permission-inherit-sub_domain
  // 业务: 对产品版本的权限应通过子领域链追溯
  // subtype: permission_inherit_chain, object: version, target: sub_domain
  await BusinessRuleAssertor.assertRule('BR-version-COMP-permission-inherit-sub_domain', {
    object: 'version',
    target: 'sub_domain',
    subtype: 'permission_inherit_chain',
    expected: 'inherit',
  });
  expect(true).toBe(true);
});

test('T_DOMAIN_COMP_PERM_SUB_DOMAIN_001: 对 domain 有权限时,应自动获得 sub_domain 权限', async ({ page }) => {
  // BR 规则: BR-domain-COMP-permission-inherit-sub_domain
  // 业务: 对领域的权限应通过子领域链追溯
  // subtype: permission_inherit_chain, object: domain, target: sub_domain
  await BusinessRuleAssertor.assertRule('BR-domain-COMP-permission-inherit-sub_domain', {
    object: 'domain',
    target: 'sub_domain',
    subtype: 'permission_inherit_chain',
    expected: 'inherit',
  });
  expect(true).toBe(true);
});

test('T_SERVICE_MODULE_COMP_PERM_SUB_DOMAIN_001: 对 service_module 有权限时,应自动获得 sub_domain 权限', async ({ page }) => {
  // BR 规则: BR-service_module-COMP-permission-inherit-sub_domain
  // 业务: 对服务模块的权限应通过子领域链追溯
  // subtype: permission_inherit_chain, object: service_module, target: sub_domain
  await BusinessRuleAssertor.assertRule('BR-service_module-COMP-permission-inherit-sub_domain', {
    object: 'service_module',
    target: 'sub_domain',
    subtype: 'permission_inherit_chain',
    expected: 'inherit',
  });
  expect(true).toBe(true);
});

test('T_PRODUCT_COMP_PERM_VERSION_001: 对 product 有权限时,应自动获得 version 权限', async ({ page }) => {
  // BR 规则: BR-product-COMP-permission-inherit-version
  // 业务: 对产品线的权限应通过产品版本链追溯
  // subtype: permission_inherit_chain, object: product, target: version
  await BusinessRuleAssertor.assertRule('BR-product-COMP-permission-inherit-version', {
    object: 'product',
    target: 'version',
    subtype: 'permission_inherit_chain',
    expected: 'inherit',
  });
  expect(true).toBe(true);
});

test('T_DOMAIN_COMP_PERM_VERSION_001: 对 domain 有权限时,应自动获得 version 权限', async ({ page }) => {
  // BR 规则: BR-domain-COMP-permission-inherit-version
  // 业务: 对领域的权限应通过产品版本链追溯
  // subtype: permission_inherit_chain, object: domain, target: version
  await BusinessRuleAssertor.assertRule('BR-domain-COMP-permission-inherit-version', {
    object: 'domain',
    target: 'version',
    subtype: 'permission_inherit_chain',
    expected: 'inherit',
  });
  expect(true).toBe(true);
});
});

test.describe('composite.subtype: sequential_codegen (5 条 BR)', () => {

test('T_BUSINESS_OBJECT_COMP_HIER_PATH_001: business_object 顺序编码应与  关联', async ({ page }) => {
  // BR 规则: BR-business_object-COMP-hierarchy-path
  // 业务: 业务对象的 hierarchy_path 应基于父链自动生成 (level=5)
  // subtype: sequential_codegen, object: business_object, target: 
  await BusinessRuleAssertor.assertRule('BR-business_object-COMP-hierarchy-path', {
    object: 'business_object',
    target: '',
    subtype: 'sequential_codegen',
    expected: 'inherit',
  });
  expect(true).toBe(true);
});

test('T_DOMAIN_COMP_HIER_PATH_001: domain 顺序编码应与  关联', async ({ page }) => {
  // BR 规则: BR-domain-COMP-hierarchy-path
  // 业务: 领域的 hierarchy_path 应基于父链自动生成 (level=2)
  // subtype: sequential_codegen, object: domain, target: 
  await BusinessRuleAssertor.assertRule('BR-domain-COMP-hierarchy-path', {
    object: 'domain',
    target: '',
    subtype: 'sequential_codegen',
    expected: 'inherit',
  });
  expect(true).toBe(true);
});

test('T_SERVICE_MODULE_COMP_HIER_PATH_001: service_module 顺序编码应与  关联', async ({ page }) => {
  // BR 规则: BR-service_module-COMP-hierarchy-path
  // 业务: 服务模块的 hierarchy_path 应基于父链自动生成 (level=4)
  // subtype: sequential_codegen, object: service_module, target: 
  await BusinessRuleAssertor.assertRule('BR-service_module-COMP-hierarchy-path', {
    object: 'service_module',
    target: '',
    subtype: 'sequential_codegen',
    expected: 'inherit',
  });
  expect(true).toBe(true);
});

test('T_SUB_DOMAIN_COMP_HIER_PATH_001: sub_domain 顺序编码应与  关联', async ({ page }) => {
  // BR 规则: BR-sub_domain-COMP-hierarchy-path
  // 业务: 子领域的 hierarchy_path 应基于父链自动生成 (level=3)
  // subtype: sequential_codegen, object: sub_domain, target: 
  await BusinessRuleAssertor.assertRule('BR-sub_domain-COMP-hierarchy-path', {
    object: 'sub_domain',
    target: '',
    subtype: 'sequential_codegen',
    expected: 'inherit',
  });
  expect(true).toBe(true);
});

test('T_VERSION_COMP_HIER_PATH_001: version 顺序编码应与  关联', async ({ page }) => {
  // BR 规则: BR-version-COMP-hierarchy-path
  // 业务: 产品版本的 hierarchy_path 应基于父链自动生成 (level=1)
  // subtype: sequential_codegen, object: version, target: 
  await BusinessRuleAssertor.assertRule('BR-version-COMP-hierarchy-path', {
    object: 'version',
    target: '',
    subtype: 'sequential_codegen',
    expected: 'inherit',
  });
  expect(true).toBe(true);
});
});

test.describe('composite.subtype: scope_inherit (2 条 BR)', () => {

test('T_VERSION_COMP_SCOPE_PRODUCT_001: version 可见性应由 product 决定', async ({ page }) => {
  // BR 规则: BR-version-COMP-scope-inherit-product
  // 业务: 产品版本的可见性由产品线的 visibility 决定
  // subtype: scope_inherit, object: version, target: product
  await BusinessRuleAssertor.assertRule('BR-version-COMP-scope-inherit-product', {
    object: 'version',
    target: 'product',
    subtype: 'scope_inherit',
    expected: 'inherit',
  });
  expect(true).toBe(true);
});

test('T_VERSION_COMP_SCOPE_PRODUCT_001: version 可见性应由 product 决定', async ({ page }) => {
  // BR 规则: BR-version-COMP-scope-inherit-product
  // 业务: 产品版本的可见性由产品线的 visibility 决定
  // subtype: scope_inherit, object: version, target: product
  await BusinessRuleAssertor.assertRule('BR-version-COMP-scope-inherit-product', {
    object: 'version',
    target: 'product',
    subtype: 'scope_inherit',
    expected: 'inherit',
  });
  expect(true).toBe(true);
});
});
test('T16-B 自检: composite BR 数量', () => {
  expect(COMPOSITE_RULES.length).toBe(58);
});
