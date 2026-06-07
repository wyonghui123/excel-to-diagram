# Tasks

- [ ] Task 1: 在 ColorCalculator.compute() 中新增 centerScopeHighlight 参数支持
  - [ ] SubTask 1.1: 查看 ColorCalculator.compute() 现有实现，理解颜色分配逻辑
  - [ ] SubTask 1.2: 修改颜色 key 生成逻辑，当 centerScopeHighlight: false 时忽略 isCenter
  - [ ] SubTask 1.3: 确保 centerScopeHighlight: true 时行为与现有逻辑一致

- [ ] Task 2: 在 useDiagramData.js 中透传 centerScopeHighlight 参数
  - [ ] SubTask 2.1: 在 diagramConfig 中添加 centerScopeHighlight 配置项（默认 true）
  - [ ] SubTask 2.2: 将 centerScopeHighlight 传递给 ColorCalculator.compute()

- [ ] Task 3: 在 ServiceModuleConfig.vue 中添加开关配置 UI
  - [ ] SubTask 3.1: 在颜色配置区域添加"区分中心范围"开关
  - [ ] SubTask 3.2: 实现开关的 v-model 绑定到 centerScopeHighlight
  - [ ] SubTask 3.3: 确保配置变更能触发图表重绘

- [ ] Task 4: 修改 Legend 组件，根据 centerScopeHighlight 决定是否显示中心范围图例项
  - [ ] SubTask 4.1: 查看现有 Legend 组件实现
  - [ ] SubTask 4.2: 接收 centerScopeHighlight 参数
  - [ ] SubTask 4.3: 当 centerScopeHighlight: false 时不渲染中心范围图例项

- [ ] Task 5: 验证功能
  - [ ] SubTask 5.1: 测试 centerScopeHighlight: true 时行为与之前一致
  - [ ] SubTask 5.2: 测试 centerScopeHighlight: false 时按纯层级着色
  - [ ] SubTask 5.3: 测试纯层级模式下 Legend 不显示中心范围项

# Task Dependencies

- Task 2 依赖 Task 1（需要 ColorCalculator 支持 centerScopeHighlight 参数）
- Task 4 依赖 Task 1 和 Task 2（需要配置项就绪）
- Task 5 在 Task 1-4 完成后进行
