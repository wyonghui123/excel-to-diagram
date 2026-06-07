# 元数据驱动架构重构 - 检查清单

## Phase 1 检查清单

### 数据一致性验证

- [ ] **关系树与列表数量一致**
  - 选择领域节点后，关系树显示的数量与关系列表一致
  - 选择子领域节点后，关系树显示的数量与关系列表一致
  - 选择服务模块节点后，关系树显示的数量与关系列表一致
  - 选择业务对象节点后，关系树显示的数量与关系列表一致

- [ ] **导出数据与前端选择一致**
  - 导出的关系数量与前端选择一致
  - 导出的业务对象数量与前端选择一致
  - 导出的层级信息正确

- [ ] **多粒度过滤正确工作**
  - 优先级: businessObject > serviceModule > subDomain > domain
  - 选择更细粒度时，只显示该粒度范围内的数据

### 代码质量验证

- [ ] **无硬编码层级链**
  ```bash
  # 搜索硬编码字符串
  grep -r "domain.*sub_domain.*service_module" meta/
  # 应无结果
  ```

- [ ] **前后端过滤逻辑统一**
  - 前端只传节点ID
  - 后端统一处理转换

- [ ] **单元测试覆盖率**
  ```bash
  pytest --cov=meta/services --cov-report=term-missing
  # 覆盖率 > 80%
  ```

### API 验证

- [ ] **GET /api/v1/meta/hierarchies**
  - 返回正确的层级结构配置
  - 包含 dimensions 和 hierarchy_scopes

- [ ] **GET /api/v1/meta/hierarchies/<id>/levels**
  - 返回正确的层级级别定义

- [ ] **GET /api/v1/meta/objects/<type>/analytics_config**
  - 返回正确的分析配置

---

## Phase 2 检查清单

### 字段控制属性验证

- [ ] **business_key 处理正确**
  - 新建时：必填 + 唯一性验证
  - 编辑时：只读（不可修改）
  - 导出时：排在最前面

- [ ] **parent_key 处理正确**
  - 新建时：必填
  - 编辑时：可编辑（允许移动层级）
  - 导入时：父对象必须存在

- [ ] **immutable 处理正确**
  - 新建时：可编辑 + 必填
  - 编辑时：只读

- [ ] **readonly_always 处理正确**
  - 新建时：只读
  - 编辑时：只读

- [ ] **mandatory 处理正确**
  - 新建时：必填
  - 编辑时：必填

- [ ] **前后端一致性**
  - 后端 `_is_field_editable` 与前端 `isFieldEditable` 逻辑一致
  - 导入导出列样式与表单字段状态一致

### 关系过滤语义验证

- [ ] **scope_mode=involved (OR 语义)**
  - 返回至少一端在范围内的关系
  - 包含"外部关系"

- [ ] **scope_mode=internal (AND 语义)**
  - 返回两端都在范围内的关系
  - 不包含"外部关系"

---

## Phase 3 检查清单

### Analytics Query 验证

- [ ] **AnalyticsConfig 解析正确**
  - YAML 中定义的 analytics 配置正确加载
  - measures 和 dimensions 正确识别

- [ ] **分析查询 API**
  - 返回正确的聚合结果
  - 支持过滤和分组

---

## 回归测试清单

### 核心功能

- [ ] 业务对象 CRUD 正常
- [ ] 关系 CRUD 正常
- [ ] 层级树展示正常
- [ ] 关系树展示正常
- [ ] 导入功能正常
- [ ] 导出功能正常

### 边界情况

- [ ] 空数据时正常显示
- [ ] 大数据量时性能正常
- [ ] 配置缺失时有明确错误提示

---

## 发布前检查

- [ ] 所有单元测试通过
- [ ] 所有集成测试通过
- [ ] 代码审查完成
- [ ] 文档更新完成
- [ ] 变更日志更新
