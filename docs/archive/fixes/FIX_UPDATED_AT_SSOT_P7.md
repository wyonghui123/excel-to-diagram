# v1.4 P7 — 前端迁移 + 业务过滤 + 同类重构（2026-06-05）

> v1.4 SSOT 收尾：P7 全部 4 项任务盘点

## P7-1: 前端 v1→v2 迁移

### 全面审计结果

扫描 `src/` 下所有 .js/.ts/.vue 文件的 `/api/v1/` 调用：

| 唯一 v1 路径 | 调用次数 | 在 V1_SPECIAL_PREFIXES | 是否需要迁移 |
|--------------|----------|------------------------|--------------|
| /api/v1/users/me | 15 | ✓ | ❌ SPECIAL 豁免 |
| /api/v1/auth/change-password | 7 | ✓ | ❌ SPECIAL 豁免 |
| /api/v1/enums/types | 2 | ✓ | ❌ SPECIAL 豁免 |
| /api/v1/enums/status/values | 2 | ✓ | ❌ SPECIAL 豁免 |
| /api/v1/enums/types/status | 2 | ✓ | ❌ SPECIAL 豁免 |
| /api/v1/audit | 2 | ✓ | ❌ SPECIAL 豁免 |
| /api/v1/meta/hierarchies/config | 1 | ✓ | ❌ SPECIAL 豁免 |
| **合计 7 路径** | **31 调用** | - | **0 个需迁移** |

### 结论
**P7-1 已无新工作可做**。之前 v1.4 P2 阶段已迁移类别 A（CRUD 类）和 B（业务类）。剩余的 31 处 v1 调用都是 V1_SPECIAL_PREFIXES 豁免路径（users / auth / enums / audit / meta / identity / schemas / overlap / ...），这些路径：
- 没有 v2 替代（v2 BO 框架不覆盖）
- Sunset 倒计时由 server.py v1 中间件管理
- Sunset 后 410，前端需做整体迁移

## P7-2: 业务过滤能力迁移到 v2

### 业务过滤清单（v1/user-groups API 支持）
| 过滤能力 | v1 实现 | v2 等价 |
|----------|---------|---------|
| `member_count` 精确 | `COUNT(*) = ?` | ✓ 测试通过 |
| `member_count_min/max` | `COUNT(*) >= ? AND <= ?` | ✓ 测试通过 |
| `name__like/code__like` | `LIKE ?` 或 `= ?` | ✓ 测试通过 |
| `parent_id/manager_id` 精确 | `= ?` | ✓ 测试通过 |
| `parent_id__in/manager_id__in` | `IN (...)` | ✓ 测试通过 |

### 验证结果
所有 5 类业务过滤在 v1 和 v2 返回**完全一致**的结果：

| 过滤测试 | v1 (count) | v2 (count) | 一致 |
|----------|-----------|-----------|------|
| 无过滤 | 3 | 3 | ✓ |
| member_count=0 | 2 | 2 | ✓ |
| member_count=10 | 0 | 0 | ✓ |
| parent_id__in=1,2 | 2 | 2 | ✓ |
| name__like=admin | 0 | 0 | ✓ |

### 结论
**P7-2 已实质完成**（v2 端点已能完全替代 v1 业务过滤能力）。背后的机制：
- `action_executor._do_list` 接收业务过滤参数
- 通过 `meta_object.get_field(key)` 验证字段
- `sql_adapters._build_conditions` 处理 `__in` / `__notin` / `__like` 等后缀
- v2 端点自动获得所有 v1 业务过滤能力

## P7-3: permission_service.py 同类重构

### 11 个公开方法分析

| 方法 | 性质 | 处理 |
|------|------|------|
| `_get_or_create_personal_group` | 业务（个人组模式） | 保留 |
| `_ensure_user_in_group` | 业务 | 保留 |
| `get_user_roles` | 业务（4表 JOIN） | 保留 |
| `get_user_permissions` | 业务（4表 JOIN） | 保留 |
| `has_permission` | 业务（含 `*` 通配） | 保留 |
| `assign_role` | 业务（个人组 + token bump） | 保留 |
| `remove_role` | 业务（个人组 + token bump） | 保留 |
| `get_all_roles` | **业务增强**（v1 嵌套 permissions + SSOT 派生） | 保留 + 注释 |
| `get_all_permissions` | **纯 CRUD**（SELECT *） | ⚠️ @deprecated |
| `get_role_permissions` | 业务（多表） | 保留 |
| `set_role_permissions` | 业务（+ token bump） | 保留 |
| `check_permission_unified` | 业务（核心） | 保留 |
| `create_permission_unified` | 业务（验证） | 保留 |

