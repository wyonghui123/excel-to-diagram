# Tasks

## Phase 1: 核心服务实现（P0 - 必须完成）

### Task 1: 创建 BusinessKeyService 基础服务
- [ ] 1.1 创建 `meta/services/business_key_service.py` 文件
- [ ] 1.2 实现 `id_to_business_key()` 方法
  - 从元数据读取 `business_key: true` 字段
  - 查询数据库获取字段值
  - 格式化输出业务键
- [ ] 1.3 实现 `batch_convert()` 方法
  - 支持批量转换
  - 优化数据库查询（单次查询）
- [ ] 1.4 实现多格式输出支持
  - `full`: 完整格式（含层级）
  - `short`: 简短格式（仅名称+编码）
  - `minimal`: 最小格式（仅编码）
- [ ] 1.5 添加缓存机制
  - 使用内存缓存（LRU策略）
  - 支持缓存失效

### Task 2: 创建 HierarchyPathService 层级路径服务
- [ ] 2.1 创建 `meta/services/hierarchy_path_service.py` 文件
- [ ] 2.2 扩展 `meta/schemas/hierarchies.yaml`
  - 定义 `absolute_full_path` 路径模板
  - 配置路径段（product → version → domain → ...）
  - 设置分隔符和最大长度
- [ ] 2.3 实现 `get_full_path()` 方法
  - 解析层级定义
  - 递归查询父级对象
  - 构建完整路径
- [ ] 2.4 实现路径格式化
  - 支持多种路径类型
  - 智能截断超长路径
  - 返回路径段列表
- [ ] 2.5 实现 `batch_get_paths()` 方法
  - 批量获取路径
  - 优化查询性能

### Task 3: 创建 ObjectIdentityService 统一标识服务
- [ ] 3.1 创建 `meta/services/object_identity_service.py` 文件
- [ ] 3.2 注入 BusinessKeyService 和 HierarchyPathService
- [ ] 3.3 实现 `get_identity()` 方法
  - 整合 Key 信息（业务键）
  - 整合 Hierarchy 信息（层级路径）
  - 返回完整标识对象
- [ ] 3.4 实现 `batch_get_identities()` 方法
  - 批量获取标识
  - 合并查询结果
- [ ] 3.5 实现多格式输出
  - `full`: 完整标识（含层级路径）
  - `short`: 简短标识（仅业务键）
  - `technical`: 技术标识（ID + 类型）
  - `detailed`: 详细标识（所有信息）

### Task 4: 编写核心服务单元测试
- [ ] 4.1 创建 `meta/tests/test_business_key_service.py`
  - 测试单个对象转换
  - 测试批量转换
  - 测试元数据驱动配置
  - 测试缓存机制
- [ ] 4.2 创建 `meta/tests/test_hierarchy_path_service.py`
  - 测试完整路径计算
  - 测试路径格式化
  - 测试路径截断
  - 测试批量获取
- [ ] 4.3 创建 `meta/tests/test_object_identity_service.py`
  - 测试完整标识获取
  - 测试批量获取
  - 测试多格式输出

## Phase 2: API 接口实现（P1 - 高优先级）

### Task 5: 创建 ObjectIdentityAPI
- [ ] 5.1 创建 `meta/api/object_identity_api.py` 文件
- [ ] 5.2 实现 `GET /api/v1/identity` 接口
  - 接收参数：object_type, object_id, format
  - 调用 ObjectIdentityService
  - 返回 JSON 响应
- [ ] 5.3 实现 `POST /api/v1/identity/batch` 接口
  - 接收对象列表
  - 批量调用服务
  - 返回映射字典
- [ ] 5.4 添加错误处理
  - 参数验证
  - 异常捕获
  - 错误响应格式
- [ ] 5.5 注册蓝图到主应用

### Task 6: 编写 API 测试
- [ ] 6.1 创建 `meta/tests/test_object_identity_api.py`
  - 测试单个对象查询
  - 测试批量查询
  - 测试错误处理
  - 测试性能（响应时间）

## Phase 3: 前端集成（P1 - 高优先级）

### Task 7: 创建 useObjectIdentity Composable
- [ ] 7.1 创建 `src/composables/useObjectIdentity.js` 文件
- [ ] 7.2 实现 `getIdentity()` 方法
  - 调用 API 接口
  - 返回响应式数据
