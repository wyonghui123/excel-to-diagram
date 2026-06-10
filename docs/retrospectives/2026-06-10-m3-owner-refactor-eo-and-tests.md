# M3 报告: effective_owner_id 派生 + 8 个测试用例

**日期**: 2026-06-10
**版本**: v1.1.0-m3
**范围**: FR-006 (effective_owner_id 派生) + 8 测试用例
**状态**: ✅ 全部完成 + 54 测试全过

---

## 1. effective_owner_id 派生 (FR-006)

### 1.1 实施位置

| 文件 | 改动 |
|------|------|
| [enrichment_engine.py](file:///d:/filework/excel-to-diagram/meta/core/enrichment_engine.py) | + `EFFECTIVE_OWNER_CHAIN` 配置; + `get_effective_owner_for_items()` 函数 |
| [query_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/query_interceptor.py) | + `_inject_effective_owner()` 方法, 在 `_enrich_records` 之后调用 |

### 1.2 链路定义

```python
EFFECTIVE_OWNER_CHAIN = {
    'product':         [],                                              # 自身
    'version':         [('product_id', 'product')],                     # 1 跳
    'domain':          [('version_id', 'version')],                     # 2 跳
    'sub_domain':      [('domain_id', 'domain')],                       # 3 跳
    'service_module':  [('sub_domain_id', 'sub_domain')],               # 4 跳
    'business_object': [('service_module_id', 'service_module')],       # 5 跳
    'relationship':    [('version_id', 'version')],                     # 2 跳
}
```

### 1.3 性能策略

- **一次 SQL JOIN 整条链** (用 IN clause), O(1) 次查询
- business_object 是最深 5 跳, 一次 SQL 拿全部数据
- 索引建议: `products(visibility)`, `products(owner_id)` 已有

### 1.4 API 验证结果

```
=== product (count=12) ===
  product_29: owner_id=1, effective_owner_id=1          ← 一致
  product_1: owner_id=None, effective_owner_id=None      ← 一致
  product_24: owner_id=1223, effective_owner_id=1223     ← 一致
  ...

=== version (count=19) ===
  version_25: owner_id=None, effective_owner_id=1       ← 从 product 派生
  version_23: owner_id=None, effective_owner_id=1
  version_17: owner_id=None, effective_owner_id=1223
  ...

=== domain (count=20) ===
  domain_320: owner_id=None, effective_owner_id=None     ← 孤儿 (无 version)
  domain_319: owner_id=None, effective_owner_id=1223
  ...
```

## 2. 8 个测试类 (54 测试用例)

[test_owner_refactor_v1_1.py](file:///d:/filework/excel-to-diagram/meta/tests/test_owner_refactor_v1_1.py)

| 类 | 测试数 | 覆盖 |
|---|-------|------|
| `TestChildNoOwnerId` | 6 | TBD-1: child 无 owner_id 字段定义 + 无 owner_aspect 引用 |
| `TestProductKeepsOwnerId` | 4 | FR-002/TBD-7: product 保留 owner_id + visibility 字段 |
| `TestScopeDerivedFromProduct` | 7 | TBD-8: child scope 派生自 product |
| `TestAutoOwnerDisabled` | 7 | TBD-9: child.auto_owner=false, product.auto_owner=true |
| `TestAutoPermissionAdmin` | 7 | TBD-11: 创建者天然 admin |
| `TestTransferDropsAdmin` | 2 | TBD-15: transfer_keep_permissions=false |
| `TestVersionNoVisibility` | 2 | TBD-7: version.yaml 无 visibility 字段 + publish_version action |
| `TestDBSchemaConsistency` | 13 | FR-001/002/003: DB schema 100% 与 yaml 一致 |
| `TestEffectiveOwnerEnrichment` | 4 | FR-006: effective_owner_id 链路定义 + 安全降级 |
| `TestOverallConsistency` | 2 | 7 个对象都有 authorization + deletability 配置 |
| **总计** | **54** | **8 个 TBD 决策 + 3 个 FR** |

### 2.1 测试结果

```
============================= 54 passed in 4.59s ==============================
```

**所有测试通过** ✅

## 3. 关键修复 (M3 期间)

### 3.1 dev-login 500 误报
- **现象**: `/api/v2/auth/dev-login` 报 500 NotFound
- **根因**: 路径错了 — dev-login 实际在 `/api/v1/auth/dev-login`
- **修复**: 用正确路径登录 OK, 后端代码无需修改

### 3.2 DB schema 校验问题
- **现象**: TestDBSchemaConsistency 失败, 显示 child 仍有 owner_id 列
- **根因**: test.py 跑测试前会用 `architecture.db.baseline` 恢复 DB, baseline 是 v1.0 状态
- **修复**: 测试用 `tmp_path_factory` + inline 跑迁移脚本, 不依赖 main DB

### 3.3 migration script 改进
- **改进**: 迁移脚本现在支持 `MIGRATION_TARGET_DB` 环境变量覆盖 SOURCE_DB
- **用途**: 测试时跑 inline 迁移 (不依赖命令行)

## 4. 改动文件

| 文件 | 改动 |
|------|------|
| [enrichment_engine.py](file:///d:/filework/excel-to-diagram/meta/core/enrichment_engine.py) | + EFFECTIVE_OWNER_CHAIN (8 行) + get_effective_owner_for_items (110 行) |
| [query_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/query_interceptor.py) | + _inject_effective_owner (25 行) |
| [manage_api.py](file:///d:/filework/excel-to-diagram/meta/api/manage_api.py) | 修: 只对 product 设 owner_id (M2 修的) |
| [migrate_v1_1_owner_refactor.py](file:///d:/filework/excel-to-diagram/meta/scripts/migrate_v1_1_owner_refactor.py) | + MIGRATION_TARGET_DB env support |
| [test_owner_refactor_v1_1.py](file:///d:/filework/excel-to-diagram/meta/tests/test_owner_refactor_v1_1.py) | + 8 个测试类, 54 用例 |

## 5. 完整链路验证 (M1+M2+M3)

```
1. yaml (M1):
   product.yaml: visibility 字段 ✓
   5 child yamls: 无 owner_id 字段, 无 owner_aspect, 无 visibility 字段 ✓
   authorization: scope 派生自 product, auto_owner=false, transfer_keep_permissions=false ✓

2. DB (M2):
   products: visibility ✓, owner_id 保留 ✓
   5 child tables: 无 owner_id, 无 visibility ✓
   relationships: 无变化 ✓

3. API (M3):
   product: owner_id + effective_owner_id 一致 ✓
   child: effective_owner_id 从 product 派生 ✓
   dev-login 200 OK (用 /api/v1/auth/dev-login) ✓

4. 测试 (M3):
   54 passed in 4.59s ✓
```

## 6. 待办 (M4)

- [ ] 前端显示 effective_owner_id (DetailPage.vue / ObjectPageShell.vue)
- [ ] spec 文档更新 + commit M1+M2+M3
- [ ] 给团队 review

---

**M3 完成. v1.1 owner refactor 全套已实施 + 验证. 等用户 commit.**
