# -*- coding: utf-8 -*-
"""
[v083 2026-09-04] permission_set_dimension_scopes.dimension_values 归一为 canonical ID-form

背景 (staging 权限集「配置条件」显示 [object Object], 2026-09-04 排查):
  permission_set_dimension_scopes.dimension_values 存在两种形态:
    - ID-form (canonical): [13, 14] / ['*'] → v079 seed / 引擎可展开
    - OBJ-form (旧保存路径残留): [{"code": "FIN", "id": 13, "name": "财务云"}]
      - 来源: 老客户端把 GET 富化后的对象数组原样回传给 POST /dimension-scopes,
        POST 直接 json.dumps 落库 (created_by/updated_by 等标记为空)
      - 危害:
        ① GET 富化把 dict 当 id 绑定进 SQL → 抛异常走 fallback 二次包裹成
           {'id': <dict>, 'name': str(<dict>)} → 前端渲染 [object Object]
        ② dimension_scope_engine.expand_dimension_values 对 OBJ 元素做
           int(dict) 失败被跳过 → 该权限集的维度数据权限实际不生效

修复 (expand, 安全, 幂等):
  逐行解析 dimension_values JSON:
    - 列表元素为 dict 且有 'id' (兜底取 'code') → 归一为标量 id
    - 已 ID-form / 通配符 ['*'] / 含无可解析 id 的 dict 的行 → 跳过不动 (防御丢数据)
  每改一行打标 updated_by='v083_normalize' (列存在时), 供 downgrade 精准恢复.
  备份: skip_backup=False 时建整表备份 permission_set_dimension_scopes_pre_v083_backup
  (runner 已做整库备份时传 skip_backup=True 跳过内部备份, 与 v079 一致).

幂等性:
  - 无 dict 元素的行不触碰; 重复执行 normalized 计数为 0
  - verify(): 全表行解析后不存在含 dict 元素的行 (不可解析的行跳过不算 OBJ)

downgrade:
  对 updated_by='v083_normalize' 的行, 从备份表按 id 恢复原 dimension_values.
"""
import json
import sqlite3
from pathlib import Path

TARGET_TABLE = 'permission_set_dimension_scopes'
BACKUP_TABLE = 'permission_set_dimension_scopes_pre_v083_backup'
MARKER = 'v083_normalize'


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    )
    return cur.fetchone() is not None


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    if not _table_exists(conn, table):
        return False
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def _create_backup(conn: sqlite3.Connection) -> bool:
    """整表备份到 BACKUP_TABLE. Returns True if created, False if already exists."""
    if not _table_exists(conn, TARGET_TABLE):
        print(f'  [v083] {TARGET_TABLE} 不存在, 跳过备份')
        return False
    if _table_exists(conn, BACKUP_TABLE):
        print(f'  [v083] {BACKUP_TABLE} 已存在 (v083 已运行), 跳过备份')
        return False
    conn.execute(f"CREATE TABLE {BACKUP_TABLE} AS SELECT * FROM {TARGET_TABLE} WHERE 0")
    conn.execute(f"INSERT INTO {BACKUP_TABLE} SELECT * FROM {TARGET_TABLE}")
    cnt = conn.execute(f"SELECT COUNT(*) FROM {BACKUP_TABLE}").fetchone()[0]
    print(f'  [v083] backed up {cnt} rows: {TARGET_TABLE} -> {BACKUP_TABLE}')
    return True


def _normalize_row_value(value):
    """尝试把一行解析后的 dimension_values 归一为纯 id list.

    Returns:
        (changed: bool, normalized: list|原始值)
      - 含可解析 id 的 dict 元素 → changed=True, 归一后的 id list
      - 含无可解析 id 的 dict → 拒绝改动该行 (changed=False, 原始值) 防丢数据
      - 无 dict 元素 (ID-form / 通配符 ['*']) → changed=False
    """
    if not isinstance(value, list):
        return False, value
    out = []
    changed = False
    for v in value:
        if isinstance(v, dict):
            vid = v.get('id')
            if vid is None:
                vid = v.get('code')
            if vid is None or vid == '':
                return False, value  # 无 id 可归, 保持原样
            out.append(vid)
            changed = True
        else:
            out.append(v)
    return changed, out


