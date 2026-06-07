# 统一BO元数据模型架构升级 Spec

## Why

当前系统的枚举类型(enum)、维度结构(dimension)等元数据分散管理，字段与枚举的关联关系弱（仅存储字符串ID），无法支持复杂的业务场景（如条件过滤、级联更新、多语言JOIN）。同时缺少统一的 BO 类型分类体系（事务型/主数据型/分析型/配置型），导致无法针对不同类型的 BO 应用最佳实践模板。

本 Spec 旨在建立**企业级统一BO元数据模型架构**，实现：

1. **配置/枚举型BO**采用混合适配器模式（复用必要能力 + 专用高速缓存）
2. **增强的字段-枚举关联**（结构化 EnumReference 替代简单字符串）
3. **完整的四大BO分类体系**（事务型/主数据型/分析型/配置型）
4. **统一的行为配置模板**（根据BO类型自动应用最佳实践）

## What Changes

### 核心新增

- 新增 `BusinessObjectCategory` 枚举（TRANSACTIONAL / MASTER\_DATA / ANALYTICAL / CONFIGURATION）
- 新增 `BoSubCategory` 枚举（DOCUMENT / PARTY / PRODUCT / ENUMERATION 等16种子类别）
- 新增 `BoCategoryConfig` 数据类（行为配置模板，20+属性）
- 新增 `EnumReference` 数据类（替代简单字符串的 enum\_type\_ref）
- 新增 `DimensionReference` 数据类（字段引用主数据BO）
- 新增 `FieldDependency` 数据类（字段间依赖声明）
- 新增 `EnhancedMetaField` 类（继承 MetaField，扩展关联能力）
- 新增 `IEnumProvider` 接口（高速读取通道）
- 新增 `IEnumAdmin` 接口（安全写入通道）
- 新增 `CachedEnumProvider` 实现（专用缓存层）
- 新增 `SecureEnumAdmin` 实现（审计+权限+缓存失效）
- 新增 `EnumCacheManager`（多级缓存管理器）
- 新增 `EnumRepository`（统一数据访问层）

### 扩展修改

- 扩展 `MetaObject` 添加 `bo_category`, `bo_sub_category`, `category_config` 字段
- 重构 `enum_api.py` 使用新的适配器模式
- 数据库迁移：为 `business_objects` 表添加分类字段

### 不变更

- 现有 `enum_types` 和 `enum_values` 表结构保持不变（向后兼容）
- 现有 API 端点保持不变（新增端点不影响旧接口）
- 现有 YAML Schema 保持兼容

## Impact

- Affected specs: enum-value-management, p0-meta-model-core-enhancement, metadata-driven-refactoring
- Affected code:
  - `meta/core/models.py` - 新增 BO 分类体系和增强字段模型
  - `meta/api/enum_api.py` - 重构为适配器模式
  - `meta/schemas/business_object.yaml` - 添加 bo\_category 配置示例
  - `meta/tools/sync_schema.py` - 支持新字段的 DDL 生成
  - 新建 `meta/core/enums/` 目录（接口、DTO、Repository、实现类）

***

## ADDED Requirements

### Requirement: BO Classification System

系统应提供统一的业务对象分类体系，支持四种核心BO类型及其子类别。

#### Scenario: 自动应用行为模板

- **GIVEN** 创建新BO时指定 bo\_category = "transactional"
- **WHEN** BO初始化完成
- **THEN** 自动应用 BoCategoryConfig 模板：audit\_level="detailed", state\_machine=True, soft\_delete=True

#### Scenario: 启发式推断现有BO分类

- **WHEN** 系统启动或执行迁移脚本
- **THEN** 基于名称规则自动推断现有BO的分类（如包含"订单"→transactional）

***

### Requirement: Enhanced Field-Enum Association

系统应支持结构化的字段-枚举关联，替代简单的字符串引用。

#### Scenario: 条件过滤枚举选项

- **GIVEN** 订单状态字段配置了 filter\_by\_dimension（根据订单类型过滤）
- **WHEN** 用户在销售订单表单中打开状态下拉框
- **THEN** 只显示 SALES\_ORDER 相关的状态选项（pending, confirmed, shipping...）
- **AND** 在退货订单表单中只显示 RETURN\_ORDER 相关选项

