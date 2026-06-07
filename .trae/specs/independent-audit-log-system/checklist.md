# 独立审计日志系统 - 验收清单

> **创建日期**: 2026-05-11
> **版本**: v1.0

---

## Phase 1: 核心能力完善 (P0)

### 1.1 AuditService增强

- [ ] T1.1.1 完善query方法，支持复杂过滤
  - [ ] 支持action过滤
  - [ ] 支持object_type过滤
  - [ ] 支持user_name过滤
  - [ ] 支持start_date/end_date过滤
  - [ ] 支持keyword搜索
  - [ ] 支持分页

- [ ] T1.1.2 完善get_object_history方法
  - [ ] 按object_type和object_id查询
  - [ ] 返回变更历史列表
  - [ ] 按时间倒序

- [ ] T1.1.3 完善get_user_activities方法
  - [ ] 按user_id查询
  - [ ] 支持天数限制
  - [ ] 返回活动统计

- [ ] T1.1.4 实现get_change_summary统计方法
  - [ ] 按action统计
  - [ ] 按object_type统计
  - [ ] 按field_name统计
  - [ ] 按user统计

- [ ] T1.1.5 实现export_audit_log导出方法
  - [ ] 支持CSV格式
  - [ ] 支持XLSX格式
  - [ ] 支持过滤条件

### 1.2 AuditQueryOptimizer实现

- [ ] T1.2.1 实现查询优化器类
  - [ ] 单例模式
  - [ ] 初始化方法

- [ ] T1.2.2 实现索引选择优化逻辑
  - [ ] object_type + object_id索引
  - [ ] user_id索引
  - [ ] created_at索引
  - [ ] action索引

- [ ] T1.2.3 实现条件重写优化
  - [ ] 简化复杂条件
  - [ ] 优化LIKE查询

- [ ] T1.2.4 实现分页优化逻辑
  - [ ] OFFSET优化
  - [ ] 游标分页支持

### 1.3 AuditAPI增强

- [ ] T1.3.1 实现GET /logs端点
  - [ ] 参数解析
  - [ ] 权限检查
  - [ ] 调用AuditService
  - [ ] 返回分页数据

- [ ] T1.3.2 实现GET /logs/:id端点
  - [ ] ID验证
  - [ ] 权限检查
  - [ ] 返回单条详情

- [ ] T1.3.3 实现GET /logs/object/:type/:id端点
  - [ ] 参数解析
  - [ ] 调用get_object_history
  - [ ] 返回对象历史

- [ ] T1.3.4 实现GET /stats/overview端点
  - [ ] 统计总数
  - [ ] 统计失败数
  - [ ] 按action统计
  - [ ] 按object统计
  - [ ] 按user统计

- [ ] T1.3.5 实现GET /export端点
  - [ ] CSV导出
  - [ ] XLSX导出
  - [ ] 过滤条件支持

- [ ] T1.3.6 实现GET /health端点
  - [ ] AsyncWriter状态
  - [ ] 数据库状态
  - [ ] 队列大小
  - [ ] 工作线程数

### 1.4 business_key增强

- [ ] T1.4.1 完善_generate_business_key方法
  - [ ] 支持所有对象类型
  - [ ] 返回格式化标识

- [ ] T1.4.2 集成ObjectIdentityService
  - [ ] 使用服务获取标识
  - [ ] 降级方案

- [ ] T1.4.3 实现字段名中文映射
  - [ ] 通用字段映射
  - [ ] 按对象类型映射

---

## Phase 2: 前端组件实现 (P0)

### 2.1 API服务封装

- [ ] T2.1.1 创建auditService.js
  - [ ] 基础配置
  - [ ] API路径

- [ ] T2.1.2 实现query方法
  - [ ] 参数构建
  - [ ] 请求发送
  - [ ] 响应处理

- [ ] T2.1.3 实现getDetail方法
  - [ ] 单条查询

- [ ] T2.1.4 实现getStats方法
  - [ ] 统计概览

- [ ] T2.1.5 实现export方法
  - [ ] 文件下载

### 2.2 Composable实现

- [ ] T2.2.1 创建useAuditLog.js
  - [ ] 状态定义
  - [ ] 基础方法

- [ ] T2.2.2 实现fetchLogs方法
  - [ ] 分页支持
  - [ ] 过滤支持

