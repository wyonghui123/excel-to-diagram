# 枚举依赖关系通用化 — 验证清单

> Edition: v4 — 新增 UI 适配验证

---

## 行业研究汇总

| 产品 | 依赖机制 | 与我们的对比 |
|------|---------|------------|
| Salesforce | Dependent Picklist（字段级依赖矩阵） | 我们是枚举类型级，可跨对象复用 |
| ServiceNow | Dependent Choice + Reference Qualifier | 我们独立关联表，多层级联更自然 |
| Google Dataplex | Taxonomy 层级树 | 纯树形，我们是图结构 |
| Microsoft Dataverse | 表关系 1:N | 场景不同，不重叠 |

---

## 设计原则验证

| 原则 | 说明 |
|------|------|
| **元模型驱动** | direction 值通过 `enum_type`/`enum_value` 管理 |
| **一等公民** | direction 和业务枚举值享有同等的管理界面 |
| **可复用** | direction 可被任何枚举类型通过 INSERT 引用 |
| **向后兼容** | `dimension_schema` API 不变 |
| **REFERENCES 无维度** | API 返回空数组，前端不渲染选择器 |
| **通用扩展性** | country→province→city 纯数据操作 |

---

## 数据模型验证

- [ ] `Direction` 在 `models.py` 中定义
- [ ] `Direction` 在 `ENUM_CLASSES` 注册
- [ ] `enum_dependency_links` 表创建成功
- [ ] 迁移后表中恰有 3 行（GENERATES/UPDATES/TRIGGERS → direction）
- [ ] REFERENCES 不在 `enum_dependency_links` 中

---

## API 验证

- [ ] `GET /api/v1/enum-dependencies/parent/relation_type/GENERATES` → 返回 direction
- [ ] `GET /api/v1/enum-dependencies/parent/relation_type/REFERENCES` → `{ dependencies: [] }`
- [ ] `GET /api/v1/enum-types/relation_type` 的 `dimension_schema` 兼容

---

## 管理端 UI 验证

- [ ] 枚举管理页面：`direction` 可见可管理（增删改枚举值）
- [ ] enum_type 详情页：新增 "枚举依赖" 子区域
- [ ] 枚举依赖子区域：可新增/删除依赖行
- [ ] 枚举依赖子区域：仅显示当前 enum_type 的依赖（fixedFilter 生效）
- [ ] `dimension_schema` textarea 标记为只读
- [ ] `enum_value` 的 `dimensions` 字段保持不变（向后兼容）

---

## 业务端 UI 验证

- [ ] `EnumService.loadDependencyOptions('relation_type', 'GENERATES')` → 返回 direction
- [ ] `EnumService.loadDependencyOptions('relation_type', 'REFERENCES')` → `[]`
- [ ] `EnumDependencySelector` 组件：GENERATES → direction 下拉出现
- [ ] `EnumDependencySelector` 组件：REFERENCES → 不渲染任何元素
- [ ] ObjectPage 合并关系表：显示 `relation_type` 中文名（生成/更新/触发/引用）
- [ ] 导入导出：兼容

---

## 回归验证

- [ ] 枚举管理页面：现有枚举不受影响
- [ ] 关系管理：CRUD 正常
- [ ] ObjectPage：业务对象详情正常加载
- [ ] ValueHelp 下拉搜索：`relation_type` 的 ValueHelp 字段正常
- [ ] 服务重启：无错误
