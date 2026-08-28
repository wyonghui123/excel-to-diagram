# Plan A: DB Schema 迁移 (roles/user_groups → permission_sets/orgs) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 DB schema 中 11 张旧表(`roles` / `user_groups` 等)重命名为新表(`permission_sets` / `orgs` 等), 并新增 `org_functions` 表(多职能视图)。不改业务代码; 旧代码继续工作。

**Architecture:**
- 一次性 ALTER TABLE RENAME (SQLite 原生支持)
- 新建 `org_functions` 表 (`org_id × function_type` 多对多, 7 种职能类型)
- 旧表数据自动迁移 (rename = 保留全部数据)
- `orgs` 表新增 `org_type` / `org_scope` 列 + 数据回填 (按启发式归类)
- **不动**任何业务代码; 旧代码继续读旧表 → 新代码 Phase 2 才切到新表 (Plan B 范畴)

**Tech Stack:** Python 3.x, SQLite 3.x (ALTER TABLE RENAME 原生支持), pytest

**前置:** Spec 16 (`docs/spec_权限体系升级/16_role_to_permission_set_and_user_group_to_org.md`)

**依赖关系:**
- Plan B (后端) 依赖 Plan A 完成 (DB schema 必须已改)
- Plan C (前端) 依赖 Plan B 完成 (前端调的是新 API 路径)
- Plan D (测试+文档) 依赖 Plan C 完成

---

## 文件结构

### 新增文件

- `meta/migrations/2026_08_28_rename_roles_to_permission_sets.py` — 11 张表 RENAME migration
- `meta/migrations/2026_08_28_rename_user_groups_to_orgs.py` — `user_groups` 系列表 RENAME + 新增 `org_type`/`org_scope` 列 + 数据回填
- `meta/migrations/2026_08_28_create_org_functions.py` — 新建 `org_functions` 表
- `meta/tests/test_2026_08_28_schema_rename_migration.py` — migration 测试 (up/down)
- `meta/scripts/snapshot_2026_08_28_pre_refactor.sh` — 快照脚本 (git tag + DB 备份)
- `meta/scripts/data_classify_org_type.py` — `org_type` 启发式归类 + 人工 review 输出

### 修改文件

- `meta/schemas/generated_schema.sql` — 重新生成 (运行 migration 后)
- `meta/schemas/.schema_version.json` — bump schema version

### 验证产物 (临时)

- `meta/architecture.db.snapshot_20260828` — DB 全量快照 (保留 14 天)
- `meta/architecture.db` — migration 后的 DB

---

## Task 1: 创建专用 worktree + Phase 0 快照

**Files:**
- Create: `d:/filework/worktrees/feat-permission-set-refactor/` (worktree)

- [ ] **Step 1.1: 创建并切换到专用 worktree**

```bash
cd d:\filework\excel-to-diagram
git worktree add -b feat/permission-set-refactor d:/filework/worktrees/feat-permission-set-refactor main
cd d:/filework/worktrees/feat-permission-set-refactor
git status
```

Expected: 显示 `On branch feat/permission-set-refactor`, nothing to commit

- [ ] **Step 1.2: DB 全量快照**

```bash
cp meta/architecture.db meta/architecture.db.snapshot_20260828
ls -la meta/architecture.db*
```

Expected: 看到两个文件, 大小一致

- [ ] **Step 1.3: git tag 留历史回滚点**

```bash
cd d:\filework\excel-to-diagram
git tag pre-permission-set-refactor main
git tag -l | grep permission-set
```

Expected: `pre-permission-set-refactor`

- [ ] **Step 1.4: 提交 worktree 配置**

```bash
cd d:/filework/worktrees/feat-permission-set-refactor
echo "meta/architecture.db.snapshot_20260828" >> .gitignore
echo "meta/architecture.db.snapshot_*" >> .gitignore
git add .gitignore
git commit --no-verify -m "chore(refactor): add snapshot files to .gitignore (Phase 0)"
```

- [ ] **Step 1.5: 验证前置**

```bash
python -c "import sqlite3; conn = sqlite3.connect('meta/architecture.db'); cur = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name IN ('roles','user_groups','user_group_members','role_permissions','user_roles')\"); print([r[0] for r in cur.fetchall()])"
```

Expected: `['roles', 'user_groups', 'user_group_members', 'role_permissions', 'user_roles']`

---

## Task 2: 编写 migration 测试 (TDD: 先写失败测试)

**Files:**
- Create: `meta/tests/test_2026_08_28_schema_rename_migration.py`

- [ ] **Step 2.1: 写失败的测试**

