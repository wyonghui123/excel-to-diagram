## 目录

1. [一、背景与目标](#一-背景与目标)
2. [二、设计原则](#二-设计原则)
3. [三、关联类型体系](#三-关联类型体系)
4. [四、审计日志（Audit Log）](#四-审计日志（audit-log）)
5. [五、详情页布局](#五-详情页布局)
6. [六、组件改造](#六-组件改造)
7. [七、配置示例](#七-配置示例)
8. [八、验收标准](#八-验收标准)
9. [九、后续增强（TODO）](#九-后续增强（todo）)
10. [十、变更记录](#十-变更记录)

---
# M18.8 详情页增强设计方案

> **版本**: v1.0
> **日期**: 2026-05-14
> **目的**: 增强详情页关联展示能力，支持嵌入式关联和统一配置

---

## 一、背景与目标

### 1.1 现状分析

当前 `DetailPage.vue` 已具备的能力：
- Tab 系统（基本信息 / 关联 / 变更历史）
- Association 内嵌（通过 Tab 展示）
- AuditLog 内嵌（通过 Tab 展示）
- 元数据驱动（YAML 配置）

现有组件复用情况：

| 组件 | 位置 | 状态 |
|------|------|------|
| DetailPage.vue | src/components/common/ | ✅ 已有 |
| useDetail.js | src/composables/ | ✅ 已有 |
| AssociationPanel.vue | src/components/common/ | ✅ 已有 |
| AuditLog.vue | src/components/common/ | ✅ 已有 |
| AnnotationList.vue | src/views/ArchDataManageApp/ | ✅ 已有 |

### 1.2 目标

1. **增强 DetailPage**：支持关联嵌入基础信息下方展示
2. **统一配置机制**：通过 YAML 配置声明所有关联
3. **架构一致性**：遵循 SAP CDS 风格的关联模型

---

## 二、设计原则

### 2.1 核心原则

| 原则 | 说明 |
|------|------|
| **元数据驱动** | 所有展示逻辑通过 YAML 配置声明 |
| **单一事实来源** | 配置即文档，YAML 是唯一的配置源 |
| **通用组件** | 复用现有组件，避免重复建设 |
| **智能推导** | 根据 aspects 自动启用相关能力 |

### 2.2 参考模型

采用 **SAP CDS 风格的关联模型**：

```
Association（关联）
├── 普通关联 (association) — 可独立存在
└── 组成关系 (composition) — 生命周期绑定
```

**SAP 引用**：
> *"In CDS models, compositions are a special kind of association that represent a parent-child hierarchical relationship, in which the child is a part of the parent and cannot exist without it."*

---

## 三、关联类型体系

### 3.1 类型定义

| 类型 | 说明 | 示例 | 生命周期 |
|------|------|------|----------|
| `association` | 普通关联 | 用户-角色 | 可独立存在 |
| `composition` | 组成关系 | 领域-子领域、对象-备注 | 随主对象 |

### 3.2 关联配置结构

```yaml
associations:
  - name: related_objects
    label: 关联对象
    target_entity: business_object
    type: association  # 普通关联
    display:
      mode: tab  # tab | embedded，默认 tab
      collapsed: false

  - name: sub_domains
    label: 子领域
    target_entity: sub_domain
    type: composition  # 组成关系
    display:
      mode: embedded  # 组成关系默认嵌入
      collapsed: true

  - name: annotations
    label: 备注
    type: composition  # 备注也是 composition
    target_entity: annotation
    config:
      categories_from_enum: annotation_category
      default_category: note
    display:
      mode: embedded
      collapsed: true
```

### 3.3 配置字段说明

| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `name` | string | 关联名称（唯一标识） | - |
| `label` | string | 显示标签 | - |
| `target_entity` | string | 目标实体 | - |
| `type` | enum | `association` \| `composition` | `association` |
| `display.mode` | enum | `tab` \| `embedded` | `tab` |
| `display.collapsed` | boolean | 默认折叠状态 | `false` |
| `config` | object | 特定类型配置 | - |

---

## 四、审计日志（Audit Log）

### 4.1 设计决策

审计日志作为**系统能力**独立处理，原因：
1. **系统内置**：不是用户配置的关联，是框架自动提供的
2. **只读特性**：用户不能编辑历史记录
3. **固定展示**：头部企业（SAP、Salesforce）都使用 Tab，无嵌入模式

### 4.2 配置方式

```yaml
# 方式1: 通过 aspects 自动启用
aspects:
  - audit_aspect

# 方式2: 显式配置
ui_view_config:
  detail:
    showAuditLog: true
```

### 4.3 智能推导规则

| 条件 | 结果 |
|------|------|
| 实体有 `audit_aspect` | 自动添加变更历史 Tab |
| 无 `audit_aspect` | 不显示变更历史 |

---

## 五、详情页布局

### 5.1 页面结构

```
┌─────────────────────────────────────────────────────────────┐
│ DetailPage.vue                                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ 基本信息字段                                          │  │
│  │ - 字段1: 值1                                        │  │
│  │ - 字段2: 值2                                        │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ [折叠] 子领域 (3)           [展开]                  │  │
│  │ ┌─────────────────────────────────────────────────┐│  │
│  │ │ AssociationPanel (embedded, composition)        ││  │
│  │ └─────────────────────────────────────────────────┘│  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ [折叠] 备注 (5)               [展开]                │  │
│  │ ┌─────────────────────────────────────────────────┐│  │
│  │ │ AnnotationList (embedded, composition)          ││  │
│  │ └─────────────────────────────────────────────────┘│  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Tab: 关联对象 │ 变更历史 │ 附件                     │  │
│  │─────────────────────────────────────────────────────│  │
│  │                                                     │  │
│  │ AssociationPanel (tab mode)                         │  │
│  │                                                     │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 渲染逻辑

```
associations 配置
    │
    ├── mode: embedded
    │   └── 渲染在基本信息下方（按 position 顺序）
    │
    └── mode: tab
        └── 合并到 "关联" Tab（统一展示）

aspects 配置
    │
    └── audit_aspect
        └── 添加 "变更历史" Tab
```

---

## 六、组件改造

### 6.1 DetailPage.vue 改造

**新增 Props**：

```typescript
interface DetailPageProps {
  // 现有...
  embeddedAssociations?: AssociationConfig[]
  tabAssociations?: AssociationConfig[]
}
```

**渲染逻辑**：

```vue
<template>
  <div class="detail-page">
    <!-- 基本信息 -->
    <BasicInfo :fields="fields" />

    <!-- 嵌入式关联（composition 默认嵌入） -->
    <template v-for="assoc in embeddedAssociations" :key="assoc.name">
      <AssociationSection
        :config="assoc"
        :collapsed="assoc.display.collapsed"
      >
        <AssociationPanel :config="assoc" mode="embedded" />
      </AssociationSection>
    </template>

    <!-- Tab 区域 -->
    <AppTabs v-model="activeTab" :tabs="tabs">
      <template v-for="assoc in tabAssociations" :key="assoc.name">
        <TabPane :label="assoc.label" :name="assoc.name">
          <AssociationPanel :config="assoc" mode="tab" />
        </TabPane>
      </template>
    </AppTabs>
  </div>
</template>
```

### 6.2 智能分类逻辑

```typescript
function classifyAssociations(associations: AssociationConfig[]) {
  const embedded: AssociationConfig[] = []
  const tab: AssociationConfig[] = []

  for (const assoc of associations) {
    // composition 默认嵌入
    if (assoc.type === 'composition' && assoc.display.mode !== 'tab') {
      embedded.push(assoc)
    } else {
      tab.push(assoc)
    }
  }

  return { embedded, tab }
}
```

---

## 七、配置示例

### 7.1 完整配置示例

```yaml
# domain.yaml
name: domain
label: 领域
aspects:
  - audit_aspect

fields:
  - name: name
    label: 名称
    type: string
    required: true

  - name: code
    label: 编码
    type: string
    required: true

  - name: description
    label: 描述
    type: text

associations:
  - name: sub_domains
    label: 子领域
    target_entity: sub_domain
    type: composition
    display:
      mode: embedded
      collapsed: true

  - name: annotations
    label: 备注
    target_entity: annotation
    type: composition
    config:
      categories_from_enum: annotation_category
    display:
      mode: embedded
      collapsed: true

  - name: related_domains
    label: 关联领域
    target_entity: domain
    type: association
    display:
      mode: tab

  - name: related_objects
    label: 关联业务对象
    target_entity: business_object
    type: association
    display:
      mode: tab

ui_view_config:
  detail:
    tabs:
      - id: basic
        label: 基本信息
        type: fields
      - id: associations
        label: 关联对象
        type: associations
      - id: history
        label: 变更历史
        type: history
        # 自动添加，audit_aspect 启用
```

### 7.2 最小配置示例

```yaml
# 最小配置：只需要声明 associations
name: domain
label: 领域

associations:
  - name: sub_domains
    target_entity: sub_domain
    type: composition
    # display.mode 默认 tab，composition 可省略

  - name: annotations
    target_entity: annotation
    type: composition
```

---

## 八、验收标准

### 8.1 功能验收

| 编号 | 标准 | 验证方式 |
|------|------|----------|
| 1 | Association 可配置 `mode: tab \| embedded` | YAML 配置 |
| 2 | `type: composition` 默认 `mode: embedded` | 渲染验证 |
| 3 | Embedded 关联渲染在基本信息下方 | UI 验证 |
| 4 | Tab 关联合并到 "关联" Tab | UI 验证 |
| 5 | `audit_aspect` 自动启用变更历史 Tab | YAML 配置 |
| 6 | Annotation 作为 `type: composition` | YAML 配置 |
| 7 | `collapsed` 配置生效 | UI 验证 |

### 8.2 非功能验收

| 编号 | 标准 |
|------|------|
| 1 | 复用现有组件（DetailPage、AssociationPanel、AuditLog、AnnotationList） |
| 2 | 所有展示逻辑通过 YAML 配置 |
| 3 | 无需修改组件代码即可配置新关联 |

---

## 九、后续增强（TODO）

| 编号 | 功能 | 说明 |
|------|------|------|
| 1 | 层级路径导航 | 点击路径节点跳转到父对象详情 |
| 2 | 关联搜索 | 在关联面板中搜索目标对象 |

---

## 十、变更记录

| 日期 | 版本 | 变更内容 |
|------|------|----------|
| 2026-05-14 | v1.0 | 初始版本 |

---

**设计完成，等待实现**
