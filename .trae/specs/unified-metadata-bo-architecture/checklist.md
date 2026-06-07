# Checklist

## Phase 1: BO分类体系基础设施

### Task 1: BO 分类枚举和配置模板
- [ ] BusinessObjectCategory 枚举包含4种类型（TRANSACTIONAL/MASTER_DATA/ANALYTICAL/CONFIGURATION）
- [ ] BoSubCategory 枚举包含16种子类别
- [ ] BoCategoryConfig 数据类包含20+属性
- [ ] BO_CATEGORY_TEMPLATES 预置字典包含4种类型的完整默认值

### Task 2: MetaObject 扩展
- [ ] MetaObject 类新增 bo_category, bo_sub_category, category_config 字段
- [ ] __post_init__() 自动应用分类模板逻辑正确
- [ ] 辅助方法 is_transactional(), is_master_data() 实现正确
- [ ] 新字段有合理默认值（向后兼容）

### Task 3: 数据库迁移
- [ ] 迁移脚本为 business_objects 表添加3个新列
- [ ] 启发式推断规则覆盖主要场景（订单→事务型、客户→主数据、枚举→配置型）
- [ ] 索引创建成功
- [ ] SQLite 和 PostgreSQL 兼容性验证通过

### Task 4: 单元测试
- [ ] 现有BO加载测试通过（向后兼容）
- [ ] 新建BO指定分类后模板自动应用正确
- [ ] 启发式推断准确率 > 90%

## Phase 2: 增强字段元数据模型

### Task 5-7: 数据模型定义
- [ ] EnumReference 数据类完整实现，支持条件过滤和多语言JOIN
- [ ] DimensionReference 数据类完整实现，支持Search Help和冗余策略
- [ ] FieldDependency 数据类完整实现，支持可见性/必填性/值依赖

### Task 8: EnhancedMetaField
- [ ] EnhancedMetaField 正确继承 MetaField
- [ ] enum_reference, dimension_reference, dependencies 字段可用
- [ ] 从旧 enum_type_ref 自动转换到新 EnumReference 的兼容逻辑正确

### Task 9: YAML Loader
- [ ] YAML 解析器可正确解析新的 enum_reference / dimension_reference / dependencies 语法
- [ ] 提供的示例文件可通过 Loader 验证

## Phase 3: 混合适配器模式

### Task 10: 接口和 DTO
- [ ] IEnumProvider 接口定义6个方法（get_values, get_value_by_code, resolve_code_to_name, resolve_name_to_code, get_select_options, is_valid_value）
- [ ] IEnumAdmin 接口定义8个方法（create/update/delete type, create/update/delete value, batch_update_sort_order, toggle_active_status）
- [ ] DTO 类（EnumTypeDTO, EnumValueDTO, EnumSelectOption）字段完整

### Task 11: EnumRepository
- [ ] 封装所有 enum_types 表 CRUD 操作
- [ ] 封装所有 enum_values 表 CRUD 操作
- [ ] 支持维度过滤查询
- [ ] 支持分页和排序

### Task 12: CachedEnumProvider
- [ ] 实现 IEnumProvider 所有方法
- [ ] 集成 EnumCacheManager
- [ ] 缓存命中时响应 < 0.1ms
- [ ] 首次加载 < 5ms

### Task 13: SecureEnumAdmin
- [ ] 实现 IEnumAdmin 所有方法
- [ ] 每次写操作调用 AuditInterceptor 记录审计日志
- [ ] 每次写操作检查权限
- [ ] 写入成功后调用缓存失效

### Task 14: EnumCacheManager
- [ ] L1 进程内缓存正常工作
- [ ] TTL 兜底失效机制生效（5分钟）
- [ ] 事件驱动 invalidate() 方法正确清除缓存
- [ ] 预热功能可加载所有活跃枚举
- [ ] 缓存统计功能正常

### Task 15: API 重构
- [ ] 现有 API 端点保持不变且正常工作
- [ ] 新增 GET /api/v1/enums/{type}/options 高速端点
- [ ] 内部实现使用适配器模式
- [ ] 前端旧代码无需修改即可运行

## Phase 4: 工具链集成与迁移

### Task 16: 前端适配
- [ ] enumService.js 支持新接口
- [ ] EnumSelect 组件性能优化
- [ ] 向后兼容验证通过

### Task 17: 性能验证
- [ ] 枚举查询 P99 < 5ms
- [ ] 缓存命中率 > 99%
- [ ] 压测报告生成

## 架构质量验收

### 向后兼容性
- [ ] 现有 100% BO 可正常加载
- [ ] 现有枚举 API 端点无破坏性变更
- [ ] 现有前端页面无需修改即可工作

### 代码质量
- [ ] 新增模块代码覆盖率 > 80%
- [ ] 类型注解完整
- [ ] 文档字符串清晰

### 性能指标
- [ ] L1 缓存命中率 > 99%
- [ ] P50 响应时间 < 1ms
- [ ] P99 响应时间 < 5ms
- [ ] 缓存预热耗时 < 2s

### 安全性
- [ ] 写入操作必须经过认证授权
- [ ] 写入操作必须记录审计日志
- [ ] 权限检查逻辑正确（管理员 vs 普通用户）

### 可维护性
- [ ] 接口定义清晰（IEnumProvider/IEnumAdmin 分离读写）
- [ ] 适配器层代码简洁（< 500行）
- [ ] 提供完整的 YAML 配置示例
- [ ] 提供架构设计文档
