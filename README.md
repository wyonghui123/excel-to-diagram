# Excel-to-Diagram

元数据驱动的业务对象管理平台。

## 核心特性

- **YAML 单一事实原则**：配置即文档，减少冗余
- **元数据驱动 UI**：通过 YAML 配置自动生成页面
- **组件单一引用**：使用 `MetaListPage` 一行代码构建列表页

## 快速开始

### 新增业务对象

1. 复制模板：
   ```bash
   cp meta/schemas/_template.yaml meta/schemas/your_object.yaml
   ```

2. 修改配置：
   ```yaml
   id: your_object
   name: 你的对象
   table_name: your_objects
   ```

3. 重启后端自动加载

### 页面组件

```vue
<!-- 一行代码构建列表页 -->
<MetaListPage
  object-type="your_object"
  enable-detail
  enable-auto-crud
/>
```

## 架构文档

| 文档 | 说明 |
|------|------|
| [核心设计原则](docs/architecture/01-principles.md) | YAML 单一事实原则、元数据驱动架构 |
| [YAML 配置规范](docs/architecture/02-yaml-conventions.md) | 字段、关联、视图配置 |
| [元数据驱动 UI](docs/architecture/03-meta-driven-ui.md) | 组件使用、插槽机制 |
| [API 契约](docs/architecture/04-api-contracts.md) | REST API 规范 |
| [常见模式](docs/architecture/05-patterns.md) | 代码模板和最佳实践 |

## YAML 单一事实原则

> **核心原则**：YAML 只配置例外情况，字段权限默认由后端智能推导。

```yaml
# ✅ 正确：最小配置
fields:
  - id: name
    required: true  # 唯一需要配置的

# ❌ 错误：冗余配置
fields:
  - id: name
    ui:
      visible: true      # 冗余！
      editable: true     # 冗余！
```

### 默认推导规则

| 属性 | 默认值 | 推导规则 |
|------|--------|---------|
| `visible` | `true` | 系统字段(id, created_at) 自动隐藏 |
| `editable` | `true` | 业务键(computed, business_key) 自动只读 |
| `export_visible` | `true` | 所有字段默认可导出 |
| `import_visible` | `true` | 所有字段默认可导入 |

## 目录结构

```
meta/
├── schemas/           # YAML 元数据配置
│   ├── _template.yaml # 新对象模板
│   ├── user.yaml
│   ├── role.yaml
│   └── user_group.yaml
├── core/              # 核心框架
│   ├── bo_framework.py
│   └── models.py
└── services/         # 服务层
    ├── query_service.py
    └── import_export_service.py

src/
├── components/common/ # 通用组件
│   ├── MetaListPage/
│   ├── DetailPage/
│   └── AssociationPanel/
└── composables/      # 组合式函数
    ├── useMetaList.js
    └── useDetail.js
```

## 开发指南

### 后端启动

```bash
python dev.py
```

### 前端启动

```bash
npm run dev
```

### YAML 配置检查

```bash
python -c "from meta.core.models import registry; print([m.id for m in registry.all()])"
```

## License

MIT
