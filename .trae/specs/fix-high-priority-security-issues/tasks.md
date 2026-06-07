# Tasks

## Task 1: JWT Secret 环境变量配置
修复 `token_service.py` 中的硬编码密钥问题。

- [x] SubTask 1.1: 修改 `TokenService.SECRET_KEY` 从环境变量读取
- [x] SubTask 1.2: 添加未配置时的随机密钥生成逻辑
- [x] SubTask 1.3: 添加启动时密钥状态日志

## Task 2: 安全表达式求值器
替换 `rule_executor.py` 中的 `eval()` 为安全实现。

- [x] SubTask 2.1: 创建 `SafeExpressionEvaluator` 类，实现 AST 解析
- [x] SubTask 2.2: 定义允许的操作符和函数白名单
- [x] SubTask 2.3: 实现字段引用解析（如 `name`、`original.name`）
- [x] SubTask 2.4: 替换 `ExpressionEvaluator.evaluate()` 调用
- [ ] SubTask 2.5: 添加单元测试验证安全性

## Task 3: 文件下载路径验证
修复 `export_import_api.py` 中的路径遍历漏洞。

- [x] SubTask 3.1: 重构 `download_export()` 函数
- [x] SubTask 3.2: 使用 `Path.resolve()` 规范化路径
- [x] SubTask 3.3: 添加路径前缀验证，确保在允许目录内
- [x] SubTask 3.4: 移除 glob 搜索逻辑，只允许精确匹配

## Task 4: 导入导出 API 认证
为导入导出端点添加认证保护。

- [x] SubTask 4.1: 为 `export_data` 添加 `@login_required` 装饰器
- [x] SubTask 4.2: 为 `import_data` 添加 `@login_required` 装饰器
- [x] SubTask 4.3: 为 `import_data_async` 添加 `@login_required` 装饰器
- [x] SubTask 4.4: 为 `import_status` 添加 `@login_required` 装饰器
- [x] SubTask 4.5: 为 `download_template` 添加 `@login_required` 装饰器
- [x] SubTask 4.6: 为 `get_import_export_config` 添加 `@login_required` 装饰器

## Task 5: 批量操作事务支持
为 `manage_service.py` 中的批量操作添加事务。

- [x] SubTask 5.1: 修改 `batch_create()` 使用事务包裹
- [x] SubTask 5.2: 修改 `batch_update()` 使用事务包裹
- [x] SubTask 5.3: 修改 `batch_delete()` 使用事务包裹
- [x] SubTask 5.4: 添加失败时的回滚逻辑
- [x] SubTask 5.5: 更新 `DataSource` 接口支持事务上下文管理器

## Task 6: MetaRegistry 线程安全
为 `models.py` 中的 `MetaRegistry` 添加线程锁。

- [x] SubTask 6.1: 添加 `threading.Lock` 类变量
- [x] SubTask 6.2: 修改 `reload()` 方法使用锁保护
- [x] SubTask 6.3: 修改 `register()` 方法使用锁保护
- [x] SubTask 6.4: 修改 `get()` 方法使用锁保护（读锁或原子访问）
- [x] SubTask 6.5: 使用"先构建后替换"策略避免 reload 期间数据不一致

## Task 7: SQLite 连接线程安全
为 `sql_adapters.py` 中的 `SQLiteAdapter` 添加连接锁。

- [x] SubTask 7.1: 在 `SQLiteAdapter.__init__()` 中创建 `threading.Lock`
- [x] SubTask 7.2: 修改 `execute()` 方法使用锁保护
- [x] SubTask 7.3: 修改 `commit()` 方法使用锁保护
- [x] SubTask 7.4: 修改 `rollback()` 方法使用锁保护

---

# Task Dependencies

- Task 2 独立
- Task 3 独立
- Task 4 独立
- Task 5 依赖 Task 7（事务需要线程安全的连接）
- Task 6 独立
- Task 7 独立

# Parallelizable Work

以下任务可并行执行：
- Task 1, Task 2, Task 3, Task 4, Task 6, Task 7 可并行
- Task 5 需等待 Task 7 完成