- [ ] T2.2.3 实现fetchLogDetail方法
  - [ ] 单条查询

- [ ] T2.2.4 实现fetchStats方法
  - [ ] 统计查询

- [ ] T2.2.5 实现fetchObjectHistory方法
  - [ ] 对象历史查询

- [ ] T2.2.6 实现exportLogs方法
  - [ ] 导出功能

- [ ] T2.2.7 实现retryFailed方法
  - [ ] 重试失败记录

### 2.3 核心组件实现

- [ ] T2.3.1 创建AuditLogFilters.vue
  - [ ] 操作类型选择
  - [ ] 对象类型选择
  - [ ] 操作人搜索
  - [ ] 时间范围选择
  - [ ] 关键词搜索

- [ ] T2.3.2 创建AuditLogDetail.vue
  - [ ] 基本信息展示
  - [ ] 变更信息展示
  - [ ] 上下文信息展示

- [ ] T2.3.3 创建AuditLogStats.vue
  - [ ] 统计卡片
  - [ ] 趋势图表

- [ ] T2.3.4 创建AuditLogList.vue
  - [ ] 表格展示
  - [ ] 分页组件

### 2.4 页面集成

- [ ] T2.4.1 重构AuditLogManagement.vue
  - [ ] 布局设计
  - [ ] 组件集成

- [ ] T2.4.2 集成useAuditLog
  - [ ] 状态管理
  - [ ] 方法调用

- [ ] T2.4.3 集成AuditLogFilters
  - [ ] 过滤交互

- [ ] T2.4.4 集成AuditLogDetail
  - [ ] 详情展示
  - [ ] 抽屉交互

- [ ] T2.4.5 集成AuditLogStats
  - [ ] 统计展示

---

## Phase 3: 保留策略与归档 (P1)

### 3.1 保留策略服务

- [ ] T3.1.1 创建AuditRetentionService
  - [ ] 初始化方法

- [ ] T3.1.2 实现保留策略配置读取
  - [ ] 读取YAML配置
  - [ ] 默认值处理

- [ ] T3.1.3 实现保留策略更新
  - [ ] 管理员配置

- [ ] T3.1.4 实现retry_failed_records
  - [ ] 查询失败记录
  - [ ] 重试逻辑
  - [ ] 批量重试

### 3.2 归档服务

- [ ] T3.2.1 创建AuditArchiveService
  - [ ] 初始化方法

- [ ] T3.2.2 实现archive方法
  - [ ] 批量归档
  - [ ] 归档验证

- [ ] T3.2.3 实现归档验证
  - [ ] 记录数验证
  - [ ] 数据完整性验证

- [ ] T3.2.4 创建audit_logs_archive表
  - [ ] 表结构定义
  - [ ] 索引创建

### 3.3 归档API

- [ ] T3.3.1 创建audit_archive_api.py
  - [ ] Blueprint定义

- [ ] T3.3.2 实现GET /config/retention端点
  - [ ] 返回配置

- [ ] T3.3.3 实现PUT /config/retention端点
  - [ ] 更新配置

- [ ] T3.3.4 实现POST /archive端点
  - [ ] 触发归档

- [ ] T3.3.5 实现POST /retry/:id端点
  - [ ] 重试单条

### 3.4 定时任务

- [ ] T3.4.1 创建audit_archive_task.py
  - [ ] 任务定义

- [ ] T3.4.2 实现定时归档逻辑
  - [ ] 每日执行
  - [ ] 归档检查

- [ ] T3.4.3 集成到定时任务调度器
  - [ ] 调度配置

---

## Phase 4: 统计仪表板 (P2)

### 4.1 统计API增强

- [ ] T4.1.1 实现GET /stats/action端点
  - [ ] 按action统计

- [ ] T4.1.2 实现GET /stats/object端点
  - [ ] 按object统计

- [ ] T4.1.3 实现GET /stats/user端点
  - [ ] 按user统计

- [ ] T4.1.4 实现GET /stats/trend端点
  - [ ] 趋势数据
  - [ ] 时间维度

### 4.2 仪表板组件

- [ ] T4.2.1 增强AuditLogStats.vue
  - [ ] 统计卡片
  - [ ] 图表容器

- [ ] T4.2.2 实现统计图表
  - [ ] 柱状图
  - [ ] 饼图

- [ ] T4.2.3 实现趋势图
  - [ ] 折线图

---

