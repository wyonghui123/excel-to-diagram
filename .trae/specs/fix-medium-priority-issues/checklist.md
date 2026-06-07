# Checklist

## Task 1: 批量预加载关联名称
- [x] `_batch_load_names()` 函数支持批量查询多个表的名称
- [x] `_batch_get_single_records()` 函数支持批量查询完整记录
- [x] `_enrich_record_with_names()` 使用批量查询
- [x] 同一请求内相同 ID 只查询一次（缓存）
- [x] 100 条记录测试从 500+ SQL 降到 10 以内

## Task 2: 关系列表分类计算优化
- [x] 分类计算直接使用 JOIN 结果字段
- [x] `_compute_category_label` 和 `_compute_category_type` 合并为 `_compute_category`
- [x] `_compute_relation_stats` 不重复执行查询
- [x] 100 条关系记录测试从 600+ SQL 降到 5 以内

## Task 3: 级联删除批量操作
- [x] `execute_cascade` 使用批量 DELETE
- [x] 收集所有待删除 ID 后一次性删除
- [x] 1000 子记录删除从 1000+ SQL 降到 10 以内

## Task 4: 静默异常处理消除
- [x] `_get_single_record()` 记录 WARNING 日志
- [x] `_load_name()` 记录 WARNING 日志
- [x] `_enrich_relationship_data()` 记录 WARNING 日志
- [x] `_enrich_with_relations()` 记录 ERROR 日志
- [x] 无 `except: pass` 或 `except Exception: pass` 残留

## Task 5: print 替换为 logging
- [x] `sql_adapters.py` 使用 logger 替代 print（11 处）
- [x] `action_executor.py` 使用 logger 替代 print（1 处）
- [x] `rule_executor.py` 使用 logger 替代 print（3 处）
- [x] `cascade_service.py` 无 print 需替换
- [x] 日志格式统一：使用标准 logging 模块

## Task 6: 统一错误响应格式
- [x] `_api_error()` 辅助函数在 manage_api.py 中可用
- [x] `_api_error()` 辅助函数在 export_import_api.py 中可用
- [x] `_api_success()` 辅助函数在两个 API 文件中可用
- [x] 开发环境返回 detail，生产环境隐藏
