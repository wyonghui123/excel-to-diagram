# 条件型权限系统任务清单

## Phase 1: 数据模型与核心服务（1周）

### 1.1 数据库表创建
- [ ] 创建 `permission_rules` 表
  - [ ] 定义表结构（id, role_id, resource_type, condition, permission_level, is_denied, inherit_to_children, propagate_to_parents, analysis_mode, created_at, created_by, updated_at）
  - [ ] 创建索引（role_id, resource_type）
  - [ ] 编写 YAML schema 文件
- [ ] 创建 `management_dimensions` 表（用友BIP管理维度）
  - [ ] 定义表结构（id, code, name, field, description）
  - [ ] 初始化预置维度（product, organization, department, employee, domain_type）
- [ ] 创建 `employee_data_scopes` 表（用友BIP员工数据权限）
  - [ ] 定义表结构（id, code, name, condition, description）
  - [ ] 初始化预置范围（self, department, department_tree, organization）
- [ ] 创建数据迁移脚本
  - [ ] 将现有 `data_permissions` 迁移为 `permission_rules`
  - [ ] condition 格式：`id = {原resource_id}`
  - [ ] 保留原表数据，标记为 deprecated

### 1.2 核心服务实现
- [ ] 创建 `ConditionPermissionService` 服务类
  - [ ] 实现 `check_permission(user_id, resource_type, resource_id, action)` 方法
  - [ ] 实现 `_get_user_conditions(user_id, resource_type)` 方法
  - [ ] 实现 `_evaluate_condition(condition, resource)` 方法
  - [ ] 实现 `_get_resource_detail(resource_type, resource_id)` 方法
- [ ] 实现 Owner 权限检查
  - [ ] 实现 `_is_owner(user_id, resource_type, resource_id)` 方法
  - [ ] 检查 created_by 和 owner_id 字段
  - [ ] Owner 返回 admin 级别权限
- [ ] 实现禁止权优先原则（用友BIP）
  - [ ] 实现 `_check_denied_rules(user_id, resource_type, resource_id)` 方法
  - [ ] 如果任何角色有 is_denied=true 的匹配规则，返回无权限
  - [ ] 禁止权优先于授权
- [ ] 实现员工数据权限模板（用友BIP）
  - [ ] 实现 `get_employee_data_scope_condition(user_id, scope_code)` 方法
  - [ ] 支持 self/department/department_tree/organization 四种范围
  - [ ] 动态替换 :user_id, :user_department_id 等参数
- [ ] 实现向下继承逻辑
  - [ ] 确保资源表有层级字段（product_id, version_id, domain_id）
  - [ ] 条件匹配时自动覆盖子级
- [ ] 实现向上传播逻辑
  - [ ] 实现 `_check_child_visibility(user_id, resource_type, resource_id)` 方法
  - [ ] 子级权限提供父级只读可见性

### 1.3 兼容层
- [ ] 修改 `DataPermissionService`
  - [ ] `get_effective_permission_level()` 内部调用 `ConditionPermissionService`
  - [ ] 保持 API 签名不变
  - [ ] 添加 deprecation warning

---

## Phase 2: 条件解析引擎（1周）

### 2.1 条件解析器实现
- [ ] 创建 `ConditionEvaluator` 类
  - [ ] 实现 predicate 类型解析（SQL WHERE 风格）
  - [ ] 实现 field_range 类型解析（字段值范围）
  - [ ] 实现 expression 类型解析（表达式引擎，可选）

### 2.2 安全性验证
- [ ] SQL 注入防护
  - [ ] 白名单字段验证
  - [ ] 参数化查询
  - [ ] 禁止危险操作（DROP, DELETE, UPDATE）
- [ ] 表达式沙箱
  - [ ] 限制可用函数
  - [ ] 限制执行时间

### 2.3 性能优化
- [ ] 条件解析缓存
  - [ ] 缓存解析后的条件结构
  - [ ] LRU 缓存策略
- [ ] 批量条件评估
  - [ ] 条件转 SQL WHERE 子句
  - [ ] 批量资源匹配

### 2.4 条件引用实例检测
- [ ] 创建 `InstanceReferenceDetector` 类
  - [ ] 实现 `detect_instance_references(condition)` 方法
  - [ ] 识别条件中的外键字段（*_id）
  - [ ] 返回引用的实例列表