## Phase 5: 权限控制 (P1)

### 5.1 角色定义

- [ ] T5.1.1 创建audit_admin角色
  - [ ] 角色定义
  - [ ] 权限配置

- [ ] T5.1.2 定义审计管理员权限
  - [ ] 权限项
  - [ ] 权限验证

- [ ] T5.1.3 创建审计管理员菜单
  - [ ] 菜单项
  - [ ] 路由配置

### 5.2 权限检查

- [ ] T5.2.1 实现audit_permission装饰器
  - [ ] 权限级别定义
  - [ ] 装饰器实现

- [ ] T5.2.2 在AuditAPI中集成权限检查
  - [ ] admin权限检查
  - [ ] superadmin权限检查

- [ ] T5.2.3 实现用户查询自己日志的逻辑
  - [ ] user角色查询限制

---

## Phase 6: 测试与文档 (P0)

### 6.1 单元测试

- [ ] T6.1.1 AuditService单元测试
  - [ ] query测试
  - [ ] get_object_history测试
  - [ ] get_change_summary测试

- [ ] T6.1.2 AuditQueryOptimizer单元测试
  - [ ] 索引选择测试
  - [ ] 查询优化测试

- [ ] T6.1.3 AuditRetentionService单元测试
  - [ ] 重试逻辑测试

- [ ] T6.1.4 AuditArchiveService单元测试
  - [ ] 归档逻辑测试

### 6.2 集成测试

- [ ] T6.2.1 AuditAPI集成测试
  - [ ] API端点测试
  - [ ] 权限测试

- [ ] T6.2.2 审计日志写入集成测试
  - [ ] 异步写入测试
  - [ ] 失败重试测试

### 6.3 前端测试

- [ ] T6.3.1 useAuditLog测试
  - [ ] 状态管理测试
  - [ ] 方法测试

- [ ] T6.3.2 AuditLogManagement组件测试
  - [ ] 组件渲染测试
  - [ ] 交互测试

### 6.4 文档

- [ ] T6.4.1 更新API文档
  - [ ] 端点说明
  - [ ] 参数说明
  - [ ] 响应示例

- [ ] T6.4.2 更新用户手册
  - [ ] 使用说明
  - [ ] 截图指引

- [ ] T6.4.3 更新运维手册
  - [ ] 部署说明
  - [ ] 运维指南

---

## 验收标准

### 功能验收

| 功能 | 验收标准 | 状态 |
|------|---------|------|
| 审计日志查询 | 支持多条件过滤、分页、排序 | ⬜ |
| 对象历史查询 | 按object_type+object_id查询 | ⬜ |
| 用户活动查询 | 按user_id查询用户操作记录 | ⬜ |
| 统计概览 | 返回总数、失败数、按action/object/user统计 | ⬜ |
| 导出功能 | 支持CSV/XLSX导出 | ⬜ |
| 保留策略 | 可配置保留天数 | ⬜ |
| 归档功能 | 定时/手动触发归档 | ⬜ |
| 失败重试 | 重试失败的审计记录 | ⬜ |
| 健康检查 | 返回系统健康状态 | ⬜ |

### 性能验收

| 指标 | 目标值 | 状态 |
|------|--------|------|
| 查询响应时间 | < 500ms | ⬜ |
| 并发查询能力 | > 50 QPS | ⬜ |
| 写入吞吐量 | > 1000 writes/s | ⬜ |
| 归档性能 | > 10000 records/hour | ⬜ |

### 安全验收

| 检查项 | 标准 | 状态 |
|--------|------|------|
| 权限控制 | 未授权用户无法访问审计日志 | ⬜ |
| 敏感信息过滤 | 密码等敏感字段被屏蔽 | ⬜ |
| 日志完整性 | 审计日志不可被篡改或删除 | ⬜ |
| 合规保留 | 符合SOX/HIPAA/GDPR要求 | ⬜ |

---

## 总体进度

| Phase | 进度 | 完成度 |
|-------|------|--------|
| Phase 1 | 0/15 | 0% |
| Phase 2 | 0/19 | 0% |
| Phase 3 | 0/14 | 0% |
| Phase 4 | 0/6 | 0% |
| Phase 5 | 0/6 | 0% |
| Phase 6 | 0/10 | 0% |
| **总计** | **0/70** | **0%** |

---

**最后更新**: 2026-05-11
