# Tasks

## Phase 1: 核心引擎开发 (Week 1)

- [x] Task 1: 实现 ManagementDimensionEngine 核心引擎
  - [x] SubTask 1.1: 创建 `meta/services/management_dimension_engine.py`
  - [x] SubTask 1.2: 实现 `_load_dimension_metadata()` - 从 hierarchies.yaml 和 permission_rule.yaml 加载维度定义
  - [x] SubTask 1.3: 实现 `get_available_dimensions()` - 获取可用管理维度列表
  - [x] SubTask 1.4: 实现 `calculate_impact()` - 计算权限影响范围（核心方法）
  - [x] SubTask 1.5: 实现 `_build_impact_query()` - 基于 condition 构建影响范围查询
  - [x] SubTask 1.6: 实现 `_apply_inheritance_rules()` - 应用向下继承和向上传播规则
  - [x] SubTask 1.7: 集成 `EnumCacheManager` - 复用缓存能力
  - [x] SubTask 1.8: 编写单元测试（覆盖率 > 80%）

- [x] Task 2: 实现 API 端点
  - [x] SubTask 2.1: 实现 `GET /api/v1/management-dimensions` - 获取管理维度列表
  - [x] SubTask 2.2: 实现 `GET /api/v1/management-dimensions/{dimension_id}/instances` - 获取维度实例列表（用于 value help）
  - [x] SubTask 2.3: 实现 `GET /api/v1/roles/{role_id}/permission-rules` - 获取角色的权限规则
  - [x] SubTask 2.4: 实现 `POST /api/v1/roles/{role_id}/permission-rules` - 保存权限规则
  - [x] SubTask 2.5: 实现 `POST /api/v1/roles/{role_id}/calculate-impact` - 计算影响范围
  - [x] SubTask 2.6: 实现 `GET /api/v1/meta/cache-stats` - 获取缓存统计
  - [x] SubTask 2.7: 编写 API 集成测试

## Phase 2: 前端组件开发 (Week 2)

- [x] Task 3: 创建 ManagementDimensionSelector 组件
  - [x] SubTask 3.1: 创建 `src/components/common/ManagementDimensionSelector.vue`
  - [x] SubTask 3.2: 实现维度列表/卡片视图切换
  - [x] SubTask 3.3: 实现维度搜索、过滤功能
  - [x] SubTask 3.4: 实现维度规则数量显示
  - [x] SubTask 3.5: 实现维度选择事件（v-model 绑定）
  - [x] SubTask 3.6: 编写组件单元测试

- [x] Task 4: 创建 ConditionRuleEditor 组件
  - [x] SubTask 4.1: 创建 `src/components/common/ConditionRuleEditor.vue`
  - [x] SubTask 4.2: 实现条件字段选择器（动态加载字段列表）
  - [x] SubTask 4.3: 实现操作符选择器（=, !=, IN, NOT IN, LIKE, >, <）
  - [x] SubTask 4.4: 实现值输入框和 value help 按钮
  - [x] SubTask 4.5: 实现 ValueHelpDialog 组件（实例选择对话框）
  - [x] SubTask 4.6: 实现权限级别选择器（read/write/admin）
  - [x] SubTask 4.7: 实现继承规则配置（向下继承、向上传播）
  - [x] SubTask 4.8: 实现禁止权配置（is_denied）
  - [x] SubTask 4.9: 编写组件单元测试

- [x] Task 5: 创建 ImpactPreview 组件
  - [x] SubTask 5.1: 创建 `src/components/common/ImpactPreview.vue`
  - [x] SubTask 5.2: 实现统计摘要展示（按对象类型分组）
  - [x] SubTask 5.3: 实现详细对象清单表格（可折叠）
  - [x] SubTask 5.4: 实现影响方式标记（直接匹配/向下继承/向上传播）
  - [x] SubTask 5.5: 实现排序、过滤功能
  - [x] SubTask 5.6: 实现导出功能（Excel）
  - [x] SubTask 5.7: 编写组件单元测试

- [x] Task 6: 重构 RolePermissionCenter 组件
  - [x] SubTask 6.1: 重构为 4 区域布局
  - [x] SubTask 6.2: 区域 1 - 管理维度选择器（集成 ManagementDimensionSelector）
  - [x] SubTask 6.3: 区域 2 - 条件规则编辑器（集成 ConditionRuleEditor）
  - [x] SubTask 6.4: 区域 3 - 影响范围预览（集成 ImpactPreview）
  - [x] SubTask 6.5: 区域 4 - 已配置规则列表（表格展示）
  - [x] SubTask 6.6: 实现区域间数据联动（维度选择→加载规则→计算影响）
  - [x] SubTask 6.7: 实现保存逻辑（保存到 permission_rule 表 + 失效缓存）
  - [x] SubTask 6.8: 编写端到端测试

## Phase 3: 集成与优化 (Week 3)

- [x] Task 7: 性能优化与监控
  - [x] SubTask 7.1: 实现热点角色权限规则预热（启动时加载 TOP 50）
  - [x] SubTask 7.2: 优化 SQL 查询性能（添加必要索引）
  - [x] SubTask 7.3: 实现缓存命中率监控（> 95%）
  - [x] SubTask 7.4: 性能压测（并发 50 用户）
  - [x] SubTask 7.5: 优化界面响应时间（< 200ms）

- [ ] Task 8: 文档与培训
  - [ ] SubTask 8.1: 编写用户操作手册
  - [ ] SubTask 8.2: 编写 API 文档
  - [ ] SubTask 8.3: 录制操作演示视频
  - [ ] SubTask 8.4: 编写运维手册（缓存管理、性能监控）

## Phase 4: 验收与上线 (Week 3)

- [ ] Task 9: 功能验收
  - [ ] SubTask 9.1: 验证 4 区域布局正确性
  - [ ] SubTask 9.2: 验证管理维度选择器功能
  - [ ] SubTask 9.3: 验证条件规则编辑器功能
  - [ ] SubTask 9.4: 验证影响范围实时计算
  - [ ] SubTask 9.5: 验证 value help 实例选择
  - [ ] SubTask 9.6: 验证性能指标达标

- [ ] Task 10: 灰度发布
  - [ ] SubTask 10.1: 在测试环境完整测试
  - [ ] SubTask 10.2: 在生产环境灰度发布（10% 用户）
  - [ ] SubTask 10.3: 监控错误率和性能指标
  - [ ] SubTask 10.4: 全量发布

# Task Dependencies

- Task 2 (API 端点) depends on Task 1 (核心引擎)
- Task 3 (ManagementDimensionSelector) depends on Task 2.1 (维度列表 API)
- Task 4 (ConditionRuleEditor) depends on Task 2.2 (实例列表 API)
- Task 5 (ImpactPreview) depends on Task 2.5 (影响计算 API)
- Task 6 (RolePermissionCenter 重构) depends on Task 3, Task 4, Task 5
- Task 7 (性能优化) depends on Task 1, Task 6
- Task 9 (功能验收) depends on Task 6, Task 7
- Task 10 (灰度发布) depends on Task 9

# Parallelizable Work

以下任务可并行执行：
- Task 3 (ManagementDimensionSelector), Task 4 (ConditionRuleEditor), Task 5 (ImpactPreview) 可并行开发
- Task 8 (文档) 可在 Task 6 完成后并行进行
