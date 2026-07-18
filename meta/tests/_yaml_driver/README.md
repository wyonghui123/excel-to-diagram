# YAML 元模型驱动测试引擎 (Meta-Model Driven Test Engine)

> **版本**: v1.1 | **更新**: 2026-07-17 | **状态**: 活跃
>
> **核心价值**: 从 `meta/schemas/*.yaml` + `rls_rules/*.yaml` + `aspects.yaml` + `meta/tests/factories/*.py` 自动推导测试用例, 每次新增/修改资产时, **无需手写新测试** 即可获得覆盖。

---

## 一、设计动机

### 1.1 问题

- 当前 38 个 yaml schema, **几乎全部没有专属测试**
- 字段增减/类型变化时, 测试人员必须手动同步 case
- 极易出现"模型改了, 测试忘了跟" → 静默回归
- **rls_rules / aspects / factories** 与 yaml 之间的一致性也没有自动化保障

### 1.2 解决 (v1.1)

```
MetaRegistry + rls_rules/*.yaml + aspects.yaml + meta/tests/factories/*.py
    │
    ├── loader.load_schemas() / load_aspects() / load_rls_rules() / load_factories()
    │   → Dict[str, MetaObject] + aspects + rls + factories
    │
    ├── discoverer.discover_all_constraints()        # v1.0
    ├── discoverer.discover_v11_constraints()         # v1.1 (aspects/RLS/factory)
    │   → List[ConstraintSpec] (153 cases for current meta)
    │
    └── pytest_plugin (参数化)
        → 每个 yaml/spec 拆成独立 case
```

**新增 yaml → 立即自动获得**: 必填校验、唯一约束、默认值类型、层级父对象引用、删除策略目标、enum 值有效性、aspects 应用、RLS 覆盖、factory 一致性。

---

## 二、目录结构

```
meta/tests/_yaml_driver/
├── __init__.py                          # 模块入口 (v1.1)
├── README.md                            # 本文件 (v1.1)
├── loader.py                            # 隔离的 MetaRegistry wrapper
│                                        # v1.1: +load_aspects/rls_rules/factories
├── discoverer.py                        # 推导 constraint spec
│                                        # v1.1: +discover_aspect/rls/factory/v11_constraints
├── pytest_plugin.py                     # pytest 钩子 (meta_object fixture)
│                                        # v1.1: +v11_spec fixture & parametrize hook
├── conftest.py                          # v1.1 新增: v11 fixtures (aspects/rls/factories/v11_specs)
└── test_yaml_driven_constraints.py      # 主测试入口
                                         # v1.1: +9 v11 test functions + global summary
```

---

## 三、运行方式

### 3.1 标准运行 (通过统一入口 test.py)

```bash
# 跑全部 yaml 驱动测试 (含 v1.0 + v1.1)
python d:\\filework\\test.py --file meta/tests/_yaml_driver/test_yaml_driven_constraints.py

# 只跑指定对象
python d:\\filework\\test.py --file meta/tests/_yaml_driver/test_yaml_driven_constraints.py -- --yaml-driver-only=user,role,product

# 跳过指定对象
python d:\\filework\\test.py --file meta/tests/_yaml_driver/test_yaml_driven_constraints.py -- --yaml-driver-skip=audit_log
```

### 3.2 Strict 模式 (v1.1 violation 默认 tolerant, 升级 fail)

```bash
# 默认: tolerant (v1.1 violations 仅打印, 不 fail)
# 升级 strict (任何 v1.1 violation 即 fail):
YAML_DRIVER_V11_STRICT=1 pytest meta/tests/_yaml_driver/test_yaml_driven_constraints.py
```

### 3.3 单独调试 (仅限本地)

```bash
pytest meta/tests/_yaml_driver/test_yaml_driven_constraints.py -v -s
```

---

## 四、推导规则

### 4.1 v1.0 - 对象级约束