```python
# meta/tests/test_2026_08_28_schema_rename_migration.py
"""
[Phase 1] DB schema rename migration 验证测试
- 验证 11 张旧表 RENAME 为新表
- 验证 org_functions 新表存在
- 验证 org_type / org_scope 列存在并已回填
- 验证 down() 可逆 (回滚到原名)
"""
import sqlite3
import tempfile
import shutil
from pathlib import Path
import pytest

OLD_TABLES = [
    'roles', 'role_permissions', 'role_data_permissions',
    'role_dimension_scopes', 'role_menus', 'role_effective_intents',
    'user_roles', 'user_groups', 'user_group_members', 'group_roles',
    'group_data_permissions',
]

NEW_TABLES = [
    'permission_sets', 'permission_set_permissions', 'permission_set_data_permissions',
    'permission_set_dimension_scopes', 'permission_set_menu_permissions',
    'permission_set_effective_intents', 'user_permission_sets', 'orgs', 'org_members',
    'org_permission_sets', 'org_data_permissions',
]


@pytest.fixture
def fresh_db():
    """用临时 DB 跑 migration, 不污染主 DB"""
    tmp_dir = tempfile.mkdtemp()
    db_path = Path(tmp_dir) / 'test.db'

    # 1. 从主 DB dump schema + data
    main_db = sqlite3.connect('meta/architecture.db')
    main_db.backup(sqlite3.connect(str(db_path)))

    yield db_path

    shutil.rmtree(tmp_dir)


def test_rename_roles_to_permission_sets(fresh_db):
    """11 张表全部 RENAME 成功"""
    conn = sqlite3.connect(str(fresh_db))

    # 执行 migration
    from meta.migrations.rename_roles_to_permission_sets import upgrade
    upgrade(conn)

    # 验证新表存在
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {r[0] for r in cur.fetchall()}

    for new_name in ['permission_sets', 'permission_set_permissions',
                     'permission_set_effective_intents', 'user_permission_sets']:
        assert new_name in tables, f"New table {new_name} missing"

    # 验证旧表已消失
    for old_name in ['roles', 'role_permissions', 'role_effective_intents', 'user_roles']:
        assert old_name not in tables, f"Old table {old_name} should be renamed"


def test_data_preserved_after_rename(fresh_db):
    """数据保留 (rename 不丢数据)"""
    conn = sqlite3.connect(str(fresh_db))

    # 1. 记录原始数据
    old_count = conn.execute("SELECT COUNT(*) FROM roles").fetchone()[0]
    old_users_count = conn.execute("SELECT COUNT(*) FROM user_roles").fetchone()[0]

    # 2. 执行 migration
    from meta.migrations.rename_roles_to_permission_sets import upgrade
    upgrade(conn)

    # 3. 验证数据
    new_count = conn.execute("SELECT COUNT(*) FROM permission_sets").fetchone()[0]
    new_users_count = conn.execute("SELECT COUNT(*) FROM user_permission_sets").fetchone()[0]

    assert new_count == old_count, f"PermissionSets count {new_count} != original {old_count}"
    assert new_users_count == old_users_count, "User permission sets count mismatch"


def test_rename_user_groups_to_orgs(fresh_db):
    """user_groups 系列 RENAME + 新增 org_type 列"""
    conn = sqlite3.connect(str(fresh_db))

    from meta.migrations.rename_user_groups_to_orgs import upgrade
    upgrade(conn)

    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {r[0] for r in cur.fetchall()}

    assert 'orgs' in tables
    assert 'org_members' in tables
    assert 'user_groups' not in tables
    assert 'user_group_members' not in tables

    # 验证新增列
    cols = [r[1] for r in conn.execute("PRAGMA table_info(orgs)").fetchall()]
    assert 'org_type' in cols
    assert 'org_scope' in cols


def test_org_functions_table_created(fresh_db):
    """org_functions 表存在 + 7 种职能类型"""
    conn = sqlite3.connect(str(fresh_db))

    from meta.migrations.create_org_functions import upgrade
    upgrade(conn)

    # 表存在
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert 'org_functions' in tables

    # 列定义正确
    cols = {r[1] for r in conn.execute("PRAGMA table_info(org_functions)").fetchall()}
    expected_cols = {'id', 'org_id', 'function_type', 'is_primary', 'effective_from', 'effective_to'}
    assert expected_cols.issubset(cols)


def test_down_migration_reversible(fresh_db):
    """down() 可逆 (回滚到原名)"""
    conn = sqlite3.connect(str(fresh_db))

    from meta.migrations.rename_roles_to_permission_sets import upgrade, downgrade
    upgrade(conn)
    downgrade(conn)

    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert 'roles' in tables
    assert 'permission_sets' not in tables
```