#### Scenario: 枚举值多语言自动JOIN

- **GIVEN** 字段配置了 enum\_reference.i18n\_join\_fields = \["name", "name\_en"]
- **WHEN** 查询业务数据列表
- **THEN** 自动从 enum\_values 表 JOIN 多语言字段，无需手动编写SQL

#### Scenario: 枚举绑定强度校验

- **GIVEN** 字段的 enum\_reference.binding\_strength = "strict"
- **WHEN** 用户提交表单时该字段的值不在有效枚举列表中
- **THEN** 校验失败，提示"值不在允许的枚举列表中"

***

### Requirement: Dimension Reference for Master Data Fields

系统应支持字段引用主数据BO，提供Search Help和冗余策略配置。

#### Scenario: 客户字段引用主数据BO

- **GIVEN** 订单表的 customer\_id 字段配置了 dimension\_reference.target\_bo = "customer"
- **WHEN** 用户在订单表单中点击客户选择框
- **THEN** 弹出客户搜索帮助框，支持按编码/名称搜索
- **AND** 选择后自动填充 customer\_name 冗余字段

#### Scenario: 维度引用冗余同步

- **GIVEN** dimension\_reference.redundancy.strategy = "denormalized" 且 sync\_on\_write = true
- **WHEN** 客户名称发生变更
- **THEN** 所有引用该客户的订单记录自动更新冗余的客户名称字段

***

### Requirement: Dual-Channel Enum Access Pattern

系统应采用双通道设计分离高速读取和安全写入。

#### Scenario: 高速读取通道（前端渲染）

- **WHEN** 页面加载需要渲染100个下拉框（每个都引用不同枚举）
- **THEN** 所有请求在 < 5ms 内返回（命中L1缓存 < 0.1ms）
- **AND** 不经过权限检查（枚举是全局共享的）

#### Scenario: 安全写入通道（管理员操作）

- **WHEN** 管理员通过管理界面修改枚举值
- **THEN** 必须经过认证授权 → 数据校验 → 审计日志 → 缓存失效 全流程
- **AND** 操作记录到审计日志表（包含操作人、时间、新旧数据）

#### Scenario: 缓存即时失效

- **GIVEN** 管理员修改了 order\_status 枚举的一个值名称
- **WHEN** 写入操作成功完成
- **THEN** 该枚举的所有缓存立即失效
- **AND** 下次读取时从数据库加载最新数据

***

### Requirement: Multi-Level Cache for Enums

系统应提供专用的多级缓存机制，优化枚举的高频读取性能。

#### Scenario: L1进程内缓存命中

- **GIVEN** 某枚举类型已被加载到 L1 缓存
- **WHEN** 业务代码请求该枚举的值列表
- **THEN** 直接从内存字典返回（< 0.1ms），不访问数据库

#### Scenario: 缓存预热

- **WHEN** 系统启动完成
- **THEN** 自动预加载所有活跃枚举类型到 L1 缓存
- **AND** 输出预热统计信息（加载数量、耗时）

#### Scenario: TTL兜底失效

- **GIVEN** 由于异常情况事件驱动失效未触发
- **WHEN** 缓存条目超过 TTL（默认5分钟）
- **THEN** 下次访问时强制从数据库重新加载

***

### Requirement: Field Dependency Declaration

系统应支持声明式的字段依赖关系，用于UI联动和权限控制。

#### Scenario: 字段可见性依赖

- **GIVEN** 折扣率字段配置了 depends\_on\_field = "customer\_level"，条件为 VIP/SVIP 时可见
- **WHEN** 用户选择的客户等级为普通用户
- **THEN** 折扣率字段隐藏且值为0

#### Scenario: 字段必填性依赖

- **GIVEN** 原因字段配置了 depends\_on\_field = "status"，当 status=REJECTED 时必填
- **WHEN** 用户将状态改为已拒绝但未填写原因
- **THEN** 表单校验失败，提示"拒绝原因必填"

***

## MODIFIED Requirements

### Requirement: MetaObject Model Enhancement

扩展 MetaObject 元模型，添加 BO 分类支持。

**修改内容**：