| Constraint | 触发条件 | 严重度 |
|---|---|---|
| `TABLE_NAME_NOT_EMPTY` | 持久化对象 table_name 为空 | error |
| `PERSISTENT_OBJECT_HAS_PK` | 无 version 字段且无显式 PK | warning |
| `BUSINESS_KEY_EXISTS_FOR_BO` | 业务对象无 business_key | warning |
| `META_OBJECT_HAS_AT_LEAST_ONE_ACTION` | 任何对象无 action | warning |
| `HIERARCHY_PARENT_OBJECT_EXISTS` | parent_object 引用不存在 | error |
| `DELETION_POLICY_TARGET_EXISTS` | 删除策略引用不存在 | error |
| `DISPLAY_NAME_FIELD_DECLARED` | display_name_field 引用不存在 | error |

### 4.2 v1.0 - 字段级约束

| Constraint | 触发条件 | 严重度 |
|---|---|---|
| `PERSISTENT_FIELD_HAS_DB_COLUMN` | storage=STORED 但 db_column 为空 | error |
| `REQUIRED_FIELD_DEFINED` | required=True 字段声明 | warning |
| `UNIQUE_FIELD_HAS_DB_INDEX` | unique 字段未在 indexes 中 | warning |
| `ENUM_FIELD_VALUES_VALID` | enum_values 不在 enum_type 中 | error |
| `DEFAULT_VALUE_TYPE_MATCHES` | default 值类型不符 | warning |

### 4.3 v1.1 - Aspects 约束 (3 类)

| Constraint | 触发条件 | 严重度 |
|---|---|---|
| `ASPECT_REFERENCED_MUST_EXIST` | object 引用的 aspect 不在 aspects.yaml 中 | error |
| `ASPECT_FIELDS_APPLIED` | 使用 audit_aspect 但缺 created_at 等字段 | warning |
| `AUDIT_ASPECT_HAS_AUDIT_CONFIG` | 使用 audit_aspect 但缺 top-level `audit` 配置 | warning |

**推导逻辑**: 双通道聚合
- 通道1: 字段 `included_from` 标签 (aspect 字段合并后)
- 通道2: `obj.aspects` 顶层属性 (yaml 引用但字段未合并)

### 4.4 v1.1 - RLS 约束 (3 类)

| Constraint | 触发条件 | 严重度 |
|---|---|---|
| `RLS_FILE_EXISTS_FOR_OBJECT` | 持久化对象无 `rls_rules/{obj}.yaml` | warning |
| `RLS_ENTITY_FIELD_VALID` | rls_rules 文件声明的 entity 在 schemas 中不存在 | error |
| `RLS_APPLIES_TO_ROLE_VALID` | rls_rules.applies_to 字段引用的 role 不存在 | warning |

### 4.5 v1.1 - Factory 一致性约束 (3 类)

| Constraint | 触发条件 | 严重度 |
|---|---|---|
| `FACTORY_OBJECT_TYPE_REGISTERED` | Factory `_OBJECT_TYPE` 在 schemas 中找不到对应对象 | error / info (白名单) |
| `FACTORY_DEFAULTS_NOT_EMPTY` | Factory 未提供 `_DEFAULTS` 或 `_base_defaults()` | warning |
| `FACTORY_DEFAULTS_COVER_REQUIRED` | Factory defaults 缺少 yaml 必填字段 | error |

### 4.6 v1.1 P2 - unique_id 确定性守护 (1 类)

| Constraint | 触发条件 | 严重度 |
|---|---|---|
| `FACTORY_UNIQUE_ID_DETERMINISTIC` | `_base.py` 中 `unique_id()` 函数存在性 + counter + lock 模式检测 | error / warning / info |

**设计动机**: 防止 `test_unique_id_unique` pre-existing bug (同毫秒重复 ID) 复发.
通过 **AST 静态分析** 检测关键安全模式 (process-local counter, threading.Lock).
每次跑 v1.1 都会验证 unique_id() 仍然安全.

**排除自动生成字段**: PK `id` + 审计字段 (`created_at`/`updated_at`/`created_by`/`updated_by`)

**v1.1 白名单机制** (避免误报):

| 白名单常量 | 内容 | 说明 |
|---|---|---|
| `FACTORY_UNMODELED_TYPES` | `import_export_task`, `subscription`, `webhook` | 这些 factory 对应 change_subscription 内部子对象, 没有独立 yaml |
| `RLS_UNMODELED_ENTITIES` | `order` | `rls_rules/order.yaml` 已写, 但 order schema 还未建模 |

