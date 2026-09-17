# Prod → Staging 权限/组织数据迁移方案

> **版本**: v1.0 (2026-09-03)
> **方向**: production 旧模型 (roles/user_groups) → staging 新模型 (permission_sets/orgs)
> **主机**: 172.20.59.7（两库同机，可直接文件级访问）
> **源库**: `/opt/app/deployments/meta/architecture.db` (只读打开 mode=ro)
> **目标库**: `/opt/app/staging/meta/architecture.db`

---

## 1. 两库现状（2026-09-03 实测）

### 1.1 Prod 旧模型

| 表 | 行数 | 说明 |
|---|---|---|
| users | 6 | admin + adminscm/adminfin/adminhrm/wyonghui/chenxi (id 1,1046-1050) |
| roles | 40 | 3 系统 (1/2/3) + **37 业务角色** (897, 1195-1232) |
| role_permissions | 954 | 45 个权限点，全部 granted=1，0 孤儿 |
| role_menu_permissions | 38 | menu_code 仅 2 种：arch-data (37 角色)、product-management (1200) |
| role_dimension_scopes | **38** | 管理维度配置（admin 1 条 + 37 业务角色各 1 条，全部 include 模式） |
| role_data_permissions | 0 | 空 |
| user_groups | 35 | 1 系统 (system_admin) + **34 业务组** (249+) |
| user_group_members | 7 | **2 条孤儿**（user 792/921 不在 users 表） |
| group_roles | 59 | 0 孤儿 |
| group_data_permissions | 0 | 空 |
| user_roles | 1 | 仅 (user 1 → role 1 admin) |
| permission_rules | 33 | 全部为同一条规则的重复：role 1, domain, `version_id = 1`, read |
| data_permissions | 82 | user 级数据权限：user 1 有 74 条、user 1049 有 8 条 |
| permissions | 255 | 权限点主数据 |

### 1.2 Staging 新模型

| 表 | 行数 | 说明 |
|---|---|---|
| users | 6 | 与 prod **完全一致**（id + username 对齐）✓ |
| permission_sets | 3 | 仅 admin/editor/viewer，**37 个业务权限集缺失** |
| permission_set_permissions | 4 | 仅 admin 的 4 条 |
| permission_set_menu_permissions | 6 | 仅 admin 的 6 条 |
| permission_set_dimension_scopes | 0 | **空（v079 seed 未落库）** |
| permission_set_data_permissions | 0 | 空 |
| orgs | 1 | 仅 system_admin，**34 个业务 org 缺失** |
| org_members / org_permission_sets | 1 / 1 | 仅系统种子 |
| user_permission_sets | 353 | ⚠️ **垃圾数据**：全部 user 1，350 条指向不存在的 ps（id 1-12674） |
| permission_rules | 0 | 空（且新模型列名已改为 permission_set_id） |
| data_permissions | 0 | 空 |
| permissions | 311 | prod 255 个权限点**全部存在且 id+code 一致** ✓，另有 56 个新增权限点 |
| menus | 39 | prod 引用的 arch-data/product-management 均存在 ✓ |

### 1.3 关键结论

1. **权限点主数据（permissions）无需迁移**：两库 id+code 完全对齐，`role_permissions.permission_id` 可直接引用。
2. **users 无需迁移**：两库 6 个用户 id+username 完全一致。
3. **ID 保留策略可行**：staging permission_sets最大 id=3、orgs 最大 id=1，prod 业务角色 id≥897、业务组 id≥249，无冲突 → 全程保留 prod 主键，关系表无需 id 重映射。
4. **staging `user_permission_sets` 必须先清理**：353 行中 350 行是孤儿引用（历史遗留垃圾），迁移前备份后删除。
5. **`functions` 表两库都不存在**："功能权限"即 `permissions` 主数据 + `role_permissions` 授权关系，映射到 `permission_set_permissions`。

---

## 2. 映射关系（对应用户理解逐条确认）

