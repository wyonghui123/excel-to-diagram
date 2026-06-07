# Tasks

## Task 1: 实现简洁版 HTML 导出功能 ✅
创建生成简洁版 HTML 文件的导出方法（离线可用，内嵌 mermaid.min.js）

- [x] SubTask 1.1: 创建 `exportAsHtmlSimple` 方法
- [x] SubTask 1.2: 使用 fetch 获取 mermaid.min.js (UMD 版本)
- [x] SubTask 1.3: Base64 编码内嵌到 HTML 中
- [x] SubTask 1.4: 使用 `mermaid.run()` 手动触发渲染
- [x] SubTask 1.5: 添加滚轮缩放功能
- [x] SubTask 1.6: 添加容器颜色渐进区分
- [x] SubTask 1.7: 修复顶部空白问题（CSS + viewBox 调整）
- [x] SubTask 1.8: 简洁版不使用 ELK（ESM chunk 依赖问题）

## Task 2: 实现彩色版 HTML 导出功能 ✅
创建生成彩色版 HTML 文件的导出方法（CDN 加载，支持 ELK）

- [x] SubTask 2.1: 创建 `exportAsHtmlFull` 方法
- [x] SubTask 2.2: 使用 `<script type="module">` 加载 mermaid v11 ESM
- [x] SubTask 2.3: 加载 ELK 布局（如果启用）
- [x] SubTask 2.4: 使用 `mermaid.registerLayoutLoaders()` 注册 ELK
- [x] SubTask 2.5: 添加滚轮缩放功能
- [x] SubTask 2.6: 添加拖拽移动功能
- [x] SubTask 2.7: 添加容器颜色渐进区分
- [x] SubTask 2.8: 修复顶部空白问题（CSS + viewBox 调整）
- [x] SubTask 2.9: 添加 CDN 加载失败提示

## Task 3: 复制到剪贴板功能 ✅
新增 `copyToClipboard` 方法

- [x] SubTask 3.1: 创建 `copyToClipboard` 方法
- [x] SubTask 3.2: 使用 Clipboard API 实现复制
- [x] SubTask 3.3: 复制成功后显示 Toast 提示

## Task 4: 工具栏按钮配置 ✅
修改 MermaidComponent 工具栏的 UI

- [x] SubTask 4.1: 添加导出按钮（"彩"标签标识彩色版）
- [x] SubTask 4.2: 按钮使用 AppIcon 格式
- [x] SubTask 4.3: 添加工具栏分隔样式

## Task 5: 验证导出功能
测试各种导出场景

- [ ] SubTask 5.1: 测试简洁版 HTML 导出 - 滚轮缩放正常
- [ ] SubTask 5.2: 测试彩色版 HTML 导出 - ELK 布局正常
- [ ] SubTask 5.3: 测试彩色版 HTML 导出 - 拖拽移动正常
- [ ] SubTask 5.4: 测试复制代码功能
- [ ] SubTask 5.5: 测试容器颜色区分效果

## Task 6: 修复彩色版容器颜色问题 ⚠️ 待处理
- [ ] SubTask 6.1: 添加调试日志确认容器数量和层级
- [ ] SubTask 6.2: 检查 `getNestingLevel` 函数是否正确识别嵌套关系
- [ ] SubTask 6.3: 可能的解决方案：改用基于索引的颜色分配

# Task Dependencies
- Task 3 依赖 Task 2 完成
- Task 5 在 Task 1, 2, 3 完成后执行
- Task 6 可与 Task 5 并行处理

# Completed Iterations

## Iteration 1: 基础导出功能
- 实现了基础的 HTML 导出功能
- 使用 Base64 内嵌 mermaid.min.js
- 发现 ELK 布局不支持（ESM chunk 依赖问题）

## Iteration 2: CDN 在线加载方案
- 改用 CDN 加载 mermaid ESM
- 引入 mermaid v11（支持 registerLayoutLoaders API）
- 成功支持 ELK 布局

## Iteration 3: 交互功能增强
- 添加滚轮缩放功能
- 添加拖拽移动功能（仅彩色版）
- 修复顶部空白问题
- 添加容器颜色渐进区分

## Iteration 4: 待处理问题
- 修复彩色版容器颜色问题（图表浅灰 vs HTML 白色）
