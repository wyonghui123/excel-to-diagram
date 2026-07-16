# 元模型定义目录

## 这是什么？

这里是**语义数据模型的定义文件**，描述了业务系统的核心对象结构。

## 如何阅读

直接打开对应的 YAML 文件即可：
- [product.yaml](./product.yaml) - 产品线（层级1）
- [version.yaml](./version.yaml) - 产品版本（层级2）
- [domain.yaml](./domain.yaml) - 领域（层级3）
- [sub_domain.yaml](./sub_domain.yaml) - 子领域（层级4）
- [service_module.yaml](./service_module.yaml) - 服务模块（层级5）
- [business_object.yaml](./business_object.yaml) - 业务对象（层级6）
- [relationship.yaml](./relationship.yaml) - 业务关系（层级7）

## 层级关系

```
产品线 (product)
  └── 版本 (version)
        └── 领域 (domain)
              └── 子领域 (sub_domain)
                    └── 服务模块 (service_module)
                          └── 业务对象 (business_object)
                                ↕ 业务关系 (relationship)
```

## 如何修改

1. **编辑 YAML 文件** - 添加/修改字段、关系、操作等
2. **检查变更** - `python -m meta.tools.sync_schema --diff`
3. **执行同步** - `python -m meta.tools.sync_schema --execute`

## 持久化控制

### 不需要持久化的对象

```yaml
id: search_dto
name: 搜索DTO
table_name: ""          # 可以留空
persistent: false       # 标记为非持久化
```

### 计算字段（不存数据库）

```yaml
fields:
  - id: display_text
    name: 显示文本
    type: string
    persistent: false   # 不持久化
    computed: true      # 计算字段
    compute_expr: "code + ' - ' + name"
```

### 数据库视图

```yaml
id: active_products
name: 活跃产品视图
table_name: v_active_products
is_view: true
view_definition: "SELECT * FROM products WHERE is_active = 1"
```

## AI Agent 注意

**这是元模型的唯一真相来源**。当需要理解业务模型或进行迭代优化时：

1. **优先阅读此目录下的 YAML 文件**
2. **修改元模型时直接编辑 YAML 文件**
3. **涉及字段变更时运行 Schema 同步**

详细规则见：`.trae/rules/meta-model-schema-sync.md`
