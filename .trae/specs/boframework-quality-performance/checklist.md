# Checklist: BOFramework 代码质量与性能优化

## P0 安全与代码质量

### FR-001: 删除死代码
- [ ] grep 确认 `_execute_create` 无外部引用
- [ ] grep 确认 `_execute_read` 无外部引用
- [ ] grep 确认 `_execute_query` 无外部引用
- [ ] grep 确认 `_execute_update` 无外部引用
- [ ] grep 确认 `_execute_delete` 无外部引用
- [ ] 5 个方法已删除
- [ ] `_execute_core` 保持不变
- [ ] 后端测试全部通过

### FR-002: SQL 参数化 LIMIT/OFFSET
- [ ] `_do_list` 有搜索分支 COUNT SQL 使用 `LIMIT ? OFFSET ?`
- [ ] `_do_list` 有搜索分支 SELECT SQL 使用 `LIMIT ? OFFSET ?`
- [ ] limit/offset 类型校验（非负整数）
- [ ] limit 上限校验（max 500）
- [ ] 后端测试全部通过

### FR-003: 字段名白名单校验
- [ ] `_do_list` else 分支不在白名单中的字段名被忽略
- [ ] 忽略时记录 warning 日志
- [ ] 前端过滤字段全部在 YAML 中定义（已验证）
- [ ] 后端测试全部通过

### FR-004: 清理调试语句
- [ ] `bo_api.py` 无 print 语句
- [ ] `persistence_interceptor.py` 无 print 语句
- [ ] `persistence_interceptor.py` 无写文件日志
- [ ] `bo_framework.py` 无 print 语句
- [ ] `grep -r "print(" meta/` 无结果（排除测试文件）
- [ ] 后端测试全部通过

### FR-005: 修正日志级别
- [ ] `persistence_interceptor.py` 无 `logger.critical`（正常流程）
- [ ] 错误场景保留 `logger.error`
- [ ] 审计相关保留 `logger.info`
- [ ] 后端测试全部通过

## P1 性能与架构优化

### FR-006: can_delete 批量化
- [ ] `ManageService.batch_check_can_delete` 方法已实现
- [ ] `QueryInterceptor._check_can_delete` 调用批量方法
- [ ] 批量方法返回 dict `{id: can_delete_bool}`
- [ ] 100 条记录查询性能提升 50%+
- [ ] 后端测试全部通过

### FR-007: FieldPolicy 框架级注册
- [ ] `field_policy_interceptor.py` 已创建
- [ ] `bo_framework.execute()` 中内联实例化已删除
- [ ] `execute()` 的 except 块捕获 FieldPolicyViolationError
- [ ] `server.py` 注册 FieldPolicyInterceptor（priority=40）
- [ ] FieldPolicy 校验失败返回 `ActionResult(success=False)`
- [ ] 后端测试全部通过

### FR-008: 前端缓存 LRU
- [ ] `lruCache.js` 已创建
- [ ] LRUCache 提供 get/set/delete/clear/size 方法
- [ ] 最大缓存 100 条
- [ ] 超时逻辑保持不变
- [ ] `boService.js` 使用 LRUCache
- [ ] `metaService.js` 使用 LRUCache
- [ ] 前端功能验证通过

### FR-009: 前端 Service 基类
- [ ] `baseService.js` 已创建
- [ ] 包含 `_handleResponse/_getHeaders/_getAuthStore/缓存逻辑`
- [ ] `boService.js` 继承 BaseService
- [ ] `metaService.js` 继承 BaseService
- [ ] 401 自动登出逻辑只在基类中实现
- [ ] 前端功能验证通过

## 全局验证

- [ ] 所有后端测试通过
- [ ] 前端列表页加载正常
- [ ] 前端过滤功能正常
- [ ] 前端搜索功能正常
- [ ] 前端分页功能正常
- [ ] 前端 CRUD 操作正常
- [ ] API 响应格式不变
