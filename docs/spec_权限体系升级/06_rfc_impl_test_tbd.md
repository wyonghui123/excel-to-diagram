## 9.4 实现与迁移计划

### 实现顺序

| 步骤 | 内容 | 依赖 | 产出 |
|------|------|------|------|
| Step 1 | `MetaAction.ACTION_SUFFIX_MAP` + `MetaObject.get_action_by_suffix/get_permission_label` | 无 | models.py 增强 |
| Step 2 | `PermissionSyncService` + 集成到 `server.py` on_meta_loaded | Step 1 | permission_sync_service.py |
| Step 3 | `MenuAutoGenerator` + `menu.yaml` | Step 1, 2 | menu_auto_generator.py, menu.yaml |
| Step 4 | `role_dimension_scope.yaml` + 建表 | 无 | 新Schema + DB表 |
| Step 5 | `DimensionScopeEngine` | Step 1, 4 | dimension_scope_engine.py |
| Step 6 | `GET /api/v1/menu/visible` 端点 | Step 3 | 角色菜单API |
| Step 7 | `POST /api/v1/roles/{id}/dimension-scopes` 端点 | Step 4 | role_dimension_scope_api.py |
| Step 8 | `GET /api/v1/roles/{id}/derived-permissions` 端点 | Step 5 | 推导预览API |
| Step 9 | `role_menu_api.py` 移除 `PERMISSION_LABELS`/`MENU_DISPLAY_NAMES` | Step 1 | 代码清理 |
| Step 10 | `init_auth.py` 委托 `PermissionSyncService` | Step 2 | 脚本重构 |
| Step 11 | 前端 `menuConfig.js` → deprecated, API驱动 | Step 6 | menuConfig.js |
| Step 12 | 前端路由守卫增加权限检查 | Step 6 | router/index.js |
| Step 13 | 前端 `DimensionScopePanel` 组件 | Step 7, 8 | RolePermissionCenter.vue |
| Step 14 | 前端移除 `menuIconMap`/`getDefaultMenus()` | Step 11 | useMenuPermissions.js |
| Step 15 | `data_permission_dimensions` YAML扩展 | Step 1 | models.py + domain.yaml等 |
| Step 16 | `PermissionAnnotation` 激活 (BOFramework叠加) | Step 1 | bo_framework.py |
| Step 17 | 权限分析中心 (用户权限总览) | Step 6, 7 | 新增API + 前端面板 |

### 风险缓解

| 风险 | 缓解策略 |
|------|---------|
| 维度范围推导不准确 | 保留手动调整入口，管理员可覆盖自动推导结果 |
| `inherit_children` 递归性能 | 使用 hierarchies.yaml 的扁平化缓存，单次SQL查询替代递归 |
| 现有角色迁移时数据冲突 | `INSERT OR IGNORE` + 非破坏性迁移脚本 |
| 前端双模式切换的UI复杂度 | 维度面板 + 菜单矩阵分Tab展示，默认显示维度面板 |
| 权限名称推导依赖 MetaRegistry 完整性 | 启动时校验：所有 BO 的 action 必须有 name |

### 测试策略

| 层级 | 范围 | 方法 |
|------|------|------|
| 单元测试 | `PermissionSyncService.sync_all()`, `DimensionScopeEngine.expand_dimension_values()` | pytest + mock data_source |
| 集成测试 | BO注册→权限同步→菜单生成 全链路 | pytest + 临时SQLite |
| API测试 | `/api/v1/menu/visible`, `/api/v1/roles/{id}/derived-permissions` | pytest + Flask test client |
| 前端E2E | 维度范围配置 → 菜单推荐 → 确认保存 → 用户登录菜单可见 | Playwright |
| 回归测试 | 现有角色权限不变 | 对比迁移前后 role_permissions 内容 |
| 性能测试 | 6层维度树 每层100条 × 继承展开 | pytest-benchmark |

### 回滚计划

1. 所有新增表使用独立表名，不影响现有表
2. `menu_permissions` 扩展列允许 NULL，回滚只需 DROP COLUMN
3. `menuConfig.js` 保留但标记 deprecated，可随时切回
4. `init_auth.py` 的原有 `seed_permissions()` 逻辑保留在文件内但注释掉
5. MetaRegistry/MetaObject 的新方法不影响现有调用

## 10. TBD 列表

| ID | 项目 | 缺失信息 | 下一步 |
|----|------|---------|--------|
| TBD-01 | `menu_permissions` 表是否需要全量替换为 `menus` 表（BO化）还是仅扩展 | 需用户确认 | 询问用户 |
| TBD-02 | 维度树(`tree_code`)是否在M1实施还是推迟到M4 | 需用户确认优先级 | 询问用户 |
| TBD-03 | `action_group` 的枚举值定义（standard/readonly/maintain/custom）是否充分 | 需业务确认 | 询问用户 |
| TBD-04 | 权限分析中心的"智能诊断"具体诊断规则和提示文案 | 需产品/运维输入 | 产品定义 |
| TBD-05 | 派生角色的UI交互方式（从角色复制 + 修改维度 vs 全新创建） | 需UX设计 | 原型设计 |
| TBD-06 | `menuConfig.js` 是完全删除还是保留为 fallback | 需确认降级策略 | 询问用户 |

---