```python
@dataclass
class MetaObject:
    # ... 原有字段 ...
    
    # ── 新增：BO分类字段 ──
    bo_category: BusinessObjectCategory = BusinessObjectCategory.MASTER_DATA
    bo_sub_category: Optional[BoSubCategory] = None
    category_config: Optional[BoCategoryConfig] = None  # 运行时自动填充
    
    def __post_init__(self):
        """初始化时自动应用分类模板"""
        if self.category_config is None:
            self.category_config = BO_CATEGORY_TEMPLATES.get(
                self.bo_category,
                BO_CATEGORY_TEMPLATES[BusinessObjectCategory.MASTER_DATA]
            )
```

***

### Requirement: Enum API Refactoring

重构枚举 API 层，使用新的适配器模式。

**修改内容**：

- 保留所有现有 API 端点（向后兼容）
- 新增高速端点：`GET /api/v1/enums/{type}/options`
- 内部实现切换为 CachedEnumProvider / SecureEnumAdmin

***

## REMOVED Requirements

无（本次为增量演进，不删除现有功能）

***

## Technical Design

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                  Consumer Layer                             │
│  DynamicForm │ MetaTable │ EnumSelect │ RuleEngine         │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│              Enum Metadata Adapter                          │
│                                                              │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │ IEnumProvider     │  │ IEnumAdmin       │                │
│  │ (High-Speed Read) │  │ (Secure Write)   │                │
│  └────────┬──────────┘  └────────┬─────────┘                │
│           │                     │                           │
│           ▼                     ▼                           │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │ CachedEnumProv.  │  │ SecureEnumAdmin  │                │
│  │ +Cache Manager   │  │ +Audit Interceptor│               │
│  │ +Enum Repository │  │ +Auth Checker     │               │
│  └────────┬──────────┘  └────────┬─────────┘                │
│           └────────┬─────────────┘                         │
│                    ▼                                        │
│        ┌──────────────────┐                                │
│        │  Enum Repository │  (Unified Data Access)          │
│        └────────┬─────────┘                                │
│                 ▼                                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Selective Reuse of BO Infrastructure    │   │
│  │  [✅] AuditInterceptor  [✅] AuthChecker             │   │
│  │  [✅] APIHandler        [✅] Validator              │   │
│  │  [❌] DataPermission    [❌] SoftDelete             │   │
│  │  [❌] ImportExport      [❌] DerivationEngine       │   │
│  └─────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                    Storage Layer                              │
│  enum_types table │ enum_values table │ SQLite/PostgreSQL    │
└─────────────────────────────────────────────────────────────┘
```

### Data Model Extension

#### business\_objects 表新增字段

```sql
-- Phase 1 迁移脚本
ALTER TABLE business_objects ADD COLUMN IF NOT EXISTS bo_category VARCHAR(20) DEFAULT 'master_data';
ALTER TABLE business_objects ADD COLUMN IF NOT EXISTS bo_sub_category VARCHAR(30);
ALTER TABLE business_objects ADD COLUMN IF NOT EXISTS category_config JSONB;

-- 启发式推断分类
UPDATE business_objects SET 
  bo_category = CASE 
    WHEN name LIKE '%订单%' OR name LIKE '%审批%' THEN 'transactional'
    WHEN name LIKE '%统计%' OR name LIKE '%报表%' THEN 'analytical'
    WHEN name LIKE '%枚举%' OR name LIKE '%参数%' THEN 'configuration'
    ELSE 'master_data'
  END;

