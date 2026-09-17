"""
[v079 2026-09-01] seed permission_set_dimension_scopes (production 模板).

背景 (Spec 16 / v070 后遗症):
  v070__rename_roles_to_permission_sets 把 role_dimension_scopes 重命名为
  permission_set_dimension_scopes, 但只重命名表, 不填数据.
  当一个新环境从 v070 顺序跑下来, 这张表是空的, 需要 seed 一份 production 的
  scope 配置 (SCMEDIT/BIZ-AREA-ROLE/FIN-AREA-ROLE/HRM-AREA-ROLE/SS-SUBDOMAIN-ROLE/...
  共 37 个非空 scope, admin ps=1 已自带 1 条 scope 所以 v079 不重复插入).

来源:
  2026-09-01 从 production 导出的 permission_set_dimension_scopes 实际行.
  涵盖 yonyou BIP 云架构数据的 6 个 AREA + 9 个 EDIT + 1 个产品 + 21 个子领域
  角色, 与 production admin/editor/viewer 之外的 36 个非系统角色一一对应.
  ps=1 (admin) 和 ps=2 (editor) / ps=3 (viewer) 不在此 migration 范围内:
    - ps=1 admin 的 scope 已在原系统中存在 (不在 v079 seed 列表)
    - ps=2/3 editor/viewer 的 scope 故意为空 (无维度限制 = 全局可见, 由维度引擎
      默认行为处理, 不属于 "需要 seed 的 production 模板")

适用:
  - localhost 全新部署 (从 v070 起跑, 无 v079 seed)
  - staging (本次修复目标)
  - 全新部署的 production (从 v070 起跑)
  - 已部署的 production: 重复执行幂等 (permission_set_id+dimension_code 唯一)

幂等性:
  PRIMARY KEY (id) AUTOINCREMENT.
  检查 permission_set_id+dimension_code 是否已存在, 已存在则跳过 INSERT.
  备份策略: 整个表复制到 permission_set_dimension_scopes_pre_v079_backup
  (与 v078 备份模式一致, 不破坏现有数据).

downgrade:
  从 permission_set_dimension_scopes_pre_v079_backup 恢复行, 删除 v079 插入的 id.

规范遵循 (meta/migrations/README.md §2):
- 文件命名 v079__seed_permission_set_dimension_scopes.py
- 入口签名 migrate(db_path, skip_backup=False) -> bool
- 幂等性 + verify() + downgrade()
"""
import json
import sqlite3
from pathlib import Path
from typing import List, Tuple

# (permission_set_id, dimension_code, scope_mode, dimension_values_json, inherit_children)
# 数据来源: 2026-09-01 production dump (permission_set_dimension_scopes 表)
SEED_SCOPES: List[Tuple[int, str, str, str, int]] = [
    # AREA 角色 (按 domain 划分)
    (897, 'domain', 'include', '[8]', 1),
    (1195, 'domain', 'include', '[15, 14, 12, 11, 8, 9, 17]', 1),
    (1196, 'domain', 'include', '[13]', 1),
    (1197, 'domain', 'include', '[7]', 1),
    # SS / MM sub_domain 角色
    (1198, 'sub_domain', 'include', '[64]', 1),
    (1199, 'sub_domain', 'include', '[60]', 1),
    # 产品角色 (YonBIP)
    (1200, 'product', 'include', '[2]', 1),
    # 云架构 EDIT 角色 (按 domain 划分)
    (1203, 'domain', 'include', '[9]', 1),   # MFGEDIT
    (1204, 'domain', 'include', '[10]', 1),  # COLLEDIT
    (1205, 'domain', 'include', '[11]', 1),  # HTEDIT
    (1206, 'domain', 'include', '[12]', 1),  # MKTEDIT
    (1207, 'domain', 'include', '[13]', 1),  # FINEDIT
    (1208, 'domain', 'include', '[14]', 1),  # AMEDIT
    (1209, 'domain', 'include', '[15]', 1),  # PROCEDIT
    (1210, 'domain', 'include', '[17]', 1),  # PMEDIT
    # 子领域 EDIT 角色 (按 sub_domain 划分)
    (1211, 'sub_domain', 'include', '[55]', 1),  # FIROLE
    (1212, 'sub_domain', 'include', '[50]', 1),  # COROLE
    (1213, 'sub_domain', 'include', '[49]', 1),  # TAXROLE
    (1214, 'sub_domain', 'include', '[56]', 1),  # TRROLE
    (1215, 'sub_domain', 'include', '[57]', 1),  # FKCROLE
    (1216, 'sub_domain', 'include', '[28]', 1),  # FAROLE
    (1217, 'sub_domain', 'include', '[33]', 1),  # GLROLE
    (1218, 'sub_domain', 'include', '[43]', 1),  # EAFROLE
    (1219, 'sub_domain', 'include', '[34]', 1),  # BMROLE
    (1220, 'sub_domain', 'include', '[41]', 1),  # AMPROLE
    (1221, 'sub_domain', 'include', '[46]', 1),  # EAF2ROLE
    (1222, 'sub_domain', 'include', '[79]', 1),  # COMPROLE
    (1223, 'sub_domain', 'include', '[76]', 1),  # COREHRROLE
    (1224, 'sub_domain', 'include', '[74]', 1),  # DGHRROLE
    (1225, 'sub_domain', 'include', '[72]', 1),  # EMPMGTROLE
    (1226, 'sub_domain', 'include', '[15]', 1),  # HRMROLE
    (1227, 'sub_domain', 'include', '[69]', 1),  # HRPUBROLE
    (1228, 'sub_domain', 'include', '[77]', 1),  # MBOROLE
    (1229, 'sub_domain', 'include', '[78]', 1),  # ORGMEMPROLE
    (1230, 'sub_domain', 'include', '[73]', 1),  # SOEAPPROLE
    (1231, 'sub_domain', 'include', '[70]', 1),  # TALDEVROLE
    (1232, 'sub_domain', 'include', '[75]', 1),  # TMROLE
]

