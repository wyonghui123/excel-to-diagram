# UI样式规范实施 Spec

## Why

当前项目已创建基础的设计令牌和组件规范文档，但尚未在代码中实际应用。缺乏统一的UI样式规范会导致：

1. 组件样式不统一，视觉体验不一致
2. 开发者各自为战，代码难以维护
3. 样式冗余和重复代码增多
4. 主题切换和深色模式难以实现

## What Changes

* 将设计令牌应用到现有组件

* 创建基础UI组件库（Button、Input、Card等）

* 建立样式检查和自动化工具

* 更新开发文档和最佳实践

* **BREAKING** 部分组件类名可能需要调整以符合新规范

## Impact

### 受影响的规范

* 组件样式定义

* 主题切换机制

* 响应式布局策略

### 受影响的代码

* `src/components/common/` - 需要重构或新建

* `src/views/` - 需要逐步迁移

* `src/styles/` - 需要补充工具类

***

## ADDED Requirements

### Requirement: 设计令牌应用

系统 SHALL 在所有组件中使用统一的设计令牌变量。

#### Scenario: 颜色使用

* **WHEN** 开发者需要设置组件颜色

* **THEN** 必须使用 `--color-*` 变量

* **AND** 禁止使用硬编码颜色值

#### Scenario: 间距使用

* **WHEN** 开发者需要设置间距

* **THEN** 必须使用 `--spacing-*` 变量

* **AND** 遵循4px基准网格系统

### Requirement: 基础组件库

系统 SHALL 提供一套完整的通用UI组件。

#### Scenario: 按钮组件

* **WHEN** 需要创建按钮

* **THEN** 使用 `AppButton` 组件

* **AND** 支持 primary/secondary/text/danger 类型

* **AND** 支持 sm/md/lg 尺寸

#### Scenario: 输入框组件

* **WHEN** 需要表单输入

* **THEN** 使用 `AppInput` 组件

* **AND** 支持错误状态显示

* **AND** 支持前缀/后缀插槽

#### Scenario: 卡片组件

* **WHEN** 需要内容容器

* **THEN** 使用 `AppCard` 组件

* **AND** 支持 header/body/footer 结构

### Requirement: 样式检查工具

系统 SHALL 提供自动化工具确保规范执行。

#### Scenario: 样式检查

* **WHEN** 提交代码时

* **THEN** 自动检查是否使用设计令牌

* **AND** 报告违规的硬编码值

#### Scenario: 文档生成

* **WHEN** 设计令牌更新时

* **THEN** 自动生成样式文档

* **AND** 更新组件使用示例

## MODIFIED Requirements

### Requirement: 现有组件迁移

现有组件 SHALL 逐步迁移到新规范。

#### Scenario: 渐进式迁移

* **WHEN** 修改现有组件时

* **THEN** 同步更新为使用设计令牌

* **AND** 保持向后兼容（如可能）

## REMOVED Requirements

### Requirement: 旧样式变量

**Reason**: 被新的设计令牌系统替代
**Migration**: 将 `variables.scss` 中的变量迁移到 `tokens.scss`

***

## 详细设计

### 1. 组件架构

```
src/components/common/
├── AppButton/
│   ├── AppButton.vue
│   ├── AppButton.spec.js
│   └── index.js
├── AppInput/
│   ├── AppInput.vue
│   ├── AppInput.spec.js
│   └── index.js
├── AppCard/
│   ├── AppCard.vue
│   ├── AppCard.spec.js
│   └── index.js
├── AppSelect/
│   ├── AppSelect.vue
│   └── index.js
└── index.js          # 统一导出
```

### 2. 设计令牌层级

```
tokens.scss (原子值)
    ↓
variables.scss (语义化映射)
    ↓
组件样式 (具体应用)
```

### 3. 样式检查规则

| 规则                  | 级别      | 说明       |
| ------------------- | ------- | -------- |
| no-hardcoded-colors | error   | 禁止硬编码颜色  |
| use-design-tokens   | warning | 建议使用设计令牌 |
| consistent-spacing  | warning | 使用标准间距   |

***

## 验收标准

1. ✅ 所有新组件使用设计令牌
2. ✅ 提供至少5个基础UI组件
3. ✅ 样式检查工具集成到CI
4. ✅ 更新开发文档
5. ✅ 至少50%现有组件迁移完成