-- 创建索引
CREATE INDEX idx_business_objects_bo_category ON business_objects(bo_category);
```

#### field\_enum\_references 表（可选高性能场景）

```sql
CREATE TABLE IF NOT EXISTS field_enum_references (
  id BIGSERIAL PRIMARY KEY,
  field_id INTEGER NOT NULL REFERENCES bo_fields(id),
  enum_type_id VARCHAR(50) NOT NULL REFERENCES enum_types(id),
  binding_strength VARCHAR(20) DEFAULT 'strict',
  filter_by_dimension JSONB,
  cascade_update BOOLEAN DEFAULT FALSE,
  i18n_join_fields JSONB DEFAULT '["name", "name_en"]',
  default_value_code VARCHAR(50),
  display_format VARCHAR(100) DEFAULT '{name}',
  sort_by VARCHAR(20) DEFAULT 'sort_order',
  value_filter JSONB,
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(field_id)
);
```

### Interface Definitions

#### IEnumProvider (High-Speed Read Channel)

```python
class IEnumProvider(ABC):
    """
    设计约束：
    - 所有方法 < 5ms 返回（缓存命中 < 1ms）
    - 不涉及写操作
    - 不涉及权限检查
    """
    
    @abstractmethod
    async def get_values(self, enum_type_id: str, include_inactive=False, **filters) -> List[EnumValueDTO]:
        """获取枚举值列表"""
        ...
    
    @abstractmethod
    async def resolve_code_to_name(self, enum_type_id: str, code: str, locale="zh") -> str:
        """编码→名称快速解析（最高频操作）"""
        ...
    
    @abstractmethod
    async def get_select_options(self, enum_type_id: str, locale="zh", **filters) -> List[EnumSelectOption]:
        """生成前端Select组件选项"""
        ...
    
    @abstractmethod
    async def is_valid_value(self, enum_type_id: str, code: str) -> bool:
        """校验枚举值有效性"""
        ...
```

#### IEnumAdmin (Secure Write Channel)

```python
class IEnumAdmin(ABC):
    """
    设计约束：
    - 所有方法必须经过认证授权
    - 所有写操作必须记录审计日志
    - 写入后自动失效相关缓存
    """
    
    @abstractmethod
    async def create_type(self, data: dict, user: UserContext) -> EnumTypeDTO:
        """创建枚举类型"""
        ...
    
    @abstractmethod
    async def update_value(self, value_id: int, data: dict, user: UserContext) -> EnumValueDTO:
        """更新枚举值"""
        ...
    
    @abstractmethod
    async def batch_update_sort_order(self, enum_type_id: str, items: list, user: UserContext) -> bool:
        """批量更新排序"""
        ...
```

### Cache Architecture

```python
class EnumCacheManager:
    """
    多级缓存管理器
    
    策略：
    - L1: 进程内字典 (dict) → 命中率预期 >99%
    - L2: 可选 Redis → 跨实例共享
    
    失效：
    - 主要: 事件驱动（管理员操作后主动清除）
    - 兜底: TTL 5分钟
    """
    
    def __init__(self):
        self._l1_cache: Dict[str, CacheEntry] = {}
        self.ttl_seconds = 300  # 5分钟TTL兜底
    
    async def get_or_load(self, enum_type_id: str, loader: Callable):
        """获取或加载缓存"""
        cache_key = f"{enum_type_id}:all"
        
        # L1 查找
        entry = self._l1_cache.get(cache_key)
        if entry and not entry.is_expired():
            return entry.data  # < 0.1ms
        
        # 未命中，加载数据
        data = await loader(enum_type_id)
        self._l1_cache[cache_key] = CacheEntry(data, ttl=self.ttl_seconds)
        return data  # < 5ms 首次
    
    async def invalidate(self, enum_type_id: str):
        """事件驱动失效"""
        keys_to_remove = [k for k in self._l1_cache.keys() 
                         if k.startswith(f"{enum_type_id}:")]
        for key in keys_to_remove:
            del self._l1_cache[key]
```

### YAML Configuration Example

```yaml
# 示例：销售订单 BO（事务型）
id: sales_order
name: 销售订单
bo_category: transactional           # ← BO分类
bo_sub_category: document
table_name: sales_orders

fields:
  # 枚举引用字段（增强版）
  - id: status
    name: 订单状态
    type: string
    required: true
    enum_reference:                   # ← 结构化配置（替代 enum_type_ref: string）
      enum_type_id: order_status
      binding_strength: strict
      filter_by_dimension:            # 条件过滤
        field: order_type
        mapping:
          SALES_ORDER: [pending, confirmed, shipping, completed]
          RETURN_ORDER: [pending_return, returned]
      cascade_update: false
      i18n_join_fields: [name, name_en]
      default_value_code: pending
      sort_by: sort_order

  # 维度引用字段（引用主数据BO）
  - id: customer_id
    name: 客户
    type: integer
    required: true
    dimension_reference:              # ← 维度引用
      target_bo: customer
      reference_type: foreign_key
      display_field: customer_name
      code_field: customer_code
      search_help:
        enabled: true
        min_length: 1
      redundancy:
        strategy: denormalized
        stored_field: customer_name
        sync_on_write: true
      on_delete: restrict

  # 字段依赖示例
  - id: discount_rate
    name: 折扣率
    type: float
    dependencies:                    # ← 字段依赖
      - depends_on_field: customer_level
        dependency_type: visibility
        condition_expression: "{customer_level} in ['VIP', 'SVIP']"
        when_true:
          visible: true
        when_false:
          visible: false
          value: 0
