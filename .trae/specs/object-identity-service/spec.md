# 对象标识转换服务体系重构 Spec

## Why

当前系统的对象标识转换能力存在严重缺失：
- ID → Business Key 转换仅通过硬编码函数实现，非元数据驱动
- Parent Key → Name/Full Name 转换功能有限，仅用于内部验证
- 缺少统一的 ObjectIdentityService 整合 Key 和 Hierarchy 信息
- 缺少统一的 API 接口和前端 Composable
- 无法支持审计日志、UI展示等通用场景

这导致系统无法提供企业级的对象身份识别能力，不符合 SAP One Domain Model 等最佳实践。

## What Changes

### 核心服务层
- 创建 `BusinessKeyService` - 元数据驱动的 ID → Business Key 转换服务
- 创建 `HierarchyPathService` - 层级路径计算服务
- 创建 `ObjectIdentityService` - 整合 Key + Hierarchy 的统一标识服务

### API 层
- 创建 `object_identity_api.py` - RESTful API 接口
  - `GET /api/v1/identity` - 单个对象标识查询
  - `POST /api/v1/identity/batch` - 批量对象标识查询

### 前端层
- 创建 `useObjectIdentity.js` - Vue Composable
  - 支持缓存机制
  - 支持响应式数据

### 元数据模型
- 扩展 `hierarchies.yaml` - 定义层级路径模板
- 利用现有 `shared_properties.yaml` 中的 `business_key` 和 `parent_key` 语义标记

### **BREAKING** 变更
- 迁移 `audit_api.py` 中的 `_generate_business_key` 函数到新服务
- 废弃 `BUSINESS_KEY_METADATA` 硬编码配置

## Impact

### 受影响的规范
- `audit-log-capability-enhancement` - 审计日志将使用新的 ObjectIdentityService
- `business-key-context-enhancement` - 导入导出将使用新的 BusinessKeyService

### 受影响的代码
- `meta/api/audit_api.py` - 迁移硬编码函数到新服务
- `meta/services/manage_service.py` - `_resolve_parent_context` 方法可被新服务替代
- `meta/schemas/hierarchies.yaml` - 需要扩展层级路径定义
- 前端审计日志页面 - 使用新的 Composable 获取对象标识

### 不受影响的部分
- 数据库结构 - 无变更
- 现有 API 接口 - 保持向后兼容
- 用户界面 - 渐进式迁移

## ADDED Requirements

### Requirement: BusinessKeyService - ID到业务键转换服务

系统应提供元数据驱动的 ID → Business Key 转换服务。

#### Scenario: 单个对象转换成功
- **WHEN** 调用 `business_key_service.id_to_business_key('domain', 123)`
- **THEN** 返回业务键字符串，如 "ERP产品 → V5 → 供应链云"

#### Scenario: 批量转换成功
- **WHEN** 调用 `business_key_service.batch_convert([('domain', 123), ('domain', 124)])`
- **THEN** 返回映射字典 `{('domain', 123): '供应链云', ('domain', 124): '制造云'}`

#### Scenario: 元数据驱动配置
- **WHEN** 对象类型的元数据定义了 `business_key: true` 字段
- **THEN** 服务自动从元数据读取字段配置，无需硬编码

#### Scenario: 多格式输出支持
- **WHEN** 调用转换方法时指定 `format='short'`
- **THEN** 返回简短格式，如 "供应链云 (V5)"

### Requirement: HierarchyPathService - 层级路径计算服务

系统应提供层级路径计算服务，支持从根节点到当前对象的完整路径。

#### Scenario: 计算完整路径
- **WHEN** 调用 `hierarchy_path_service.get_full_path('business_object', 456)`
- **THEN** 返回完整路径对象，包含 `{'full': 'ERP产品 → V5 → 供应链云 → 库存管理', 'depth': 4}`

#### Scenario: 路径格式化
- **WHEN** 指定 `path_type='absolute_full_path'`
- **THEN** 返回包含产品和版本的绝对路径

#### Scenario: 路径截断
- **WHEN** 路径长度超过 `max_length=80`
- **THEN** 智能截断并标记 `truncated: true`

### Requirement: ObjectIdentityService - 统一对象标识服务

系统应提供整合 Key 和 Hierarchy 信息的统一对象标识服务。

#### Scenario: 获取完整标识
- **WHEN** 调用 `object_identity_service.get_identity('domain', 123, format='full')`
- **THEN** 返回完整标识对象：
  ```json
  {
    "formatted": "ERP产品 → V5 → 供应链云 [SUPPLY_CHAIN]",
    "technical": {"id": 123, "object_type": "domain"},
    "semantic": {"business_key": "ERP|V5|SUPPLY_CHAIN"},
    "display": {"name": "供应链云", "code": "SUPPLY_CHAIN"},
    "hierarchical": {"full_path": "ERP产品 → V5 → 供应链云", "depth": 3}
  }
  ```

#### Scenario: 批量获取标识
- **WHEN** 调用 `batch_get_identities([('domain', 123), ('domain', 124)])`
- **THEN** 返回所有对象的完整标识映射

### Requirement: ObjectIdentityAPI - RESTful API接口

系统应提供 RESTful API 接口供前端调用。

