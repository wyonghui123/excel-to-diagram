# Tasks: 对象日志详情页面（可复用模块）+ 全对象详情页适配

## M-LOG-1: 后端增强 + Composable + AuditLog 增强

### T1.1 后端 $metadata 端点返回 aspects
- **FR**: FR-001
- **Priority**: Must
- **Files**: `meta/services/view_config_service.py`, `meta/api/bo_api.py`
- **Description**: 在 $metadata 响应中新增 `aspects` 字段，返回对象的 aspect 声明数组
- **Acceptance**: 调用 `GET /api/v2/bo/domain/$metadata` 返回 `"aspects": ["hierarchy_aspect", "audit_aspect", ...]`

### T1.2 创建 useAuditLogs Composable
- **FR**: FR-003
- **Priority**: Must
- **Files**: `src/composables/useAuditLogs.js`
- **Description**: 统一日志数据加载 composable，支持分页/筛选
- **Acceptance**: `useAuditLogs(objectType, objectId)` 返回 `{ logs, total, loading, loadLogs, setFilters, setPage }`

### T1.3 AuditLog 增加分页支持
- **FR**: FR-004
- **Priority**: Must
- **Files**: `src/components/common/AuditLog/AuditLog.vue`
- **Description**: 新增 `total`, `showPagination`, `currentPage`, `pageSize` props 和 `page-change` event
- **Acceptance**: 当 `showPagination=true` 时底部显示分页器

### T1.4 AuditLog 增加筛选支持
- **FR**: FR-004
- **Priority**: Must
- **Files**: `src/components/common/AuditLog/AuditLog.vue`
- **Description**: 新增 `showFilter` prop 和 `filter-change` event，顶部显示操作类型筛选栏
- **Acceptance**: 当 `showFilter=true` 时顶部显示筛选标签

### T1.5 useDetail 增加分页状态
- **FR**: FR-010
- **Priority**: Must
- **Files**: `src/composables/useDetail.js`
- **Description**: 增加 `auditLogsTotal`, `auditLogsPage` 状态，`loadAuditLogsData` 支持分页参数
- **Acceptance**: `loadAuditLogsData({ page: 2 })` 返回第二页数据

---

## M-LOG-2: 智能推导 + YAML 清理 + DetailPage 集成

### T2.1 前端智能推导 history tab
- **FR**: FR-002
- **Priority**: Must
- **Files**: `src/composables/useDetail.js`
- **Description**: 在 `loadUIConfig()` 中检测 aspects 包含 `audit_aspect` 时自动追加 history tab
- **Acceptance**: domain 对象详情页自动出现"变更历史" Tab（无需 YAML 配置）

### T2.2 验证已有 history tab 不重复
- **FR**: FR-002, NFR-004
- **Priority**: Must
- **Files**: `src/composables/useDetail.js`
- **Description**: 智能推导前检测是否已有手动配置的 `type: history` tab，有则跳过
- **Acceptance**: user/role/user_group 详情页仍只显示一个"变更历史" Tab

### T2.3 清理 YAML 冗余 history tab 配置
- **FR**: FR-008
- **Priority**: Must
- **Files**: `meta/schemas/user.yaml`, `meta/schemas/role.yaml`, `meta/schemas/user_group.yaml`, `meta/schemas/_template.yaml`
- **Description**: 移除 `type: history` 的 tab 配置，改由智能推导
- **Acceptance**: 清理后 user/role/user_group 详情页仍正常显示"变更历史" Tab

### T2.4 确认所有对象 audit_aspect 声明完整
- **FR**: FR-009
- **Priority**: Must
- **Files**: `meta/schemas/*.yaml`
- **Description**: 检查所有业务对象是否声明了 `aspects: [audit_aspect]`
- **Acceptance**: 所有需要审计的对象都已声明

### T2.5 DetailPage 集成分页和详情弹窗
- **FR**: FR-010
- **Priority**: Must
- **Files**: `src/components/common/DetailPage/DetailPage.vue`
- **Description**: history tab 渲染传入分页参数，监听 page-change/log-click 事件
- **Acceptance**: 详情页的"变更历史" Tab 支持分页和点击交互

---

## M-LOG-3: AuditLogDetail + ChangeHistory + 独立实现统一

### T3.1 创建 AuditLogDetail 组件
- **FR**: FR-006
- **Priority**: Should
- **Files**: `src/components/common/AuditLogDetail/AuditLogDetail.vue`, `src/components/common/AuditLogDetail/index.js`
- **Description**: 日志详情 Drawer 组件，展示完整变更内容
- **Acceptance**: 打开日志详情 Drawer 可查看字段级变更对比

### T3.2 AuditLog 增加点击展开/Drawer 模式
- **FR**: FR-005
- **Priority**: Should
- **Files**: `src/components/common/AuditLog/AuditLog.vue`
- **Description**: 新增 `clickMode` prop（expand/drawer），点击日志条目触发交互
- **Acceptance**: `clickMode='drawer'` 时点击打开 AuditLogDetail Drawer

### T3.3 重写 ChangeHistory 组件
- **FR**: FR-007
- **Priority**: Must
- **Files**: `src/views/SystemManagement/ChangeHistory.vue`
- **Description**: 基于 useAuditLogs 重写，替代空占位
- **Acceptance**: EnumTypeDetail 的"变更历史" Tab 显示实际日志数据

### T3.4 统一 RoleDetailDrawer 日志实现
- **FR**: FR-011
- **Priority**: Should
- **Files**: `src/views/SystemManagement/RoleDetailDrawer.vue`
- **Description**: 替换自行实现的日志 Tab 为 AuditLog 组件
- **Acceptance**: RoleDetailDrawer 日志 Tab 使用统一组件

### T3.5 统一 RolePermissionDetail 日志实现
- **FR**: FR-011
- **Priority**: Should
- **Files**: `src/views/SystemManagement/RolePermissionDetail.vue`
- **Description**: 替换手动集成的日志 Tab 为 AuditLog 组件
- **Acceptance**: RolePermissionDetail 日志 Tab 使用统一组件

### T3.6 全对象详情页验证
- **FR**: FR-002, NFR-004
- **Priority**: Must
- **Description**: 逐一验证所有声明了 audit_aspect 的对象详情页是否正确显示"变更历史" Tab
- **Acceptance**: 所有对象的详情页 history Tab 功能正常
