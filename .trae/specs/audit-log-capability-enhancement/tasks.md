# Tasks

## Phase 1: 核心能力实现（3天）

- [x] Task 1.1: 实现 DerivationExecutor 派生字段查询引擎
  - [x] SubTask 1.1.1: 创建 meta/core/derivation_executor.py 文件
  - [x] SubTask 1.1.2: 实现 derive_field() 方法 - 根据 derivation 规则派生字段值
  - [x] SubTask 1.1.3: 实现 _derive_from_audit_logs() 方法 - 从 audit_logs 派生字段
  - [x] SubTask 1.1.4: 实现 _derive_user_name() 方法 - 派生 created_by/updated_by
  - [x] SubTask 1.1.5: 实现 derive_batch() 方法 - 批量派生（性能优化）
  - [x] SubTask 1.1.6: 编写单元测试 test_derivation_executor.py

- [x] Task 1.2: 实现 audit_interceptor 审计日志写入装饰器
  - [x] SubTask 1.2.1: 创建 meta/services/audit_interceptor.py 文件
  - [x] SubTask 1.2.2: 实现 @audit_log 装饰器 - 自动记录业务操作
  - [x] SubTask 1.2.3: 使用 AsyncAuditWriter.submit() 提交审计日志写入任务
  - [x] SubTask 1.2.4: 支持记录变更前后数据（old_data, new_data）
  - [x] SubTask 1.2.5: 支持完整上下文（user_id, user_name, ip_address, user_agent, trace_id）
  - [x] SubTask 1.2.6: 业务事务与审计日志事务分离（V2 模式）

- [x] Task 1.3: 实现 MetadataValidator 元数据验证器
  - [x] SubTask 1.3.1: 创建 meta/core/metadata_validator.py 文件
  - [x] SubTask 1.3.2: 实现 validate_all() 方法 - 验证所有元对象
  - [x] SubTask 1.3.3: 实现 _validate_source_of_truth() 方法 - 验证 source_of_truth 一致性
  - [x] SubTask 1.3.4: 检测 derivation 规则缺失
  - [x] SubTask 1.3.5: 检测 redundant_storage 技术债务
  - [x] SubTask 1.3.6: 实现 log_results() 方法 - 输出验证结果
  - [x] SubTask 1.3.7: 编写单元测试 test_metadata_validator.py

- [x] Task 1.4: 修复 user_group_service 审计日志
  - [x] SubTask 1.4.1: 为 create_group() 添加 @audit_log 装饰器
  - [x] SubTask 1.4.2: 为 update_group() 添加 @audit_log 装饰器
  - [x] SubTask 1.4.3: 为 delete_group() 添加 @audit_log 装饰器
  - [x] SubTask 1.4.4: 添加 _get_object() 方法用于审计日志
  - [x] SubTask 1.4.5: 测试验证审计日志写入

- [x] Task 1.5: 修复 user_api 审计日志
  - [x] SubTask 1.5.1: 为 create_user() 添加审计日志记录
  - [x] SubTask 1.5.2: 为 delete_user() 添加审计日志记录
  - [x] SubTask 1.5.3: 使用 AuditInterceptor 异步写入
  - [x] SubTask 1.5.4: 测试验证审计日志写入

- [x] Task 1.6: 修复 role_api 审计日志
  - [x] SubTask 1.6.1: 为 create_role() 添加审计日志记录
  - [x] SubTask 1.6.2: 为 delete_role() 添加审计日志记录
  - [x] SubTask 1.6.3: 使用 AuditInterceptor 异步写入
  - [x] SubTask 1.6.4: 测试验证审计日志写入

## Phase 2: 前端集成（2天）

- [x] Task 2.1: 实现 metaEnhancer 前端元数据增强
  - [x] SubTask 2.1.1: 创建 src/utils/metaEnhancer.js 文件
  - [x] SubTask 2.1.2: 实现 enhanceMetaWithAudit() 函数
  - [x] SubTask 2.1.3: 自动追加 created_at/updated_at 列
  - [x] SubTask 2.1.4: 自动追加 created_at_range 过滤器
  - [x] SubTask 2.1.5: 自动设置 showChangeHistory: true
  - [x] SubTask 2.1.6: 导出 AUDIT_META 常量

- [ ] Task 2.2: 重构 userMeta 使用 enhanceMetaWithAudit
  - [ ] SubTask 2.2.1: 导入 enhanceMetaWithAudit
  - [ ] SubTask 2.2.2: 移除手动定义的审计字段
  - [ ] SubTask 2.2.3: 使用 enhanceMetaWithAudit() 增强
  - [ ] SubTask 2.2.4: 测试验证用户列表显示审计字段