```

***

## Migration Strategy

### Phase 1: Foundation (Week 1-2)

**目标**: 建立 BO 分类基础设施

**交付物**:

- [ ] 在 `models.py` 添加 `BusinessObjectCategory`, `BoSubCategory`, `BoCategoryConfig`
- [ ] 扩展 `MetaObject` 添加分类字段
- [ ] 创建数据库迁移脚本（ALTER TABLE 添加列 + 启发式推断）
- [ ] 编写单元测试验证向后兼容性

**验收标准**:

- ✅ 现有 100% BO 可正常加载（新字段有默认值）
- ✅ 新建 BO 可指定 bo\_category 并自动应用行为模板

### Phase 2: Field Enhancement (Week 3-4)

**目标**: 增强字段级元数据

**交付物**:

- [ ] 实现 `EnumReference`, `DimensionReference`, `FieldDependency` 数据类
- [ ] 实现 `EnhancedMetaField` 继承 `MetaField`
- [ ] 更新 YAML Loader 支持新语法解析
- [ ] 创建 `field_enum_references` 表（可选）

**验收标准**:

- ✅ 新建 BO 可用增强语法定义字段
- ✅ 旧 BO 向后兼容（新字段有默认值）

### Phase 3: Adapter Implementation (Week 5-6)

**目标**: 实现混合适配器模式

**交付物**:

- [ ] 定义 `IEnumProvider`, `IEnumAdmin` 接口
- [ ] 实现 `EnumRepository`（统一数据访问层）
- [ ] 实现 `CachedEnumProvider`（高速读取 + L1缓存）
- [ ] 实现 `SecureEnumAdmin`（安全写入 + 审计 + 权限）
- [ ] 实现 `EnumCacheManager`（多级缓存管理器）
- [ ] 重构 `enum_api.py` 使用新适配器

**验收标准**:

- ✅ 高速读取 P99 < 5ms（缓存命中 < 1ms）
- ✅ 写入操作完整记录审计日志
- ✅ 写入后缓存即时失效

### Phase 4: Tooling & Integration (Week 7-8)

**目标**: 工具链集成和数据迁移

**背景说明（重要）**：

> 本Phase需要与\*\*混合组件策略（Hybrid Component Strategy）\*\*协同执行。
> 根据[混合组件策略Spec](../hybrid-component-strategy/spec.md)，前端UI组件分为两类：
>
> - **B类业务组件（保持自建）**：EnumSelect、MetaTable、FilterBar等
> - **A类基础组件（EP替换）**：AppSelect、AppInput、AppButton等
>
> 本Phase的UI适配工作需要同时覆盖这两类组件的数据层优化。

**交付物**:

#### 4.1 后端工具链

- [ ] 开发 BO 分类向导 UI
- [ ] 开发字段关联配置 UI（可视化配置枚举/维度引用）
- [ ] 迁移现有 BO 数据（启发式分类）

#### 4.2 前端B类组件数据层优化（EnumSelect等）

- [ ] 更新 `src/services/enumService.js` 支持新的 `/api/v1/enums/{type}/options` 高速接口
- [ ] 优化 `EnumSelect.vue` 组件**内部数据获取逻辑**切换到新接口
  - ⚠️ **注意**：EnumSelect是**B类业务组件，保持自建实现不变**
  - ✅ 仅优化其数据源：从旧API → 新IEnumProvider高速通道
  - ✅ 保持637行业务逻辑（键盘导航、ARIA、分组、搜索、多选）全部保留
- [ ] 验证 EnumSelect 性能提升（目标：枚举加载 < 100ms）

#### 4.3 前端A类组件EP迁移 + 枚举对接（AppSelect等）

- [ ] 改造 `AppSelect.vue` 为 el-select 适配层（参考混合策略Phase 2）
- [ ] 实现 AppSelect 的枚举数据供给模式：
  ```vue
  <!-- AppSelect（A类适配层）使用新枚举接口示例 -->
  <script setup>
  import { getEnumOptions } from '@/services/enumService' // 高速接口

  const enumOptions = ref([])
  onMounted(async () => {
    if (props.enumTypeId) {
      // 调用统一BO模型的 IEnumProvider：P99 < 5ms
      enumOptions.value = await getEnumOptions(props.enumTypeId)
    }
  })
  </script>
  ```
- [ ] 确保 AppSelect（el-select）与 EnumSelect（自建）在视觉上一致（YonDesign橙色主题）

#### 4.4 性能测试与优化

- [ ] 编写压测脚本验证枚举查询 P99 < 5ms
- [ ] 监控缓存命中率（目标 > 99%）
- [ ] 对比优化前后前端渲染性能（EnumSelect/AppSelect）
- [ ] 生成性能测试报告

**验收标准**:

- ✅ 团队可独立完成 BO 创建和配置
- ✅ 现有 BO 全部完成分类迁移
- ✅ 枚举查询性能达标（P99 < 5ms）
- ✅ EnumSelect（B类）功能完全正常，性能提升明显
- ✅ AppSelect（A类）成功改造为el-select且枚举数据正确显示
- ✅ 两类组件视觉风格统一（YonDesign橙色主题）

### Phase 4.1: UI Component Integration Strategy (Detailed)

> 📅 **新增章节** - 2026-05-10
> 📝 **结合混合组件策略细化**

#### 4.1.1 Component Classification Matrix

| 组件类型               | 混合策略分类         | 统一BO模型角色          | Phase 4任务  | 改造范围      |
| ------------------ | -------------- | ----------------- | ---------- | --------- |
| **EnumSelect**     | B类（保持自建）       | 核心业务组件，直接消费枚举API  | Task 16a   | 仅数据层优化    |
| **EnumSearchHelp** | B类（保持自建）       | 搜索帮助弹窗，消费枚举+维度API | Task 16a扩展 | 数据层优化     |
| **AppSelect**      | A类（→el-select） | 通用选择器，可选用枚举数据     | Task 16b   | 完整EP适配层改造 |
| **FilterBar**      | B类（保持自建）       | 多字段过滤器，可能包含枚举字段   | Task 16a扩展 | 数据层优化     |
| **MetaTable**      | B类（保持自建）       | 元模型表格，可能包含枚举列     | 未来Phase 5  | 内部子控件可选优化 |

#### 4.1.2 Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend Layer                           │
│                                                              │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │  EnumSelect     │    │  AppSelect      │   (A类: EP)    │
│  │  (B类: 自建637行)│    │  (el-select)    │                │
│  └────────┬────────┘    └────────┬────────┘                │
│           │                      │                          │
│           ▼                      ▼                          │
│  ┌──────────────────────────────────────┐                   │
│  │        enumService.js               │                   │
│  │  ┌─────────────────────────────┐    │                   │
│  │  │ getEnumOptions(typeId)      │    │                   │
│  │  │ → GET /api/v1/enums/{id}/options │                  │
│  │  └─────────────────────────────┘    │                   │
│  └──────────────────┬──────────────────┘                   │
│                     │                                       │
└─────────────────────┼───────────────────────────────────────┘
                      │ HTTP (P99 < 5ms)
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                 Backend API Layer                            │
│                                                              │
│  ┌──────────────────────────────────────┐                   │
│  │        enum_api.py                   │                   │
│  │  /api/v1/enums/{type}/options       │                   │
│  │  → CachedEnumProvider.get_select_options()             │
│  └──────────────────┬───────────────────┘                   │
│                     │                                       │
│                     ▼                                       │
│  ┌──────────────────────────────────────┐                   │
│  │     EnumCacheManager (L1 Cache)     │                   │
│  │  命中率 > 99% | 响应 < 0.1ms        │                   │
│  └──────────────────────────────────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

#### 4.1.3 Implementation Guidelines

**Guideline 1: EnumSelect (B类) Optimization**

```javascript
// src/services/enumService.js (更新)

