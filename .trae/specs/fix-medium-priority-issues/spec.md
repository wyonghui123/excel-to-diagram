# 中优先级性能与可维护性问题修复 Spec

## Why

代码审查发现 8 个中优先级问题，涉及性能瓶颈（N+1 查询）、代码可维护性（职责越界、全局变量、重复代码）和运维困难（错误处理不统一、日志不规范）。这些问题不影响功能正确性，但影响系统性能、可维护性和运维效率。

## What Changes

### 性能优化
- 消除 `_enrich_record_with_names` 中的 N+1 查询
- 消除关系列表的 N+1 分类计算
- 优化级联删除为批量操作

### 可维护性改进
- API 层职责边界清理
- 消除 `except: pass` 静默异常
- 统一错误响应格式

### 运维改进
- `print` 替换为 `logging`
- 统一日志格式

## Impact

- Affected code:
  - `meta/api/manage_api.py`
  - `meta/services/query_service.py`
  - `meta/services/cascade_service.py`
  - `meta/core/action_executor.py`

---

## ADDED Requirements

### Requirement: 批量预加载关联名称

系统 SHALL 在查询列表时批量预加载关联名称，消除 N+1 查询。

#### Scenario: 批量查询 business_object 列表
- **WHEN** 查询 100 条 business_object 记录
- **THEN** 使用 3 次批量查询（service_modules、sub_domains、domains）替代 500 次单条查询

#### Scenario: 批量查询 relationship 列表
- **WHEN** 查询 100 条 relationship 记录
- **THEN** 直接使用 JOIN 结果中的字段计算分类，不再额外查询

---

### Requirement: 级联删除批量操作

系统 SHALL 使用 `DELETE WHERE ... IN (...)` 批量删除，消除逐条删除。

#### Scenario: 删除包含 1000 个子记录的父记录
- **WHEN** 执行级联删除
- **THEN** 使用 2-3 条批量 DELETE 语句替代 1000+ 条单条 DELETE

---

### Requirement: 静默异常处理消除

系统 SHALL 记录而非忽略可预期的异常。

#### Scenario: 名称加载失败
- **WHEN** `_load_name` 因数据不一致无法加载名称
- **THEN** 记录 WARNING 日志并返回 None，不静默吞掉

#### Scenario: 关联数据查询失败
- **WHEN** `_enrich_with_relations` 查询失败
- **THEN** 记录 ERROR 日志并设置空列表，不静默吞掉

---

### Requirement: 统一日志模块

系统 SHALL 使用 `logging` 模块替代 `print()`。

#### Scenario: 记录错误
- **WHEN** 数据库操作失败
- **THEN** 使用 `logger.error()` 记录，包含异常堆栈

#### Scenario: 记录调试信息
- **WHEN** 需要调试 SQL 执行
- **THEN** 使用 `logger.debug()` 记录，可通过级别过滤

---

### Requirement: 统一错误响应格式

系统 SHALL 使用统一的错误响应格式。

#### Scenario: API 操作失败
- **WHEN** 任何 API 操作失败
- **THEN** 返回格式统一的错误响应：
```json
{
  "success": false,
  "error_code": "VALIDATION_ERROR",
  "message": "业务友好的错误信息",
  "detail": {}  // 可选，开发环境才有
}
```

---

## MODIFIED Requirements

### Requirement: API 层职责边界

原实现：
- `_enrich_record_with_names` 在 API 层（85 行）
- `_compute_category_label`/`_compute_category_type` 在 API 层（各 45 行）
- `list_relationships` 手写 150+ 行 SQL

修改为：
- 将名称解析逻辑移入 `QueryService` 或独立的 `NameResolverService`
- 将分类计算逻辑移入 `RelationshipService`
- 使用 `QueryBuilder` 重构 `list_relationships`

### Requirement: print 替换为 logging

原实现：
```python
print("[ERROR] Create table failed: {0}".format(str(e)))
print("[RuleExecutor] Expression error: ...")
```

修改为：
```python
logger = logging.getLogger(__name__)
logger.error("Create table failed: %s", str(e), exc_info=True)
logger.debug("RuleExecutor expression: %s", expression)
```

---

## REMOVED Requirements

无移除的需求。
