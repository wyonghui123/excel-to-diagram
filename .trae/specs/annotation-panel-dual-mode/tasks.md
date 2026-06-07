# Tasks

- [x] Task 1: 添加模式切换按钮到备注面板头部
  - [x] SubTask 1.1: 在 annotationOverlay.js 中添加 mode 状态（compact/detail）
  - [x] SubTask 1.2: 在头部添加模式切换按钮（简洁模式/详情模式）
  - [x] SubTask 1.3: 实现点击切换模式的逻辑

- [x] Task 2: 实现详情模式的样式
  - [x] SubTask 2.1: 详情模式下移除文字截断样式（white-space: nowrap → normal）
  - [x] SubTask 2.2: 详情模式下移除 max-width 限制
  - [x] SubTask 2.3: 详情模式下调整面板高度自适应内容
  - [x] SubTask 2.4: 添加详情模式下的最大高度和滚动支持

- [x] Task 3: 实现模式状态持久化
  - [x] SubTask 3.1: 使用 sessionStorage 保存模式状态
  - [x] SubTask 3.2: 页面刷新时恢复之前的模式状态

# Task Dependencies
- Task 2 依赖 Task 1（需要先有模式切换逻辑）
- Task 3 依赖 Task 1（需要在模式切换时保存状态）