#### Scenario: 单个对象标识查询
- **WHEN** 前端请求 `GET /api/v1/identity?object_type=domain&object_id=123&format=full`
- **THEN** 返回 JSON 格式的对象标识

#### Scenario: 批量对象标识查询
- **WHEN** 前端请求 `POST /api/v1/identity/batch` 包含对象列表
- **THEN** 返回所有对象的标识映射

### Requirement: useObjectIdentity Composable - 前端集成

系统应提供 Vue Composable 供前端组件使用。

#### Scenario: 获取单个对象标识
- **WHEN** 组件调用 `const { getIdentity } = useObjectIdentity()` 和 `getIdentity('domain', 123)`
- **THEN** 返回响应式的对象标识数据

#### Scenario: 缓存机制
- **WHEN** 多次请求同一对象的标识
- **THEN** 从缓存中读取，避免重复 API 调用

## MODIFIED Requirements

### Requirement: 审计日志业务键生成

**原需求**: 使用硬编码的 `BUSINESS_KEY_METADATA` 配置生成业务键

**修改后**: 使用 `BusinessKeyService` 从元数据动态生成业务键

#### Scenario: 审计日志展示
- **WHEN** 审计日志需要显示对象标识
- **THEN** 调用 `ObjectIdentityService.get_identity()` 获取完整标识

## REMOVED Requirements

### Requirement: BUSINESS_KEY_METADATA 硬编码配置

**Reason**: 迁移到元数据驱动的方式，由 `BusinessKeyService` 从元数据动态读取

**Migration**: 
1. 保留 `audit_api.py` 中的 `_generate_business_key` 函数作为过渡
2. 标记为 `@deprecated`，内部调用新服务
3. 逐步迁移所有调用方到新服务

## 技术设计

### 1. BusinessKeyService 设计

```python
class BusinessKeyService:
    """元数据驱动的业务键转换服务"""
    
    def id_to_business_key(
        self, 
        object_type: str, 
        object_id: int,
        format: str = 'full'
    ) -> str:
        """
        将对象ID转换为业务键
        
        Args:
            object_type: 对象类型
            object_id: 对象ID
            format: 输出格式 ('full', 'short', 'minimal')
        
        Returns:
            业务键字符串
        """
        
    def batch_convert(
        self,
        requests: List[Tuple[str, int]]
    ) -> Dict[Tuple[str, int], str]:
        """批量转换"""
```

### 2. HierarchyPathService 设计

```python
class HierarchyPathService:
    """层级路径计算服务"""
    
    def get_full_path(
        self,
        object_type: str,
        object_id: int,
        path_type: str = 'absolute_full_path',
        max_length: int = 80
    ) -> Dict[str, Any]:
        """
        获取对象的完整层级路径
        
        Returns:
            {
                'full': 'ERP产品 → V5 → 供应链云',
                'short': '供应链云 (V5)',
                'segments': [...],
                'depth': 3,
                'truncated': False
            }
        """
```

### 3. ObjectIdentityService 设计

```python
class ObjectIdentityService:
    """统一对象标识服务"""
    
    def __init__(self):
        self.business_key_service = BusinessKeyService()
        self.hierarchy_path_service = HierarchyPathService()
    
    def get_identity(
        self,
        object_type: str,
        object_id: int,
        format: str = 'full',
        include_technical: bool = False
    ) -> Dict[str, Any]:
        """
        获取对象的完整身份标识
        
        Returns:
            {
                'formatted': 'ERP产品 → V5 → 供应链云 [SUPPLY_CHAIN]',
                'technical': {...},
                'semantic': {...},
                'display': {...},
                'hierarchical': {...}
            }
        """
```

## 实施策略

### 分阶段实施

#### Phase 1: 核心服务实现（P0）
- 实现 `BusinessKeyService`
- 实现 `HierarchyPathService`
- 实现 `ObjectIdentityService`
- 编写单元测试

#### Phase 2: API 接口实现（P1）
- 实现 `object_identity_api.py`
- 编写 API 测试

#### Phase 3: 前端集成（P1）
- 实现 `useObjectIdentity.js`
- 迁移审计日志页面使用新 Composable

#### Phase 4: 迁移与废弃（P2）
- 迁移 `audit_api.py` 使用新服务
- 标记旧函数为 `@deprecated`
- 更新文档

### 风险控制

1. **向后兼容**: 保留旧函数，标记为废弃
2. **渐进式迁移**: 先实现新服务，再逐步迁移调用方
3. **测试覆盖**: 每个阶段都有完整的测试验证
4. **回滚计划**: 保留旧代码，可快速回滚

## 验收标准

### 功能验收
- [ ] BusinessKeyService 支持元数据驱动配置
- [ ] HierarchyPathService 支持完整路径计算
- [ ] ObjectIdentityService 整合 Key 和 Hierarchy 信息
- [ ] API 接口正常工作
- [ ] 前端 Composable 支持缓存

### 性能验收
- [ ] 单个对象标识查询 < 50ms
- [ ] 批量查询（100个对象） < 500ms
- [ ] 缓存命中率 > 80%

### 质量验收
- [ ] 所有单元测试通过
- [ ] 所有集成测试通过
- [ ] 代码覆盖率 > 80%
- [ ] 无 lint 错误
