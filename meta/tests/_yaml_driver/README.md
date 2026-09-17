# YAML 元模型驱动测试引擎 (Meta-Model Driven Test Engine)

> **版本**: v1.0 | **更新**: 2026-07-17 | **状态**: 活跃
>
> **核心价值**: 从 `meta/schemas/*.yaml` 自动推导测试用例, 每次新增/修改 yaml 时, **无需手写新测试** 即可获得覆盖。

---

## 一、设计动机

### 1.1 问题

- 当前 38 个 yaml schema, **几乎全部没有专属测试**
- 字段增减/类型变化时, 测试人员必须手动同步 case
- 极易出现"模型改了, 测试忘了跟" → 静默回归

### 1.2 解决

```
MetaRegistry
    │
    ├── loader.load_schemas()
    │   → Dict[str, MetaObject]
    │
    ├── discoverer.discover_all_constraints()
    │   → List[ConstraintSpec]  (38 yaml × N 字段 = 100+ cases)
    │
    └── pytest_plugin (参数化)
        → 每个 yaml 拆成独立 case
```

**新增 yaml → 立即自动获得**: 必填校验、唯一约束、默认值类型、层级父对象引用、删除策略目标、enum 值有效性。

---

## 二、目录结构

```
meta/tests/_yaml_driver/
├── __init__.py                          # 模块入口
├── README.md                            # 本文件
├── loader.py                            # 隔离的 MetaRegistry wrapper
├── discoverer.py                        # 推导 constraint spec
├── pytest_plugin.py                     # pytest 钩子 (meta_object fixture)
└── test_yaml_driven_constraints.py      # 主测试入口
```

---

## 三、运行方式

### 3.1 标准运行 (通过统一入口 test.py)

```bash
# 跑全部 yaml 驱动测试
python d:\\filework\\test.py --file meta/tests/_yaml_driver/test_yaml_driven_constraints.py

# 只跑指定对象
python d:\\filework\\test.py --file meta/tests/_yaml_driver/test_yaml_driven_constraints.py -- --yaml-driver-only=user,role,product

# 跳过指定对象
python d:\\filework\\test.py --file meta/tests/_yaml_driver/test_yaml_driven_constraints.py -- --yaml-driver-skip=audit_log
```

### 3.2 单独调试 (仅限本地, 不走统一入口)

```bash
pytest meta/tests/_yaml_driver/test_yaml_driven_constraints.py -v
```

---

## 四、推导规则 (v1.0)

### 4.1 对象级约束

| Constraint | 触发条件 | 严重度 |
|---|---|---|
| `TABLE_NAME_NOT_EMPTY` | 持久化对象 table_name 为空 | error |
| `PERSISTENT_OBJECT_HAS_PK` | 无 version 字段且无显式 PK | warning |
| `BUSINESS_KEY_EXISTS_FOR_BO` | 业务对象无 business_key | warning |
| `META_OBJECT_HAS_AT_LEAST_ONE_ACTION` | 任何对象无 action | warning |
| `HIERARCHY_PARENT_OBJECT_EXISTS` | parent_object 引用不存在 | error |
| `DELETION_POLICY_TARGET_EXISTS` | 删除策略引用不存在 | error |
| `DISPLAY_NAME_FIELD_DECLARED` | display_name_field 引用不存在 | error |

### 4.2 字段级约束

| Constraint | 触发条件 | 严重度 |
|---|---|---|
| `PERSISTENT_FIELD_HAS_DB_COLUMN` | storage=STORED 但 db_column 为空 | error |
| `REQUIRED_FIELD_DEFINED` | required=True 字段声明 | warning |
| `UNIQUE_FIELD_HAS_DB_INDEX` | unique 字段未在 indexes 中 | warning |
| `ENUM_FIELD_VALUES_VALID` | enum_values 不在 enum_type 中 | error |
| `DEFAULT_VALUE_TYPE_MATCHES` | default 值类型不符 | warning |

---

## 五、扩展点

### 5.1 新增约束类型

在 `discoverer.py` 的 `CONSTRAINT_TYPES` 集合中添加常量, 然后在 `_discover_*_constraints` 函数里实现推导逻辑。

### 5.2 接入 RLS 规则 / aspects

下一步可扩展:
- 扫描 `rls_rules/*.yaml` → 推导行级安全矩阵测试
- 扫描 `meta/schemas/aspects.yaml` → 推导 aspects 自动应用测试

### 5.3 工厂一致性检查

把 `meta/tests/factories/` 的 16 个工厂与 yaml 字段做交叉验证:
- 工厂 defaults 必须覆盖 yaml 全部 required 字段
- 工厂字段类型必须与 yaml 字段类型一致

---

## 六、与现有测试体系的关系

| 测试类型 | 入口 | 作用 |
|---|---|---|
| **YAML 元模型驱动** (本引擎) | `meta/tests/_yaml_driver/` | 推导 schema 级别的约束 |
| **后端 API 单元/集成** | `meta/tests/api/` | 测单个 API endpoint |
| **后端单元** | `meta/tests/test_*.py` | 测单个函数/类 |
| **E2E** | `e2e/` | 测端到端业务流 |
| **前端 vitest** | `src/**/__tests__/` | 测前端组件 |

---

## 七、CHANGELOG

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-07-17 | v1.0 | 初版: 4 个文件 (loader/discoverer/plugin/case), 推导 12 类约束 |