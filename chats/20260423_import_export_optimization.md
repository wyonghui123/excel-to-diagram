# Import/Export 功能优化 - 2026-04-23

## 优化目标
完善 Excel 导出导入功能，确保列字段的只读/必填规则正确应用。

---

## 1. 说明页优化

### 问题
- 说明页样式奇怪（字体太大）
- 筛选条件不应显示在说明页

### 修复
- 优化说明页样式（边框、分组、标签样式）
- 移除筛选条件行
- 字体调整为 11px（原来是 14px）

---

## 2. 列字段排除规则

### 问题
- 版本和产品线列仍然显示
- 业务对象sheet有多余列（领域、子领域、服务模块重复）
- 导出头有重复列名

### 根因分析
1. `export_visible` 默认值是 `True`，所有字段都导出
2. 层级字段重复添加
3. 关系对象有虚拟字段冲突

### 修复
1. **修改 models.py 默认值**
   ```python
   # export_visible 默认改为 False
   export_visible: bool = False
   ```

2. **修改 yaml_loader.py 默认值**
   ```python
   export_visible=data.get("export_visible", False)
   ```

3. **添加 relationship 专属排除字段**
   ```python
   if meta_obj.id == 'relationship':
       default_exclude_fields.update({
           'source_domain_id', 'source_sub_domain_id', 'source_service_module_id',
           'target_domain_id', 'target_sub_domain_id', 'target_service_module_id',
           'source_domain_name', 'source_sub_domain_name', 'source_service_module_name',
           'target_domain_name', 'target_sub_domain_name', 'target_service_module_name',
           ...
       })
   ```

4. **排除版本/产品线层级列**
   ```python
   exclude_hierarchy_types = {'version', 'product', 'product_line'}
   ```

---

## 3. 业务规则完善

### 确认的规则

| 字段类型 | 新增时 | 编辑时 |
|---------|--------|---------|
| **业务关键字** (code) | 必填 | 只读 |
| **父对象编码** (第一层) | 必填 | 只读 |
| **父对象编码** (第二层及以上) | - | 只读 |
| **父对象名称** | - | 只读 |
| **外键字段** (_id) | - | 只读 |
| **ID字段** | - | 排除（不导出） |

### 导入校验
- business_key 必填校验
- 唯一性校验（同一文件中 business_key 值不能重复）
- 存在性提示（如果 business_key 已存在，提示将执行更新操作）

### 外键查找
通过父对象的 `code` 字段查找父对象 ID：
```python
parent_record = self._find_by_key(parent_info["parent_type"], "code", parent_code)
```

---

## 4. Excel 表头注释更新

### 列头注释规则
- **业务关键字**：`【业务关键字】新增必填，编辑时只读`
- **第一层父对象编码**：`【父对象编码】新增必填；编辑时只读，通过此编码关联父对象`
- **第二层父对象编码**：`父对象编码，只读`
- **父对象名称**：`父对象名称，只读`

### 说明页内容
新增以下说明：
- **业务关键字**：编码字段为业务关键字，用于唯一标识记录。新增时必填，编辑时只读。系统通过此字段查找和匹配记录。
- **父对象编码**：用于关联父对象。新增时必填，编辑时只读。填写父对象的业务编码（如服务模块编码）。

---

## 5. 文件名优化

### 问题
文件名包含 `arch_data` 前缀

### 修复
移除前缀，改为：
```
{产品线}_{版本}_{时间戳}.xlsx
{版本}_{时间戳}.xlsx
{时间戳}.xlsx
```

---

## 6. 过滤条件修复

### 问题
relation_codes 过滤条件不生效

### 修复
```python
# 添加 relation_codes 到 relation_code 字段的映射
if key == 'relation_codes' and 'relation_code' in valid_fields:
    conditions.append(QueryCondition(
        field='relation_code', 
        operator=QueryOperator.IN, 
        values=value
    ))
```

---

## 7. 关系计数不一致问题

### 问题
全选时树形节点显示的关系数量与列表显示的不一致

### 根因
yaml_loader.py 中 `export_visible` 默认值与 models.py 不一致

### 修复
统一 yaml_loader.py 中的默认值：
```python
export_visible=data.get("export_visible", False)
```

---

## 8. ID 字段排除

### 分析
- ID 是数据库自增主键，导入时无法提供
- 所有编辑/删除操作都已通过 business_key (code) 定位
- ID 在导入时是无用的列

### 修复
将 `id` 添加到 `default_exclude_fields`：
```python
default_exclude_fields = {
    'id', 'created_at', 'updated_at', ...
}
```

---

## 最终导出列数对比

| Sheet | 优化前 | 优化后 |
|-------|--------|---------|
| 业务对象 | 16 | 10 |
| 服务模块 | 13 | 7 |
| 子领域 | 11 | 6 |
| 领域 | 9 | 4 |
| 关系 | 33 | 9 |

---

## 待办事项

### 页面编辑优化 (TODO_page_edit.md)
- [ ] DynamicForm.vue 硬编码改为元数据驱动
- [ ] EditForm.vue readonlyHierarchyFields 改为元数据推导
- [ ] 统一只读判断逻辑

### 业务规则
- [ ] 新增模式：business_key 可编辑
- [ ] 编辑模式：business_key 只读、外键只读
- [ ] 唯一性校验：business_key 需要唯一性检查

---

## 服务管理经验

### StopCommand 卡住的根因
- Flask Debug 模式的 stat reloader 会在终止后立即重启进程
- 需要用强制杀死而非优雅终止

### 改进方案
```powershell
# 强制终止
taskkill /F /PID <pid>

# 服务状态检测（避免 hang）
Test-NetConnection -ComputerName localhost -Port 5000 -InformationLevel Quiet
```

### 项目规则文件
已创建 `.trae/rules/project_rules.md` 记录服务器管理规范。