白名单内违规降级为 `info` (positive), 不计入 strict mode 的 error 数。

---

## 五、输出策略: positive-or-negative

v1.1 discoverer 对每个对象 + 每个约束类型, **最多输出 1 条 spec**:
- **违规**: severity=error/warning → negative spec
- **健康**: severity=info → positive spec (证明规则跑过)

pytest 通过 `pytest_generate_tests` 把每条 spec 展开为独立 case, parametrize id 为 `{obj}__{field}__{constraint}`。这样:
- **违规** → case 失败 (默认 tolerant, 仅打印) / 失败 (strict mode, fail)
- **健康** → case 通过

---

## 六、tolerant vs strict 模式

| 模式 | 触发 | 行为 |
|---|---|---|
| **tolerant (默认)** | 无环境变量 | 违规 spec 仅 print `[V11-VIOLATION]`, case pass |
| **strict** | `YAML_DRIVER_V11_STRICT=1` | 任何 v1.1 违规 spec 都 fail |

**为何默认 tolerant**: v1.1 范围宽, 当前项目存在 11 个真实 error (factory defaults 缺字段) + 26 个 warning (无 RLS 规则) + 3 个 factory 未注册 schema。这些是**真实工程问题**而非测试引擎 bug, 不应阻塞现有测试通过。strict mode 用于 CI 严格门禁。

---

## 七、当前实测统计 (commit 2026-07-17)

