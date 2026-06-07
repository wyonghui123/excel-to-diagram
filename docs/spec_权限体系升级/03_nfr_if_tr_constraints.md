# 4-8: 非功能需求 / 外部接口 / 过渡 / 约束 / 优先级

## 4. 非功能需求

### NFR-001: 性能
- **描述**: `DimensionScopeEngine.expand_dimension_values()` 在处理5层继承时应在500ms内完成
- **度量**: 使用6层 hierarchy_chain（product→version→domain→sub_domain→service_module→business_object），每层100条数据
- **优先级**: Should

### NFR-002: 向后兼容
- **描述**: 现有角色的权限关系不受影响，所有新功能不影响已有 role_permissions / role_menu_permissions / permission_rules 数据
- **度量**: 运行现有 init 脚本后，新代码启动不产生差异
- **优先级**: Must

### NFR-003: 可观测性
- **描述**: PermissionSyncService 和 DimensionScopeEngine 的所有同步/推导操作需记录日志
- **度量**: INFO 级别记录创建/更新/删除的权限和菜单数量
- **优先级**: Should

### NFR-004: 可测试性
- **描述**: 所有新增服务的核心方法必须支持单元测试（通过注入 data_source mock）
- **度量**: `PermissionSyncService.sync_all()` 和 `DimensionScopeEngine.auto_sync_all()` 的单元测试覆盖率 ≥ 80%
- **优先级**: Should

## 5. 外部接口需求

### IF-001: GET /api/v1/menu/visible
- **类型**: REST API
- **端点**: `GET /api/v1/menu/visible`
- **描述**: 返回当前用户可见的菜单树（含层级结构、icon、color、description、page_type）
- **错误处理**: 未登录返回401，无菜单返回空列表

### IF-002: POST /api/v1/roles/{role_id}/dimension-scopes
- **类型**: REST API
- **端点**: `POST /api/v1/roles/{role_id}/dimension-scopes`
- **描述**: 保存角色的维度范围声明
- **请求体**: `[{dimension_code, dimension_values, inherit_children, scope_mode}]`
- **错误处理**: 角色不存在返回404

### IF-003: GET /api/v1/roles/{role_id}/derived-permissions
- **类型**: REST API
- **端点**: `GET /api/v1/roles/{role_id}/derived-permissions`
- **描述**: 预览从维度范围推导的菜单+权限+数据规则（不实际保存）
- **响应体**: `{recommended_menus, derived_permissions, data_conditions}`

### IF-004: DimensionScopePanel 前端组件
- **类型**: UI 组件
- **入口**: RolePermissionCenter.vue 的新增 Tab "维度范围"
- **交互**: 级联维度选择器 (product→version→domain→...)，选中后实时预览数据访问范围

## 6. 过渡需求

### TR-001: 权限数据迁移
- **描述**: 现有 `permissions` 表数据向自动同步迁移
- **策略**: `PermissionSyncService.sync_all()` 使用 INSERT OR IGNORE，不删除已有权限记录（仅新增缺失）
- **回滚**: 保留 `init_auth.py` 的原有逻辑为 deprecated 但可执行

### TR-002: 菜单数据迁移
- **描述**: 将 `menu_permissions` 表升级为新 Schema（新增 color/description/page_type/object_types/auto_generated）
- **策略**: ALTER TABLE 添加新列，默认值填充；`init_menu_permissions.py` 保留但标记 deprecated
- **回滚**: 新列允许 NULL 且不影响现有查询

### TR-003: 角色维度范围初始化
- **描述**: 为现有角色从 `permission_rules` 反向提取维度范围
- **策略**: 提供一次性迁移脚本 `migrate_dimension_scopes.py`，解析 condition 字符串提取维度值
- **回滚**: 迁移脚本非破坏性，仅向 role_dimension_scopes 表插入数据

## 7. 约束与假设

### 7.1 技术约束
- TC-01: Python 3.9+, Vue 3 + TypeScript
- TC-02: 数据库引擎不变（SQLite），不使用外键
- TC-03: YAML Schema 格式向后兼容，新增字段可选
- TC-04: `MetaAction.ACTION_SUFFIX_MAP` 定义在 `models.py`，为唯一映射源

### 7.2 业务约束
- BC-01: 现有角色的权限关系 100% 不受影响
- BC-02: 新增功能不影响 CRUD API 的性能基准

### 7.3 假设
- AS-01: 权限表中 `code` 格式统一为 `{resource_type}:{action_suffix}` — 已验证
- AS-02: action_id 到 permission_suffix 的映射规则: `crud_create→create, crud_read→read, crud_update→update, crud_delete→delete` — 已验证
- AS-03: hierarchies.yaml 的6层结构（product→version→domain→sub_domain→service_module→business_object）稳定 — 已确认
- AS-04: `menu_permissions` 表可通过 ALTER TABLE 安全扩展 — 待验证

## 8. 优先级与里程碑

| ID | 需求 | 优先级 | 原因 |
|----|------|--------|------|
| FR-001 | 权限自动同步 | Must | 消除最大断裂点 |
| FR-002 | 菜单元数据化 | Must | 菜单成为一等BO |
| FR-003 | 角色维度范围 | Must | 核心入口变革 |
| FR-004 | 维度推导数据权限 | Must | 维度驱动核心 |
| FR-005 | 维度推荐菜单 | Must | 维度驱动核心 |
| FR-006 | 维度推导功能权限 | Must | 维度驱动核心 |
| FR-007 | 硬编码消除 | Must | 单一事实源 |
| FR-008 | 前端菜单API驱动 | Must | 消除5套菜单 |
| FR-015 | 双模式共存 | Must | 向后兼容 |
| FR-009 | 数据权限声明化 | Should | 增强粒度 |
| FR-010 | 字段级权限 | Should | 增强粒度 |
| FR-011 | 派生角色 | Could | 锦上添花 |
| FR-012 | 维度树升级 | Could | 长期架构 |
| FR-013 | action_group | Could | 按钮级授权 |
| FR-014 | 权限分析中心 | Could | 运维增强 |

### 里程碑

| 里程碑 | 范围 | 需求 |
|--------|------|------|
| M1: 基础打通 (2周) | 后端：权限同步 + Menu BO + 维度表 + 维度引擎 | FR-001, FR-002, FR-003, FR-004, FR-015 |
| M2: 前端统一 (2周) | 前端：菜单API + 路由守卫 + 维度面板 | FR-005, FR-006, FR-007, FR-008 |
| M3: 增强能力 (2周) | 数据权限 + 字段级 + 权限诊断 | FR-009, FR-010, FR-014 |
| M4: 长期演进 (按需) | 派生角色 + 维度树 + action_group | FR-011, FR-012, FR-013 |
