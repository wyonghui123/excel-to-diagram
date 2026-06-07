# 元数据驱动架构重构 - 任务清单

> 基于 SAP One Model 和 Analytics Query View 最佳实践

---

## Phase 1: 统一层级过滤服务

### TD-1: 移除硬编码层级链

**目标**: 确保所有代码都从 `hierarchies.yaml` 读取层级链

**任务**:
- [x] 检查 `config_driven_hierarchy_filter.py` 是否完全使用配置
- [x] 检查 `hierarchy_filter_service.py` 是否有硬编码
- [x] 检查 `import_export_service.py` 是否有硬编码
- [x] 检查 `manage_api.py` 是否有硬编码
- [x] 重构 `cascade_service.py` 使用配置驱动
- [x] 重构 `hierarchy_validation_service.py` 使用配置驱动
- [x] 添加配置缺失时的错误提示

**验收标准**:
- [x] 搜索代码库无 `domain → sub_domain → service_module` 硬编码字符串
- [x] 配置文件缺失时有明确的错误提示
- [x] 68 个配置驱动相关测试通过

---

### TD-2: 前端过滤条件构建统一

**目标**: 前端只传节点ID，后端负责转换为过滤条件

**任务**:
- [x] 审查 `hierarchyFilterBuilder.js` 的职责
- [x] 添加 `fetchHierarchyConfig()` 函数从 API 获取配置
- [x] 添加 `getFallbackConfig()` 作为降级方案
- [x] 更新所有函数支持 config 参数
- [x] 后端 API 接收节点ID并转换为过滤条件

**验收标准**:
- [x] 前端不再硬编码 HIERARCHY_LEVELS
- [x] 前端可从 API 动态获取配置
- [x] 后端统一处理节点ID到过滤条件的转换

---

### P1-3: 元数据 API 增强

**目标**: 提供前端动态获取元数据的 API

**任务**:
- [x] 实现 `GET /api/v1/meta/hierarchies` 端点
- [x] 实现 `GET /api/v1/meta/hierarchies/<id>/levels` 端点
- [x] 实现 `GET /api/v1/meta/hierarchies/config` 端点
- [x] 实现 `GET /api/v1/meta/objects/<type>/field_controls` 端点
- [x] 添加 API 单元测试

**验收标准**:
- [x] API 返回正确的元数据配置
- [x] 18 个 API 测试通过

---

## Phase 2: 关系过滤语义统一

### P2.5: 字段控制属性统一

**目标**: 确保前后端字段控制属性逻辑一致

**任务**:
- [x] 审查后端 `_is_field_editable` 方法
- [x] 审查前端 `isFieldEditable` 方法
- [x] 确认 `business_key` 处理一致（新建必填+唯一，编辑只读）
- [x] 确认 `parent_key` 处理一致（新建必填，编辑可改）
- [x] 确认 `immutable` 处理一致（新建可编辑，编辑只读）
- [x] 确认 `readonly_always` 处理一致（始终只读）
- [x] 确认 `mandatory` 处理一致（业务必填）
- [x] 添加字段控制 API 端点

**验收标准**:
- [x] 前后端字段可编辑性判断一致
- [x] 导入导出列样式正确标记
- [x] 表单字段正确禁用/启用

---

### TD-4: 关系过滤语义统一

**目标**: 添加 `scope_mode` 参数支持不同的过滤语义

**任务**:
- [x] 定义 `scope_mode` 参数: `involved` (OR) / `internal` (AND)
- [x] 后端 `manage_api.py` 支持 `scope_mode` 参数
- [x] 添加相关测试

**验收标准**:
- [x] `scope_mode=involved` 返回至少一端在范围内的关系
- [x] `scope_mode=internal` 返回两端都在范围内的关系

---

## Phase 3: Analytics Query 支持

### P2-1: AnalyticsConfig 扩展

**目标**: 支持分析查询配置

**任务**:
- [ ] 在 `models.py` 中添加 `AnalyticsConfig` 类
- [ ] 扩展 `ViewConfig` 支持 `analytics` 属性
- [ ] 更新 `yaml_loader.py` 解析 analytics 配置
- [ ] 创建示例 YAML 文件

**验收标准**:
- YAML 中可定义 analytics 配置
- Python 模型正确解析配置

---

### P2-2: 分析查询 API

**目标**: 提供分析查询能力

**任务**:
- [ ] 实现 `GET /api/v1/analytics/<view_id>` 端点
- [ ] 支持维度和度量查询
- [ ] 支持过滤和分组
- [ ] 添加缓存机制

**验收标准**:
- API 返回正确的聚合结果
- 查询性能满足要求

---

## Phase 4: Aspects 机制（可选）

### P3-1: Aspects 设计与实现

**目标**: 支持字段组合复用

**任务**:
- [ ] 设计 aspects YAML 结构
- [ ] 实现 `apply_aspects` 函数
- [ ] 更新现有对象定义使用 aspects
- [ ] 添加测试

**验收标准**:
- 对象可引用 aspects
- aspects 字段正确合并到对象定义

---

## Phase 5: 关系类型增强（可选）

### P3-2: 关系类型扩展

**目标**: 支持更精细的关系类型

**任务**:
- [ ] 扩展 `RelationType` 枚举
- [ ] 更新 `hierarchies.yaml` 支持关系类型配置
- [ ] 实现不同的删除行为策略
- [ ] 添加测试

**验收标准**:
- 支持 composition / aggregation / reference 类型
- 删除行为按配置正确执行
