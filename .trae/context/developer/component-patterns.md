# 组件模式

## 核心组件架构

```
useBlockDiagram/
├── model/              # 数据模型（DiagramNode, DiagramLink, DiagramContainer）
├── transform/          # 数据转换器
├── layout/             # 布局计算
├── strategy/           # 策略模式（图表类型个性化配置）
├── syntax/             # Mermaid语法生成
├── behavior/           # 行为层（缩放、选择、tooltip）
├── style/              # 样式层
├── renderer/           # 渲染器
└── useBlockDiagram.js  # 统一入口
```

## 新增图表类型

只需添加新的策略配置，无需修改核心逻辑。

## 新增功能模块

遵循Feature-First原则：
1. 在 src/features/ 下创建功能目录
2. 在 .trae/specs/ 下创建功能规范
3. 遵循TDD开发流程