- [ ] 集成到删除流程
  - [ ] 修改 `manage_service.delete()` 方法
  - [ ] 删除前检查权限规则依赖
  - [ ] 返回警告或阻止删除

---

## Phase 3: 分析型权限扩展（1周）

### 3.1 分析模式配置
- [ ] 实现 `analysis_mode` 字段解析
  - [ ] aggregation_only：强制聚合模式
  - [ ] allowed_fields：字段白名单
  - [ ] masked_fields：字段脱敏配置

### 3.2 查询构建器集成
- [ ] 创建 `AnalysisPermissionBuilder` 类
  - [ ] `apply_row_filter(query_builder, conditions)`：注入 WHERE 条件
  - [ ] `apply_field_restrictions(query_builder, allowed_fields)`：字段限制
  - [ ] `apply_masking(query_builder, masked_fields)`：数据脱敏
  - [ ] `force_aggregation(query_builder)`：强制聚合

### 3.3 数据脱敏函数
- [ ] 实现脱敏函数
  - [ ] `mask_middle_4`：中间4位脱敏（手机号）
  - [ ] `mask_email`：邮箱脱敏
  - [ ] `show_range`：显示范围（薪资）

---

## Phase 4: API 与 UI（1周）

### 4.1 API 端点
- [ ] 创建 `permission_rule_api.py`
  - [ ] GET `/api/v1/permission-rules`：获取权限规则列表
  - [ ] GET `/api/v1/permission-rules/<id>`：获取单个规则
  - [ ] POST `/api/v1/permission-rules`：创建权限规则
  - [ ] PUT `/api/v1/permission-rules/<id>`：更新权限规则
  - [ ] DELETE `/api/v1/permission-rules/<id>`：删除权限规则
  - [ ] POST `/api/v1/permission-rules/preview`：预览匹配资源
- [ ] 修改现有权限 API
  - [ ] 添加 condition 字段到响应
  - [ ] 保持向后兼容

### 4.2 前端 UI
- [ ] 创建条件编辑器组件
  - [ ] 字段选择器
  - [ ] 操作符选择器
  - [ ] 值输入器
  - [ ] 条件预览
- [ ] 修改角色权限配置界面
  - [ ] 条件型权限配置区域
  - [ ] 权限级别选择
  - [ ] 继承/传播选项
  - [ ] 分析模式配置（高级）
- [ ] 资源预览功能
  - [ ] 显示匹配的资源数量
  - [ ] 显示匹配的资源列表

### 4.3 迁移工具 UI
- [ ] 创建迁移管理界面
  - [ ] 显示迁移进度
  - [ ] 显示迁移统计
  - [ ] 回滚功能

---

## Phase 5: 测试与文档（并行）

### 5.1 单元测试
- [ ] `ConditionPermissionService` 测试
  - [ ] 条件匹配测试
  - [ ] 向下继承测试
  - [ ] 向上传播测试
- [ ] `ConditionEvaluator` 测试
  - [ ] predicate 类型测试
  - [ ] field_range 类型测试
  - [ ] 安全性测试

### 5.2 集成测试
- [ ] 权限检查流程测试
- [ ] 迁移流程测试
- [ ] API 端点测试

### 5.3 文档
- [ ] API 文档更新
- [ ] 迁移指南
- [ ] 使用示例

---

## Task Dependencies

```
Phase 1.1 (数据库表) 
  → Phase 1.2 (核心服务) 
  → Phase 1.3 (兼容层)

Phase 1.2 (核心服务) 
  → Phase 2.1 (条件解析器)

Phase 2.1 (条件解析器) 
  → Phase 3.1 (分析模式配置)

Phase 1.2 + Phase 2.1 
  → Phase 4.1 (API 端点)

Phase 4.1 (API 端点) 
  → Phase 4.2 (前端 UI)

Phase 1.1 + Phase 4.1 
  → Phase 4.3 (迁移工具)

Phase 1-4 
  → Phase 5 (测试与文档) - 可并行
```

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 条件解析性能 | 高 | 缓存 + 批量查询 |
| SQL 注入 | 高 | 白名单 + 参数化 |
| 迁移数据丢失 | 中 | 保留原表 + 回滚功能 |
| 向后兼容 | 中 | 兼容层 + deprecation warning |