BACKUP_TABLE = 'permission_set_dimension_scopes_pre_v079_backup'
TARGET_TABLE = 'permission_set_dimension_scopes'

# migration runner 通过 SHA256 checksum 检测内容变更.
# 任何修改此文件需同步更新 CHECKSUMS, 否则 runner 会拒绝加载.
# 这里固定一个版本戳让 file mtime 变化时 checksum 也变化.
SEED_VERSION = '2026-09-01'


def _table_exists(conn, name):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _create_backup(conn):
    """备份整个 permission_set_dimension_scopes 表.

    Returns True if backup was created, False if already exists (idempotent).
    """
    if not _table_exists(conn, TARGET_TABLE):
        print(f'  [v079] {TARGET_TABLE} 不存在, 跳过备份')
        return False
    if _table_exists(conn, BACKUP_TABLE):
        print(f'  [v079] {BACKUP_TABLE} 已存在 (v079 已运行), 跳过备份')
        return False

    schema_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (TARGET_TABLE,),
    ).fetchone()
    if not schema_row or not schema_row[0]:
        print(f'  [v079] 无法获取 {TARGET_TABLE} schema, 跳过备份')
        return False

    conn.execute(f"CREATE TABLE {BACKUP_TABLE} AS SELECT * FROM {TARGET_TABLE} WHERE 0")
    conn.execute(f"INSERT INTO {BACKUP_TABLE} SELECT * FROM {TARGET_TABLE}")
    cnt = conn.execute(f"SELECT COUNT(*) FROM {BACKUP_TABLE}").fetchone()[0]
    print(f'  [v079] backed up {cnt} rows: {TARGET_TABLE} -> {BACKUP_TABLE}')
    return True


def _get_ps_column(conn):
    """Detect FK column: permission_set_id (post-v070) or role_id (pre-v070)."""
    cur = conn.execute(f"PRAGMA table_info({TARGET_TABLE})")
    cols = {row[1] for row in cur.fetchall()}
    if 'permission_set_id' in cols:
        return 'permission_set_id'
    if 'role_id' in cols:
        return 'role_id'
    raise RuntimeError(
        f'[v079] {TARGET_TABLE} has neither permission_set_id nor role_id column. '
        f'Found: {sorted(cols)}'
    )


def _seed_one(conn, ps_id, dim_code, scope_mode, dim_values_json, inherit_children, ps_col):
    """INSERT OR IGNORE 一行 dimension scope.

    幂等: 通过 (ps_col, dimension_code) 唯一约束跳过重复.
    注意: 该表原生没有 UNIQUE 约束, 所以这里手动 SELECT 检查.
    """
    # 检查是否已存在
    cur = conn.execute(
        f"SELECT id FROM {TARGET_TABLE} "
        f"WHERE {ps_col} = ? AND dimension_code = ?",
        [ps_id, dim_code],
    )
    if cur.fetchone() is not None:
        return False  # 已存在, 跳过

    # 校验 dimension_values 是合法 JSON
    try:
        json.loads(dim_values_json)
    except (json.JSONDecodeError, TypeError) as e:
        raise ValueError(
            f'[v079] invalid JSON for ps={ps_id} dim={dim_code}: {dim_values_json!r} ({e})'
        )

    conn.execute(
        f"INSERT INTO {TARGET_TABLE} "
        f"(dimension_code, dimension_values, inherit_children, scope_mode, "
        f" {ps_col}, created_by, updated_by, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
        [dim_code, dim_values_json, inherit_children, scope_mode,
         ps_id, 'v079_seed', 'v079_seed'],
    )
    return True


