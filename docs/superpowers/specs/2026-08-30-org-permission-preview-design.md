# org / user 权限预览 设计文档

> 分支：`feat-permission-set-refactor`（Spec16 权限集重构 + org 迁移）
> 日期：2026-08-30 | 状态：设计已获批，待实现
> 涉及：前端 3007 / 后端 5000

## 1. 需求与价值

为 org 与 user 提供**只读的权限预览视图**，从"对象视角"一次性看清其全部有效权限，
包括来自父级/祖先组织派生（inherited/derived）的权限，并追溯每项权限的来源。

核心价值：
- **透视继承链**：org 直接挂载的权限 + 祖先组织派生权限，当前 UI 无法一次看清。
- **来源追溯**：每项权限标注来源组织/层级，回答"这个权限从哪来"。
- **排障效率**：权限不对时快速定位是未配置、还是被某层派生覆盖。
- **能力复用**：org 与 user 预览共享同一聚合内核，后续任意 identity 可直接扩展。

**明确不在范围内（YAGNI）**：成员透视、导出、跳转定位、点选生效；仅只读 MVP。

## 2. 竞品研究（结论佐证）

WebSearch 调研头部产品，均支持从对象(授权对象)视角查看有效权限并含来源追溯：

| 产品 | 能力 | 对本设计佐证 |
|------|------|-------------|
| 用友 YonBIP 权限分析中心 (2024) | 按对象汇总有效权限，含继承 | 支持"组织/角色对象视角"预览 |
| 金蝶（权限查询） | 按授权对象 或 按权限 + 来源 + 导出 | 来源追溯是标配 |
| 苍穹用户组 | 用户组权限集父子继承 | 继承派生模型一致 |
| SAP PFCG | 角色继承派生角色，effective 汇总 | 有效权限 = 直接 + 派生并集 |
| Salesforce PermissionSetAnalyzer | 多 PermissionSet 并集求有效权限 | 跨 set 去重聚合 |

结论：**功能权限 + 数据权限两个维度 + 来源追溯** 符合行业主流；当期不做成员透视有其他产品未完全对齐，故 YAGNI。

## 3. 元数据驱动架构：通用「只读聚合 Tab」

经权衡（详见 3.5），采用**通用 `readonly_aggregate` section 类型**，
把"权限预览"建模为一个后端计算 returns + 前端通用只读渲染器，而非硬编码组件，
也不滥用 association 语义。

### 3.1 后端共享聚合内核（一个函数，两种身份）

```
get_permission_preview(identity_type: 'org' | 'user', identity_id):
  # 根组织集合
  if org:
    roots = [org_id]
    chain = roots + reversed(get_all_ancestor_orgs(org_id))   # ↑根→祖先，逐级
  if user:
    roots = get_user_effective_org_ids(user_id)               # 有效org全集(直属+祖先)，天然 set

  # 对 roots 逐级 get_org_permission_sets，记录 source_org_id / name / (org 有 level)
  # 功能权限：按 permission_set_id 去重
  #   - org：取"最深"挂载（本组织优先，向上递减）
  #   - user：无层级优选语义，跨 root 同 set 用 sources[] 平铺
  # 每个 set 取 granted=true 的 permissions（granted=false 调降为"排除"标注）
  # 数据权限：跨有效 org 按 (resource_type, resource_id, permission_level) 去重 + sources[]

  返回统一结构（见 3.2）
```

