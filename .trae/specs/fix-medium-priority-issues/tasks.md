# Tasks

## Task 1: 批量预加载关联名称
消除 `_enrich_record_with_names` 中的 N+1 查询。

- [x] SubTask 1.1: 创建 `_batch_load_names()` 函数，支持批量查询
- [x] SubTask 1.2: 创建 `_batch_get_single_records()` 函数，支持批量查询
- [x] SubTask 1.3: 重构 `_enrich_record_with_names()` 使用批量查询
- [x] SubTask 1.4: 添加缓存机制避免同一请求内重复查询
- [x] SubTask 1.5: 验证 100 条记录查询从 500 次降到 3-5 次

## Task 2: 关系列表分类计算优化
消除关系列表查询的 N+1 分类计算。

- [x] SubTask 2.1: 直接使用 JOIN 结果中的 domain_id/sub_domain_id 字段
- [x] SubTask 2.2: 合并 `_compute_category_label` 和 `_compute_category_type` 为单一函数
- [x] SubTask 2.3: 移除 `_compute_relation_stats` 中的重复查询
- [x] SubTask 2.4: 验证关系列表查询性能提升

## Task 3: 级联删除批量操作
优化 `CascadeService.execute_cascade` 为批量删除。

- [x] SubTask 3.1: 重构 `execute_cascade` 使用批量 DELETE
- [x] SubTask 3.2: 收集所有待删除 ID 后一次性删除
- [x] SubTask 3.3: 验证删除性能提升

## Task 4: 静默异常处理消除
消除 `except: pass` 静默异常。

- [x] SubTask 4.1: 修复 `_get_single_record()` 中的 `except Exception as e: pass`
- [x] SubTask 4.2: 修复 `_load_name()` 中的 `except Exception as e: pass`
- [x] SubTask 4.3: 修复 `_enrich_relationship_data()` 中的 `except Exception: pass`
- [x] SubTask 4.4: 修复 `_enrich_with_relations()` 中的 `except Exception:`
- [x] SubTask 4.5: 所有异常处记录 WARNING 或 ERROR 日志

## Task 5: print 替换为 logging
将所有 `print()` 替换为 `logging` 模块。

- [x] SubTask 5.1: 在 `sql_adapters.py` 中添加 logger（11 处替换）
- [x] SubTask 5.2: 在 `action_executor.py` 中添加 logger（1 处替换）
- [x] SubTask 5.3: 在 `rule_executor.py` 中添加 logger（3 处替换）
- [x] SubTask 5.4: 在 `cascade_service.py` 中添加 logger（0 处，无 print）
- [x] SubTask 5.5: 统一日志格式（包含模块名、时间、级别、消息）

## Task 6: 统一错误响应格式
统一 API 错误响应格式。

- [x] SubTask 6.1: 定义统一错误响应模型 `_api_error()`
- [x] SubTask 6.2: 在 `manage_api.py` 中创建 `_api_error()` 辅助函数
- [x] SubTask 6.3: 在 `export_import_api.py` 中创建 `_api_error()` 辅助函数
- [x] SubTask 6.4: 统一所有 API 的错误响应格式
- [x] SubTask 6.5: 开发环境返回 detail，生产环境隐藏 detail

---

# Task Dependencies

- Task 1 独立
- Task 2 独立
- Task 3 独立
- Task 4 独立
- Task 5 独立
- Task 6 独立

# Parallelizable Work

所有任务可并行执行。

# 性能目标

| 场景 | 优化前 | 优化后 |
|------|--------|--------|
| 100 条 business_object 列表查询 | 500+ SQL | 5-10 SQL |
| 100 条 relationship 列表查询 | 600+ SQL | 2 SQL |
| 级联删除 1000 子记录 | 1000+ DELETE | 3-5 DELETE |
