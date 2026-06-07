# 备注面板双模式切换功能 Spec

## Why
当前备注面板在简洁模式下文字会被截断，导出PDF时无法完整展示备注内容。需要提供一种详情模式，让用户可以在导出PDF前切换到详情模式，确保所有备注内容完整展示。

## What Changes
- 在备注面板头部添加模式切换按钮
- 新增"简洁模式"和"详情模式"两种显示方式
- 简洁模式：保持现有样式，文字截断，适合日常查看
- 详情模式：文字完整显示，自动换行，适合导出PDF

## Impact
- Affected specs: 备注显示功能
- Affected code: 
  - `src/composables/useMermaid/annotation/annotationOverlay.js` - 备注面板渲染逻辑

## ADDED Requirements

### Requirement: 备注面板模式切换
系统应提供备注面板的双模式切换功能，允许用户在简洁模式和详情模式之间切换。

#### Scenario: 切换到详情模式
- **WHEN** 用户点击备注面板头部的"详情模式"按钮
- **THEN** 备注面板切换到详情模式，所有备注内容完整显示，文字自动换行

#### Scenario: 切换到简洁模式
- **WHEN** 用户点击备注面板头部的"简洁模式"按钮
- **THEN** 备注面板切换到简洁模式，备注内容截断显示，保持紧凑布局

### Requirement: 详情模式样式
详情模式下，备注面板应满足以下要求：

#### Scenario: 详情模式布局
- **WHEN** 备注面板处于详情模式
- **THEN** 
  - 备注面板高度自适应内容
  - 每条备注内容完整显示，不截断
  - 文字自动换行
  - 最大高度限制为300px，超出部分可滚动

### Requirement: 模式状态持久化
系统应记住用户选择的模式偏好。

#### Scenario: 模式状态保持
- **WHEN** 用户切换模式后刷新页面或重新生成图表
- **THEN** 备注面板应保持用户之前选择的模式

## MODIFIED Requirements

### Requirement: 备注面板头部
备注面板头部需要增加模式切换控件。

#### Scenario: 头部显示
- **WHEN** 备注面板渲染时
- **THEN** 头部显示"备注 ▼"和模式切换按钮（简洁/详情）

## REMOVED Requirements
无