- 复核里沿用现有编排：`get_user_effective_org_ids`（[org_service.py L88-103](file:///d:/filework/worktrees/feat-permission-set-refactor/meta/services/org_service.py)）、
  `get_all_ancestor_orgs`（L176-198，自带循环检测）、`get_org_permission_sets`（L286+）。

### 3.2 统一返回结构（org / user 同一 schema）

```jsonc
{
  "identity_type": "org",
  "identity_id": "12",
  "identity_name": "采购部",
  "root_orgs": [ { "org_id": "12", "org_name": "采购部" } ],       // user 时为有效 org 全集
  "summary": { "permission_set_count": 5, "source_org_count": 3, "direct_count": 2, "inherited_count": 3 },

  "permission_sets": [
    {
      "permission_set_id": "ps_1",
      "permission_set_code": "SCP_BASE",
      "permission_set_name": "供应链基础",
      "system_flag": false,
      "granted": true,                                  // false = 排除
      "source_orgs": [ { "org_id": "12", "org_name": "采购部", "relation": "direct|inherited" } ],
      "permissions": [ { "permission_id": "p1", "permission_code": "VIEW", "permission_name": "查看", "granted": true } ]
    }
  ],

  "data_permissions": [
    {
      "resource_type": "domain",
      "resource_id": "d1",
      "resource_name": "供应链计划",
      "permission_level": "read",                       // read|write|...
      "inherit_to_children": true,
      "sources": [ { "org_id": "12", "org_name": "采购部", "permission_set_name": "供应链基础" } ]
    }
  ]
}
```

### 3.3 前端：通用 section 类型 `readonly_aggregate`

- `ObjectPageContent.vue` 新增 `section.type === 'readonly_aggregate'` 渲染分支，
  渲染通用组件 `ReadonlyAggregateSection.vue`（与 association / custom 平级，不污染关联语义）。
- `DetailPage.vue` 的 tab 转换逻辑（现 `tab.type === 'association'` 分支 L733-763）
  扩一个 `readonly_aggregate` 分支，将 tab 配置透传为 section。
- 通用组件职责（全部由 `props.config` 驱动，不感知具体对象）：
  - 标题 + 统计行（`summary`）
  - 权限集卡片列表，可展开显示权限码/操作点；`granted=false` 灰化标"排除"
  - 数据权限资源聚合表（资源类型/名称/权限级别/继承至子级/来源 tooltip）
  - 空态 / 加载 spinner / 错误重试

### 3.4 元数据配置（驱动声明）

```yaml
# org 详情 tab 配置
- key: permission_preview
  label: 权限预览
  type: readonly_aggregate
  component: PermissionPreview
  props:
    endpoint: /api/org/{id}/permission-preview   # 后端按当前对象类型插值
    display:
      # 列/卡片字段元数据，通用组件内置默认，可按对象覆盖
      columns:
        - { key: resource_type, label: 资源类型 }
        - { key: resource_name, label: 资源 }
        - { key: permission_level, label: 权限级别 }
        - { key: inherit_to_children, label: 继承至子级 }
        - { key: sources, label: 来源 }
```

用户详情 tab 配置同理，`endpoint: /api/user/{id}/permission-preview`。

### 3.5 备选路线权衡（为何不选另两条）

| 路线 | 结论 | 理由 |
|------|------|------|
| **A. custom section（每对象组件）** | 否 | 按对象耦合，非元数据驱动；后续新增预览要再写 Vue 组件 |
| **B. association view** | 否 | association 本质=真实子表记录列表（`queryAssociations` 拉单表）。数据权限 Tab 无底层 BO 表，无法表达；功能权限的"有效含继承去重"也不是子表列表。硬塞需给 `association_engine` 加自定义计算型 resolver，污染关联语义 |
| **C. 完整 action→tab 机制** | 暂缓 | action returns→view 是净新增概念；本项目暂无该渲染机制。本文案的"后端 returns + 通用只读渲染器"已等价覆盖轻量需求，action 全量语义留待需要 command/query 分离时再加 |
| **D. 通用 readonly_aggregate（本文案）** | ✅ 推荐 | 配置驱动 + 通用组件 + 共享内核；org/user 零重复代码，后续 identity 即插即用 |

## 4. 展示结构

### 4.1 入口

- org 详情 drawer 新增 Tab「权限预览」（`enableDetailPage` 链路，`MetaListPage.vue` → `DetailPage.vue`）
- user 详情 drawer 新增 Tab「权限预览」
- 纯只读 MVP：不导出 / 不跳转 / 不点选生效。

### 4.2 功能权限 Tab

- 顶部统计：`有效 N 个权限集（本组织直挂 X / 父级继承 Y）`（user 为 `来源组织 M 个`）。
- 每权限集卡片：名称 / 编码 / 系统 tag / 来源徽标（org 停层级，user 停组织名 + tooltip）。
- 展开显权限码 + 操作点；`granted=false` 灰化标"排除"。
- 空态文案：`该组织未配置权限，且无父级继承`（无 roots 时）。

### 4.3 数据权限 Tab

- 资源聚合表：资源类型 / 名称 / 权限级别 / 继承至子级 / 来源。
- 跨有效 org 按 `(resource_type, resource_id, permission_level)` 去重，其余来源收进 `sources[]`，
  tooltip 展示完整来源链。

## 5. 错误处理

- **循环引用**：祖先链构建复用 `get_all_ancestor_orgs`，自带循环检测，抛出即终止。
- **scopeCode 类失败绝不回退全量**：本功能是聚合只读，无"回退加载全量"逻辑，天然规避既往高负载问题。
- **空态**：无 roots / 无权限集 → 明确空态文案，不报错。
- **接口失败**：前端口局部 spinner + 错误条 + 重试按钮，不阻塞整个 drawer。

## 6. 测试

### 6.1 后端服务单测（聚合内核）
- `source_org_id/name`、`relation(direct|inherited)` 正确填充
- 继承链：直属 + 祖先逐级并入；`org` 最深优先、`user` 多 root `sources[]` 平铺
- 去重规则：功能按 `permission_set_id`、数据按 `(resource,level)`
- `granted=false` 标排除
- 空 org / 无祖先 org / 用户无 org 空态
- 祖先循环 → 抛错（现有逻辑覆盖）

### 6.2 端点测试
- `GET /api/org/{id}/permission-preview`、`GET /api/user/{id}/permission-preview` 只读、返回结构与 schema 一致、非法 id / 不存在 id 的正确错误。

### 6.3 前端
- 通用组件：空态 / 错误重试 / 卡片展开 / 来源 tooltip。
- 链路：org 详情 drawer → 新 Tab 正常渲染；user 详情 drawer 同理。