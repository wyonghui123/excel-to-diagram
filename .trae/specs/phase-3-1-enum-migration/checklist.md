# Phase 3.1: 枚举对象迁移 - 验收清单

> **开始日期**: 2026-05-11
> **计划周期**: Week 1-2 (约10个工作日)
> **状态**: 📋 规划中

---

## 总体验收标准

| 类别 | 完成标准 | 状态 |
|------|----------|------|
| **功能** | 枚举对象100%功能覆盖 | ⏳ |
| **代码** | 新增代码 < 300行 | ⏳ |
| **测试** | 测试覆盖率 ≥ 90% | ⏳ |
| **迁移** | enum_api.py减少 ≥ 500行 | ⏳ |
| **兼容** | 向后兼容100%保持 | ⏳ |

---

## Phase 3.1.1: EnumProtectionInterceptor 创建

### 任务 1.1: 创建拦截器文件

- [ ] 文件 `meta/core/interceptors/enum_protection_interceptor.py` 创建成功
- [ ] EnumProtectionInterceptor 类结构正确
- [ ] priority 属性返回 35
- [ ] before_action 方法签名正确
- [ ] _validate_update 方法存在
- [ ] _validate_delete 方法存在

### 任务 1.2: 系统枚举保护

- [ ] 系统枚举修改返回错误 `ENUM_IMMUTABLE`
- [ ] 系统枚举删除返回错误 `ENUM_IMMUTABLE`
- [ ] 有值的枚举类型删除返回错误 `HAS_VALUES`
- [ ] 单元测试通过

### 任务 1.3: 锁定枚举保护

- [ ] 锁定枚举的值修改返回错误 `ENUM_LOCKED`
- [ ] 锁定枚举的值删除返回错误 `ENUM_LOCKED`
- [ ] 单元测试通过

### 任务 1.4: 系统预置值保护

- [ ] 系统预置值删除返回错误 `SYSTEM_VALUE_IMMUTABLE`
- [ ] 单元测试通过

### 任务 1.5: 注册拦截器

- [ ] 在 bo_framework.py 中正确导入
- [ ] 在 BOFramework.__init__ 中注册
- [ ] 拦截器优先级正确（35）

---

## Phase 3.1.2: enum_type.yaml 增强

### 任务 2.1: aspects 引用

- [ ] `aspects: [audit_aspect]` 添加成功
- [ ] YAML 语法正确
- [ ] 通过 schema 验证

### 任务 2.2: import_export 配置

- [ ] `import_export.import_enabled: true`
- [ ] `import_export.export_enabled: true`
- [ ] `import_export.cascade_export: false`
- [ ] `import_export.conflict_strategy: upsert`
- [ ] YAML 语法正确

### 任务 2.3: audit 配置

- [ ] `audit.enabled: true`
- [ ] `audit.strategy: changed_only`
- [ ] 审计日志正确记录

### 任务 2.4: validations 约束

- [ ] `system_immutable` 校验规则添加
- [ ] `system_no_delete` 校验规则添加
- [ ] 系统枚举保护生效

---

## Phase 3.1.3: enum_value.yaml 增强

### 任务 3.1: aspects 引用

- [ ] `aspects: [audit_aspect]` 添加成功
- [ ] YAML 语法正确
- [ ] 通过 schema 验证

### 任务 3.2: import_export 配置

- [ ] `import_export.import_enabled: true`
- [ ] `import_export.export_enabled: true`
- [ ] `import_export.conflict_key: "enum_type_id,code"`
- [ ] YAML 语法正确

### 任务 3.3: audit 配置

- [ ] `audit.enabled: true`
- [ ] `audit.strategy: changed_only`
- [ ] 审计日志正确记录

### 任务 3.4: validations 约束

- [ ] `locked_enum_no_modify` 校验规则添加
- [ ] `locked_enum_no_delete` 校验规则添加
- [ ] `system_value_no_delete` 校验规则添加
- [ ] 锁定枚举保护生效
- [ ] 系统值保护生效

---

## Phase 3.1.4: v2 API 路由

### 任务 4.1: 枚举类型 API

- [ ] `POST /api/v2/bo/enum_type` 创建路由正确
- [ ] `GET /api/v2/bo/enum_type` 查询路由正确
- [ ] `GET /api/v2/bo/enum_type/:id` 详情路由正确
- [ ] `PUT /api/v2/bo/enum_type/:id` 更新路由正确
- [ ] `DELETE /api/v2/bo/enum_type/:id` 删除路由正确
- [ ] CRUD 操作测试通过

### 任务 4.2: 枚举值 API

- [ ] `GET /api/v2/bo/enum_type/:enum_type_id/values` 查询路由正确
- [ ] `POST /api/v2/bo/enum_type/:enum_type_id/values` 创建路由正确
- [ ] `GET /api/v2/bo/enum_value/:id` 详情路由正确
- [ ] `PUT /api/v2/bo/enum_value/:id` 更新路由正确
- [ ] `DELETE /api/v2/bo/enum_value/:id` 删除路由正确
- [ ] CRUD 操作测试通过

### 任务 4.3: 分页查询

- [ ] `page` 参数正确处理
- [ ] `page_size` 参数正确处理
- [ ] `keyword` 搜索功能正常
- [ ] `category` 过滤功能正常
- [ ] `mutability` 过滤功能正常
- [ ] 返回格式 `{items, total, page, page_size}` 正确

### 任务 4.4: computed 字段

- [ ] `value_count` 计算字段返回正确
- [ ] `dimension_count` 计算字段返回正确
- [ ] 列表显示正常

### 任务 4.5: 变更历史

- [ ] enum_type 详情包含 `change_history`
- [ ] 审计日志正确记录 CREATE/UPDATE/DELETE
- [ ] 变更历史查询测试通过