def _do_upgrade(conn: sqlite3.Connection) -> int:
    """归一所有 OBJ-form 行, 返回改动行数."""
    if not _table_exists(conn, TARGET_TABLE):
        print(f'  [v083] {TARGET_TABLE} 不存在, 跳过 (该表由 v070 rename 建立)')
        return 0

    rows = conn.execute(f"SELECT id, dimension_values FROM {TARGET_TABLE}").fetchall()
    updated = 0
    for rid, raw in rows:
        try:
            parsed = json.loads(raw) if raw else []
        except (json.JSONDecodeError, TypeError):
            print(f'  [WARN] row id={rid} dimension_values 非合法 JSON, 跳过: {raw!r}')
            continue
        changed, normalized = _normalize_row_value(parsed)
        if not changed:
            continue
        new_json = json.dumps(normalized, ensure_ascii=False)
        if _has_column(conn, TARGET_TABLE, 'updated_by'):
            conn.execute(
                f"UPDATE {TARGET_TABLE} SET dimension_values = ?, updated_by = ? WHERE id = ?",
                (new_json, MARKER, rid),
            )
        else:
            conn.execute(
                f"UPDATE {TARGET_TABLE} SET dimension_values = ? WHERE id = ?",
                (new_json, rid),
            )
        updated += 1
        print(f'  [NORMALIZE] id={rid}: {raw} -> {new_json}')
    print(f'  [v083] normalize summary: updated={updated}, scanned={len(rows)}')
    return updated


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """[v083] 归一 permission_set_dimension_scopes.dimension_values 为 ID-form."""
    if not db_path.exists():
        print(f'[v083] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v083] 开始: dimension_values 归一为 canonical ID-form')
        if not skip_backup:
            _create_backup(conn)
        _do_upgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v083] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """验证: 全表不存在含 dict 元素 (OBJ-form) 的行."""
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, TARGET_TABLE):
            print(f'  [v083 verify] {TARGET_TABLE} 不存在')
            return False
        bad = []
        rows = conn.execute(f"SELECT id, dimension_values FROM {TARGET_TABLE}").fetchall()
        for rid, raw in rows:
            try:
                parsed = json.loads(raw) if raw else []
            except (json.JSONDecodeError, TypeError):
                continue  # 不可解析的行不判 OBJ (v083 不动它们)
            if isinstance(parsed, list) and any(isinstance(v, dict) for v in parsed):
                bad.append(rid)
        if bad:
            print(f'  [v083 verify] FAIL: 仍有 OBJ-form 行: {bad}')
            return False
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    """回滚 v083: 从备份表按 id 恢复被归一行的原 dimension_values."""
    if not db_path.exists():
        print(f'[v083 downgrade] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, TARGET_TABLE):
            print(f'[v083 downgrade] {TARGET_TABLE} 不存在')
            return False
        if not _table_exists(conn, BACKUP_TABLE):
            print(f'[v083 downgrade] 备份表 {BACKUP_TABLE} 不存在, 无法恢复')
            return False
        if not _has_column(conn, TARGET_TABLE, 'updated_by'):
            print('[v083 downgrade] updated_by 列不存在, 无法识别 v083 改动行, 拒绝降级')
            return False
        cur = conn.execute(
            f"UPDATE {TARGET_TABLE} "
            f"SET dimension_values = (SELECT b.dimension_values FROM {BACKUP_TABLE} b "
            f"                         WHERE b.id = {TARGET_TABLE}.id) "
            f"WHERE updated_by = ? AND id IN (SELECT id FROM {BACKUP_TABLE})",
            (MARKER,),
        )
        print(f'  [v083 downgrade] 恢复 {cur.rowcount} 行 dimension_values')
        conn.execute(
            f"UPDATE {TARGET_TABLE} SET updated_by = NULL WHERE updated_by = ?",
            (MARKER,),
        )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v083 downgrade] 失败: {e}')
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('meta/architecture.db')
    print(f'[v083] running on {db}')
    success = migrate(db)
    print(f'[v083] success={success}, verify={verify(db)}')
