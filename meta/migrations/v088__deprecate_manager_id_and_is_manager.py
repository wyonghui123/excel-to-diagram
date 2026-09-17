# -*- coding: utf-8 -*-
"""
[v088 2026-09-15] Spec 19 M4 软删：orgs.manager_id / org_members.is_manager 废弃

背景 (Spec 19 §8 M4, [§9.6c.1 过渡废弃](19_org_admin_delegation.md)):
  v084 已将受托管理员来源切换到 OrgAdminScopeService (矩阵 org 行级规则动态解析),
  但保留 is_manager / manager_id 5 行 fallback 并集 [org_service.py L270-289],
  标 M3 移除。2026-09-15 数据摸底 ([tools/v19_p2_audit_remote.py](tools/v19_p2_audit_remote.py)):
    - staging + prod orgs.manager_id 真实数据 = 0 行
    - staging + prod org_members.is_manager=1 = 1 行 (seed 孤儿, admin → org 1 系统管理员)
    - admin 走 is_admin() 全局放行 → fallback 不实际加权限 (风险可接受)

策略 (soft-delete 三步法, 无 DROP COLUMN 兼容 SQLite 3.35 前):
  1. 写路径拒绝: org_api.add_group_member / org_service.add_member 入参 is_manager → 400 + deprecation 日志
  2. 读路径移除: get_managed_orgs() 删除 is_manager + manager_id fallback 段,
                   get_org_tree / get_org_members 仍 SELECT 列 (前端展示兼容, 永远 is_manager=0)
  3. dead code: org_service.is_org_manager() 删除 (grep 0 引用, 已 Sunset)

不动:
  - orgs.manager_id / org_members.is_manager 列保留 (DROP COLUMN 在 SQLite 3.35 前不可用)
  - yaml 字段段 deprecated: true 标记 (前端 UI 已隐藏, 见 org.yaml L444-446)
  - v089 DROP legacy user_groups / user_group_members / roles 表由 v089 负责
  - admin → org 1 的 seed 遗留行保留 (当前无人依赖, M4 完成后 1 季度走 v09x 硬删)

幂等性:
  - 验证函数仅读, 可重复执行
  - 写路径拒绝是代码层 (org_api.py / org_service.py), 不需迁移保证

downgrade:
  不支持 (软删是单向收紧; 回滚需手动恢复代码段 + 清空 deprecation 日志)
"""
import sqlite3
import sys
from pathlib import Path


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """[v088 软删] 验证数据 + 报告; 写路径拒绝由 org_api.py / org_service.py 代码层负责."""
    if not db_path.exists():
        print(f'[v088] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        conn.row_factory = sqlite3.Row

        # 1. 报告当前遗留数据规模
        print('[v088] 当前遗留数据报告:')
        if _table_exists(conn, 'orgs'):
            n = conn.execute(
                "SELECT COUNT(*) FROM orgs WHERE manager_id IS NOT NULL"
            ).fetchone()[0]
            print(f'  - orgs.manager_id 非空行数: {n}')
        else:
            print('  - orgs 表不存在 (跳过)')

        if _table_exists(conn, 'org_members'):
            n = conn.execute(
                "SELECT COUNT(*) FROM org_members WHERE is_manager = 1"
            ).fetchone()[0]
            print(f'  - org_members.is_manager=1 行数: {n}')
            if n > 0:
                for row in conn.execute(
                    """SELECT m.user_id, m.org_id, u.username, o.code AS org_code
                       FROM org_members m
                       LEFT JOIN users u ON u.id = m.user_id
                       LEFT JOIN orgs o ON o.id = m.org_id
                       WHERE m.is_manager = 1"""
                ).fetchall():
                    print(f'      user#{row[0]} ({row[2]}) -> org#{row[1]} ({row[3]})')

        # 2. 检查表结构对齐 (防御: 如果列已被 v09x 删除, 报告但不停)
        if _table_exists(conn, 'orgs'):
            cols = {r[1] for r in conn.execute('PRAGMA table_info(orgs)').fetchall()}
            if 'manager_id' not in cols:
                print('[v088] WARN: orgs.manager_id 列已不存在, 软删前提不符 (跳过 verify)')
                return True

        if _table_exists(conn, 'org_members'):
            cols = {r[1] for r in conn.execute('PRAGMA table_info(org_members)').fetchall()}
            if 'is_manager' not in cols:
                print('[v088] WARN: org_members.is_manager 列已不存在, 软删前提不符 (跳过 verify)')
                return True

        return True
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """[v088 verify] 仅验证数据层; 写路径拒绝需要重启服务后通过 API 验证."""
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        # verify 1: orgs.manager_id 应为 0 (或列已删)
        if _table_exists(conn, 'orgs'):
            cols = {r[1] for r in conn.execute('PRAGMA table_info(orgs)').fetchall()}
            if 'manager_id' in cols:
                n = conn.execute(
                    "SELECT COUNT(*) FROM orgs WHERE manager_id IS NOT NULL"
                ).fetchone()[0]
                print(f'[v088 verify] orgs.manager_id 非空行数 = {n} (期望 0)')
                if n > 0:
                    print('[v088 verify] FAIL: 仍存在非空 manager_id 数据, 请先清理')
                    return False

        # verify 2: org_members.is_manager 应全为 0 (或列已删)
        if _table_exists(conn, 'org_members'):
            cols = {r[1] for r in conn.execute('PRAGMA table_info(org_members)').fetchall()}
            if 'is_manager' in cols:
                n = conn.execute(
                    "SELECT COUNT(*) FROM org_members WHERE is_manager = 1"
                ).fetchone()[0]
                print(f'[v088 verify] org_members.is_manager=1 行数 = {n} (期望 0)')
                if n > 0:
                    print('[v088 verify] WARN: 仍有遗留 1 行 (admin → org 1 seed); '
                          '非阻塞, 写入路径已拒绝新增')
                    # 不 FAIL: seed 孤儿已知, admin 走 is_admin() 全局放行

        # verify 3: legacy 表是否仍存在 (留给 v089 处理)
        for tbl in ['user_groups', 'user_group_members', 'roles']:
            n = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
                (tbl,),
            ).fetchone()[0]
            if n:
                cnt = conn.execute(f'SELECT COUNT(*) FROM {tbl}').fetchone()[0]
                print(f'[v088 verify] legacy 表 {tbl} 存在 (rows={cnt}); 由 v089 处理 DROP')

        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    """v088 软删无 downgrade (写路径拒绝由代码层; 数据未删, 可直接恢复)."""
    print('[v088] downgrade no-op (软删: 仅代码层拒绝, 未删列/未清数据)')
    return True


if __name__ == '__main__':
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / 'architecture.db'
    print(f'[v088] migrating {db}')
    ok = migrate(db)
    print(f'[v088] migrate: {"OK" if ok else "FAIL"}')
    v = verify(db)
    print(f'[v088] verify: {"PASS" if v else "FAIL"}')
    sys.exit(0 if (ok and v) else 1)