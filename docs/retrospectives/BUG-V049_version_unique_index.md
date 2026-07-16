# BUG-V049: version 唯一索引错误导致不同产品无法创建同名版本

> 日期: 2026-07-09 | 严重度: P1 | 状态: 已修复

## 现象

用户 wyonghui 创建产品 DEMOPORD3，版本编码 V1，保存时报错：
```
操作失败，已回滚所有操作: version[0]: 值 已存在
```

## 根因

1. **2026-06-13 移除 naming_aspect/code 字段**：version 的唯一标识从 `(product_id, code)` 变为 `(product_id, name)`，但数据库索引未同步修改

2. **index_rule_engine 的 business_key_unique 规则**：对每个 `business_key=True` 的字段自动创建单字段唯一索引（`uidx_{table}_{column}`）

3. **version.yaml 的 `name` 字段标记了 `business_key: true`**：引擎自动创建了 `uidx_versions_name ON versions(name)` — 全局唯一

4. **引擎不读 `import_export.conflict_key`**：虽然 version.yaml 在 `conflict_key: "product_id,name"` 声明了联合唯一，但 `_get_fields_in_composite_unique()` 只检查 `meta_obj.indexes`（显式定义的索引），不读 conflict_key

5. **已有数据**：DEMOPROD (product_id=533) 已有 V1 版本 (id=883)，新产品创建 V1 时全局唯一索引拦截

## 错误链路

```
用户创建产品+版本 → DeepInsertEngine → SQLite INSERT INTO versions(name='V1')
                                              ↓
                           uidx_versions_name (全局唯一) → UNIQUE constraint failed
                                              ↓
                           _make_unique_message → "值 已存在"
                                              ↓
                           _DeepInsertError → "version[0]: 值 已存在"
```

## 修复

### 1. version.yaml 显式定义联合唯一索引

```yaml
indexes:
  - name: uidx_versions_product_name
    fields: [product_id, name]
    type: unique
    priority: high
    description: "产品+版本名称联合唯一索引"
```

这样 `_get_fields_in_composite_unique()` 检测到 `name` 在复合唯一索引中，跳过单字段唯一索引创建。

### 2. 数据库迁移脚本

`meta/migrations/fix_version_unique_index.py`:
- DROP INDEX `uidx_versions_name`
- CREATE UNIQUE INDEX `uidx_versions_product_name ON versions(product_id, name)`

### 3. 验证

- 引擎测试：`uidx_versions_name` 不再被创建，`uidx_versions_product_name` 存在
- API 测试：DEMOPROD (id=533) 的 V1 和 DEMOPORD3 (id=535) 的 V1 共存

## 教训

1. **schema 变更必须同步检查索引**：移除 code 字段时，应同时检查索引是否需要调整
2. **conflict_key 和 indexes 应保持一致**：`import_export.conflict_key` 声明的联合唯一约束应该也出现在 `indexes` 段
3. **index_rule_engine 应考虑 conflict_key**：未来可增强 `_get_fields_in_composite_unique()` 也读取 conflict_key 作为复合唯一约束的来源

## 影响范围

- 文件：`meta/schemas/version.yaml`（添加 indexes 段）
- 文件：`meta/migrations/fix_version_unique_index.py`（新增迁移脚本）
- 数据库：`uidx_versions_name` → `uidx_versions_product_name`
