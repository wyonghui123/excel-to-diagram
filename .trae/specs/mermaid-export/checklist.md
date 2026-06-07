# Checklist

## MermaidComponent.vue 工具栏修改

- [x] 工具栏包含导出按钮（复制 | 彩色版）
- [x] 导出按钮位于全屏按钮后面
- [x] 按钮使用图标格式（AppIcon）
- [x] 按钮有正确的 Tooltip 提示
- [x] 彩色版按钮带有"彩"标签

## MermaidComponent.vue 方法修改

### 简洁版导出 (exportAsHtmlSimple)
- [x] 添加了 `exportAsHtmlSimple` 方法
- [x] 使用 fetch 获取 mermaid.min.js (UMD 版本)
- [x] Base64 编码内嵌到 HTML 中
- [x] 使用 `mermaid.run()` 手动触发渲染
- [x] 支持滚轮缩放
- [x] 支持容器颜色渐进区分
- [x] 修复顶部空白问题
- [x] 简洁版不使用 ELK（ESM chunk 依赖问题）

### 彩色版导出 (exportAsHtmlFull)
- [x] 添加了 `exportAsHtmlFull` 方法
- [x] 使用 `<script type="module">` 加载 mermaid v11 ESM
- [x] 加载 ELK 布局（如果启用）
- [x] 使用 `mermaid.registerLayoutLoaders()` 注册 ELK
- [x] 支持滚轮缩放
- [x] 支持拖拽移动
- [x] 支持容器颜色渐进区分
- [x] 修复顶部空白问题
- [x] 添加 CDN 加载失败提示

### 复制功能 (copyToClipboard)
- [x] 添加了 `copyToClipboard` 方法
- [x] 使用 Clipboard API
- [x] 复制成功后显示 Toast 提示

## 导出 HTML CSS 样式

### 简洁版 HTML CSS
- [x] `pre.mermaid` 样式正确（不是 `.mermaid pre`）
- [x] `line-height: 0` 消除行高空白
- [x] `transform-origin: top left` 缩放从左上角开始
- [x] 支持滚轮缩放的 `cursor` 样式

### 彩色版 HTML CSS
- [x] `pre.mermaid` 样式正确
- [x] 添加 `.notice` 提示框样式
- [x] 支持滚轮缩放和拖拽的 `cursor` 样式

## 功能测试

- [ ] 简洁版 HTML 导出后用浏览器打开显示正常
- [ ] 简洁版 HTML 支持滚轮缩放
- [ ] 彩色版 HTML 导出后用浏览器打开显示正常
- [ ] 彩色版 HTML 支持滚轮缩放
- [ ] 彩色版 HTML 支持拖拽移动
- [ ] 彩色版 HTML 的 ELK 布局正常
- [ ] 复制的代码可以粘贴到 Mermaid Live Editor 渲染正确
- [ ] 容器颜色渐进区分效果正确

## 待解决问题

- ⚠️ 彩色版容器背景色问题
  - 图表上是浅灰色，但彩色full HTML上显示白色
  - 原因：可能是 `getNestingLevel` 函数无法正确识别嵌套关系
  - 优先级：高
