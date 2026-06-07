# Checklist

## 架构分析验证
- [x] Palantir Foundry Ontology 架构分析完整
- [x] SAP HANA CDS View 架构分析完整
- [x] 架构对比表格正确
- [x] 统一 VIEW/AGGREGATE/COMPOSITE 的理由清晰
- [x] VIRTUAL 类型的必要性说明完整

## 枚举定义
- [x] `ObjectType` 枚举定义正确（ENTITY / VIEW / VIRTUAL）
- [x] `FieldStorage` 枚举定义正确（STORED / VIRTUAL）
- [x] `FieldSource` 枚举定义正确（OWN / MAPPED / COMPUTED / DERIVED / AGGREGATED）

## 配置类定义
- [x] `ViewConfig` 配置类定义完整（sources, joins, group_by, aggregates, filters, sql_definition）
- [x] `VirtualConfig` 配置类定义完整（usage, source_type, lifecycle, serializable）
- [x] `MetricReference` 配置类定义完整（object_id, field_id, function_id, filter）
- [x] `ViewSource` 配置类定义完整（object_id, alias）
- [x] `ViewJoin` 配置类定义完整（type, source, target, on）
- [x] `ViewAggregate` 配置类定义完整（field_id, function, source_field, distinct）
- [x] `ViewFilter` 配置类定义完整（condition）

## MetaFunction 类
- [x] `MetaFunction` dataclass 定义正确
- [x] `MetaObject.functions` 字段已添加
- [x] `MetaObject.get_functions()` 方法已实现

## MetaField 扩展
- [x] `storage` 属性已添加，默认值为 STORED
- [x] `source` 属性已添加，默认值为 OWN
- [x] 派生相关属性已添加（derive_from_object, derive_from_field）
- [x] 聚合相关属性已添加（aggregate_function, aggregate_source_field）
- [x] 向后兼容属性保持有效（persistent, computed）

## MetaObject 扩展
- [x] `object_type` 属性已添加，默认值为 ENTITY
- [x] `view_config` 属性已添加
- [x] `virtual_config` 属性已添加
- [x] `base_objects` 属性已添加
- [x] 向后兼容属性保持有效（persistent, is_view, view_definition）

## MetaRule 扩展
- [x] `metric_refs` 属性已添加

## MetaRegistry 扩展
- [x] `get_objects_by_type()` 方法已实现
- [x] `get_functions()` 方法已实现

## YAML 加载器更新
- [x] 支持 `object_type` 字段解析
- [x] 支持 `view_config` 配置解析（sources, joins, group_by, aggregates, filters）
- [x] 支持 `virtual_config` 配置解析
- [x] 支持 `functions` 列表解析
- [x] 支持 `storage` 和 `source` 字段属性解析

## Schema 生成器更新
- [x] 根据 `object_type` 生成正确的 SQL（TABLE / VIEW）
- [x] 根据 `view_config` 生成正确的 SQL VIEW 定义
- [x] 根据 `storage` 属性正确处理字段列生成

## 规则执行器更新
- [x] 规则与对象类型的约束检查已实现
- [x] `metric_refs` 指标引用解析已实现
- [x] `MetaFunction` 执行已实现

## 字段存储策略验证
- [x] 字段级存储策略与对象类型的关系表正确
- [x] ENTITY 默认 storage=STORED，允许 OWN/MAPPED/COMPUTED/DERIVED
- [x] VIEW 默认 storage=VIRTUAL，允许 MAPPED/COMPUTED/AGGREGATED
- [x] VIRTUAL 默认 storage=VIRTUAL，允许 OWN/COMPUTED

## 规则约束矩阵验证
- [x] 规则-对象类型约束矩阵正确
- [x] MetaValidation: ENTITY ✅, VIEW ⚠️, VIRTUAL ✅
- [x] MetaConstraint: ENTITY ✅, VIEW ❌, VIRTUAL ❌
- [x] MetaComputation: ENTITY ✅, VIEW ❌, VIRTUAL ✅
- [x] MetaStateTransition: ENTITY ✅, VIEW ❌, VIRTUAL ❌
- [x] MetaTrigger: ENTITY ✅, VIEW ✅, VIRTUAL ✅
- [x] MetaDerivation: ENTITY ✅, VIEW ✅, VIRTUAL ❌

## 对象分层依赖验证
- [x] 对象分层依赖设计图正确
- [x] VIEW 可引用 ENTITY
- [x] VIRTUAL 可引用任意层
- [x] 规则可引用任意层级的对象和度量

## YAML 示例验证
- [x] ENTITY 对象示例完整（customer）
- [x] VIEW 聚合视图示例完整（sales_analysis）
- [x] VIEW 组合视图示例完整（product_detail）
- [x] VIRTUAL DTO 示例完整（order_create_dto）
- [x] 规则引用视图指标示例完整（order.credit_check）
- [x] 多层视图示例完整（monthly_sales）

## 测试验证
- [x] 对象类型定义测试通过
- [x] 视图配置测试通过
- [x] 字段存储策略测试通过
- [x] 规则与对象类型约束测试通过
- [x] 跨对象指标引用测试通过
- [x] 计算函数测试通过
- [x] 全部测试通过（`python meta/tests/run_all_tests.py`）