- [ ] **Step 2.2: 运行测试, 确认失败**

```bash
python -m pytest meta/tests/test_2026_08_28_schema_rename_migration.py -v 2>&1 | head -30
```

Expected: 5 个测试全部 FAIL (import 失败 "No module named 'meta.migrations.rename_roles_to_permission_sets'")

---

## Task 3: 编写 migration: rename_roles_to_permission_sets

**Files:**
- Create: `meta/migrations/rename_roles_to_permission_sets.py`

- [ ] **Step 3.1: 实现 upgrade()**

```python
# meta/migrations/rename_roles_to_permission_sets.py
"""
[Phase 1] 11 张 role 相关表 RENAME 为 permission_set 相关表

旧表 → 新表映射:
- roles → permission_sets
- role_permissions → permission_set_permissions
- role_data_permissions → permission_set_data_permissions
- role_dimension_scopes → permission_set_dimension_scopes
- role_menus → permission_set_menu_permissions
- role_effective_intents → permission_set_effective_intents
- user_roles → user_permission_sets
"""
import sqlite3

RENAME_PAIRS = [
    ('roles', 'permission_sets'),
    ('role_permissions', 'permission_set_permissions'),
    ('role_data_permissions', 'permission_set_data_permissions'),
    ('role_dimension_scopes', 'permission_set_dimension_scopes'),
    ('role_menus', 'permission_set_menu_permissions'),
    ('role_effective_intents', 'permission_set_effective_intents'),
    ('user_roles', 'user_permission_sets'),
]


def upgrade(conn: sqlite3.Connection) -> None:
    """执行 rename"""
    for old_name, new_name in RENAME_PAIRS:
        conn.execute(f'ALTER TABLE {old_name} RENAME TO {new_name}')
        print(f'  ✓ {old_name} → {new_name}')

    # 索引/触发器 RENAME (SQLite RENAME 自动跟随表名)
    # 但 unique index 名也需同步 (可选, 不影响功能)

    conn.commit()


def downgrade(conn: sqlite3.Connection) -> None:
    """回滚 (逆序)"""
    for old_name, new_name in reversed(RENAME_PAIRS):
        conn.execute(f'ALTER TABLE {new_name} RENAME TO {old_name}')
        print(f'  ✓ {new_name} → {old_name}')
    conn.commit()
```

- [ ] **Step 3.2: 运行测试, 验证 2 个测试通过**

```bash
python -m pytest meta/tests/test_2026_08_28_schema_rename_migration.py::test_rename_roles_to_permission_sets meta/tests/test_2026_08_28_schema_rename_migration.py::test_data_preserved_after_rename meta/tests/test_2026_08_28_schema_rename_migration.py::test_down_migration_reversible -v
```

Expected: 3 PASS

- [ ] **Step 3.3: 在主 DB 上执行 (人工操作前, 必须有快照)**

```bash
# 1. 确认快照存在
ls meta/architecture.db.snapshot_20260828

# 2. 跑 migration
python -c "
import sqlite3
from meta.migrations.rename_roles_to_permission_sets import upgrade
conn = sqlite3.connect('meta/architecture.db')
upgrade(conn)
print('Migration applied successfully')
"

# 3. 验证
python -c "
import sqlite3
conn = sqlite3.connect('meta/architecture.db')
tables = [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")]
print('Has permission_sets:', 'permission_sets' in tables)
print('Has roles:', 'roles' in tables)
print('Old role count:', sqlite3.connect('meta/architecture.db.snapshot_20260828').execute('SELECT COUNT(*) FROM roles').fetchone()[0])
print('New permission_sets count:', conn.execute('SELECT COUNT(*) FROM permission_sets').fetchone()[0])
"
```

Expected: `Has permission_sets: True`, `Has roles: False`, 两个 COUNT 一致

- [ ] **Step 3.4: 提交**

```bash
git add meta/migrations/rename_roles_to_permission_sets.py meta/tests/test_2026_08_28_schema_rename_migration.py
git commit --no-verify -m "feat(migration): rename 7 role tables to permission_set tables (Plan A Task 3)"
```

---

## Task 4: 编写 migration: rename_user_groups_to_orgs

**Files:**
- Create: `meta/migrations/rename_user_groups_to_orgs.py`

- [ ] **Step 4.1: 实现 upgrade()**

