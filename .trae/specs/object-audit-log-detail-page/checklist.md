# Checklist: 对象日志详情页面（可复用模块）+ 全对象详情页适配

## Functional Requirements Verification

- [ ] FR-001: $metadata 端点返回 aspects 数组
  - [ ] 声明 audit_aspect 的对象返回中包含 "audit_aspect"
  - [ ] 未声明 aspects 的对象返回空数组
- [ ] FR-002: 智能推导 history tab
  - [ ] 有 audit_aspect 的对象自动出现"变更历史" Tab
  - [ ] 无 audit_aspect 的对象不出现"变更历史" Tab
  - [ ] 已有手动 history tab 的对象不重复显示
  - [ ] 无 detail 配置但有 audit_aspect 的对象自动创建基础 tabs + history
- [ ] FR-003: useAuditLogs Composable
  - [ ] 支持分页参数
  - [ ] 支持筛选参数
  - [ ] useDetail.loadAuditLogsData() 内部使用统一接口
  - [ ] ChangeHistory 使用 useAuditLogs
- [ ] FR-004: AuditLog 分页筛选
  - [ ] 底部分页器正常工作
  - [ ] 操作类型筛选正常工作
  - [ ] 现有功能（展开/收起、空状态、加载状态）不受影响
- [ ] FR-005: AuditLog 点击展开
  - [ ] clickMode='expand' 时点击展开详情
  - [ ] clickMode='drawer' 时点击打开 Drawer
  - [ ] hover 视觉反馈
- [ ] FR-006: AuditLogDetail 弹窗
  - [ ] 展示操作类型/时间/操作人/对象类型/对象ID
  - [ ] 变更字段表格（字段名|变更前|变更后）
  - [ ] 变更前值删除线+红色，变更后值绿色加粗
  - [ ] 创建操作显示"创建记录"
  - [ ] 删除操作显示"删除记录"
  - [ ] v-model:visible 控制
- [ ] FR-007: ChangeHistory 重写
  - [ ] 基于 useAuditLogs 自行加载数据
  - [ ] 支持分页和筛选
  - [ ] 空状态友好提示
  - [ ] EnumTypeDetail 引用自动生效
- [ ] FR-008: YAML 冗余配置清理
  - [ ] user.yaml 移除 history tab
  - [ ] role.yaml 移除 history tab
  - [ ] user_group.yaml 移除 history tab
  - [ ] _template.yaml 移除 history tab
  - [ ] 清理后功能无回退
- [ ] FR-009: audit_aspect 声明完整
  - [ ] 所有需要审计的对象都已声明
  - [ ] audit_log 不声明 audit_aspect
- [ ] FR-010: DetailPage 集成
  - [ ] 传入分页参数
  - [ ] 监听 page-change/log-click 事件
  - [ ] 集成 AuditLogDetail Drawer
  - [ ] useDetail 增加 auditLogsTotal/auditLogsPage
- [ ] FR-011: 独立实现统一
  - [ ] RoleDetailDrawer 使用 AuditLog
  - [ ] RolePermissionDetail 使用 AuditLog

## Nonfunctional Requirements Verification

- [ ] NFR-001: 分页加载性能
  - [ ] 默认每页 20 条
  - [ ] 翻页响应时间 < 500ms
- [ ] NFR-002: 统一数据源
  - [ ] 无直接调用 /audit-logs API 的前端代码
- [ ] NFR-003: 设计规范遵循
  - [ ] 颜色使用 CSS 变量，无硬编码
  - [ ] 间距使用 CSS 变量
  - [ ] 字体使用 CSS 变量
  - [ ] 使用规范组件（Drawer/Pagination/状态徽章）
- [ ] NFR-004: 向后兼容
  - [ ] user/role/user_group 详情页不重复显示 history tab

## Transition Requirements Verification

- [ ] TR-001: YAML 迁移
  - [ ] 先实现智能推导再清理 YAML
  - [ ] 清理后验证功能无回退
  - [ ] 有回滚方案
- [ ] TR-002: 独立实现迁移
  - [ ] 逐个替换并验证
  - [ ] 有回滚方案

## Per-Object Verification

- [ ] user: 详情页显示"变更历史" Tab
- [ ] role: 详情页显示"变更历史" Tab
- [ ] user_group: 详情页显示"变更历史" Tab
- [ ] domain: 详情页显示"变更历史" Tab
- [ ] sub_domain: 详情页显示"变更历史" Tab
- [ ] service_module: 详情页显示"变更历史" Tab
- [ ] business_object: 详情页显示"变更历史" Tab
- [ ] relationship: 详情页显示"变更历史" Tab
- [ ] product: 详情页显示"变更历史" Tab
- [ ] version: 详情页显示"变更历史" Tab
- [ ] enum_type: 详情页显示"变更历史" Tab
- [ ] enum_value: 详情页显示"变更历史" Tab
- [ ] annotation: 详情页显示"变更历史" Tab
- [ ] audit_log: 详情页不显示"变更历史" Tab
