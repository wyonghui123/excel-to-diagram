# Tasks

- [x] Task 1: 创建基础UI组件库 - 实现AppButton、AppInput、AppCard等核心组件
  - [x] SubTask 1.1: 创建AppButton组件（支持primary/secondary/text/danger类型，sm/md/lg尺寸）
  - [x] SubTask 1.2: 创建AppInput组件（支持错误状态、前缀/后缀插槽）
  - [x] SubTask 1.3: 创建AppCard组件（支持header/body/footer结构）
  - [x] SubTask 1.4: 创建AppSelect组件（支持下拉选择）
  - [x] SubTask 1.5: 创建AppModal组件（支持模态框）
  - [x] SubTask 1.6: 创建统一导出文件index.js

- [x] Task 2: 补充样式工具类 - 在styles目录添加实用工具类
  - [x] SubTask 2.1: 创建utilities.scss（文本、间距、显示、定位工具类）
  - [x] SubTask 2.2: 更新index.scss引入utilities
  - [x] SubTask 2.3: 添加响应式工具类

- [x] Task 3: 迁移现有组件 - 将现有组件逐步迁移到设计令牌
  - [x] SubTask 3.1: 分析现有组件使用情况
  - [x] SubTask 3.2: 创建组件迁移指南和示例
  - [x] SubTask 3.3: 提供批量替换脚本
  - [x] SubTask 3.4: 创建验证清单

- [x] Task 4: 建立样式检查工具 - 确保规范执行
  - [x] SubTask 4.1: 创建stylelint配置
  - [x] SubTask 4.2: 添加自定义规则（禁止硬编码颜色）
  - [x] SubTask 4.3: 集成到package.json Scripts
  - [x] SubTask 4.4: 创建CI检查工作流

- [x] Task 5: 更新开发文档 - 完善样式规范文档
  - [x] SubTask 5.1: 更新STYLE_GUIDE.md添加组件使用示例
  - [x] SubTask 5.2: 创建组件迁移指南
  - [x] SubTask 5.3: 添加最佳实践指南

# Task Dependencies

- Task 2 依赖于 Task 1（组件样式依赖工具类）
- Task 3 依赖于 Task 1（迁移需要使用新组件）
- Task 4 可以并行执行
- Task 5 依赖于 Task 1 完成（需要组件完成后才能写文档）