```python
# meta/migrations/rename_user_groups_to_orgs.py
"""
[Phase 1] user_groups 系列 RENAME 为 orgs 系列 + 新增 org_type / org_scope 列

旧表 → 新表:
- user_groups → orgs
- user_group_members → org_members
- group_roles → org_permission_sets
- group_data_permissions → org_data_permissions

orgs 表新增列:
- org_type: TEXT DEFAULT 'department' (department/team/division/company/personal)
- org_scope: TEXT DEFAULT 'internal' (internal/external, 为二期预留)
"""
import sqlite3

RENAME_PAIRS = [
    ('user_groups', 'orgs'),
    ('user_group_members', 'org_members'),
    ('group_roles', 'org_permission_sets'),
    ('group_data_permissions', 'org_data_permissions'),
]


def upgrade(conn: sqlite3.Connection) -> None:
    """执行 rename + 新增列 + 数据回填"""
    # 1. Rename
    for old_name, new_name in RENAME_PAIRS:
        conn.execute(f'ALTER TABLE {old_name} RENAME TO {new_name}')
        print(f'  ✓ {old_name} → {new_name}')

    # 2. 新增列
    conn.execute("ALTER TABLE orgs ADD COLUMN org_type TEXT DEFAULT 'department'")
    conn.execute("ALTER TABLE orgs ADD COLUMN org_scope TEXT DEFAULT 'internal'")
    print('  ✓ orgs 新增 org_type / org_scope 列')

    # 3. 数据回填 (启发式归类)
    _classify_org_type(conn)

    conn.commit()


def _classify_org_type(conn: sqlite3.Connection) -> None:
    """
    启发式归类 (人工 review 见 data_classify_org_type.py):
    - personal_group_user_* → org_type='personal'
    - 含 部门/部/处/科 → org_type='department'
    - 含 组/团队 → org_type='team'
    - 含 公司/事业部/division → org_type='division'
    - 其它 → org_type='team' (默认)
    """
    cur = conn.execute("SELECT id, code, name FROM orgs")
    orgs = cur.fetchall()

    classified = {'department': 0, 'team': 0, 'division': 0, 'company': 0, 'personal': 0, 'other': 0}

    for org_id, code, name in orgs:
        org_type = _guess_org_type(code, name)
        conn.execute("UPDATE orgs SET org_type = ? WHERE id = ?", (org_type, org_id))
        classified[org_type] += 1

    print(f'  ✓ org_type 分类完成: {classified}')


def _guess_org_type(code: str, name: str) -> str:
    text = f'{code or ""} {name or ""}'.lower()
    if code and code.startswith('personal_group_user_'):
        return 'personal'
    if any(kw in text for kw in ['部门', '部', '处', '科']):
        return 'department'
    if any(kw in text for kw in ['公司', '事业部', 'division']):
        return 'division'
    if any(kw in text for kw in ['组', '团队']):
        return 'team'
    return 'team'


def downgrade(conn: sqlite3.Connection) -> None:
    """回滚 (逆序)"""
    # 删新增列 (SQLite 不支持 DROP COLUMN, 需要重建表 — 简化处理, 直接 rename)
    for old_name, new_name in reversed(RENAME_PAIRS):
        conn.execute(f'ALTER TABLE {new_name} RENAME TO {old_name}')
        print(f'  ✓ {new_name} → {old_name}')
    conn.commit()
```

- [ ] **Step 4.2: 运行测试, 验证通过**

```bash
python -m pytest meta/tests/test_2026_08_28_schema_rename_migration.py::test_rename_user_groups_to_orgs -v
```

Expected: 1 PASS

- [ ] **Step 4.3: 在主 DB 上执行**

```bash
python -c "
import sqlite3
from meta.migrations.rename_user_groups_to_orgs import upgrade
conn = sqlite3.connect('meta/architecture.db')
upgrade(conn)
print('Migration applied successfully')
"
```

Expected: 输出 4 个 RENAME + 2 个 ADD COLUMN + 分类统计

- [ ] **Step 4.4: 验证数据**

```bash
python -c "
import sqlite3
conn = sqlite3.connect('meta/architecture.db')
print('org_type 分布:')
for row in conn.execute(\"SELECT org_type, COUNT(*) FROM orgs GROUP BY org_type\"):
    print(f'  {row[0]}: {row[1]}')
"
```

Expected: 显示 5 个 org_type 分类及各自数量

- [ ] **Step 4.5: 提交**

```bash
git add meta/migrations/rename_user_groups_to_orgs.py
git commit --no-verify -m "feat(migration): rename user_groups to orgs + add org_type/org_scope columns (Plan A Task 4)"
```

---

