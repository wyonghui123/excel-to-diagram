# Checklist

- [x] ColorCalculator.compute() 支持 centerScopeHighlight 参数
- [x] centerScopeHighlight: true 时颜色分配逻辑与现有行为一致
- [x] centerScopeHighlight: false 时忽略 isCenter，按纯层级分配颜色
- [x] useDiagramData.js 中 centerScopeHighlight 默认值为 true
- [x] ServiceModuleConfig.vue 中添加了"区分中心范围"开关
- [x] 开关值能正确绑定到 centerScopeHighlight 配置
- [x] Legend 组件接收 centerScopeHighlight 参数
- [x] Legend 在 centerScopeHighlight: false 时不显示中心范围图例项
- [x] centerScopeHighlight 配置变更能触发图表重绘