| 类型 | 数量 |
|---|---|
| 对象总数 | 39 个 yaml schema |
| Aspects 数 | 4 (audit_aspect, hierarchy_aspect, naming_aspect, owner_aspect) |
| RLS 文件数 | 10 (rls_rules/*.yaml) |
| Factory 数 | 14 (meta/tests/factories/*.py) |
| **v1.0 测试 case** | 249 (216 passed + 33 skipped) |
| **v1.1 测试 case** | 124 (positive info spec) + 11 (negative error) + 26 (negative warning) |
| **v1.1 真实违规 (当前)** | 11 error + 26 warning |

### 7.1 当前 v1.1 发现的真实工程问题

```
[error] FACTORY_DEFAULTS_COVER_REQUIRED x 8
  - AnnotationFactory missing [category, target_id, target_type]
  - AuditLogFactory missing [log_category, log_level]
  - BusinessObjectFactory missing [version_id]
  - DomainFactory missing [version_id]
  - ProductFactory missing [visibility]
  - RelationshipFactory missing [source_bo_id, target_bo_id, version_id]
  - VersionFactory missing [product_id]

[error] FACTORY_OBJECT_TYPE_REGISTERED x 3
  - ImportExportFactory -> import_export_task (no schema)
  - SubscriptionFactory -> subscription (no schema)
  - WebhookFactory -> webhook (no schema)

[error] RLS_ENTITY_FIELD_VALID x 1
  - rls_rules/order.yaml entity='order' (no matching schema)

[warning] RLS_FILE_EXISTS_FOR_OBJECT x 26
  - 26 个持久化对象无 rls_rules/{obj}.yaml (业务范围未覆盖)
```

---

## 八、扩展点

### 8.1 新增 v1.1 约束类型

1. 在 `discoverer.py` 的 `CONSTRAINT_TYPES` 集合中添加常量
2. 在对应 `discover_<category>_constraints()` 函数中实现 positive-or-negative 推导
3. 在 `_yaml_driver/conftest.py` 中加 fixture (如有需要)
4. 在 `pytest_plugin.py` 的 `_V11_CONSTRAINT_TYPES` 中加入
5. 在 `test_yaml_driven_constraints.py` 中加对应 `test_v11_<name>(v11_spec)` 函数

### 8.2 后续可扩展方向

- ENUM 类型一致性 (yaml enum_type 与 factory enum 默认值)
- INDEX 推导 (yaml indexes 与 SQL DDL 一致性)
- ACTION 完整性 (object.actions 与 api endpoint 路由)
- VERSION 兼容性 (yaml version 与 DB schema migration)

---

## 九、与现有测试体系的关系

| 测试类型 | 入口 | 作用 |
|---|---|---|
| **YAML 元模型驱动** (本引擎) | `meta/tests/_yaml_driver/` | 推导 schema + aspects + rls + factory 级别的约束 |
| **后端 API 单元/集成** | `meta/tests/api/` | 测单个 API endpoint |
| **后端单元** | `meta/tests/test_*.py` | 测单个函数/类 |
| **E2E** | `e2e/` | 测端到端业务流 |
| **前端 vitest** | `src/**/__tests__/` | 测前端组件 |

---

## 十、CHANGELOG

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-07-17 | v1.0 | 初版: 4 个文件 (loader/discoverer/plugin/case), 推导 12 类约束 |
| 2026-07-17 | v1.1 | 扩展 9 类新约束 (3 Aspects + 3 RLS + 3 Factory), 引入 positive-or-negative 输出策略 + tolerant/strict 双模式 |
| 2026-07-17 | v1.1.1 | 修复 11 个真实工程问题 (8 个 factory defaults 缺字段 + 3 个未建模 factory); 加白名单机制 (`FACTORY_UNMODELED_TYPES`/`RLS_UNMODELED_ENTITIES`); 新增 `discover_test_coverage.py` 工具 |
| 2026-07-17 | v1.1.2 | P2: 加 `FACTORY_UNIQUE_ID_DETERMINISTIC` 约束 (AST 静态分析 unique_id 的 counter+lock 模式); `test_unique_id_robustness.py` 加 `@pytest.mark.slow` + `factories/tests/conftest.py` 默认 skip slow (`SKIP_SLOW=0` 强制跑) |

## 十一、配套工具

### discover_test_coverage.py

**作用**: 扫描每个 yaml schema 在 test_*.py 文件中的覆盖度, 生成覆盖矩阵报告。

```bash
# 标准运行 (输出 .trae/coverage/test_coverage.{md,json})
python meta/tests/_yaml_driver/discover_test_coverage.py

# CI 模式 (无覆盖 schema 时 exit 1)
python meta/tests/_yaml_driver/discover_test_coverage.py --fail-on-none

# 自定义目录
python meta/tests/_yaml_driver/discover_test_coverage.py \
    --schema-dir meta/schemas \
    --test-pattern "meta/tests/test_*.py" \
    --output-dir .trae/coverage
```

**3 个覆盖维度**:
1. **schema_id 命中**: `user` 等 schema_id 在测试文件中出现 (字符串字面量 + API 路径)
2. **table_name 命中**: `users` 等 table_name 在测试文件中出现
3. **class 命中**: 测试类名含 schema 名 (如 `TestUser`, `TestUserAuth`)

**覆盖度判定**: covered (3 维全命中) / partial (1-2 维) / none (0 维)

**当前报告 (2026-07-17)**: 42 schema / 52% covered / 42% partial / 4% none (2 个无覆盖: `ai_async_task`, `new_object`)

### deep_coverage_analysis.py (P2 综合分析工具)

**作用**: 6 维度综合分析每个 schema 的覆盖度 + 风险评级 + 改进建议

```bash
python meta/tests/_yaml_driver/deep_coverage_analysis.py
# 输出: .trae/coverage/deep_coverage.json
```

**6 维度**:
1. **yaml-driven** (30 分): v1.0/v1.1 推导的自动 case 数
2. **手写测试** (25 分): test_*.py 中严格命中的文件数
3. **factory** (15 分): 是否有对应 factory
4. **rls** (10 分): 是否有 rls_rules 规则
5. **aspects** (10 分): 应用的 aspect 数
6. **frontend** (10 分): 前端 .vue/.ts 文件引用

**风险等级**: HIGH (0-39) / MEDIUM (40-69) / LOW (70-100)

**当前报告 (2026-07-17)**:
- 38 schema / 22 HIGH / 9 MEDIUM / 7 LOW
- 平均分 ~43/100
- 主要风险: Factory 65% 缺失 + RLS 76% 缺失
- 工厂采用率 (419 个 test_*.py): 3% use Factory.create() — 行业基准 30-50%