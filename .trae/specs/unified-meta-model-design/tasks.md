# Tasks

- [x] Task 1: 新增枚举定义
  - [x] SubTask 1.1: 新增 `ObjectType` 枚举（ENTITY / VIEW / VIRTUAL）
  - [x] SubTask 1.2: 新增 `FieldStorage` 枚举（STORED / VIRTUAL）
  - [x] SubTask 1.3: 新增 `FieldSource` 枚举（OWN / MAPPED / COMPUTED / DERIVED / AGGREGATED）

- [x] Task 2: 新增配置类定义
  - [x] SubTask 2.1: 新增 `ViewConfig` 配置类（sources, joins, group_by, aggregates, filters, sql_definition）
  - [x] SubTask 2.2: 新增 `VirtualConfig` 配置类（usage, source_type, lifecycle）
  - [x] SubTask 2.3: 新增 `MetricReference` 配置类（object_id, field_id, function_id, filter）

- [x] Task 3: 新增 MetaFunction 类
  - [x] SubTask 3.1: 定义 `MetaFunction` dataclass（id, name, expression, return_type, parameters, references）
  - [x] SubTask 3.2: 在 `MetaObject` 中新增 `functions` 字段

- [x] Task 4: 扩展 MetaField 类
  - [x] SubTask 4.1: 新增 `storage` 属性（默认 STORED）
  - [x] SubTask 4.2: 新增 `source` 属性（默认 OWN）
  - [x] SubTask 4.3: 新增派生相关属性（derive_from_object, derive_from_field）
  - [x] SubTask 4.4: 新增聚合相关属性（aggregate_function, aggregate_source_field）
  - [x] SubTask 4.5: 保持向后兼容（persistent, computed 属性）

- [x] Task 5: 扩展 MetaObject 类
  - [x] SubTask 5.1: 新增 `object_type` 属性（默认 ENTITY）
  - [x] SubTask 5.2: 新增 `view_config` 属性
  - [x] SubTask 5.3: 新增 `virtual_config` 属性
  - [x] SubTask 5.4: 新增 `base_objects` 属性
  - [x] SubTask 5.5: 保持向后兼容（persistent, is_view, view_definition 属性）
  - [x] SubTask 5.6: 新增 `get_functions()` 方法

- [x] Task 6: 扩展 MetaRule 类
  - [x] SubTask 6.1: 新增 `metric_refs` 属性（List[MetricReference]）

- [x] Task 7: 扩展 MetaRegistry 类
  - [x] SubTask 7.1: 新增 `get_objects_by_type()` 方法
  - [x] SubTask 7.2: 新增 `get_functions()` 方法

- [x] Task 8: 更新 YAML 加载器
  - [x] SubTask 8.1: 支持 `object_type` 字段解析
  - [x] SubTask 8.2: 支持 `view_config` 配置解析
  - [x] SubTask 8.3: 支持 `virtual_config` 配置解析
  - [x] SubTask 8.4: 支持 `functions` 列表解析
  - [x] SubTask 8.5: 支持 `storage` 和 `source` 字段属性解析

- [x] Task 9: 更新 Schema 生成器
  - [x] SubTask 9.1: 根据 `object_type` 生成不同的 SQL（TABLE / VIEW）
  - [x] SubTask 9.2: 根据 `view_config` 生成 SQL VIEW 定义
  - [x] SubTask 9.3: 根据 `storage` 属性决定字段是否生成列

- [x] Task 10: 更新规则执行器
  - [x] SubTask 10.1: 实现规则与对象类型的约束检查
  - [x] SubTask 10.2: 实现 `metric_refs` 指标引用解析
  - [x] SubTask 10.3: 实现 `MetaFunction` 执行

- [x] Task 11: 新增测试用例
  - [x] SubTask 11.1: 测试对象类型定义（ENTITY / VIEW / VIRTUAL）
  - [x] SubTask 11.2: 测试视图配置（聚合、关联、组合）
  - [x] SubTask 11.3: 测试字段存储策略
  - [x] SubTask 11.4: 测试规则与对象类型约束
  - [x] SubTask 11.5: 测试跨对象指标引用
  - [x] SubTask 11.6: 测试计算函数

- [x] Task 12: 运行全部测试验证
  - [x] SubTask 12.1: 运行 `python meta/tests/run_all_tests.py`
  - [x] SubTask 12.2: 确认所有测试通过

# Task Dependencies

- [Task 3] depends on [Task 1]
- [Task 4] depends on [Task 1]
- [Task 5] depends on [Task 1, Task 2, Task 3]
- [Task 6] depends on [Task 2]
- [Task 7] depends on [Task 5]
- [Task 8] depends on [Task 1, Task 2, Task 3, Task 4, Task 5, Task 6]
- [Task 9] depends on [Task 5]
- [Task 10] depends on [Task 5, Task 6]
- [Task 11] depends on [Task 1-10]
- [Task 12] depends on [Task 11]
