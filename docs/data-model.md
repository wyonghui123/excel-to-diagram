# 数据模型文档

## 1. Excel 导入数据模型

### 1.1 业务对象 (Business Object)

业务对象代表系统中的业务实体，如用户、订单、产品等。

```typescript
interface BusinessObject {
  /** 业务对象编码 */
  boCode: string;
  /** 业务对象名称 */
  boName: string;
  /** 业务对象类型 */
  boType: 'entity' | 'value-object' | 'event' | 'service';
  /** 所属领域 */
  domain: string;
  /** 子领域 */
  subDomain?: string;
  /** 描述 */
  description?: string;
  /** 标注分类 */
  annotationCategory?: 'info' | 'warning' | 'success' | 'danger';
  /** 标注内容 */
  annotationContent?: string;
}
```

**Excel 字段映射**:

| Excel 列名 | 字段 | 说明 |
|------------|------|------|
| BO_CODE | boCode | 业务对象编码 |
| BO_NAME | boName | 业务对象名称 |
| BO_TYPE | boType | 类型：entity/value-object/event/service |
| DOMAIN | domain | 领域 |
| SUB_DOMAIN | subDomain | 子领域 |
| DESC | description | 描述 |
| ANNOTATION_CATEGORY | annotationCategory | 标注分类 |
| ANNOTATION_CONTENT | annotationContent | 标注内容 |

**示例数据**:

| BO_CODE | BO_NAME | BO_TYPE | DOMAIN |
|---------|---------|---------|--------|
| BO_USER | 用户 | entity | 客户域 |
| BO_ORDER | 订单 | entity | 交易域 |

---

### 1.2 服务模块 (Service Module)

服务模块代表系统中的服务组件或子系统。

```typescript
interface ServiceModule {
  /** 服务编码 */
  smCode: string;
  /** 服务名称 */
  smName: string;
  /** 领域 */
  domain: string;
  /** 子领域 */
  subDomain?: string;
  /** 服务类型 */
  smType?: 'application' | 'domain' | 'infrastructure';
  /** 技术栈 */
  techStack?: string;
  /** 标注分类 */
  annotationCategory?: 'info' | 'warning' | 'success' | 'danger';
  /** 标注内容 */
  annotationContent?: string;
}
```

**Excel 字段映射**:

| Excel 列名 | 字段 | 说明 |
|------------|------|------|
| SM_CODE | smCode | 服务编码 |
| SM_NAME | smName | 服务名称 |
| DOMAIN | domain | 领域 |
| SUB_DOMAIN | subDomain | 子领域 |
| SM_TYPE | smType | 服务类型 |
| TECH_STACK | techStack | 技术栈 |

---

### 1.3 关系 (Relationship)

关系描述业务对象或服务模块之间的关联。

```typescript
interface Relationship {
  /** 源节点编码 */
  source: string;
  /** 目标节点编码 */
  target: string;
  /** 关系类型 */
  relationType: 'dependency' | 'association' | 'aggregation' | 'composition' | 'inheritance';
  /** 关系描述 */
  description?: string;
  /** 是否双向 */
  bidirectional?: boolean;
}
```

**Excel 字段映射**:

| Excel 列名 | 字段 | 说明 |
|------------|------|------|
| SOURCE | source | 源节点 |
| TARGET | target | 目标节点 |
| REL_TYPE | relationType | 关系类型 |
| DESC | description | 描述 |
| BIDIRECTIONAL | bidirectional | 是否双向 |

---

## 2. 分组模型 (Group Model)

### 2.1 分组 (Group)

分组用于组织业务对象和服务模块，形成层级结构。

```typescript
interface Group {
  /** 分组唯一标识 */
  id: string;
  /** 分组名称 */
  name: string;
  /** 父分组 ID */
  parentId: string | null;
  /** 分组层级 */
  level: 0 | 1 | 2;
  /** 领域 */
  domain: string;
  /** 子分组 */
  childGroups: Group[];
  /** 直接子节点 */
  childNodes: DiagramNode[];
  /** 是否折叠 */
  collapsed: boolean;
  /** 颜色 */
  color?: string;
}
```

**层级说明**:

| level | 含义 | 示例 |
|-------|------|------|
| 0 | 一级分组（领域） | 客户域、交易域、库存域 |
| 1 | 二级分组（子领域） | 客户域-用户管理 |
| 2 | 三级分组（服务组） | 用户管理-认证服务 |

---

### 2.2 图表节点 (Diagram Node)

```typescript
interface DiagramNode {
  /** 节点 ID */
  id: string;
  /** 显示标签 */
  label: string;
  /** 节点类型 */
  type: 'service' | 'object' | 'component' | 'group';
  /** 所属分组 */
  groupId: string;
  /** 节点数据 */
  data: BusinessObject | ServiceModule;
  /** 位置坐标 */
  position?: { x: number; y: number };
  /** 尺寸 */
  size?: { width: number; height: number };
}
```

