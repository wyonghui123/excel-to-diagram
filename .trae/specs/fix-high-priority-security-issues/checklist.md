# Checklist

## Task 1: JWT Secret 环境变量配置
- [x] `TokenService.SECRET_KEY` 从环境变量 `JWT_SECRET_KEY` 读取
- [x] 未配置时生成随机密钥并记录警告日志
- [ ] 单元测试验证环境变量读取逻辑

## Task 2: 安全表达式求值器
- [x] `SafeExpressionEvaluator` 类实现 AST 解析
- [x] 白名单验证拒绝 `__class__`、`__mro__`、`import` 等危险操作
- [x] 支持合法的字段引用（如 `name`、`original.name`）
- [x] 支持合法的操作符（`==`、`!=`、`>`、`<`、`and`、`or`、`not`、`in`）
- [ ] 单元测试覆盖安全边界场景

## Task 3: 文件下载路径验证
- [x] `download_export()` 使用 `Path.resolve()` 规范化路径
- [x] 验证最终路径以 `EXPORT_FOLDER` 路径为前缀
- [x] 路径遍历攻击返回 403 Forbidden
- [x] 移除了 glob 搜索逻辑

## Task 4: 导入导出 API 认证
- [x] `/api/v1/export` POST 端点需要认证
- [x] `/api/v1/import` POST 端点需要认证
- [x] `/api/v1/import/async` POST 端点需要认证
- [x] `/api/v1/import/status/<task_id>` GET 端点需要认证
- [x] `/api/v1/import/template/<object_type>` GET 端点需要认证
- [x] `/api/v1/import-export/config/<object_type>` GET 端点需要认证
- [x] 未认证请求返回 401 Unauthorized

## Task 5: 批量操作事务支持
- [x] `batch_create()` 在事务中执行
- [x] `batch_update()` 在事务中执行
- [x] `batch_delete()` 在事务中执行
- [x] 部分失败时回滚所有已执行操作
- [x] `DataSource` 支持事务上下文管理器（`with ds.transaction():`）

## Task 6: MetaRegistry 线程安全
- [x] `MetaRegistry` 使用 `threading.Lock` 保护状态
- [x] `reload()` 方法使用锁保护
- [x] `reload()` 使用"先构建后替换"策略
- [ ] 并发测试验证无竞态条件

## Task 7: SQLite 连接线程安全
- [x] `SQLiteAdapter` 使用 `threading.Lock` 保护连接操作
- [x] `execute()` 方法线程安全
- [x] `commit()` 方法线程安全
- [x] `rollback()` 方法线程安全
- [ ] 并发测试验证无 `ProgrammingError`