| 用户理解 | Prod 源 | Staging 目标 | 列映射 | 行数 |
|---|---|---|---|---|
| role → 权限集 | `roles` | `permission_sets` | id/code/name/description/is_active/is_system 直拷 | **37**（跳过已有 admin/editor/viewer，按 code 判重） |
| role 下的功能权限 → 权限集的功能权限 | `role_permissions` | `permission_set_permissions` | role_id→permission_set_id，permission_id 不变，granted 直拷 | **954** |
| role 下的菜单权限 → 权限集的菜单权限 | `role_menu_permissions` | `permission_set_menu_permissions` | role_id→permission_set_id，menu_code 直拷 | **38** |
| role 下的管理维度配置 → 权限集的数据权限 | `role_dimension_scopes` | `permission_set_dimension_scopes` | role_id→permission_set_id，dimension_code/dimension_values/inherit_children/scope_mode 直拷 | **38** |
| role 下的数据权限（资源级） | `role_data_permissions` | `permission_set_data_permissions` | 同构直拷 | 0（prod 为空，机制保留） |
| （补充）读规则 | `permission_rules` | `permission_rules` | **role_id→permission_set_id**（新模型列名已改）；33 行重复去重为 1 行 | **1** |
| （补充）user 级数据权限 | `data_permissions` | `data_permissions` | user_id/resource_type/resource_id/permission_level/inherit_to_children 直拷 | **82** |
| group → org | `user_groups` | `orgs` | id/name/code/parent_id/manager_id/description 直拷；org_type='department'、org_scope='internal' 默认值 | **34**（跳过已有 system_admin） |
| group 与 role 的关系 → org 与权限集的关系 | `group_roles` | `org_permission_sets` | group_id→org_id，role_id→permission_set_id | **59** |
| （补充）组成员 | `user_group_members` | `org_members` | group_id→org_id，user_id/is_manager 直拷 | **5**（跳过 2 条孤儿 user 792/921，记录日志） |
| （补充）用户直配角色 | `user_roles` | `user_permission_sets` | user_id 直拷，role_id→permission_set_id | **1** |

**权限继承链验证**（以 wyonghui 为例）：
prod `ugm(user 1049 → group 249 scmgroup)` + `group_roles(249 → role 897 SCMEDIT)` + `role_dimension_scopes(897, domain, [8])`
→ 迁移后 `org_members(1049 → org 249)` + `org_permission_sets(249 → ps 897)` + `permission_set_dimension_scopes(897, domain, [8])` ✓ 链路完整保留。

**不迁移**：permissions 主数据（已对齐）、menus（staging 超集）、users（已对齐）、staging 遗留旧表 roles/user_groups/group_roles（Spec16 已废弃，待 v080/v081 补账统一清理，本方案不触碰）。

---

## 3. 交付物与执行设计

### 3.1 交付物

- `tools/migrate_prod_perm_to_staging.py` — 一次性迁移脚本（部署在 172.20.59.7 执行，遵循 v079 seed migration 模式）
- 特性：**幂等**（按主键/业务键查重跳过）、**全表备份**（`<table>_pre_mx_backup`）、**verify()** 行数对账、**downgrade()** 从备份表恢复
- prod 库以 `file:...?mode=ro` 只读打开，物理上不可能写坏 prod

### 3.2 执行步骤（预计 10 分钟窗口）

```
Step 0  前置检查
        - 两库存在且可打开；staging 服务运行中（迁移在低峰执行，SQLite 短事务）
        - 权限点对齐校验：prod.role_permissions 引用的 45 个 permission_id
          必须全部存在于 staging.permissions（不为 0 即中止，绝不静默跳过）
        - users 对齐校验：两库 users id 集合一致（不一致即中止）

Step 1  全量备份 staging DB
        cp /opt/app/staging/meta/architecture.db /opt/app/staging/meta/architecture.db.bak.mx_YYYYmmdd_HHMMSS

Step 2  各目标表整表备份 → <table>_pre_mx_backup（11 张目标表）

Step 3  清理垃圾：DELETE FROM user_permission_sets（353 行孤儿，已备份）

Step 4  主数据迁移（顺序执行，均为单事务短批）
        M1 roles → permission_sets          (37)
        M8 user_groups → orgs               (34)

Step 5  关系/配置迁移（校验外键引用存在后才 INSERT）
        M2 role_permissions → ps_permissions (954)
        M3 role_menu_permissions → ps_menu   (38)
        M4 role_dimension_scopes → ps_dim    (38)
        M5 role_data_permissions → ps_data   (0)
        M6 permission_rules（去重→1）
        M7 data_permissions                  (82)
        M9 group_roles → org_permission_sets (59)
        M10 user_group_members → org_members (5, 跳孤儿)
        M11 user_roles → user_permission_sets(1)

Step 6  刷新冗余计数列
        UPDATE permission_sets SET menu_count/permission_count/data_perm_count/user_count
        （按各子表 COUNT 重算，旧模型同名列迁移时不拷贝）

Step 7  verify() 行数对账（见 §4）→ 不过则自动回滚并退出非 0
```

### 3.3 幂等性

每条 INSERT 前按唯一键查重：
- permission_sets/orgs 按 `code`；关系表按 `(父id, 子id/键)` 组合
- 重复执行输出 `inserted=N, skipped=M`，第二次应 inserted=0

---

## 4. 验证方案

### 4.1 行数对账（verify 硬校验，任一不符即 FAIL）

> 实际执行后修正：与 3.2 预估差异来自 dedupe（staging 已有的种子行与 prod 重叠）。

