# 验收检查清单

## 功能验收

### 组件库

- [x] AppButton组件实现符合规范
  - [x] 支持primary/secondary/text/danger类型
  - [x] 支持sm/md/lg尺寸
  - [x] 支持disabled状态
  - [x] 使用设计令牌变量
  - [x] 支持loading状态
  - [x] 支持block/circle/ghost变体

- [x] AppInput组件实现符合规范
  - [x] 支持错误状态显示
  - [x] 支持前缀/后缀插槽
  - [x] 支持disabled状态
  - [x] 使用设计令牌变量
  - [x] 支持clearable
  - [x] 支持label和hint

- [x] AppCard组件实现符合规范
  - [x] 支持header/body/footer结构
  - [x] 支持hover效果
  - [x] 使用设计令牌变量
  - [x] 支持多种阴影级别
  - [x] 支持clickable/disabled/loading状态

- [x] AppSelect组件实现符合规范
  - [x] 支持下拉选择
  - [x] 支持禁用选项
  - [x] 使用设计令牌变量
  - [x] 支持searchable
  - [x] 支持multiple多选

- [x] AppModal组件实现符合规范
  - [x] 支持遮罩层
  - [x] 支持关闭按钮
  - [x] 使用设计令牌变量
  - [x] 支持默认底部按钮
  - [x] 支持自定义宽度
  - [x] 支持响应式布局

### 样式工具类

- [x] utilities.scss创建完成
  - [x] 文本工具类（text-left/center/right, text-ellipsis）
  - [x] 间距工具类（m-*, p-*系列）
  - [x] 显示工具类（d-none, d-block, d-flex）
  - [x] 定位工具类（position-relative/absolute/fixed）
  - [x] 响应式工具类（hide-*, show-*）
  - [x] Flexbox工具类
  - [x] 背景/边框/阴影工具类
  - [x] Z-Index工具类

### 组件迁移

- [x] 现有组件分析完成
- [x] 创建组件迁移指南
- [x] 提供批量替换脚本
- [x] 创建验证清单

### 样式检查工具

- [x] stylelint配置创建
  - [x] 禁止硬编码颜色规则
  - [x] SCSS规范规则
  - [x] 选择器命名规范
- [x] package.json scripts集成
  - [x] lint:style命令
  - [x] lint:style:fix命令
- [x] CI检查工作流配置
  - [x] GitHub Actions工作流

### 文档更新

- [x] STYLE_GUIDE.md更新
  - [x] 添加组件使用示例
  - [x] 添加最佳实践
- [x] MIGRATION_GUIDE.md创建
  - [x] 迁移步骤说明
  - [x] 代码示例
  - [x] 批量替换脚本

## 质量验收

- [x] 所有组件使用设计令牌
- [x] 样式检查配置完成
- [x] 深色模式变量定义完成
- [x] 响应式断点定义完成
- [x] 组件支持键盘访问

## 性能验收

- [x] 组件按需导出
- [x] 样式文件结构清晰
- [x] 无重复定义

## 交付物清单

- [x] src/components/common/AppButton/
- [x] src/components/common/AppInput/
- [x] src/components/common/AppCard/
- [x] src/components/common/AppSelect/
- [x] src/components/common/AppModal/
- [x] src/components/common/index.js
- [x] src/styles/tokens.scss
- [x] src/styles/utilities.scss
- [x] src/styles/COMPONENT_STANDARDS.md
- [x] src/styles/STYLE_GUIDE.md
- [x] src/styles/MIGRATION_GUIDE.md
- [x] .stylelintrc.json
- [x] .github/workflows/lint.yml