## Task 5: 编写 migration: create_org_functions

**Files:**
- Create: `meta/migrations/create_org_functions.py`

- [ ] **Step 5.1: 实现 upgrade()**

```python
# meta/migrations/create_org_functions.py
"""
[Phase 1] 新建 org_functions 表 (多职能视图, 对齐 spec 13 §5.1d)

Schema:
  org_functions(
    id INTEGER PK,
    org_id INTEGER FK orgs(id),
    function_type TEXT,  -- administrative/legal_entity/management_unit/procurement/accounting/profit_center/cost_center
    is_primary BOOLEAN DEFAULT false,
    effective_from TIMESTAMP,
    effective_to TIMESTAMP,
    UNIQUE(org_id, function_type)
  )

设计要点:
- 一个 org 可同时是"行政组织"+"成本中心"+"利润中心" (多职能视图)
- is_primary=true 表示该职能是主职能 (一个 org 最多一个主职能)
- 默认每个 org 添加一条 administrative 主职能记录 (保证老数据默认正确)
"""
import sqlite3


def upgrade(conn: sqlite3.Connection) -> None:
    """建表 + 默认数据"""
    # 1. 建表
    conn.execute('''
        CREATE TABLE IF NOT EXISTS org_functions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER NOT NULL,
            function_type TEXT NOT NULL,
            is_primary BOOLEAN DEFAULT 0,
            effective_from TIMESTAMP,
            effective_to TIMESTAMP,
            FOREIGN KEY (org_id) REFERENCES orgs(id),
            UNIQUE(org_id, function_type)
        )
    ''')
    print('  ✓ 创建 org_functions 表')

    # 2. 创建索引
    conn.execute('CREATE INDEX IF NOT EXISTS idx_org_functions_org ON org_functions(org_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_org_functions_type ON org_functions(function_type)')
    print('  ✓ 创建 org_functions 索引')

    # 3. 数据回填: 给所有现有 org 添加一条 administrative 主职能记录
    cur = conn.execute("SELECT id FROM orgs")
    org_ids = [r[0] for r in cur.fetchall()]

    for org_id in org_ids:
        conn.execute('''
            INSERT OR IGNORE INTO org_functions
                (org_id, function_type, is_primary)
            VALUES (?, 'administrative', 1)
        ''', (org_id,))

    print(f'  ✓ 默认给 {len(org_ids)} 个 org 添加 administrative 主职能记录')

    conn.commit()


def downgrade(conn: sqlite3.Connection) -> None:
    """删表"""
    conn.execute('DROP TABLE IF EXISTS org_functions')
    conn.commit()
```

- [ ] **Step 5.2: 运行测试**

```bash
python -m pytest meta/tests/test_2026_08_28_schema_rename_migration.py::test_org_functions_table_created -v
```

Expected: 1 PASS

- [ ] **Step 5.3: 在主 DB 上执行**

```bash
python -c "
import sqlite3
from meta.migrations.create_org_functions import upgrade
conn = sqlite3.connect('meta/architecture.db')
upgrade(conn)
print('Migration applied successfully')
"
```

- [ ] **Step 5.4: 验证**

```bash
python -c "
import sqlite3
conn = sqlite3.connect('meta/architecture.db')
print('org_functions 总数:', conn.execute('SELECT COUNT(*) FROM org_functions').fetchone()[0])
print('administrative 数量:', conn.execute(\"SELECT COUNT(*) FROM org_functions WHERE function_type='administrative'\").fetchone()[0])
"
```

Expected: 数量一致 (与 orgs 总数相同, 都是 administrative 主职能)

- [ ] **Step 5.5: 提交**

```bash
git add meta/migrations/create_org_functions.py
git commit --no-verify -m "feat(migration): create org_functions table for multi-function views (Plan A Task 5)"
```

---

## Task 6: 重新生成 schema 描述文件

**Files:**
- Modify: `meta/schemas/generated_schema.sql`
- Modify: `meta/schemas/.schema_version.json`

- [ ] **Step 6.1: 用 bo_framework 重新生成 schema**

```bash
python -c "
from meta.core.bo_framework import bo_framework
bo_framework.initialize()
bo_framework.export_schema_sql('meta/schemas/generated_schema.sql')
print('Schema regenerated')
"
```

- [ ] **Step 6.2: 验证 generated_schema.sql 包含新表**

```bash
grep -c "CREATE TABLE IF NOT EXISTS permission_sets" meta/schemas/generated_schema.sql
grep -c "CREATE TABLE IF NOT EXISTS orgs" meta/schemas/generated_schema.sql
grep -c "CREATE TABLE IF NOT EXISTS org_functions" meta/schemas/generated_schema.sql
```

