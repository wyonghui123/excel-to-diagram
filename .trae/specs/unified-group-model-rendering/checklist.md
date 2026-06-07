# 分组模型统一渲染 - 检查清单

## Phase 0: 基线建立

- [ ] **C0.1**: BO图5个场景基线截图和Mermaid代码已保存
- [ ] **C0.2**: SM图5个场景基线截图和Mermaid代码已保存
- [x] **C0.3**: diagramConfigStore中useUnifiedRenderer字段已添加，默认为false
- [x] **C0.4**: 应用正常启动，所有功能不受影响

## Phase 1: 新建核心模块

- [x] **C1.1**: types.js中createGroup返回值包含color、textColor、annotationCategory、annotationContent字段
- [x] **C1.2**: enrichGroupModel.js文件已创建，函数签名正确
- [x] **C1.3**: ColorCalculator.js文件已创建，compute方法输出{ colorMap, groupColorMap }
- [x] **C1.4**: UnifiedRenderer.js文件已创建，render方法输出Mermaid代码字符串
- [x] **C1.5**: groupModel/index.js已导出新模块
- [x] **C1.6**: 应用正常启动，新文件存在但未被调用，不影响现有功能

## Phase 2: SM图接入统一渲染

- [x] **C2.1**: useDiagramData.js SM分支中if(configStore.useUnifiedRenderer)代码已添加
- [x] **C2.2**: 旧代码保留，flag=false时走旧路径
- [ ] **C2.3**: flag=true时SM图渲染结果与基线一致（5个场景）
- [ ] **C2.4**: SM图节点颜色与旧渲染器一致
- [ ] **C2.5**: SM图连线正确显示
- [ ] **C2.6**: SM图2层subgraph嵌套正确

## Phase 3: BO图接入统一渲染

- [x] **C3.1**: useDiagramData.js BO分支中if(configStore.useUnifiedRenderer)代码已添加
- [ ] **C3.2**: flag=true时BO图渲染结果与基线一致（5个场景）
- [ ] **C3.3**: BO图节点id已从name改为code
- [ ] **C3.4**: BO图3层subgraph嵌套正确
- [ ] **C3.5**: BO图连线颜色与旧渲染器一致
- [ ] **C3.6**: BO图节点大小自适应正常

## Phase 4: 切换默认渲染器

- [ ] **C4.1**: useUnifiedRenderer默认值已改为true
- [ ] **C4.2**: BO图5个场景回归测试通过
- [ ] **C4.3**: SM图5个场景回归测试通过
- [ ] **C4.4**: 切换图表类型后重新生成正常
- [ ] **C4.5**: 修改中心范围后重新生成正常
- [ ] **C4.6**: 修改配色方案后重新生成正常
- [ ] **C4.7**: 禁用/启用分组后重新生成正常
- [ ] **C4.8**: 自动分组功能正常
- [ ] **C4.9**: 配置页面颜色与图表颜色一致
- [x] **C4.10**: fallbackToLegacyRenderer()方法可用

## Phase 5: 清理旧代码

- [ ] **C5.1**: diagramDataBuilder.js已删除
- [ ] **C5.2**: serviceModuleDiagramBuilder.js已删除
- [ ] **C5.3**: useBusinessObjectSyntax.js已删除
- [ ] **C5.4**: useServiceModuleSyntax.js已删除
- [ ] **C5.5**: useMermaidColors.js已删除
- [ ] **C5.6**: useDiagramData.js中旧渲染路径已移除
- [ ] **C5.7**: useDiagramData.js中旧import已移除
- [ ] **C5.8**: feature flag已移除
- [ ] **C5.9**: 调试日志已清理
- [ ] **C5.10**: 应用功能完整，无旧渲染器残留