- [ ] 7.3 实现 `batchGetIdentities()` 方法
  - 批量调用 API
  - 返回映射字典
- [ ] 7.4 实现缓存机制
  - 使用 `ref` 存储缓存
  - 缓存键：`${objectType}:${objectId}:${format}`
  - 缓存失效策略
- [ ] 7.5 实现错误处理
  - API 调用失败处理
  - 加载状态管理

### Task 8: 迁移审计日志页面
- [ ] 8.1 修改 `src/views/SystemManagement/AuditLogManagement.vue`
  - 引入 `useObjectIdentity`
  - 替换硬编码的业务键生成逻辑
- [ ] 8.2 优化审计日志展示
  - 使用完整标识显示
  - 支持展开查看层级路径
- [ ] 8.3 测试前端功能
  - 测试审计日志显示正确
  - 测试缓存生效
  - 测试性能

## Phase 4: 迁移与废弃（P2 - 中优先级）

### Task 9: 迁移 audit_api.py
- [ ] 9.1 修改 `_generate_business_key()` 函数
  - 标记为 `@deprecated`
  - 内部调用 BusinessKeyService
- [ ] 9.2 更新所有调用方
  - 审计日志 API
  - 其他使用该函数的地方
- [ ] 9.3 添加迁移文档
  - 说明新旧 API 差异
  - 提供迁移示例

### Task 10: 清理硬编码配置
- [ ] 10.1 标记 `BUSINESS_KEY_METADATA` 为废弃
- [ ] 10.2 添加迁移脚本
  - 将硬编码配置转换为元数据定义
- [ ] 10.3 更新文档
  - 说明新的元数据驱动方式
  - 提供配置示例

## Phase 5: 文档与验收（P2 - 中优先级）

### Task 11: 编写文档
- [ ] 11.1 编写服务使用文档
  - BusinessKeyService 使用指南
  - HierarchyPathService 使用指南
  - ObjectIdentityService 使用指南
- [ ] 11.2 编写 API 文档
  - 接口说明
  - 请求/响应示例
  - 错误码说明
- [ ] 11.3 编写前端集成文档
  - useObjectIdentity 使用指南
  - 最佳实践

### Task 12: 性能优化与验收
- [ ] 12.1 性能测试
  - 单个对象查询性能
  - 批量查询性能
  - 缓存命中率
- [ ] 12.2 代码质量检查
  - Lint 检查
  - 类型检查
  - 代码覆盖率
- [ ] 12.3 最终验收
  - 所有测试通过
  - 所有检查点完成

# Task Dependencies

- [Task 2] depends on [Task 1] (BusinessKeyService 需要先实现)
- [Task 3] depends on [Task 1, Task 2] (ObjectIdentityService 整合两个服务)
- [Task 4] depends on [Task 1, Task 2, Task 3]
- [Task 5] depends on [Task 3] (API 调用 ObjectIdentityService)
- [Task 6] depends on [Task 5]
- [Task 7] depends on [Task 5] (Composable 调用 API)
- [Task 8] depends on [Task 7]
- [Task 9] depends on [Task 1, Task 8]
- [Task 10] depends on [Task 9]
- [Task 11] depends on [Task 1-10]
- [Task 12] depends on [Task 1-11]

# Risk Mitigation

## 风险 1: 元数据模型不完整
- **影响**: BusinessKeyService 无法正确读取字段定义
- **缓解措施**: 
  - Phase 1 实现时先验证元数据完整性
  - 提供默认值和降级策略

## 风险 2: 性能问题
- **影响**: 批量查询时响应时间过长
- **缓解措施**:
  - 实现缓存机制
  - 优化数据库查询（单次批量查询）
  - 添加性能监控

## 风险 3: 向后兼容性
- **影响**: 迁移过程中旧代码可能失效
- **缓解措施**:
  - 保留旧函数并标记废弃
  - 渐进式迁移
  - 完整的测试覆盖

## 风险 4: 前端集成复杂度
- **影响**: 前端迁移工作量大
- **缓解措施**:
  - 先实现 Composable
  - 提供迁移示例
  - 逐步迁移页面

# Estimated Timeline

- **Phase 1**: 2-3 天（核心服务）
- **Phase 2**: 1 天（API 接口）
- **Phase 3**: 1-2 天（前端集成）
- **Phase 4**: 1 天（迁移与废弃）
- **Phase 5**: 1 天（文档与验收）

**总计**: 6-8 天
