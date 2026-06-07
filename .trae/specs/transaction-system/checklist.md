# Checklist: 事务系统完备性改造

## Phase 1: 事务基础设施修复

### SQLiteAdapter 事务核心
- [ ] `begin_transaction()` 执行 `BEGIN` 语句
- [ ] `commit()` 仅事务内时提交
- [ ] `rollback()` 仅事务内时回滚
- [ ] `_in_transaction` 状态标记正确设置/清除
- [ ] `in_transaction` 只读属性
- [ ] `set_savepoint()` 创建保存点
- [ ] `rollback_to()` 回滚到保存点
- [ ] `release_savepoint()` 释放保存点
- [ ] `PRAGMA foreign_keys = ON` 启用

### SQLDataSource 条件化 commit
- [ ] `insert()` 事务内不自动 commit
- [ ] `update()` 事务内不自动 commit
- [ ] `delete()` 事务内不自动 commit
- [ ] `batch_insert()` 事务内不自动 commit
- [ ] 非事务模式行为不变（向后兼容）

### DataSource 抽象接口
- [ ] `in_transaction` 抽象属性
- [ ] `set_savepoint/rollback_to/release_savepoint` 抽象方法
- [ ] `transaction()` 异常回滚逻辑正确

### 异常类
- [ ] `ConcurrentModificationError` 定义

### Phase 1 测试
- [ ] 13 个单元测试全部通过
- [ ] 现有测试不受影响

## Phase 2: 关键场景事务包裹

### ActionExecutor
- [ ] `_do_create` 包裹 transaction()
- [ ] `_do_update` 包裹 transaction()
- [ ] `_do_delete` 包裹 transaction()
- [ ] V2 审计日志写入（事务后独立 mini 事务）
- [ ] `_write_audit_log_async()` 方法

### CascadeService
- [ ] `execute_cascade` 包裹 transaction()
- [ ] 所有 `self.ds.commit()` 移除

### API 层
- [ ] `user_api.create_user` 事务包裹
- [ ] `user_api.delete_user` 事务包裹
- [ ] `role_api.create_role` 事务包裹
- [ ] `role_api.delete_role` 事务包裹
- [ ] `enum_api` 裸 commit 消除
- [ ] `manage_api.delete_annotations_by_target` 事务包裹

### 导入操作
- [ ] `import_cascade` 事务包裹
- [ ] 异步导入独立事务

### Phase 2 测试
- [ ] 10 个集成测试全部通过
- [ ] 现有测试不受影响

## Phase 3: 高级事务能力

### 乐观锁
- [ ] MetaObject 自动追加 version 字段
- [ ] `update_with_version()` 方法
- [ ] `_do_update` 支持 version 检查
- [ ] 数据库迁移执行成功
- [ ] 现有数据 version 默认为 1

### allOrNone
- [ ] `batch_create` 支持 all_or_none 参数
- [ ] `batch_update` 支持 all_or_none 参数
- [ ] `batch_delete` 支持 all_or_none 参数

### WAL checkpoint
- [ ] `checkpoint()` 方法
- [ ] 定期执行策略

### Phase 3 测试
- [ ] 6 个高级测试全部通过
- [ ] 现有测试不受影响

## 全局验证

- [ ] 所有现有测试通过
- [ ] 手动验证：创建操作失败可回滚
- [ ] 手动验证：级联删除失败可回滚
- [ ] 手动验证：并发更新冲突检测
- [ ] 手动验证：审计日志 V2 异步写入
