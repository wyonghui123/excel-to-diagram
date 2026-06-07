# Tasks: BOFramework 代码质量与性能优化

## 里程碑 1: P0 安全与代码质量修复

### Task 1: FR-001 删除 bo_framework.py 死代码
- [ ] 1.1 grep 确认 `_execute_create/_execute_read/_execute_query/_execute_update/_execute_delete` 无外部引用
- [ ] 1.2 删除 `_execute_create` (L161-183)
- [ ] 1.3 删除 `_execute_read` (L185-203)
- [ ] 1.4 删除 `_execute_query` (L205-279)
- [ ] 1.5 删除 `_execute_update` (L281-308)
- [ ] 1.6 删除 `_execute_delete` (L310-323)
- [ ] 1.7 运行后端测试确认通过

### Task 2: FR-004 清理调试语句
- [ ] 2.1 清理 `bo_api.py` 中 L39, L43, L47 的 print 语句
- [ ] 2.2 清理 `persistence_interceptor.py` 中 `_do_list` 的所有 print 语句
- [ ] 2.3 清理 `persistence_interceptor.py` 中 `_do_list` 的写文件日志代码
- [ ] 2.4 清理 `bo_framework.py` 中 `_execute_after_interceptors` 的 print 语句
- [ ] 2.5 运行后端测试确认通过

### Task 3: FR-005 修正日志级别
- [ ] 3.1 修改 `persistence_interceptor.py` 中 `logger.critical` → `logger.debug`
- [ ] 3.2 确认 `bo_framework.py` 中死代码已删除（含 critical），无需额外修改
- [ ] 3.3 运行后端测试确认通过

### Task 4: FR-002 SQL 参数化 LIMIT/OFFSET
- [ ] 4.1 修改 `_do_list` 有搜索分支的 COUNT SQL，LIMIT/OFFSET 改为参数化
- [ ] 4.2 修改 `_do_list` 有搜索分支的 SELECT SQL，LIMIT/OFFSET 改为参数化
- [ ] 4.3 添加 limit/offset 类型校验和上限校验（max 500）
- [ ] 4.4 运行后端测试确认通过

### Task 5: FR-003 字段名白名单校验
- [ ] 5.1 修改 `_do_list` 的 else 分支，不在白名单中的字段名忽略并记录 warning
- [ ] 5.2 检查前端所有过滤请求参数是否在 YAML 中定义（解决 TBD-3）
- [ ] 5.3 运行后端测试确认通过

## 里程碑 2: P1 性能与架构优化

### Task 6: FR-007 FieldPolicy 框架级注册
- [ ] 6.1 检查 exceptions.py 是否已有 FieldPolicyViolationError（解决 TBD-2）
- [ ] 6.2 新建 `meta/core/interceptors/field_policy_interceptor.py`
- [ ] 6.3 在 `bo_framework.execute()` 中删除 L86-98 的内联实例化
- [ ] 6.4 在 `execute()` 的 except 块中添加 FieldPolicyViolationError 捕获
- [ ] 6.5 在 `server.py` 中注册 FieldPolicyInterceptor（priority=40）
- [ ] 6.6 运行后端测试确认通过

### Task 7: FR-006 can_delete 批量化
- [ ] 7.1 阅读 ManageService.check_can_delete 完整实现（解决 TBD-1）
- [ ] 7.2 新增 ManageService.batch_check_can_delete 方法
- [ ] 7.3 修改 QueryInterceptor._check_can_delete 调用批量方法
- [ ] 7.4 运行后端测试确认通过
- [ ] 7.5 性能对比测试

### Task 8: FR-008 前端缓存 LRU
- [ ] 8.1 新建 `src/utils/lruCache.js`
- [ ] 8.2 修改 `boService.js` 使用 LRUCache
- [ ] 8.3 修改 `metaService.js` 使用 LRUCache
- [ ] 8.4 前端功能验证

### Task 9: FR-009 前端 Service 基类
- [ ] 9.1 新建 `src/services/baseService.js`
- [ ] 9.2 重构 `boService.js` 继承 BaseService
- [ ] 9.3 重构 `metaService.js` 继承 BaseService
- [ ] 9.4 前端功能验证