def _migrate_impl(db_path):
    if not db_path.exists():
        print(f'[v079] DB 不存在: {db_path}')
        return False

    if not db_path.parent.exists():
        print(f'[v079] DB parent dir 不存在: {db_path.parent}')
        return False

    conn = sqlite3.connect(str(db_path))
    try:
        print(f'[v079] seed version: {SEED_VERSION}')

        if not _table_exists(conn, TARGET_TABLE):
            print(f'[v079] {TARGET_TABLE} 不存在, 请先跑 v070__rename_roles_to_permission_sets')
            return False

        print(f'[v079] step 1: backup {TARGET_TABLE} -> {BACKUP_TABLE}')
        _create_backup(conn)

        # 校验 permission_set_id 必须存在 (防御误 seed)
        ps_ids = sorted({row[0] for row in SEED_SCOPES})
        ph = ','.join('?' * len(ps_ids))
        cur = conn.execute(
            f"SELECT id FROM permission_sets WHERE id IN ({ph})",
            ps_ids,
        )
        existing = {row[0] for row in cur.fetchall()}
        missing = set(ps_ids) - existing
        if missing:
            raise ValueError(
                f'[v079] 以下 permission_set_id 在 permission_sets 表中不存在, '
                f'请先创建角色: {sorted(missing)}'
            )

        print(f'[v079] step 2: seed {len(SEED_SCOPES)} dimension scopes')
        ps_col = _get_ps_column(conn)
        print(f'  [v079] using FK column: {ps_col}')
        inserted = 0
        skipped = 0
        for ps_id, dim_code, scope_mode, dim_values, inherit in SEED_SCOPES:
            if _seed_one(conn, ps_id, dim_code, scope_mode, dim_values, inherit, ps_col):
                inserted += 1
            else:
                skipped += 1

        print(f'[v079] seed summary: inserted={inserted}, skipped={skipped} (已存在)')

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v079] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path):
    """验证 v079: SEED_SCOPES 中每条都已存在于目标表 (按 ps_id+dim_code)."""
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, TARGET_TABLE):
            return False
        ps_col = _get_ps_column(conn)
        all_ok = True
        for ps_id, dim_code, _mode, _val, _inh in SEED_SCOPES:
            cur = conn.execute(
                f"SELECT 1 FROM {TARGET_TABLE} "
                f"WHERE {ps_col} = ? AND dimension_code = ?",
                [ps_id, dim_code],
            )
            if cur.fetchone() is None:
                print(f'  [v079 verify] 缺失: ps={ps_id} dim={dim_code}')
                all_ok = False
        return all_ok
    finally:
        conn.close()


def downgrade(db_path, skip_backup=False):
    """回滚 v079: 从 backup 恢复原行, 删除 v079 插入的新行.

    实现:
    1. 删除 permission_set_dimension_scopes 中 created_by='v079_seed' 的行
    2. 从 backup 表恢复 (INSERT OR IGNORE, 不覆盖已存在的)
    """
    if not db_path.exists():
        print(f'[v079 downgrade] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, TARGET_TABLE):
            return False

        # 删除 v079 插入的行
        cur = conn.execute(
            f"DELETE FROM {TARGET_TABLE} WHERE created_by = 'v079_seed'"
        )
        print(f'  [v079 downgrade] 删除 v079_seed 行: {cur.rowcount}')

        # 从 backup 恢复 (如果有 backup 表)
        if _table_exists(conn, BACKUP_TABLE):
            cnt = conn.execute(f"SELECT COUNT(*) FROM {BACKUP_TABLE}").fetchone()[0]
            conn.execute(
                f"INSERT INTO {TARGET_TABLE} SELECT * FROM {BACKUP_TABLE} "
                "WHERE id NOT IN (SELECT id FROM " + TARGET_TABLE + ")"
            )
            print(f'  [v079 downgrade] backup 中 {cnt} 行已尝试恢复 (INSERT OR IGNORE)')

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v079 downgrade] 失败: {e}')
        raise
    finally:
        conn.close()


def migrate(db_path, skip_backup=False):
    """v079: seed permission_set_dimension_scopes from production template.

    Args:
        db_path: SQLite 数据库路径
        skip_backup: 跳过 backup 表创建 (默认 False - 安全)

    Returns:
        True 如果成功执行或已执行 (幂等).
    """
    if skip_backup:
        print('[v079] WARNING: skip_backup=True, no rollback possible')
        conn = sqlite3.connect(str(db_path))
        try:
            if not _table_exists(conn, TARGET_TABLE):
                return False
            ps_col = _get_ps_column(conn)
            for ps_id, dim_code, scope_mode, dim_values, inherit in SEED_SCOPES:
                _seed_one(conn, ps_id, dim_code, scope_mode, dim_values, inherit, ps_col)
            conn.commit()
            return True
        finally:
            conn.close()
    return _migrate_impl(db_path)


if __name__ == '__main__':
    import sys
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('meta/architecture.db')
    print(f'[v079] running on {db}')
    success = migrate(db)
    print(f'[v079] success={success}, verify={verify(db)}')