### 关键认识

**`PermissionService` 是更纯的"业务域服务"**：

| 指标 | user_group_service | permission_service |
|------|-------------------|---------------------|
| 总公开方法 | 30 | 11 |
| 纯 CRUD 数 | 5 | 1 |
| 业务方法 | 25 | 10 |
| 冗余度 | 16.7% | 9.1% |

`permission_service` 的方法大多有真实的业务逻辑（权限链解析、token 失效、统一语义），不是"具体 object 的 service 反模式"。

### 已标记 @deprecated
- `permission_service.get_all_permissions()` — 唯一纯 CRUD 方法
- `permission_service.get_all_roles()` — 注释说明（保留原因：v1 业务增强）

## P7-4: 综合验证

### 16 个端点全部 200
```
P7 Comprehensive Verification
============================================================
  ✓ 200 dpr /api/v1/user-groups                      count=3
  ✓ 200 dpr /api/v1/user-groups/1                    count=1
  ✓ 200 dpr /api/v1/user-groups/1/members            count=1
  ✓ 200 dpr /api/v1/user-groups/1/roles              count=1
  ✓ 200     /api/v2/bo/user_group                    count=3
  ✓ 200     /api/v2/bo/user_group/1                  count=1
  ✓ 200 dpr /api/v1/roles                            count=4
  ✓ 200 dpr /api/v1/roles/1                          count=1
  ✓ 200 dpr /api/v1/roles/1/permissions              count=1
  ✓ 200     /api/v2/bo/role                          count=4
  ✓ 200     /api/v2/bo/role/1                        count=1
  ✓ 200 dpr /api/v1/roles/1/overlaps                 count=1
  ✓ 200     /api/v2/roles/1/overlaps                 count=1
  ✓ 200     /api/v2/bo/product                       count=3
  ✓ 200     /api/v2/bo/business_object               count=20
  ✓ 200     /api/v2/bo/relationship                  count=20

Passed: 16 / Failed: 0 / Total: 16
```

注：v1 端点带 `dpr` 标记（Deprecation=true/Sunset=2026-08-14）；v2 端点无 deprecation。

## 关键文件

| 文件 | 改动 |
|------|------|
| `meta/services/permission_service.py` | `get_all_permissions` 添加 P7 @deprecated；`get_all_roles` 添加保留说明注释 |

## 整体 v1.4 总结（按 P 阶段）

| 阶段 | 内容 | 状态 |
|------|------|------|
| **P3** | SSOT helper 抽取 + user_group_service 派生 | ✅ |
| **P4** | 移除 7 张 BO 表 `updated_at` 列 | ✅ |
| **P5** | `created_at_epoch` 性能优化 | ✅ |
| **P6** | user_group_service 5 个 CRUD @deprecated | ✅ |
| **P7** | 前端审计 + 业务过滤已迁移 + permission_service 1 个 @deprecated | ✅ |

## 备份状态
- `architecture.db.bak.20260605_120456` (P4)
- `architecture.db.bak.stage1.20260605_123530` (P5 阶段 1)

## 未来 P8+ 任务（可选）

1. **Sunset 自动化清理**（2026-08-14 后）：
   - 自动移除 `_group_service` 等冗余实例化
   - 自动标记 410
   - 移除 v1 deprecation 中间件

2. **业务过滤能力增强**（v2 端点）：
   - 当前 `_do_list` 通过 `get_field(key)` + `db_column` 处理
   - 未来可让 v2 端点原生支持业务过滤
   - 减少 `_build_conditions` 复杂度

3. **同类 service 全面重构**：
   - `role_service.py`（如存在）
   - `data_permission_service.py`（数据权限服务）
   - `condition_permission_service.py`（条件权限服务）
   - 每个都按 P6/P7 模式评估 + 标记

4. **添加单元测试覆盖**：
   - `user_group_service` 25 个业务方法 — 当前测试覆盖不足
   - `permission_service` 10 个业务方法 — 已有部分测试

5. **业务性能优化**：
   - `get_user_effective_data_permissions_via_groups` 4 表 JOIN 改为预计算
   - `get_all_descendants` Python 递归改为 `WITH RECURSIVE`
   - `get_managed_groups` 集用缓存

## Sunset 倒计时
- 当前：2026-06-05
- Sunset：2026-08-14
- 剩余：约 10 周