---

### 2.3 图表边 (Diagram Edge)

```typescript
interface DiagramEdge {
  /** 边 ID */
  id: string;
  /** 源节点 */
  source: string;
  /** 目标节点 */
  target: string;
  /** 关系类型 */
  relation: string;
  /** 源分组 */
  sourceGroup: string;
  /** 目标分组 */
  targetGroup: string;
  /** 标签 */
  label?: string;
  /** 是否高亮 */
  highlighted?: boolean;
}
```

---

## 3. Mermaid 语法模型

### 3.1 Mermaid 配置

```typescript
interface MermaidConfig {
  /** 主题 */
  theme: 'default' | 'dark' | 'neutral' | 'forest';
  /** 图表方向 */
  direction: 'TB' | 'BT' | 'LR' | 'RL';
  /** 节点间距 */
  nodeSpacing?: number;
  /** rank 间距 */
  rankSpacing?: number;
  /** 曲线类型 */
  curve?: 'basis' | 'linear' | 'cardinal';
  /** 是否启用动画 */
  animation?: boolean;
  /** 字体 */
  fontFamily?: string;
}
```

**方向说明**:

| 值 | 含义 |
|----|------|
| TB | Top to Bottom |
| BT | Bottom to Top |
| LR | Left to Right |
| RL | Right to Left |

---

### 3.2 颜色方案

```typescript
interface ColorScheme {
  /** 主题名称 */
  name: string;
  /** 分组颜色列表 */
  groupColors: string[];
  /** 服务节点颜色 */
  serviceColor: string;
  /** 业务对象颜色 */
  objectColor: string;
  /** 边颜色 */
  edgeColor: string;
  /** 高亮颜色 */
  highlightColor: string;
}
```

**预设颜色方案**:

| 方案 | 适用场景 |
|------|----------|
| default | 默认配色 |
| pastel | 柔和配色 |
| vivid | 鲜艳配色 |
| professional | 专业商务配色 |

---

## 4. 布局模型

### 4.1 布局配置

```typescript
interface LayoutConfig {
  /** 布局类型 */
  type: 'elk' | 'dagre' | 'grid' | 'linear' | 'grouped';
  /** ELK 布局配置 */
  elk?: {
    /** 算法 */
    algorithm: 'layered' | 'stress' | 'disk';
    /** 节点间距 */
    nodeSpacing: number;
    /** rank 间距 */
    rankSpacing: number;
  };
  /** 分组布局配置 */
  grouped?: {
    /** 分组排列方式 */
    groupDirection: 'TB' | 'LR';
    /** 组内节点布局 */
    innerLayout: 'stack' | 'grid' | 'scatter';
  };
}
```

---

## 5. 导出数据模型

### 5.1 导出选项

```typescript
interface ExportOptions {
  /** 导出格式 */
  format: 'svg' | 'png' | 'pdf';
  /** 文件名 */
  filename?: string;
  /** 背景色 */
  backgroundColor?: string;
  /** 是否包含图例 */
  includeLegend?: boolean;
  /** 缩放比例 */
  scale?: number;
  /** 宽度 */
  width?: number;
  /** 高度 */
  height?: number;
}
```

---

## 6. 状态管理模型

### 6.1 图表步骤状态

```typescript
interface DiagramStepState {
  /** 当前步骤 (1-5) */
  currentStep: 1 | 2 | 3 | 4 | 5;
  /** 步骤数据 */
  stepData: {
    step1?: { file: File };
    step2?: { scope: 'all' | 'domain' | 'module' };
    step3?: { chartType: 'flowchart' | 'block' | 'sequence' };
    step4?: { config: LayoutConfig };
    step5?: { renderedSvg: string };
  };
}
```

---

## 7. 数据验证规则

### 7.1 业务对象验证

```typescript
const businessObjectRules = {
  boCode: [
    { required: true, message: '编码不能为空' },
    { pattern: /^[A-Z][A-Z0-9_]*$/, message: '编码格式不正确' }
  ],
  boName: [
    { required: true, message: '名称不能为空' },
    { maxLength: 50, message: '名称不能超过50字符' }
  ],
  boType: [
    { required: true, message: '类型不能为空' },
    { enum: ['entity', 'value-object', 'event', 'service'], message: '类型无效' }
  ]
};
```

---

## 8. 数据库存储模型 (如需持久化)

### 8.1 项目表

```sql
CREATE TABLE projects (
  id VARCHAR(36) PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  description TEXT,
  excel_data MEDIUMTEXT,
  mermaid_code TEXT,
  layout_config JSON,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

### 8.2 架构图版本表

```sql
CREATE TABLE diagram_versions (
  id VARCHAR(36) PRIMARY KEY,
  project_id VARCHAR(36),
  version INT,
  mermaid_code TEXT,
  comment TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (project_id) REFERENCES projects(id)
);
```

---

*文档更新时间: 2026-04-08*