// 旧接口（保持兼容）
export async function getEnumValues(enumTypeId) {
  return api.get(`/api/v1/enums/${enumTypeId}`)
}

// 新接口（高速通道，推荐）
export async function getEnumOptions(enumTypeId, filters = {}) {
  // 调用统一BO模型 Phase 3 实现的新端点
  const response = await api.get(`/api/v1/enums/${enumTypeId}/options`, {
    params: filters,
    timeout: 5000, // 5秒超时
  })
  
  // 返回格式：[{ value: 'pending', label: '待处理', color: '#ea580c' }, ...]
  return response.data.map(item => ({
    value: item.code,
    label: item.name,
    color: item.color_tag,  // YonDesign颜色标签
    disabled: !item.is_active,
    ...item.extended_attrs  // 扩展属性（如图标、描述）
  }))
}
```

```vue
<!-- src/components/common/EnumSelect/EnumSelect.vue (部分更新) -->

<script setup>
import { ref, onMounted, watch } from 'vue'
import { getEnumOptions } from '@/services/enumService' // 使用新接口

const props = defineProps({
  enumTypeId: { type: String, required: true },
  // ... 其他原有props保持不变 ...
})

// 优化：使用新的高速接口
const options = ref([])

async function loadOptions() {
  if (!props.enumTypeId) return
  
  try {
    // 调用 IEnumProvider 高速通道：P99 < 5ms
    options.value = await getEnumOptions(props.enumTypeId, {
      include_inactive: false,
      locale: 'zh'
    })
    
    console.log(`[EnumSelect] 加载枚举 ${props.enumTypeId}: ${options.value.length} 个选项`)
  } catch (error) {
    console.error('[EnumSelect] 枚举加载失败:', error)
    // 降级：可选择性调用旧接口
  }
}

