# 管理维度权限配置界面验收检查清单

## 核心引擎验收

- [ ] ManagementDimensionEngine 成功加载 hierarchies.yaml 和 permission_rule.yaml 元数据
- [ ] `get_available_dimensions()` 返回正确的管理维度列表（产品、版本、领域、子领域等）
- [ ] `calculate_impact()` 正确计算受影响的对象及其父子关联
- [ ] `_build_impact_query()` 基于 condition 正确构建 SQL 查询
- [ ] `_apply_inheritance_rules()` 正确处理向下继承和向上传播
- [ ] EnumCacheManager 集成成功，缓存功能正常
- [ ] 单元测试覆盖率 > 80%

## API 端点验收

- [ ] `GET /api/v1/management-dimensions` 返回正确的管理维度列表
- [ ] `GET /api/v1/management-dimensions/{dimension_id}/instances` 返回正确的实例列表（用于 value help）
- [ ] `GET /api/v1/roles/{role_id}/permission-rules` 返回角色的权限规则
- [ ] `POST /api/v1/roles/{role_id}/permission-rules` 成功保存权限规则到 permission_rule 表
- [ ] `POST /api/v1/roles/{role_id}/calculate-impact` 正确计算影响范围
- [ ] `GET /api/v1/meta/cache-stats` 返回缓存统计信息
- [ ] API 集成测试全部通过

## 前端组件验收

### ManagementDimensionSelector 组件

- [ ] 维度列表/卡片视图切换正常
- [ ] 维度搜索、过滤功能正常
- [ ] 维度规则数量显示正确
- [ ] 维度选择事件正常触发（v-model 绑定）
- [ ] 组件单元测试通过

### ConditionRuleEditor 组件

- [ ] 条件字段选择器正常工作（动态加载字段列表）
- [ ] 操作符选择器正常（=, !=, IN, NOT IN, LIKE, >, <）
- [ ] 值输入框和 value help 按钮正常
- [ ] ValueHelpDialog 组件正常工作（实例选择对话框）
- [ ] 权限级别选择器正常（read/write/admin）
- [ ] 继承规则配置正常（向下继承、向上传播）
- [ ] 禁止权配置正常（is_denied）
- [ ] 组件单元测试通过

### ImpactPreview 组件

- [ ] 统计摘要显示正确（按对象类型分组）
- [ ] 详细对象清单表格正确显示
- [ ] 影响方式标记正确（直接匹配/向下继承/向上传播）
- [ ] 排序、过滤功能正常
- [ ] 导出 Excel 功能正常
- [ ] 组件单元测试通过

### RolePermissionCenter 组件

- [ ] 4 区域布局正确显示
- [ ] 区域 1（管理维度选择器）集成 ManagementDimensionSelector 正常
- [ ] 区域 2（条件规则编辑器）集成 ConditionRuleEditor 正常
- [ ] 区域 3（影响范围预览）集成 ImpactPreview 正常
- [ ] 区域 4（已配置规则列表）表格展示正常
- [ ] 区域间数据联动正确（维度选择→加载规则→计算影响）
- [ ] 保存逻辑正确（保存到 permission_rule 表 + 失效缓存）
- [ ] 端到端测试通过

## 功能验收

### 管理维度元数据管理

- [ ] 默认管理维度列表正确显示（产品、版本、领域、子领域等）
- [ ] 支持添加自定义管理维度
- [ ] 维度元数据来源正确（hierarchies.yaml 和 permission_rule.yaml）

### 条件规则编辑器

- [ ] 配置领域维度条件规则正常
- [ ] 配置产品维度条件规则正常
- [ ] 配置权限级别和继承规则正常
- [ ] Value Help 显示实例列表正确

### 影响范围实时预览

- [ ] 计算领域维度的影响范围正确
- [ ] 查看详细影响对象清单正常
- [ ] 向上父关联计算正确
- [ ] 向下级联计算正确

### 管理维度配置界面布局

- [ ] 界面布局正确（4 区域）
- [ ] 选择管理维度正常
- [ ] 保存条件规则正常

## 性能验收

- [ ] 缓存命中时，权限影响计算 < 0.1ms
- [ ] 首次计算时，权限影响计算 < 100ms
- [ ] 缓存命中率 > 95%
- [ ] 界面响应时间 < 200ms
- [ ] 并发测试通过（50 用户同时配置）
- [ ] 热点角色权限规则预热功能正常

## 权限规则缓存与性能

- [ ] 缓存权限规则计算结果正常
- [ ] 规则变更后缓存自动失效
- [ ] 性能指标达标

## 文档验收

- [ ] 用户操作手册完整、清晰
- [ ] API 文档完整、准确
- [ ] 操作演示视频录制完成
- [ ] 运维手册完整（缓存管理、性能监控）

## 灰度发布验收

- [ ] 测试环境完整测试通过
- [ ] 生产环境灰度发布成功（10% 用户）
- [ ] 监控错误率和性能指标正常
- [ ] 全量发布成功

## 向后兼容性验收

- [ ] 现有 permission_rule 表数据保持不变
- [ ] 现有权限检查逻辑不受影响
- [ ] 新界面与旧数据兼容
