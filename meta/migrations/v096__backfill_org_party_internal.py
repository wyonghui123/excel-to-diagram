# -*- coding: utf-8 -*-
"""[v096 2026-10-20] 回填 org → party 内部表示（仅 legal_entity 职能的 org）

背景:
  parties.source='org' 的行是「我方」内部主体的唯一表示，读面为 party_internal 视图
  （谓词 source='org'）；party_relation.party1_id（我方侧）引用这些行。
  此前全库无任何写入路径产生该行 ⇒ 视图恒 0 行 ⇒ 我方侧候选为空、入口不可用。
  写入侧机制见 meta/services/org_party_mirror_service.py（决策口径 / 不删除原则在其中）。

本迁移做什么:
  遍历具备 legal_entity（法人）职能的 org，逐个子调用 OrgPartyMirrorService
  对齐其 party 内部表示（无则建、有则同步 name/status）。
  **只建法人 org** —— 不按 org 全量镜像。依据见服务模块头：部门不是往来主体。

幂等:
  服务内先按 (source='org', org_id) 查存量，重复执行为 UPDATE/no-op；backfill 返回
  新建行数，故二次执行返回 0 且不新增行。

回滚:
  仅删除**未被 party_relations 引用**的内部表示行（真外键，被引用者不可删）；
  被引用的行保留并打印清单 —— 内部表示一旦被引用即成为历史事实。

为何用 migration 而非 sync_schema:
  这是数据回填（DML），不是结构变更；且必须在应用启动前完成，前端才可见候选。
  版本号取 v096：v095 已被 org.yaml 注释登记为 org_scope 硬删预留位。

前置:
  依赖 orgs / org_functions / parties / party_relations 四表；缺任一张则跳过（多应用库路由）。
"""
import sqlite3
import sys
from pathlib import Path

# 允许以 `python meta/migrations/v096__backfill_org_party_internal.py` 直接执行
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_REQUIRED_TABLES = ('orgs', 'org_functions', 'parties')


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _legal_entity_org_ids(conn: sqlite3.Connection):
    return [r[0] for r in conn.execute(
        "SELECT o.id FROM orgs o JOIN org_functions f ON f.org_id = o.id "
        "WHERE f.function_type = 'legal_entity' ORDER BY o.id"
    ).fetchall()]


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    db_path = Path(db_path)
    if not db_path.exists():
        print(f'[v096] DB 不存在: {db_path}')
        return False

    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        missing = [t for t in _REQUIRED_TABLES if not _table_exists(conn, t)]
        if missing:
            print(f'[v096] SKIP: 缺少依赖表 {missing}（该库不承载 org/party 域）')
            return True
        org_ids = _legal_entity_org_ids(conn)
        if not org_ids:
            print('[v096] SKIP: 无具备 legal_entity 职能的 org')
            return True
    finally:
        conn.close()

    # 复用服务的幂等写入路径（与运行时同一口径，避免两套编号/同步逻辑漂移）
    from meta.core.datasource import get_data_source
    from meta.core.table_name_validator import register_table_name
    from meta.services.org_party_mirror_service import OrgPartyMirrorService

    # 服务内走 ds.insert('parties')，而 ds.insert 会经 validate_table_name 白名单
    # （白名单 = 系统表 ∪ registry 已注册表）。standalone 执行本迁移时 registry 尚未
    # 装载 ⇒ 'parties' 不在白名单而抛 ValueError。app 启动路径下 registry 已装载、
    # 无需此行；此处补登记保证「直接 python 本脚本」也能跑（先例: task_sla / doc_flow_schema）。
    register_table_name('parties')

    print(f'[v096] 开始: 回填 {len(org_ids)} 个法人 org 的 party 内部表示')
    ds = get_data_source('sqlite', database=str(db_path))
    created = OrgPartyMirrorService(ds).backfill()
    print(f'  - [{"CREATE" if created else "KEEP"}] 新建 {created} 行, '
          f'其余已存在并已同步')
    return True


def verify(db_path: Path) -> bool:
    """每个 legal_entity org 都存在且仅存在一行 source='org' 的内部表示。"""
    db_path = Path(db_path)
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        missing = [t for t in _REQUIRED_TABLES if not _table_exists(conn, t)]
        if missing:
            print(f'[v096 verify] SKIP: 缺少依赖表 {missing}')
            return True
        org_ids = _legal_entity_org_ids(conn)
        if not org_ids:
            print('[v096 verify] OK: 无 legal_entity org, 无需回填')
            return True

        bad = []
        for org_id in org_ids:
            rows = conn.execute(
                "SELECT id FROM parties WHERE source='org' AND org_id=?", (org_id,)
            ).fetchall()
            if len(rows) != 1:
                bad.append((org_id, len(rows)))
        if bad:
            print(f'[v096 verify] FAIL: 以下 org 的内部表示行数不为 1: {bad}')
            return False

        total = conn.execute(
            "SELECT COUNT(*) FROM parties WHERE source='org'").fetchone()[0]
        print(f'[v096 verify] OK: {len(org_ids)} 个法人 org 各有 1 行, '
              f'parties.source=\'org\' 共 {total} 行')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    """删除未被引用的内部表示行（被 party_relations 引用的保留）。"""
    db_path = Path(db_path)
    if not db_path.exists():
        print(f'[v096] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        if not _table_exists(conn, 'parties'):
            print('[v096] SKIP: parties 表不存在')
            return True

        referenced = set()
        if _table_exists(conn, 'party_relations'):
            referenced = {r[0] for r in conn.execute(
                "SELECT party1_id FROM party_relations WHERE party1_id IS NOT NULL "
                "UNION SELECT party2_id FROM party_relations WHERE party2_id IS NOT NULL"
            ).fetchall()}

        rows = conn.execute(
            "SELECT id FROM parties WHERE source='org'").fetchall()
        deletable = [r[0] for r in rows if r[0] not in referenced]
        kept = [r[0] for r in rows if r[0] in referenced]

        if deletable:
            placeholders = ','.join(['?'] * len(deletable))
            conn.execute(
                f"DELETE FROM parties WHERE id IN ({placeholders})", deletable)
        conn.commit()
        print(f'[v096] 回滚: 删除 {len(deletable)} 行, 保留(已被关系引用) {len(kept)} 行')
        if kept:
            print(f'  - [KEEP] party id={kept} 仍被 party_relations 引用')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v096] downgrade 失败: {e}')
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    from meta.core.db_path import get_meta_db_path

    db = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(get_meta_db_path())
    print(f'[v096] migrating {db}')
    ok = migrate(db)
    print(f'[v096] migrate: {"OK" if ok else "FAIL"}')
    v = verify(db)
    print(f'[v096] verify: {"PASS" if v else "FAIL"}')
    sys.exit(0 if (ok and v) else 1)