| 目标表 | 期望（实际） | 说明 |
|---|---|---|
| permission_sets | 40 | 3 种子 + 37 |
| permission_set_permissions | **957** (≥953) | 4 种子 + 953，1 条与 admin 既有行去重 |
| permission_set_menu_permissions | 44 | 6 + 38 |
| permission_set_dimension_scopes | 38 | 0 + 38 |
| permission_set_data_permissions | 0 | prod 为空 |
| permission_rules | 1 | 33 行重复去重后 1 条 |
| data_permissions | **21** | prod 82 行按 UNIQUE(user_id,resource_type,resource_id) 聚合（21 插入 + 2 升级 + 59 去重） |
| orgs | 35 | 1 + 34 |
| org_permission_sets | **59** (≥59) | 1 种子 + 58，(1,1,1) 去重 |
| org_members | **5** | 1 种子 + 4，(1,1,1) 去重，另跳 2 条孤儿 user 792/921 |
| user_permission_sets | 1 | 清 353 行垃圾后按 prod user_roles 重灌 |

附加校验：全部关系表孤儿引用 = 0；permission_sets 冗余计数列与子表实际 COUNT 一致。

### 4.2 API smoke（复用 staging_postcheck.py）

1. `staging_postcheck.py` 16 项全绿
2. 登录 wyonghui → 可见菜单含 arch-data，权限矩阵 (SCP) 非空
3. 组织管理页：org 列表 35 条、scmgroup 挂 SCMEDIT 权限集
4. 权限集管理页：业务权限集 37 个、维度 scope 正确显示（domain=[8] 等）

### 4.3 回滚策略（三层）

| 层级 | 手段 | 适用 |
|---|---|---|
| L1 脚本内 | `downgrade()`: TRUNCATE 目标表 + 从 `*_pre_mx_backup` 回灌 | verify 失败当场回滚 |
| L2 文件级 | 恢复 `architecture.db.bak.mx_*` 全量备份 | 迁移后发现逻辑问题 |
| L3 服务级 | 重启 core_service(13011) 清理内存缓存 | 回滚后收尾 |

---

## 5. 风险与对策

| 风险 | 对策 |
|---|---|
| 迁移时服务并发写 SQLite | 低峰窗口执行；单事务短批；migration_lock 模式防并发 |
| cron 旧备份再次覆盖 staging DB | 已于 9-2 禁用 `/opt/app/shared/sync_staging_db.sh`；迁移前 postcheck 确认 |
| 脏数据混入（孤儿引用） | Step 0 外键预校验不过即中止（不静默跳过）；ugm 2 条孤儿显式记录 skip 日志 |
| 33 行重复 permission_rules | 迁移时 GROUP BY 去重，只迁 1 条有效规则 |
| 误写 prod | prod 以 mode=ro 只读 URI 打开，物理不可写 |
| 计数列（user_count 等）漂移 | 迁移后统一重算，不信任 prod 拷贝值 |

---

## 6. 执行记录（2026-09-03 13:20，已完成）

| 步骤 | 结果 |
|---|---|
| dry-run | 2 轮修正（M7 UNIQUE 约束聚合策略、verify 表名/期望值）后全绿 |
| Step 0 预校验 | 5 项全过；ugm 2 条孤儿预告 |
| Step 1/2 备份 | 全量 `architecture.db.bak.mx_20260903_132052` + 12 张 `*_pre_mx_backup` |
| Step 3-6 迁移 | 单事务执行 M1-M11 + 计数列重算，COMMIT 成功 |
| Step 7 verify | 行数对账 9 项 OK + 孤儿引用 10 项 = 0 |
| postcheck | `staging_postcheck.py` **16/16 ALL GREEN**（含真实登录、菜单、SCP 权限矩阵非空） |

执行细节：
- M2 953 插入 + 1 去重（admin 既有权限行重叠）；M9 58 插入 + 1 去重；M10 4 插入 + 1 去重 + 2 孤儿跳过
- M7 发现 staging `data_permissions` 有 UNIQUE(user_id, resource_type, resource_id) 而 prod 允许同 key 多级别 → 聚合到最高级别（admin > write > read）：21 插入 + 2 升级 + 59 去重
- 迁移脚本：`tools/migrate_prod_perm_to_staging.py`（dry-run / --apply / --status / --downgrade 四模式）
- 回滚资产：`--downgrade` 从备份表恢复；全量备份 `architecture.db.bak.mx_20260903_132052`

---

## 7. 后续事项（非本方案范围）

1. v080/v081 补账：清理 staging 遗留旧表 roles/user_groups/group_roles（迁移验证通过后执行）
2. postmortem 文档补充本次迁移经验教训
3. 长期：将"prod 基准数据 seed"沉淀为 vNNN migration（v079 模式），替代一次性脚本