onMounted(loadOptions)
watch(() => props.enumTypeId, loadOptions)
</script>

<!-- template 和 style 保持原有637行逻辑不变 -->
```

**Guideline 2: AppSelect (A类) EP Migration + Enum Integration**

```vue
<!-- src/components/common/AppSelect/AppSelect.vue (改造后) -->

<template>
  <el-select
    v-model="selectValue"
    :placeholder="placeholder"
    :disabled="disabled"
    :clearable="clearable"
    :filterable="filterable"
    :multiple="multiple"
    :size="epSize"
    @change="handleChange"
  >
    <!-- 方式1: 直接绑定options（推荐用于枚举场景） -->
    <el-option
      v-for="opt in enumOptions"
      :key="opt.value"
      :label="opt.label"
      :value="opt.value"
      :disabled="opt.disabled"
    >
      <!-- 可选：自定义选项内容（如带颜色标签） -->
      <template #default>
        <span class="app-select__option-content">
          <span v-if="opt.color" class="color-dot" :style="{ backgroundColor: opt.color }"></span>
          <span>{{ opt.label }}</span>
        </span>
      </template>
    </el-option>
    
    <!-- 方式2: 使用插槽（保持向后兼容） -->
    <slot name="option" :option="option" v-for="option in customOptions" />
  </el-select>
</template>

<script setup>
import { computed, ref, onMounted, watch } from 'vue'
import { getEnumOptions } from '@/services/enumService'

const props = defineProps({
  modelValue: { type: [String, Number, Array], default: '' },
  enumTypeId: { type: String, default: '' },  // 新增：枚举类型ID
  options: { type: Array, default: () => [] }, // 原有：手动传入options
  // ... 其他原有props映射到EP ...
})

const emit = defineEmits(['update:modelValue', 'change'])

// 枚举数据供给（自动从新接口获取）
const enumOptions = ref([])
const customOptions = computed(() => props.options)

// 尺寸映射：我们的 sm/md/lg → EP的 small/default/large
const epSize = computed(() => {
  const sizeMap = { sm: 'small', md: 'default', lg: 'large' }
  return sizeMap[props.size] || 'default'
})

// v-model双向绑定
const selectValue = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

// 自动加载枚举数据
onMounted(async () => {
  if (props.enumTypeId && !props.options.length) {
    enumOptions.value = await getEnumOptions(props.enumTypeId)
  }
})

function handleChange(val) {
  emit('change', val)
}
</script>

<style scoped>
/* YonDesign橙色主题下的颜色点样式 */
.color-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 8px;
}

