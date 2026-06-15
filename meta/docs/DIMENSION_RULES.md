# DIMENSION_RULES.md

> **Dimension (管理维度) 业务规则文档**
> 版本: v1.0
> 创建: 2026-06-14
> BMRD DEFER ID: DIM-FULL

## 1. Dimension 类型

| 类型 | 说明 | 示例 | 优先级 |
|------|------|------|--------|
| `org` | 组织维度 | 公司/部门/团队 | P0 |
| `geo` | 地理维度 | 国家/省/市/区域 | P0 |
| `product` | 产品维度 | 产品线/产品/版本 | P0 |
| `time` | 时间维度 | 年/季度/月/周 | P1 |
| `user` | 用户维度 | 角色/职位/职级 | P1 |
| `custom` | 自定义维度 | 用户自定义 | P2 |

## 2. Dimension 层级

### 树形结构
- 通过 `parent_id` 字段关联形成树
- 支持 **N 级嵌套** (理论无限, 实际建议 ≤ 5 级)
- 根节点 `parent_id = NULL`

### 字段
| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | int | 维度 ID |
| `code` | str | 维度 code (唯一) |
| `name` | str | 维度显示名 |
| `type` | str | 维度类型 (见上表) |
| `parent_id` | int? | 父维度 ID, NULL = 根 |
| `scope` | str | 可见性范围 (见 §3) |
| `enabled` | bool | 是否启用 |

## 3. Dimension 范围 (Scope)

| 范围 | 标识 | 说明 |
|------|------|------|
| **私有** | `private` | 仅创建者可见 |
| **团队** | `team` | 本团队成员可见 |
| **组织** | `org` | 全公司可见 |
| **公开** | `public` | 所有用户可见 (需特殊权限) |

### 范围继承
- 子维度的可见性 ⊆ 父维度的可见性
- 例: 父为 `team` → 子不能是 `public`
- 例: 父为 `org` → 子可以是 `team`/`org`/`public`

## 4. Permission Rules (权限规则)

### 4.1 Role 与 Dimension 的关系
- Role 通过 `dimension_scope` 字段限制可访问的 dimension 实例
- `dimension_scope` 格式: `[{dimension_id, instance_ids[]}]`
- 例: `role:R001` 只能访问 `dimension:geo` 下 `instance_id=[1, 2, 3]` (中国/华东/上海)

### 4.2 Permission Rules
- 定义 role 在 dimension 下的具体动作权限
- 动作: `READ`, `WRITE`, `DELETE`, `APPROVE`
- 例: `role:R001` 在 `dimension:org:dept_id=10` 下有 `READ + WRITE` 权限

### 4.3 API 端点
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/management-dimensions` | GET | 列出所有维度 |
| `/api/v1/management-dimensions/{id}/instances` | GET | 列出维度下的实例 |
| `/api/v1/role/{id}/permission-rules` | GET | 获取 role 的权限规则 |
| `/api/v1/role/{id}/permission-rules` | POST | 保存 role 的权限规则 |
| `/api/v1/role/{id}/calculate-impact` | POST | 计算权限变更影响 |

> **注意**: 上述端点 v1 已迁移到 v2 (`/api/v2/bo/management_dimension`),
> 但 v2 路由尚未完整实现, 当前仍走 v1 (Agent 路径修正后).

## 5. 范围继承 (Inheritance)

### 5.1 继承规则
- 父 dimension 的权限**自动继承**给子 dimension
- 子 dimension **可覆盖**父的权限设置 (子节点独立配置)
- 覆盖是**显式**的, 默认继承

### 5.2 继承示例
```
dimension:org (root)
├── dimension:org:dept_eng (sub, inherits 'org' scope)
│   ├── dimension:org:dept_eng:team_a (sub-sub, inherits 'team' scope from override)
│   └── dimension:org:dept_eng:team_b (sub-sub, inherits 'team' scope)
└── dimension:org:dept_sales (sub, inherits 'org' scope)
```

### 5.3 冲突解决
- 多个父维度冲突时, **最严格** scope 生效
- 例: 父 A `team`, 父 B `org` → 子取 `team` (更严格)

## 6. 数据权限引擎

### 6.1 引擎组成
- `dimension_scope_engine.py` - 范围计算
- `management_dimension_engine.py` - 维度操作
- `runtime_dimension_resolver.py` - 运行时解析
- `data_permission_interceptor.py` - 拦截器集成

### 6.2 查询流程
```
1. 用户发起查询 (例: GET /api/v2/bo/order?page_size=10)
2. data_permission_interceptor 拦截
3. runtime_dimension_resolver 解析用户的 dimension scope
4. 拼接 SQL WHERE 条件 (基于 dimension_scope.instance_ids)
5. 返回过滤后的数据
```

## 7. 缓存与性能

### 7.1 缓存策略
- `dimension_scope` 计算结果**缓存 5 分钟** (基于 user_id + role_id)
- 角色权限变更时**主动失效**缓存
- 缓存存储: `meta/cache-stats` 端点可查

### 7.2 性能指标
- 简单查询 (1 个 dimension) < 50ms
- 复杂查询 (3+ dimension) < 200ms
- 缓存命中时 < 10ms

## 8. 测试覆盖

### 8.1 后端测试
- `meta/tests/test_dimension_scope_engine.py` - 引擎
- `meta/tests/test_dimension_scope_v101.py` - v1.01 范围
- `meta/tests/test_management_dimension_api.py` - API
- `meta/tests/test_role_menu_dim_api.py` - 角色-菜单-维度
- `meta/tests/test_dimension_aware_filtering.py` - 维度过滤

### 8.2 集成点
- `meta/services/condition_permission_service.py` - 条件权限
- `meta/core/interceptors/data_permission_interceptor.py` - 数据权限拦截
- `meta/core/rbac.py` - 角色权限基础

## 9. 已知限制 (Known Limitations)

| 限制 | 原因 | 解决方案 |
|------|------|----------|
| v2 路由不完整 | 路由迁移半成品 | 暂时回退 v1, 跟踪 issue #TBD |
| 维度类型固定 | 类型在枚举里 | P2: 支持动态注册自定义类型 |
| 层级无循环检测 | 业务侧兜底 | P2: 添加检测脚本 |
| 范围继承无事务 | 性能优化 | 接受最终一致 |

## 10. DEFER 状态

| DEFER ID | 状态 | 解锁条件 |
|----------|------|----------|
| DIM-FULL | 🟡 DEFER (文档化完成) | v2 路由修复后改为 ACTIVE |

## 11. 未来规划

- [ ] v2 路由完整迁移 (1-2 天)
- [ ] 维度类型动态注册 (P2)
- [ ] 层级循环检测 (P2)
- [ ] 范围继承事务化 (P3)
- [ ] 多语言维度名称 (P3, 依赖 E34)

## 12. BMRD 规则

本规则文档对应 BMRD 规则:
- `DIM-1` - dimension 列表 API
- `DIM-2` - dimension_object_mapping 关联
- `DATA-PERM-DIM-1` - role_data_permission
- `DATA-PERM-DIM-2` - employee_data_scope
- `DATA-PERM-DIM-3` - group_data_permission
- `DATA-PERM-DIM-4` - data_scope 多端点

## 13. 参考

- 后端文件: `meta/services/dimension_scope_engine.py` (入口)
- 后端文件: `meta/api/management_dimension_api.py` (API 端点)
- 迁移历史: `migrated_at: 2026-05-14`, `sunset_at: 2026-06-05`
- BMRD 框架: `.trae/specs/_business_rules/_data_permission_dimension_rules.yaml`
