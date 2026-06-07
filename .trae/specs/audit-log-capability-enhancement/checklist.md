# 审计日志能力完善与治理机制 Checklist

## Phase 1: 核心能力实现

### DerivationExecutor
- [ ] meta/core/derivation_executor.py 文件已创建
- [ ] derive_field() 方法正确派生字段值
- [ ] _derive_from_audit_logs() 方法从 audit_logs 查询数据
- [ ] _derive_user_name() 方法正确解析派生规则
- [ ] derive_batch() 方法支持批量派生
- [ ] 单元测试 test_derivation_executor.py 通过

### AuditInterceptor
- [ ] meta/services/audit_interceptor.py 文件已创建
- [ ] @audit_log 装饰器自动记录业务操作
- [ ] _write_audit_log() 函数正确写入审计日志
- [ ] 支持记录变更前后数据（old_data, new_data）
- [ ] 支持完整上下文（user_id, user_name, ip_address, user_agent, trace_id）
- [ ] 单元测试 test_audit_interceptor.py 通过

### MetadataValidator
- [ ] meta/core/metadata_validator.py 文件已创建
- [ ] validate_all() 方法验证所有元对象
- [ ] _validate_source_of_truth() 方法验证一致性
- [ ] 检测 derivation 规则缺失时报错
- [ ] 检测 redundant_storage 时输出警告
- [ ] log_results() 方法正确输出验证结果
- [ ] 单元测试 test_metadata_validator.py 通过

### Service 修复
- [ ] user_group_service.create_group() 使用 @audit_log 装饰器
- [ ] user_group_service.update_group() 使用 @audit_log 装饰器
- [ ] user_group_service.delete_group() 使用 @audit_log 装饰器
- [ ] user_service.create_user() 使用 @audit_log 装饰器
- [ ] user_service.update_user() 使用 @audit_log 装饰器
- [ ] user_service.delete_user() 使用 @audit_log 装饰器
- [ ] role_service.create_role() 使用 @audit_log 装饰器
- [ ] role_service.update_role() 使用 @audit_log 装饰器
- [ ] role_service.delete_role() 使用 @audit_log 装饰器

## Phase 2: 前端集成

### MetaEnhancer
- [ ] src/utils/metaEnhancer.js 文件已创建
- [ ] enhanceMetaWithAudit() 函数自动注入审计字段
- [ ] 自动追加 created_at/updated_at 列
- [ ] 自动追加 created_at_range 过滤器
- [ ] 自动设置 showChangeHistory: true
- [ ] 单元测试 metaEnhancer.spec.js 通过

### Meta 重构
- [ ] userMeta.js 使用 enhanceMetaWithAudit()
- [ ] roleMeta.js 使用 enhanceMetaWithAudit()
- [ ] userGroupMeta.js 使用 enhanceMetaWithAudit()
- [ ] 用户列表正确显示审计字段
- [ ] 角色列表正确显示审计字段
- [ ] 用户组列表正确显示审计字段

## Phase 3: 验证与文档

### 文档
- [ ] docs/TECH-DEBT.md 文件已创建
- [ ] TD-001: 审计字段冗余存储已记录
- [ ] 技术债务有状态、优先级、负责人、截止日期
- [ ] .trae/rules/audit-compliance.md 文件已创建
- [ ] 审计日志写入规范已定义
- [ ] source_of_truth 一致性要求已定义
- [ ] 代码审查检查清单已定义

### 启动验证
- [ ] meta/server.py 添加 validate_metadata_on_startup()
- [ ] 应用启动时自动运行元数据验证
- [ ] 验证结果正确输出

### 集成测试
- [ ] 新建用户组审计日志完整流程测试通过
- [ ] 更新用户组审计日志完整流程测试通过
- [ ] 删除用户组审计日志完整流程测试通过
- [ ] 变更历史正确显示

## Phase 4: 数据修复

- [ ] 现有用户组 created_by/updated_by 已补充
- [ ] 现有角色 created_by/updated_by 已补充
- [ ] 现有用户 created_by/updated_by 已补充
- [ ] 数据修复结果已验证

## 功能验收

### 审计日志自动写入
- [ ] 新建用户组时 created_at 自动填充
- [ ] 新建用户组时 created_by 自动填充
- [ ] 更新用户组时 updated_at 自动填充
- [ ] 更新用户组时 updated_by 自动填充
- [ ] 审计日志自动写入 audit_logs 表
- [ ] 变更历史正确显示

### 元数据验证
- [ ] MetadataValidator 检测到 source_of_truth 不一致时报错
- [ ] MetadataValidator 检测到 redundant_storage 时输出警告
- [ ] 应用启动时自动运行元数据验证

### 技术债务跟踪
- [ ] TECH-DEBT.md 记录了所有技术债务
- [ ] audit-compliance.md 定义了审计合规规范
- [ ] 所有技术债务都有负责人和截止日期

## 保障机制验收

### 启动时自动验证
- [ ] 应用启动时输出元数据验证结果
- [ ] 验证失败时有明确的错误日志

### 技术债务强制关联
- [ ] aspects.yaml 中 redundant_storage 关联了 tech_debt_id

### 代码审查检查清单
- [ ] .trae/rules/code-review-checklist.md 包含审计日志检查项

### 定期技术债务回顾
- [ ] docs/TECH-DEBT-REVIEW.md 定义了每周回顾流程
