# 高优先级安全与数据完整性问题修复 Spec

## Why

代码审查发现 7 个高优先级问题，涉及安全漏洞（JWT硬编码、eval注入、路径遍历、API无认证）和数据完整性风险（批量操作无事务、线程不安全）。这些问题可能导致认证绕过、代码执行、数据泄露和数据损坏。

## What Changes

### 安全修复
- JWT Secret 从硬编码改为环境变量配置
- `ExpressionEvaluator.eval()` 替换为安全的表达式解析器
- 文件下载 API 添加路径验证，防止路径遍历攻击
- 导入导出 API 添加认证保护

### 数据完整性修复
- 批量操作添加事务支持
- `MetaRegistry` 添加线程锁保护
- `SQLiteAdapter` 添加连接级线程锁

## Impact

- Affected specs: auth-permission-system, batch-export-import
- Affected code:
  - `meta/services/token_service.py`
  - `meta/core/rule_executor.py`
  - `meta/api/export_import_api.py`
  - `meta/services/manage_service.py`
  - `meta/core/models.py` (MetaRegistry)
  - `meta/core/sql_adapters.py`

---

## ADDED Requirements

### Requirement: JWT Secret 环境变量配置

系统 SHALL 从环境变量读取 JWT Secret，而非硬编码。

#### Scenario: 正常启动
- **WHEN** 环境变量 `JWT_SECRET_KEY` 已设置
- **THEN** 系统使用该值作为 JWT 签名密钥

#### Scenario: 未配置密钥
- **WHEN** 环境变量 `JWT_SECRET_KEY` 未设置
- **THEN** 系统生成随机密钥并记录警告日志

---

### Requirement: 安全表达式求值

系统 SHALL 使用安全的表达式解析器替代 `eval()`，只允许白名单操作。

#### Scenario: 合法表达式
- **WHEN** 规则表达式只包含允许的操作符和字段引用
- **THEN** 表达式正常求值并返回结果

#### Scenario: 非法表达式
- **WHEN** 规则表达式包含 `__class__`、`__mro__`、`import` 等危险操作
- **THEN** 系统拒绝执行并返回错误

---

### Requirement: 文件下载路径验证

系统 SHALL 验证下载文件路径在允许目录内。

#### Scenario: 合法文件路径
- **WHEN** 请求下载的文件在 `EXPORT_FOLDER` 目录内
- **THEN** 返回文件内容

#### Scenario: 路径遍历攻击
- **WHEN** 请求路径包含 `..` 或指向允许目录外
- **THEN** 返回 403 Forbidden

---

### Requirement: 导入导出 API 认证

系统 SHALL 对导入导出 API 端点强制认证。

#### Scenario: 已认证用户
- **WHEN** 请求携带有效 Authorization Header
- **THEN** 正常执行导入导出操作

#### Scenario: 未认证请求
- **WHEN** 请求未携带认证信息
- **THEN** 返回 401 Unauthorized

---

### Requirement: 批量操作事务支持

系统 SHALL 在事务中执行批量操作，确保原子性。

#### Scenario: 批量创建成功
- **WHEN** 批量创建的所有记录都有效
- **THEN** 所有记录提交到数据库

#### Scenario: 批量创建部分失败
- **WHEN** 批量创建中某条记录失败
- **THEN** 回滚所有已创建的记录，返回错误信息

---

### Requirement: MetaRegistry 线程安全

系统 SHALL 使用线程锁保护 `MetaRegistry` 的状态变更。

#### Scenario: 并发 reload
- **WHEN** 多个线程同时调用 `reload()`
- **THEN** 只有一个线程执行 reload，其他线程等待

#### Scenario: reload 期间读取
- **WHEN** 一个线程正在 reload 时另一个线程读取
- **THEN** 读取线程要么获得旧数据，要么获得新数据，不会读到不完整状态

---

### Requirement: SQLite 连接线程安全

系统 SHALL 使用线程锁保护 SQLite 连接操作。

#### Scenario: 并发查询
- **WHEN** 多个线程同时执行 SQL 查询
- **THEN** 查询按顺序执行，不会出现 `ProgrammingError`

---

## MODIFIED Requirements

### Requirement: TokenService 配置

原实现：
```python
SECRET_KEY = 'bip-arch-mgmt-secret-key-2026'
```

修改为：
```python
SECRET_KEY = os.environ.get('JWT_SECRET_KEY')
if not SECRET_KEY:
    SECRET_KEY = os.urandom(32).hex()
    logger.warning("JWT_SECRET_KEY not set, using random key")
```

### Requirement: ExpressionEvaluator 求值

原实现使用 `eval(expression, safe_globals, safe_locals)`

修改为使用 AST 解析 + 白名单验证的表达式求值器。

---

## REMOVED Requirements

无移除的需求。