### 任务 4.6: 权限控制

- [ ] 创建需要管理员权限，未授权返回 403
- [ ] 更新需要管理员权限，未授权返回 403
- [ ] 删除需要管理员权限，未授权返回 403
- [ ] 查询需要登录权限，未登录返回 401

---

## Phase 3.1.5: 维度过滤扩展

### 任务 5.1: 扩展 PersistenceInterceptor

- [ ] `_do_list` 方法添加维度过滤逻辑
- [ ] `dimensions` JSON 字段过滤正确
- [ ] 多维度组合过滤正常

### 任务 5.2: 测试

- [ ] 单维度过滤测试通过
- [ ] 多维度组合过滤测试通过
- [ ] 测试覆盖率 ≥ 80%

### 任务 5.3: 性能优化

- [ ] 查询性能可接受（< 500ms）
- [ ] 无明显性能问题
- [ ] 如需要，JSON 索引已添加

---

## Phase 3.1.6: 端到端测试

### 任务 6.1: 单元测试

- [ ] EnumProtectionInterceptor 测试覆盖率 ≥ 90%
- [ ] 所有测试通过
- [ ] 测试报告生成

### 任务 6.2: 集成测试

- [ ] 枚举类型 CRUD 测试通过
- [ ] 枚举值 CRUD 测试通过
- [ ] 维度过滤测试通过
- [ ] 审计日志测试通过
- [ ] 保护机制测试通过

### 任务 6.3: 向后兼容测试

- [ ] enum_api.py 重定向到 v2 API
- [ ] 数据一致性验证通过
- [ ] 无数据丢失

### 任务 6.4: 文档更新

- [ ] API 文档更新完整
- [ ] 架构文档更新完整
- [ ] README 更新完整
- [ ] 链接有效

---

## 特殊场景测试

### 系统枚举保护测试

- [ ] 创建系统枚举 → 成功
- [ ] 修改系统枚举 → 返回错误
- [ ] 删除空系统枚举 → 返回错误
- [ ] 删除有值的系统枚举 → 返回错误

### 锁定枚举保护测试

- [ ] 创建锁定枚举类型 → 成功
- [ ] 修改锁定枚举类型的值 → 返回错误
- [ ] 删除锁定枚举类型的值 → 返回错误

### 系统预置值保护测试

- [ ] 删除系统预置枚举值 → 返回错误
- [ ] 修改系统预置枚举值 → 成功
- [ ] 查看系统预置枚举值 → 成功

### 维度过滤测试

- [ ] 按单个维度过滤 → 正确
- [ ] 按多个维度组合过滤 → 正确
- [ ] 维度值为空时过滤 → 正确

---

## 最终验收

### 功能验收

- [ ] enum_type 功能 100% 覆盖
- [ ] enum_value 功能 100% 覆盖
- [ ] 所有 API 端点正常
- [ ] 所有保护机制生效

### 性能验收

- [ ] API 响应时间 < 500ms
- [ ] 数据库查询优化完成
- [ ] 无内存泄漏

### 代码质量验收

- [ ] 新增代码 < 300行
- [ ] 测试覆盖率 ≥ 90%
- [ ] 无新增技术债务
- [ ] 代码风格符合规范

### 迁移验收

- [ ] enum_api.py 代码减少 ≥ 500行
- [ ] 向后兼容 100% 保持
- [ ] 无功能退化
- [ ] 文档完整

---

## Phase 3.1.7: 前端适配

### 任务 7.1: EnumTypeManagement.vue 适配

- [ ] API路径从 `/api/v1/enum-types` 改为 `/api/v2/bo/enum_type`
- [ ] 返回格式适配：`data.data` → `data.items`
- [ ] 分页功能正常
- [ ] 筛选功能正常
- [ ] 列表显示正常
- [ ] 变更历史功能正常

### 任务 7.2: EnumValueManagement.vue 适配

- [ ] API路径从 `/api/v1/enum-types/:id/values` 改为 `/api/v2/bo/enum_value`
- [ ] 通过 `enum_type_id` 参数过滤
- [ ] 枚举值列表显示正常
- [ ] 维度过滤功能正常
- [ ] 搜索功能正常
- [ ] 分页功能正常

### 任务 7.3: EnumTypeCreate.vue 适配

- [ ] API路径从 `/api/v1/enum-types` 改为 `/api/v2/bo/enum_type`
- [ ] POST 请求正常工作
- [ ] 新建枚举类型功能正常
- [ ] 表单验证正常
- [ ] 成功提示正常

### 任务 7.4: EnumValueFormDialog.vue 适配

- [ ] API路径从 `/api/v1/enum-types/:id/values` 改为 `/api/v2/bo/enum_value`
- [ ] 创建枚举值功能正常
- [ ] 编辑枚举值功能正常
- [ ] 删除枚举值功能正常
- [ ] 维度配置功能正常

### 前端适配整体验收

- [ ] 枚举类型管理页面完全可用
- [ ] 枚举值管理页面完全可用
- [ ] 新建枚举类型功能完全可用
- [ ] 新建/编辑枚举值功能完全可用
- [ ] 错误提示正常显示
- [ ] 系统枚举保护在前端正确提示
- [ ] 锁定枚举保护在前端正确提示
- [ ] 浏览器控制台无错误
- [ ] 所有按钮点击正常
- [ ] 页面跳转正常

---

## 签署确认

| 角色 | 姓名 | 日期 | 签名 |
|------|------|------|------|
| 开发 | | | |
| 测试 | | | |
| PM | | | |
| 架构 | | | |

---

**清单版本**: v1.0
**最后更新**: 2026-05-11
**下次审查**: Phase 3.1 完成后