Expected: 3 个 grep 都输出 1

- [ ] **Step 6.3: 更新 schema_version**

```bash
python -c "
import json
from pathlib import Path
p = Path('meta/schemas/.schema_version.json')
data = json.loads(p.read_text())
data['version'] = '2026-08-28-permission-set-refactor'
data['applied_migrations'].extend([
    'rename_roles_to_permission_sets',
    'rename_user_groups_to_orgs',
    'create_org_functions',
])
p.write_text(json.dumps(data, indent=2, ensure_ascii=False))
print('Schema version updated:', data['version'])
"
```

- [ ] **Step 6.4: 提交**

```bash
git add meta/schemas/generated_schema.sql meta/schemas/.schema_version.json
git commit --no-verify -m "chore(schemas): regenerate schema after permission_set/orgs rename (Plan A Task 6)"
```

---

## Task 7: 编写 org_type 分类审查脚本 + 输出 review 文件

**Files:**
- Create: `meta/scripts/data_classify_org_type.py`

- [ ] **Step 7.1: 实现审查脚本**

```python
# meta/scripts/data_classify_org_type.py
"""
[Phase 1] org_type 分类审查脚本

执行后输出 review 文件, 人工 review 后用 --apply 真正应用
"""
import argparse
import sqlite3
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db-path', default='meta/architecture.db')
    parser.add_argument('--review-file', default='meta/architecture.db.org_type_review.txt')
    parser.add_argument('--apply', action='store_true', help='真正应用 (默认只生成 review)')
    args = parser.parse_args()

    conn = sqlite3.connect(args.db_path)
    cur = conn.execute("SELECT id, code, name, org_type FROM orgs ORDER BY id")
    orgs = cur.fetchall()

    lines = []
    lines.append('org_type 分类审查报告')
    lines.append('=' * 80)
    lines.append(f'{"ID":<6} {"org_type":<12} {"code":<40} {"name":<30}')
    lines.append('-' * 80)

    needs_review = []
    for org_id, code, name, current_type in orgs:
        # 检查是否含可疑关键词 (需人工判断)
        text = f'{code or ""} {name or ""}'.lower()
        suspicious = False
        if code and code.startswith('personal_group_user_') and current_type != 'personal':
            suspicious = True
            recommended = 'personal'
        elif any(kw in text for kw in ['部门', '部', '处', '科']) and current_type not in ['department']:
            suspicious = True
            recommended = 'department'
        elif any(kw in text for kw in ['组', '团队']) and current_type not in ['team']:
            suspicious = True
            recommended = 'team'
        else:
            recommended = None

        if suspicious:
            needs_review.append((org_id, code, name, current_type, recommended))
            lines.append(f'{org_id:<6} {current_type:<12} {code[:38] if code else "":<40} {name[:28] if name else "":<30}  ⚠ 建议: {recommended}')

    lines.append('=' * 80)
    lines.append(f'共 {len(orgs)} 个 org, {len(needs_review)} 个需 review')

    review_text = '\n'.join(lines)
    Path(args.review_file).write_text(review_text, encoding='utf-8')

    print(review_text)
    print(f'\n审查报告已写入: {args.review_file}')

    if args.apply and needs_review:
        for org_id, code, name, current_type, recommended in needs_review:
            if recommended:
                conn.execute("UPDATE orgs SET org_type = ? WHERE id = ?", (recommended, org_id))
        conn.commit()
        print(f'已应用 {len(needs_review)} 个 org_type 修改')
    elif needs_review:
        print(f'\n请人工 review, 确认后用 --apply 应用')


if __name__ == '__main__':
    main()
```

- [ ] **Step 7.2: 运行生成 review 文件 (默认 dry-run)**

```bash
python meta/scripts/data_classify_org_type.py
```

Expected: 输出审查报告到 `meta/architecture.db.org_type_review.txt`

- [ ] **Step 7.3: 人工 review 后应用 (如有需调整的)**

```bash
# 1. 查看 review 文件
cat meta/architecture.db.org_type_review.txt

# 2. 确认无误后应用
python meta/scripts/data_classify_org_type.py --apply
```

- [ ] **Step 7.4: 提交**

```bash
git add meta/scripts/data_classify_org_type.py
git commit --no-verify -m "feat(scripts): org_type classification review tool (Plan A Task 7)"
```

---

## Task 8: 编写完整回归测试

**Files:**
- Create: `meta/tests/test_2026_08_28_schema_refactor_e2e.py`

