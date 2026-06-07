# 架构数据备注打标功能 Spec

## Why

当前架构数据管理界面支持对领域、子领域、服务模块、业务对象、业务关系进行 CRUD 操作，但缺乏为这些对象添加业务备注的能力。用户需要在数据管理过程中为核心对象添加多条业务打标备注，以便在 AA 图中展示标注信息，更好地传达业务语义和关键信息。

## What Changes

- 新增独立的 `annotation` 对象，支持一个对象关联多条备注
- 在详情视图中展示备注列表，支持添加、编辑、删除备注
- 在列表视图中展示备注数量和预览
- 备注数据与 AA 图标注功能对接

## Impact

### Affected Specs

- `diagram-annotation` - 图表备注功能需要扩展支持新的数据源

### Affected Code

- `meta/schemas/annotation.yaml` - 新增备注对象元模型
- `meta/objects/annotation.py` - 新增备注对象 Python 类
- `meta/api/manage_api.py` - 新增备注 CRUD API
- `src/views/ArchDataManageApp/components/DynamicDetail.vue` - 详情视图备注列表
- `src/views/ArchDataManageApp/components/AnnotationList.vue` - 新增备注列表组件

## ADDED Requirements

### Requirement: 备注对象元模型定义

系统 SHALL 定义独立的 `annotation` 对象：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | integer | 主键 |
| target_type | string | 关联对象类型（domain/sub_domain/service_module/business_object/relationship） |
| target_id | integer | 关联对象ID |
| category | string | 备注分类（important/warning/info/tip） |
| content | text | 备注内容 |
| created_at | datetime | 创建时间 |
| created_by | string | 创建人 |
| updated_at | datetime | 更新时间 |
| updated_by | string | 更新人 |

#### Scenario: 备注与对象关联

- **WHEN** 用户为某个领域添加备注
- **THEN** 系统创建备注记录
- **AND** `target_type` = 'domain'
- **AND** `target_id` = 领域ID

### Requirement: 备注分类选项

系统 SHALL 提供以下备注分类：

| 分类 | 图标 | 标签 | 用途 |
|------|------|------|------|
| important | ⚠️ | 重要 | 重要提醒 |
| warning | 🚨 | 警告 | 警告信息 |
| info | ℹ️ | 信息 | 一般说明（默认） |
| tip | 💡 | 提示 | 提示建议 |

#### Scenario: 备注分类默认值

- **WHEN** 用户未选择备注分类
- **THEN** 系统默认使用 `info` 分类

### Requirement: 数据库 Schema 创建

系统 SHALL 创建 `annotations` 表：

```sql
CREATE TABLE annotations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  target_type VARCHAR(50) NOT NULL,
  target_id INTEGER NOT NULL,
  category VARCHAR(20) NOT NULL,
  content TEXT,
  created_at DATETIME NOT NULL,
  created_by VARCHAR(100),
  updated_at DATETIME,
  updated_by VARCHAR(100)
);

CREATE INDEX idx_annotation_target ON annotations(target_type, target_id);
```

### Requirement: 详情视图备注列表展示

系统 SHALL 在详情视图中展示备注列表：

- 列表标题：备注信息 (N)
- 每条备注显示：分类图标 + 内容预览 + 创建时间
- 支持操作：添加、编辑、删除
- 无备注时显示"暂无备注"

#### Scenario: 有备注的详情显示

- **WHEN** 对象有关联备注
- **THEN** 详情页显示"备注信息"列表
- **AND** 显示备注数量
- **AND** 每条备注显示分类图标和内容

#### Scenario: 无备注的详情显示

- **WHEN** 对象无关联备注
- **THEN** 详情页显示"备注信息"区域
- **AND** 显示"暂无备注"提示
- **AND** 显示"添加备注"按钮

### Requirement: 备注添加功能

系统 SHALL 支持添加备注：

- 点击"添加备注"按钮弹出备注表单
- 表单字段：分类（下拉）、内容（文本框）
- 保存后备注关联到当前对象

#### Scenario: 添加备注成功

- **WHEN** 用户填写备注并保存
- **THEN** 系统创建备注记录
- **AND** 备注列表更新显示新备注
- **AND** 显示成功提示

### Requirement: 备注编辑功能

系统 SHALL 支持编辑备注：

- 点击备注项的"编辑"按钮
- 弹出备注表单，显示当前值
- 保存后更新备注内容

#### Scenario: 编辑备注成功

- **WHEN** 用户修改备注并保存
- **THEN** 系统更新备注记录
- **AND** 备注列表更新显示修改后的内容
- **AND** 显示成功提示

### Requirement: 备注删除功能

系统 SHALL 支持删除备注：

- 点击备注项的"删除"按钮
- 弹出确认对话框
- 确认后删除备注

#### Scenario: 删除备注成功

- **WHEN** 用户确认删除备注
- **THEN** 系统删除备注记录
- **AND** 备注列表更新
- **AND** 显示成功提示

### Requirement: 列表视图备注预览

系统 SHALL 在列表视图中展示备注预览：

- 备注列标题：备注
- 展示格式：`[数量] 第一条备注内容截取...`
- 无备注时显示 `-`
- 鼠标悬停显示所有备注预览

#### Scenario: 有备注的列表显示

- **WHEN** 对象有关联备注
- **THEN** 列表显示备注数量图标
- **AND** 显示第一条备注内容前20字

#### Scenario: 多条备注的悬停预览