.app-select__option-content {
  display: flex;
  align-items: center;
}
</style>
```

#### 4.1.4 Testing Strategy

| 测试场景           | 涉及组件                   | 验证要点                        |
| -------------- | ---------------------- | --------------------------- |
| EnumSelect高速加载 | EnumSelect (B类)        | 枚举选项 < 100ms 显示，缓存命中 < 50ms |
| AppSelect EP渲染 | AppSelect (A类)         | el-select正确显示，样式为橙色主题       |
| 枚举数据一致性        | EnumSelect + AppSelect | 同一enumTypeId返回相同选项列表        |
| 视觉风格统一         | 所有组件                   | YonDesign橙色(#ea580c)正确应用    |
| 向后兼容           | 旧页面                    | 无代码修改即可工作                   |

***

### Phase 5: Analytics Support (Week 9-10) \[Optional]

**目标**: 分析型 BO 专项支持

**交付物**:

- [ ] 实现分析型 BO 特殊处理逻辑
- [ ] 事实表/维度表自动识别
- [ ] 聚合策略配置 UI

**验收标准**:

- ✅ 可基于 BO 元数据自动生成分析模型

***

## Risk & Mitigation

| 风险           | 概率    | 影响    | 缓解措施                                            |
| ------------ | ----- | ----- | ----------------------------------------------- |
| 向后兼容性破坏      | 中     | 高     | 所有新字段设默认值；渐进式迁移                                 |
| 性能下降         | 低     | 中     | 冗余字段缓存；异步索引构建                                   |
| 学习曲线陡峭       | 中     | 中     | 详细文档；IDE自动补全；示例库                                |
| 过度工程         | 高     | 高     | MVP优先；按需迭代；避免一步到位                               |
| **UI组件迁移冲突** | **中** | **中** | **明确A/B类边界；EnumSelect不动仅优化数据层；AppSelect完整迁移**   |
| **EP主题不一致**  | **低** | **中** | **强制使用element-variables.scss；YonDesign橙色变量全覆盖** |

***

## Success Metrics

**技术指标**:

- ✅ 现有 100% BO 可正常加载（向后兼容）
- ✅ 枚举查询 P99 < 5ms（P50 < 1ms）
- ✅ 缓存命中率 > 99%
- ✅ 代码覆盖率 > 80%（新增模块）
- ✅ **前端枚举加载性能 < 100ms（EnumSelect/AppSelect）**
- ✅ **EP组件主题一致性 100%（橙色#ea580c）**

**业务指标**:

- ✅ BO 分类准确率 > 90%（人工抽检）
- ✅ 字段关联配置错误率 < 5%
- ✅ 团队满意度 > 4.0/5.0
- ✅ **UI组件迁移零破坏性回归（71个引用文件无需修改）**

***

## Cross-Spec Dependencies

### 与混合组件策略（Hybrid Component Strategy）的协同

| 统一BO模型阶段             | 混合组件策略阶段          | 协同关系      | 关键产出                              |
| -------------------- | ----------------- | --------- | --------------------------------- |
| **Phase 3 ✅ 完成**     | Phase 0 (基础设施)    | 无依赖       | IEnumProvider接口就绪                 |
| **Phase 4 (当前)**     | Phase 1 (高价值组件)   | 并行执行      | DateTimePicker/Pagination等先完成EP迁移 |
| **Phase 4 Task 16a** | Phase 2 (表单控件)    | **强依赖**   | AppSelect(el-select)需要消费枚举数据      |
| **Phase 4 Task 16b** | Phase 2 (表单控件)    | **同一工作流** | AppSelect改造 + 枚举对接同步完成            |
| **Phase 5 (未来)**     | Phase 5 (B类子控件优化) | 前置依赖      | MetaTable内部分页器/输入框可选EP化           |

**建议执行顺序**：

```
Week 7-8 (并行):
  ├─ 统一BO Phase 4: 后端工具链 + EnumSelect数据层优化
  └─ 混合策略 Phase 1-2: A类组件EP迁移（DateTimePicker/Pagination/AppSelect）

关键交汇点：Week 8 第二周
  ✅ AppSelect(el-select) 就绪
  ✅ enumService.js 高速接口就绪
  → 集成测试：AppSelect + 枚举数据端到端验证
```

