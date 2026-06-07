# Checklist

## Phase 1: 元模型配置验证

### relationship.yaml 验证
- [x] ui_view_config.list 配置完整
- [x] ui_view_config.detail 配置完整
- [x] ui_view_config.form 配置完整
- [x] ui_view_config.filter 配置完整
- [x] 虚拟字段 source_bo_name, target_bo_name, category_label 定义正确
- [x] 筛选器定义符合规范

### business_object.yaml 验证
- [x] detail.facets 包含 relation_list 分面
- [x] relation_list 配置参数正确（source, source_field, target_field, display_mode）
- [x] list.columns 包含 relation_count 列

### 层级对象 YAML 验证
- [x] domain.yaml 包含 relation_count 列配置
- [x] sub_domain.yaml 包含 relation_count 列配置
- [x] service_module.yaml 包含 relation_count 列配置
- [x] computation 规则定义正确

## Phase 2: 后端 API 验证

### 视图配置 API 验证
- [x] GET /api/v1/meta/{object_type}/filter-config 返回正确数据
- [x] GET /api/v1/meta/{object_type}/detail-view 包含 relation_list 分面数据
- [x] 筛选器配置数据格式正确

### 关系查询 API 验证
- [x] GET /api/v1/relationships 支持多条件筛选
- [x] 筛选参数正确解析（business_objects, category_types, relation_codes）
- [x] 返回数据包含 stats 统计信息
- [x] GET /api/v1/business_object/{id}/relations 返回正确数据
- [x] source_relations 和 target_relations 正确区分

### 关系分类计算验证
- [x] 跨领域关系正确识别
- [x] 同领域跨子领域关系正确识别
- [x] 同子领域跨服务模块关系正确识别
- [x] 同服务模块关系正确识别

### 统计规则计算验证
- [x] computation_service.py 创建完成
- [x] count_relations 统计规则实现
- [x] descendants 和 self 两种 scope 支持

## Phase 3: 前端框架验证

### Tab 切换验证
- [x] 顶部 Tab 正确显示（层级数据/业务关系）
- [x] Tab 切换状态正确管理
- [x] 层级数据 Tab 显示树形导航
- [x] 业务关系 Tab 显示筛选器

### 筛选器组件验证
- [x] DynamicFilter.vue 组件创建完成
- [x] multi_select 类型筛选器正确渲染
- [x] checkbox_group 类型筛选器正确渲染
- [x] 筛选器默认值正确设置（全选）
- [x] 筛选器联动逻辑正确
- [x] 筛选结果正确应用

## Phase 4: 业务对象详情验证

### 关联关系展示验证
- [x] RelationFacet.vue 组件创建完成
- [x] 作为源的关系正确显示
- [x] 作为目标的关系正确显示
- [x] 关系数量统计正确
- [x] "查看全部"跳转功能正常

### DynamicDetail 集成验证
- [x] relation_list 分面类型正确识别
- [x] 关联关系数据正确加载
- [x] RelationFacet 组件正确嵌入详情页

## Phase 5: 业务关系管理验证

### 关系列表验证
- [x] 关系列表正确渲染
- [x] 列定义符合配置
- [x] 排序功能正常
- [x] 分页功能正常

### 关系编辑验证
- [x] 新建关系表单正确显示（复用 DynamicForm）
- [x] 编辑关系表单正确显示
- [x] 保存功能正常
- [x] 删除功能正常

## Phase 6: 关系数量统计列验证

### 前端展示验证
- [x] DynamicTable.vue 支持 computed 列渲染
- [x] 统计列样式为可点击链接
- [x] 点击统计数量触发事件
- [x] relation-count-click 事件正确传递行数据

## Phase 7: 自动化测试验证

### 后端单元测试
- [x] test_relation_api.py 创建完成
- [x] 测试 computation_service 计算逻辑
- [x] 测试关系数量计算

### API 端点测试
- [x] test_relation_endpoints.py 创建完成
- [x] 测试 filter-config API
- [x] 测试 relationships API
- [x] 测试 business_object/{id}/relations API

## 端到端验证

### 用户场景 1：查看业务对象关联关系
- [x] 打开业务对象详情页
- [x] 关联关系区块正确显示
- [x] 点击"查看全部"跳转到关系页面

### 用户场景 2：筛选业务关系
- [x] 切换到业务关系 Tab
- [x] 选择业务对象筛选
- [x] 选择分类维度筛选
- [x] 选择关系类型筛选
- [x] 列表正确过滤

### 用户场景 3：新建业务关系
- [x] 点击"新建关系"按钮
- [x] 表单正确显示
- [x] 选择源业务对象
- [x] 选择关系类型
- [x] 选择目标业务对象
- [x] 保存成功

### 用户场景 4：查看统计列
- [x] 领域/子领域/服务模块/业务对象列表显示关系数量列
- [x] 关系数量可点击
- [x] 点击后跳转到关系页面