- **WHEN** 鼠标悬停在备注列
- **THEN** 显示 Tooltip 列出所有备注预览
- **AND** 每条备注显示分类图标和内容截取

## Data Model

### 备注对象元模型 (annotation.yaml)

```yaml
id: annotation
name: 备注信息
table_name: annotations
description: 为架构对象添加的业务备注信息

fields:
  - id: id
    name: ID
    type: integer
    db_column: id
    required: true
    unique: true

  - id: target_type
    name: 关联对象类型
    type: string
    db_column: target_type
    required: true
    description: 备注关联的对象类型
    ui:
      widget: select
      options:
        - value: domain
          label: 领域
        - value: sub_domain
          label: 子领域
        - value: service_module
          label: 服务模块
        - value: business_object
          label: 业务对象
        - value: relationship
          label: 业务关系

  - id: target_id
    name: 关联对象ID
    type: integer
    db_column: target_id
    required: true
    description: 备注关联的对象ID

  - id: category
    name: 备注分类
    type: string
    db_column: category
    description: 备注分类
    ui:
      widget: select
      options:
        - value: important
          label: ⚠️ 重要
        - value: warning
          label: 🚨 警告
        - value: info
          label: ℹ️ 信息
        - value: tip
          label: 💡 提示

  - id: content
    name: 备注内容
    type: text
    db_column: content
    description: 备注详细内容
    ui:
      widget: textarea
      placeholder: 请输入备注内容...

  - id: created_at
    name: 创建时间
    type: datetime
    db_column: created_at

  - id: created_by
    name: 创建人
    type: string
    db_column: created_by

  - id: updated_at
    name: 更新时间
    type: datetime
    db_column: updated_at

  - id: updated_by
    name: 更新人
    type: string
    db_column: updated_by
```

## UI Interaction Design

### 详情视图备注列表

```
┌─────────────────────────────────────────────────────────────────┐
│ 备注信息 (3)                                    [+ 添加备注]    │
├─────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ ⚠️ 核心业务领域，需要重点关注系统稳定性...                   │ │
│ │    2026-04-22 10:30  admin              [编辑] [删除]       │ │
│ └─────────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ ℹ️ 包含采购审批流程，支持多级审批...                         │ │
│ │    2026-04-21 15:20  user1              [编辑] [删除]       │ │
│ └─────────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ 💡 建议增加自动化测试覆盖...                                 │ │
│ │    2026-04-20 09:00  tester             [编辑] [删除]       │ │
│ └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 备注表单弹窗

```
┌─────────────────────────────────────────┐
│ 添加备注                         [×]    │
├─────────────────────────────────────────┤
│                                         │
│ 分类：  [⚠️ 重要 ▼]                     │
│         ├─ ⚠️ 重要                     │
│         ├─ 🚨 警告                     │
│         ├─ ℹ️ 信息                     │
│         └─ 💡 提示                     │
│                                         │
│ 内容：  ┌─────────────────────────────┐ │
│         │ 核心业务领域，需要重点关注   │ │
│         │ 系统稳定性...               │ │
│         └─────────────────────────────┘ │
│                                         │
│              [取消]  [保存]             │
└─────────────────────────────────────────┘
```

### 列表视图备注列

```
┌──────────────────────────────────────────────────────────────────┐
│ 名称        │ 编码    │ 所属领域  │ 备注              │ 操作    │
├──────────────────────────────────────────────────────────────────┤
│ 供应链      │ SUPPLY  │ -        │ [3] ⚠️ 核心业务... │ ...     │
│ 采购        │ PROC    │ 供应链   │ [1] ℹ️ 包含审批... │ ...     │
│ 订单        │ ORDER   │ 销售     │ -                 │ ...     │
└──────────────────────────────────────────────────────────────────┘
```

### 悬停预览 Tooltip

```
┌─────────────────────────────────────────┐
│ ⚠️ 核心业务领域，需要重点关注...        │
│ ℹ️ 包含采购审批流程...                  │
│ 💡 建议增加自动化测试...                │
└─────────────────────────────────────────┘
```

## Constraints & Assumptions

### Technical Constraints

- 备注与对象是多对一关系
- 删除对象时，关联备注一并删除（级联删除）
- 备注内容最大长度：无限制（TEXT 类型）

### Business Constraints

- 备注不支持富文本格式
- 备注不支持附件
- 备注不支持回复/评论

### Assumptions

- 用户通过架构数据管理界面编辑备注
- 备注数据在 AA 图中通过现有 annotation 功能展示
- 备注分类图标与 AA 图保持一致

## Priorities & Milestone Suggestions

| ID | Requirement | Priority | Reason |
|----|-------------|----------|--------|
| FR-001 | 备注对象元模型定义 | Must | 数据层基础 |
| FR-002 | 数据库 Schema 创建 | Must | 数据持久化 |
| FR-003 | 备注 CRUD API | Must | 接口支持 |
| FR-004 | 详情视图备注列表展示 | Should | 信息展示 |
| FR-005 | 备注添加功能 | Should | 数据编辑 |
| FR-006 | 备注编辑功能 | Should | 数据编辑 |
| FR-007 | 备注删除功能 | Should | 数据编辑 |
| FR-008 | 列表视图备注预览 | Should | 用户体验 |

### Suggested Milestones

- **Milestone 1**: 数据层改造（FR-001, FR-002, FR-003）
- **Milestone 2**: UI 层改造（FR-004, FR-005, FR-006, FR-007, FR-008）

## TBD List

暂无待确认事项。