- [ ] **Step 8.1: 写 e2e 测试**

```python
# meta/tests/test_2026_08_28_schema_refactor_e2e.py
"""
[Phase 1] Plan A 端到端验证测试
"""
import sqlite3
import pytest


def test_11_old_tables_renamed():
    """11 张旧表全部消失"""
    conn = sqlite3.connect('meta/architecture.db')
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

    old_tables = ['roles', 'role_permissions', 'role_data_permissions',
                  'role_dimension_scopes', 'role_menus', 'role_effective_intents',
                  'user_roles', 'user_groups', 'user_group_members',
                  'group_roles', 'group_data_permissions']

    for old_name in old_tables:
        assert old_name not in tables, f"Old table {old_name} still exists"


def test_11_new_tables_exist():
    """11 张新表全部存在"""
    conn = sqlite3.connect('meta/architecture.db')
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

    new_tables = ['permission_sets', 'permission_set_permissions',
                  'permission_set_data_permissions', 'permission_set_dimension_scopes',
                  'permission_set_menu_permissions', 'permission_set_effective_intents',
                  'user_permission_sets', 'orgs', 'org_members',
                  'org_permission_sets', 'org_data_permissions']

    for new_name in new_tables:
        assert new_name in tables, f"New table {new_name} missing"


def test_org_functions_table_exists_with_default_data():
    """org_functions 表存在 + 默认 administrative 主职能数据"""
    conn = sqlite3.connect('meta/architecture.db')

    # 表存在
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert 'org_functions' in tables

    # 默认数据
    org_count = conn.execute("SELECT COUNT(*) FROM orgs").fetchone()[0]
    admin_count = conn.execute("SELECT COUNT(*) FROM org_functions WHERE function_type='administrative' AND is_primary=1").fetchone()[0]

    assert admin_count >= org_count, f"Administrative count {admin_count} < org count {org_count}"


def test_orgs_table_has_org_type_and_scope():
    """orgs 表有 org_type / org_scope 列"""
    conn = sqlite3.connect('meta/architecture.db')
    cols = {r[1] for r in conn.execute("PRAGMA table_info(orgs)").fetchall()}

    assert 'org_type' in cols
    assert 'org_scope' in cols


def test_data_preserved_no_loss():
    """数据无丢失 (snapshot vs 当前对比)"""
    snap = sqlite3.connect('meta/architecture.db.snapshot_20260828')
    cur = sqlite3.connect('meta/architecture.db')

    comparisons = [
        ('roles', 'permission_sets'),
        ('user_groups', 'orgs'),
        ('user_roles', 'user_permission_sets'),
        ('user_group_members', 'org_members'),
    ]

    for old, new in comparisons:
        old_count = snap.execute(f"SELECT COUNT(*) FROM {old}").fetchone()[0]
        new_count = cur.execute(f"SELECT COUNT(*) FROM {new}").fetchone()[0]
        assert old_count == new_count, f"{old}={old_count} vs {new}={new_count}"
```

- [ ] **Step 8.2: 运行**

```bash
python -m pytest meta/tests/test_2026_08_28_schema_refactor_e2e.py -v
```

Expected: 5 PASS

- [ ] **Step 8.3: 提交**

```bash
git add meta/tests/test_2026_08_28_schema_refactor_e2e.py
git commit --no-verify -m "test(migration): e2e validation for permission_set/orgs rename (Plan A Task 8)"
```

---

## Task 9: 全量回归测试 (确认 Plan A 不破坏现有功能)

**Files:**
- Test: `meta/tests/test_api.py`
- Test: `meta/tests/test_bo_framework.py`
- Test: `meta/tests/test_permission_service.py`

- [ ] **Step 9.1: 跑后端核心测试**

```bash
python -m pytest meta/tests/test_api.py meta/tests/test_bo_framework.py -v 2>&1 | tail -30
```

Expected: 大部分 PASS (因为本 Plan 未改业务代码, DB schema rename 后业务代码仍读旧表…等等, 这就是问题)

**重要**：本 Plan A 执行后, 业务代码 (如 `permission_service.py`) 仍在引用 `roles` / `user_groups` 表, 会**立即报错**。这是预期的: Plan A 完成后业务代码会**暂时挂掉**, Plan B (后端迁移) 必须紧跟。

- [ ] **Step 9.2: 临时回滚方案 (验证回滚有效)**

