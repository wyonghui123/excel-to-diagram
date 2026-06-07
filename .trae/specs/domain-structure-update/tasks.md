# 领域结构更新 - 实现计划

## [ ] Task 1: 更新预览页面模板
- **Priority**: P0
- **Depends On**: None
- **Description**:
  - 更新预览页面中的领域结构命名
  - 将"领域产品"变更为"领域"
  - 将"产品模块"变更为"子领域"
  - 将"产品子模块"变更为"服务模块"
  - 更新相关的表头和标签
- **Acceptance Criteria Addressed**: AC-1, AC-3
- **Test Requirements**:
  - `human-judgment` TR-1.1: 预览页面显示正确的新命名
  - `human-judgment` TR-1.2: 所有相关标签和表头都已更新
- **Notes**: 修改App.vue文件中的模板部分

## [ ] Task 2: 更新字段识别逻辑
- **Priority**: P0
- **Depends On**: None
- **Description**:
  - 更新字段映射逻辑，识别新的列名称
  - 确保系统能识别"领域"、"子领域"、"服务模块"等新列名
  - 保持对旧列名称的兼容性
- **Acceptance Criteria Addressed**: AC-2, AC-4
- **Test Requirements**:
  - `programmatic` TR-2.1: 系统能正确识别新的列名称
  - `programmatic` TR-2.2: 系统能正确识别旧的列名称
  - `programmatic` TR-2.3: 字段映射逻辑正确无误
- **Notes**: 修改processPreviewData方法中的字段映射部分

## [ ] Task 3: 更新数据处理逻辑
- **Priority**: P0
- **Depends On**: Task 2
- **Description**:
  - 更新数据处理逻辑中的类型名称
  - 将"domain"类型的显示名称从"领域产品"变更为"领域"
  - 将"module"类型的显示名称从"产品模块"变更为"子领域"
  - 将"submodule"类型的显示名称从"产品子模块"变更为"服务模块"
- **Acceptance Criteria Addressed**: AC-1
- **Test Requirements**:
  - `programmatic` TR-3.1: 数据处理逻辑正确使用新的类型名称
  - `human-judgment` TR-3.2: 业务对象类型显示正确的新命名
- **Notes**: 修改businessObjectsArray的构建逻辑

## [ ] Task 4: 更新产品子模块关系处理
- **Priority**: P1
- **Depends On**: Task 1, Task 3
- **Description**:
  - 更新产品子模块关系的显示名称
  - 将"产品子模块关系"变更为"服务模块关系"
  - 更新相关的表头和标签
- **Acceptance Criteria Addressed**: AC-1, AC-3
- **Test Requirements**:
  - `human-judgment` TR-4.1: 服务模块关系显示正确的新命名
  - `human-judgment` TR-4.2: 相关表头和标签都已更新
- **Notes**: 修改预览页面中的产品子模块关系部分

## [ ] Task 5: 测试和验证
- **Priority**: P1
- **Depends On**: All previous tasks
- **Description**:
  - 测试新的列名称识别
  - 测试旧的列名称兼容性
  - 验证预览页面的显示
  - 确保系统功能正常
- **Acceptance Criteria Addressed**: All
- **Test Requirements**:
  - `programmatic` TR-5.1: 新列名称识别测试通过
  - `programmatic` TR-5.2: 旧列名称兼容性测试通过
  - `human-judgment` TR-5.3: 预览页面显示正确
  - `human-judgment` TR-5.4: 系统功能正常
- **Notes**: 执行全面测试，确保所有功能正常工作