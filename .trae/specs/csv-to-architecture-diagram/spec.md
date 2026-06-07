# CSV导入架构图生成工具 - 产品需求文档

## Overview
- **Summary**: 开发一个基于CSV文件导入的架构图生成工具，能够将CSV数据转换为业务对象和产品模块架构图，支持Draw.io和Excalidraw两种图表引擎。
- **Purpose**: 解决业务分析和系统设计中需要快速将业务对象关系和产品模块结构可视化的问题，提高架构设计效率。
- **Target Users**: 业务分析师、系统架构师、产品经理和开发人员。

## Goals
- 支持从CSV文件导入业务对象和产品模块数据
- 自动生成业务对象关系图和产品模块架构图
- 提供Draw.io和Excalidraw两种图表引擎选择
- 支持图表导出功能
- 提供直观的用户界面和操作流程

## Non-Goals (Out of Scope)
- 不支持Excel文件的复杂公式解析
- 不提供图表的实时协作编辑功能
- 不支持导出为其他图表格式（如Visio）
- 不包含数据存储和持久化功能

## Background & Context
- 现有的项目已经实现了基本的Excel/CSV导入和关系图生成功能
- 项目使用Vue 3框架，集成了xlsx、draw.io和excalidraw等依赖
- 当前实现主要关注业务对象关系图，需要扩展支持产品模块架构图

## Functional Requirements
- **FR-1**: 支持CSV文件导入，解析业务对象和产品模块数据
- **FR-2**: 自动识别并提取CSV中的业务对象和产品模块信息
- **FR-3**: 生成业务对象关系图，展示对象之间的关联关系
- **FR-4**: 生成产品模块架构图，展示模块之间的层次结构
- **FR-5**: 提供Draw.io和Excalidraw两种图表引擎选择
- **FR-6**: 支持图表导出为图片或原生格式
- **FR-7**: 提供直观的用户界面，包括文件上传、图表类型选择和导出功能

## Non-Functional Requirements
- **NFR-1**: 性能要求：处理包含100个业务对象的CSV文件不超过5秒
- **NFR-2**: 兼容性：支持主流CSV格式，包括不同编码（UTF-8、GBK）
- **NFR-3**: 可用性：提供清晰的错误提示和用户引导
- **NFR-4**: 可扩展性：设计模块化架构，便于后续功能扩展

## Constraints
- **Technical**: 基于现有的Vue 3项目架构，使用已集成的依赖库
- **Business**: 保持工具的简洁性和易用性，避免过度复杂的功能
- **Dependencies**: 依赖xlsx库进行文件解析，依赖draw.io和excalidraw进行图表渲染

## Assumptions
- CSV文件包含明确的业务对象和产品模块信息
- 用户具备基本的CSV文件结构设计能力
- 图表引擎（Draw.io和Excalidraw）能够正确渲染生成的架构图

## Acceptance Criteria

### AC-1: CSV文件导入功能
- **Given**: 用户选择并上传包含业务对象和产品模块信息的CSV文件
- **When**: 系统解析CSV文件并提取相关数据
- **Then**: 系统成功解析文件并显示解析结果
- **Verification**: `programmatic`
- **Notes**: 支持UTF-8和GBK编码的CSV文件

### AC-2: 业务对象关系图生成
- **Given**: 系统已解析CSV文件中的业务对象和关系数据
- **When**: 用户选择生成业务对象关系图
- **Then**: 系统生成并显示业务对象之间的关联关系图
- **Verification**: `human-judgment`
- **Notes**: 关系图应清晰展示对象之间的连接和关系类型

### AC-3: 产品模块架构图生成
- **Given**: 系统已解析CSV文件中的产品模块数据
- **When**: 用户选择生成产品模块架构图
- **Then**: 系统生成并显示产品模块的层次结构图
- **Verification**: `human-judgment`
- **Notes**: 架构图应清晰展示模块之间的层次关系

### AC-4: 图表引擎选择
- **Given**: 系统已生成架构图数据
- **When**: 用户选择不同的图表引擎（Draw.io或Excalidraw）
- **Then**: 系统使用选择的引擎重新渲染架构图
- **Verification**: `programmatic`
- **Notes**: 两种引擎应正确渲染相同的架构图数据

### AC-5: 图表导出功能
- **Given**: 系统已生成架构图
- **When**: 用户点击导出按钮
- **Then**: 系统将架构图导出为图片或原生格式文件
- **Verification**: `programmatic`
- **Notes**: 支持常见图片格式和图表引擎的原生格式

## Open Questions
- [ ] 产品模块架构图的具体数据结构和层次关系如何定义？
- [ ] 图表导出的具体格式和实现方式需要进一步确定
- [ ] 是否需要支持自定义图表样式和布局？