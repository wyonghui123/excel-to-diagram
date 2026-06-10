# M1 迁移报告: owner 字段重构 (yaml 层面)

**日期**: 2026-06-10
**版本**: v1.1.0-m1
**范围**: FR-008 + FR-004 (改 6 个 yaml, 不动 DB)
**状态**: ✅ 完成 + 验证通过

---

## 1. 改动汇总

| 文件 | 改动 | 验证 |
|------|------|------|
| `meta/schemas/product.yaml` | + visibility 字段 (private/public); scope 改 visibility-aware; `transfer_keep_permissions: false` | ✅ |
| `meta/schemas/version.yaml` | - owner_id 字段 + - visibility 字段; 移除 `owner_aspect`; scope 派生自 product | ✅ |
| `meta/schemas/domain.yaml` | - owner_id 字段; 移除 `owner_aspect`; scope 派生自 product | ✅ |
| `meta/schemas/sub_domain.yaml` | - owner_id 字段; 移除 `owner_aspect`; scope 派生自 product | ✅ |
| `meta/schemas/service_module.yaml` | - owner_id 字段; 移除 `owner_aspect`; scope 派生自 product | ✅ |
| `meta/schemas/business_object.yaml` | - owner_id 字段; 移除 `owner_aspect`; scope 派生自 product | ✅ |
| `meta/schemas/relationship.yaml` | scope 派生自 product (relationship 本无 owner_id 字段) | ✅ |

## 2. 字段分布 (M1 实施后)

| 对象 | owner_id | visibility | auto_owner | transfer_keep | scope 来源 |
|------|---------|-----------|------------|---------------|-----------|
| **product** | ✅ 保留 | ✅ 新增 (private/public) | ✅ True | ❌ **False** (TBD-15) | `visibility='public' OR owner_id=$user` |
| **version** | ❌ 删除 | ❌ 上移 | ❌ False | ❌ False | `product_id IN (SELECT ... FROM products WHERE visibility='public' OR owner_id=$user)` |
| **domain** | ❌ 删除 | ❌ | ❌ False | ❌ False | `version_id IN (SELECT v.id ... JOIN products p ...)` |
| **sub_domain** | ❌ 删除 | ❌ | ❌ False | ❌ False | `domain_id IN (SELECT d.id ... JOIN products p ...)` |
| **service_module** | ❌ 删除 | ❌ | ❌ False | ❌ False | `sub_domain_id IN (SELECT sd.id ... JOIN products p ...)` |
| **business_object** | ❌ 删除 | ❌ | ❌ False | ❌ False | `service_module_id IN (SELECT sm.id ... JOIN products p ...)` |
| **relationship** | (本来就没) | ❌ | ❌ False | ❌ False | `version_id IN (SELECT v.id ... JOIN products p ...)` |

## 3. 关键决策落实

| TBD | 决策 | 实施位置 |
|-----|------|---------|
| TBD-1 | child 不保留 owner | 5 个 yaml 删 owner_id + 移除 owner_aspect |
| TBD-7 | visibility 上移到 product | product.yaml 加 visibility 字段 |
| TBD-8 | child scope 派生自 product | 6 个 yaml 改 scope 表达式 |
| TBD-9 | 关闭 auto_owner | 6 个 yaml auto_owner: false |
| TBD-10 | 保留 inherit_to_children | 6 个 yaml inherit_to_children: true |
| TBD-11 | 保留 auto_permission=admin | 6 个 yaml auto_permission: admin |
| TBD-15 | transfer 不保留原 owner 权限 | product.yaml transfer_keep_permissions: false |

## 4. 验证结果

### 4.1 yaml 加载验证
```
Loaded 39 objects from D:\filework\excel-to-diagram\meta\schemas
=== M1 真实加载验证 ===
product:OK(owner=True,vis=True,auto_owner=True)
version:OK(owner=False,vis=False,auto_owner=False)
domain:OK(owner=False,vis=False,auto_owner=False)
sub_domain:OK(owner=False,vis=False,auto_owner=False)
service_module:OK(owner=False,vis=False,auto_owner=False)
business_object:OK(owner=False,vis=False,auto_owner=False)
relationship:OK(owner=False,vis=False,auto_owner=False)
[OK] M1 全部验证通过!
```

### 4.2 NFR-003 grep 验证
- `id: owner_id` 字段定义仅在 `aspects.yaml` (共享 aspect) 和 `shared_properties.yaml` 出现
- 6 个业务 yaml 中已无 `id: owner_id` 字段定义
- 6 个业务 yaml 中残留的 `owner_id` 字符串都是 v1.1 删除的注释说明

## 5. ⚠️ 实施过程中发现并修复

1. **遗漏 owner_aspect 引用**: 5 个 child yaml 顶部仍引用 `owner_aspect`,这会在 yaml_loader 合并 aspect 时把 owner_id 字段"加回来"。**已修复**: 移除 owner_aspect 引用。
2. **遗漏 publish_version action**: version.yaml 的 `state_transition` 引用 visibility 字段。**已修复**: 整个 action 移除。
3. **遗漏 visibility 引用**: list 列、detail facets、form sections 中多处引用 visibility。**已修复**: 全部移除。

## 6. 不变项 (M1 不动)

- ❌ 数据库 schema (M2 处理)
- ❌ `meta/core/interceptors/owner_permission_interceptor.py` (yaml 驱动, 无需改)
- ❌ API endpoint 行为 (M2 迁移前, 字段还在, 不会报错)
- ❌ 前端组件 (M3 处理 effective_owner_id 派生显示)

## 7. 风险与回滚

### 风险
| 风险 | 概率 | 影响 | 状态 |
|------|------|------|------|
| API 调用传 owner_id 字段无效果 | 100% | 低 (字段被忽略) | 可接受, M2 删除列后才彻底 |
| visibility 字段前端表单仍显示 version 的 | 中 | 中 | UI 提示问题, 不影响数据 |
| scope 子查询性能问题 | 中 | 中 | M3 实施时 EXPLAIN 验证 |

### 回滚
```bash
git checkout HEAD -- meta/schemas/{product,version,domain,sub_domain,service_module,business_object,relationship}.yaml
```

## 8. 后续 M2/M3 待办

- [ ] **M2**: 数据库迁移 (维护窗口, ~30 min)
  - products 加 visibility 字段
  - 6 张 child 表 DROP owner_id 列
  - versions 表 DROP visibility 列
- [ ] **M3**: 实现 effective_owner_id 派生 (后端 + 前端)
- [ ] **M3**: 8 个测试用例 (test_owner_refactor_v1_1.py)
- [ ] **M4**: 文档更新

---

**M1 完成, 等待用户决定是否进入 M2 维护窗口。**