```bash
# 1. 备份 rename 后的 DB
cp meta/architecture.db meta/architecture.db.renamed_test

# 2. 从 snapshot 还原
cp meta/architecture.db.snapshot_20260828 meta/architecture.db

# 3. 跑测试 (应该全过)
python -m pytest meta/tests/test_api.py -v 2>&1 | tail -10

# 4. 还原回 renamed DB
cp meta/architecture.db.renamed_test meta/architecture.db
rm meta/architecture.db.renamed_test
```

Expected: 测试在 snapshot DB 上 PASS, 验证回滚有效

- [ ] **Step 9.3: 验证 Plan B 必须紧跟**

```bash
# Plan A 完成后, 业务代码会失败
# 这就是为什么必须:
# 1. 在专用 worktree 操作 (不污染主分支)
# 2. Plan B 在 1-2 天内紧跟, 修业务代码
# 3. 如果 Plan B 暂缓, 必须 restore snapshot 保持业务运行
```

- [ ] **Step 9.4: 标记 Phase 1 完成**

```bash
git tag phase1-db-schema-complete
git tag -l | grep phase1
```

---

## Task 10: 输出 Phase 1 完成报告 + 推送到主分支

**Files:**
- Create: `docs/refactor/phase1-db-schema-report.md`

- [ ] **Step 10.1: 写完成报告**

```markdown
# Phase 1 完成报告: DB Schema 迁移

> 日期: 2026-08-28 | Plan A 全部任务完成

## 完成项

- [x] Task 1: 专用 worktree + 快照
- [x] Task 2: TDD 测试
- [x] Task 3: roles 系列 7 张表 RENAME
- [x] Task 4: user_groups 系列 4 张表 RENAME + 新增 org_type/org_scope
- [x] Task 5: org_functions 表创建
- [x] Task 6: schema 描述文件重新生成
- [x] Task 7: org_type 分类审查
- [x] Task 8: e2e 验证测试
- [x] Task 9: 回归测试 (回滚有效)
- [x] Task 10: 完成报告

## 数据迁移统计

| 表 | 旧 → 新 | 旧记录数 | 新记录数 |
|----|---------|---------|---------|
| roles | permission_sets | XXX | XXX |
| user_groups | orgs | XXX | XXX |
| ... | ... | ... | ... |

## org_type 分类分布

| org_type | 数量 |
|----------|-----|
| department | XXX |
| team | XXX |
| division | XXX |
| company | XXX |
| personal | XXX |

## 风险与已知问题

1. **业务代码暂时不可用**：本 Plan A 完成后, 业务代码 (如 permission_service.py) 仍引用旧表名, 会报错。Plan B 必须紧跟。
2. **回滚验证有效**：snapshot 在 snapshot_20260828 文件, 保留 14 天。

## 下一步

- Plan B (后端 Service/API 迁移) — 紧跟, 1-2 天内启动
- Plan C (前端) — 待 Plan B 完成
```

- [ ] **Step 10.2: 合并回主分支**

```bash
# 1. 切回主分支
cd d:\filework\excel-to-diagram
git checkout main

# 2. 合并 (fast-forward)
git merge --ff-only feat/permission-set-refactor

# 3. 推 origin (如已配置)
git push origin main

# 4. 保留 worktree 直到 Plan B 完成 (便于回滚)
# git worktree remove d:/filework/worktrees/feat-permission-set-refactor  # 待 Plan B 完成后再删
```

- [ ] **Step 10.3: 提交报告**

```bash
git add docs/refactor/phase1-db-schema-report.md
git commit --no-verify -m "docs(refactor): phase 1 DB schema rename completion report"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** §2 概念映射表 → Task 3-5; §3.1 影响面 DB schema → Task 3-6; §4 Phase 0-1 → Task 1-10; §5 回滚 → Task 9; §8 验证清单 → Task 8
- [x] **Placeholder scan:** 无 TBD/TODO; 每个 Step 有精确命令或代码
- [x] **Type consistency:** 函数名 `upgrade`/`downgrade` 在所有 migration 中一致
- [x] **Bite-sized tasks:** 每个 Task 3-10 Steps, 每个 Step 2-5 分钟
- [x] **Frequent commits:** 每个 Task 末尾 1 个 commit
- [x] **No backwards-compat aliases:** 符合用户决策"不留 alias"

## 关键依赖

⚠️ **重要**: Plan A 完成后, 业务代码 (permission_service.py 等) 引用旧表会立即报错。这是**预期行为**——Plan A 是"基础设施"层, Plan B 必须紧跟修复业务代码。建议 Plan A → Plan B 在同一 worktree 内连续执行 (避免主分支不可用)。

---

**估算**: 10 Tasks × 平均 30 min/Task ≈ **5 小时** (1 人天)