- [ ] Task 2.3: 重构 roleMeta 使用 enhanceMetaWithAudit
  - [ ] SubTask 2.3.1: 导入 enhanceMetaWithAudit
  - [ ] SubTask 2.3.2: 移除手动定义的审计字段
  - [ ] SubTask 2.3.3: 使用 enhanceMetaWithAudit() 增强
  - [ ] SubTask 2.3.4: 测试验证角色列表显示审计字段

- [ ] Task 2.4: 重构 userGroupMeta 使用 enhanceMetaWithAudit
  - [ ] SubTask 2.4.1: 导入 enhanceMetaWithAudit
  - [ ] SubTask 2.4.2: 移除手动定义的审计字段
  - [ ] SubTask 2.4.3: 使用 enhanceMetaWithAudit() 增强
  - [ ] SubTask 2.4.4: 测试验证用户组列表显示审计字段

## Phase 3: 验证与文档（1天）

- [x] Task 3.1: 创建技术债务跟踪文档
  - [x] SubTask 3.1.1: 创建 docs/TECH-DEBT.md 文件
  - [x] SubTask 3.1.2: 记录 TD-001: 审计字段冗余存储
  - [x] SubTask 3.1.3: 定义状态、优先级、负责人、截止日期
  - [x] SubTask 3.1.4: 定义解决方案和迁移计划

- [x] Task 3.2: 创建审计合规规范文档
  - [x] SubTask 3.2.1: 创建 .trae/rules/audit-compliance.md 文件
  - [x] SubTask 3.2.2: 定义审计日志写入规范
  - [x] SubTask 3.2.3: 定义 source_of_truth 一致性要求
  - [x] SubTask 3.2.4: 定义代码审查检查清单

- [ ] Task 3.3: 集成启动时验证
  - [ ] SubTask 3.3.1: 在 meta/server.py 中添加 validate_metadata_on_startup()
  - [ ] SubTask 3.3.2: 加载所有元对象
  - [ ] SubTask 3.3.3: 运行 MetadataValidator
  - [ ] SubTask 3.3.4: 输出验证结果

- [ ] Task 3.4: 编写集成测试
  - [ ] SubTask 3.4.1: 测试新建用户组审计日志完整流程
  - [ ] SubTask 3.4.2: 测试更新用户组审计日志完整流程
  - [ ] SubTask 3.4.3: 测试删除用户组审计日志完整流程
  - [ ] SubTask 3.4.4: 测试变更历史显示

## Phase 4: 数据修复（1天）

- [ ] Task 4.1: 修复现有数据的审计字段
  - [ ] SubTask 4.1.1: 为现有用户组补充 created_by/updated_by
  - [ ] SubTask 4.1.2: 为现有角色补充 created_by/updated_by
  - [ ] SubTask 4.1.3: 为现有用户补充 created_by/updated_by
  - [ ] SubTask 4.1.4: 验证数据修复结果

# Task Dependencies

- [Task 1.2] depends on [Task 1.1] (audit_interceptor 需要 DerivationExecutor)
- [Task 1.4] depends on [Task 1.2] (user_group_service 需要 audit_interceptor)
- [Task 1.5] depends on [Task 1.2] (user_service 需要 audit_interceptor)
- [Task 1.6] depends on [Task 1.2] (role_service 需要 audit_interceptor)
- [Task 2.2] depends on [Task 2.1] (userMeta 需要 metaEnhancer)
- [Task 2.3] depends on [Task 2.1] (roleMeta 需要 metaEnhancer)
- [Task 2.4] depends on [Task 2.1] (userGroupMeta 需要 metaEnhancer)
- [Task 3.3] depends on [Task 1.3] (启动验证需要 MetadataValidator)
- [Task 3.4] depends on [Task 1.4, Task 1.5, Task 1.6] (集成测试需要所有 service 修复完成)
- [Task 4.1] depends on [Task 1.4, Task 1.5, Task 1.6] (数据修复需要 service 修复完成)

# Parallelizable Work

以下任务可以并行执行：
- Task 1.1, Task 1.3 (DerivationExecutor 和 MetadataValidator 无依赖)
- Task 1.4, Task 1.5, Task 1.6 (三个 service 修复可以并行)
- Task 2.2, Task 2.3, Task 2.4 (三个 meta 重构可以并行)
- Task 3.1, Task 3.2 (文档创建可以并行)
