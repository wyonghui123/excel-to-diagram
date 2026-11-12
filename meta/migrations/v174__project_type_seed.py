"""v174 — 项目类型种子（项目侧 P1 出口补齐）

依据:
  docs/specs/spec-project-type-object-model-research-2026-10-31.md §2.1 / §6 AC-01
  SAP PS 项目类型四分（01 投资 / 02 客户 / 03 内部 / 04 维护）

为什么需要:
  v172 已建 type_definitions 结构并把项目菜单 / 权限落库，但未播种任何
  scope_bo='project' 的类型行；缺种子时项目新建页「项目类型」下拉为空，
  项目根本建不出来（AC-01 不可达）。

播种 4 条 header 级类型（scope_bo='project' / level='header'）:
  P_INVEST   投资项目
  P_CUSTOMER 客户项目
  P_INTERNAL 内部项目
  P_MAINT    维护项目

幂等:
  按 (scope_bo, level, code) 判存在；已存在只刷新名称 / 说明，不覆盖 status
  （实施侧停用过的类型不会被重跑迁移重新激活）。

回滚:
  删除本迁移创建的 4 条类型（仅当 projects 未引用该类型时）。
"""
import sqlite3
from pathlib import Path

SCOPE_BO = 'project'
LEVEL = 'header'

PROJECT_TYPES = (
    ('P_INVEST', '投资项目',
     '资本性支出项目（SAP PS 类型 01）：预算来自投资计划，通常跨年度'),
    ('P_CUSTOMER', '客户项目',
     '客户交付项目（SAP PS 类型 02）：与销售订单 / 合同挂钩，收入按客户确认'),
    ('P_INTERNAL', '内部项目',
     '内部研发 / 管理费用项目（SAP PS 类型 03）：不对外确认收入'),
    ('P_MAINT', '维护项目',
     '运维 / 维护服务项目（SAP PS 类型 04）：长期服务合同下的持续交付'),
)


def _table_exists(conn, name):
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _type_row(conn, code):
    return conn.execute(
        'SELECT id, status FROM type_definitions '
        'WHERE scope_bo = ? AND level = ? AND code = ?',
        (SCOPE_BO, LEVEL, code)).fetchone()


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print('[v174] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v174] 开始: 项目类型种子')
        if not _table_exists(conn, 'type_definitions'):
            print('[v174] 缺少 type_definitions，跳过')
            return False

        for code, name, desc in PROJECT_TYPES:
            row = _type_row(conn, code)
            if row:
                conn.execute(
                    'UPDATE type_definitions SET name = ?, description = ? '
                    'WHERE id = ?', (name, desc, row[0]))
            else:
                conn.execute(
                    'INSERT INTO type_definitions '
                    '(code, name, scope_bo, level, status, description, created_at) '
                    "VALUES (?, ?, ?, ?, 'active', ?, datetime('now'))",
                    (code, name, SCOPE_BO, LEVEL, desc))
        conn.commit()
        print('[v174] 迁移提交完成: %d 条项目类型' % len(PROJECT_TYPES))
        return True
    except Exception as e:
        conn.rollback()
        print('[v174] 失败: %s' % e)
        return False
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v174 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, 'type_definitions'):
            print('[v174 verify] FAIL: 缺少 type_definitions')
            return False
        rows = conn.execute(
            'SELECT code FROM type_definitions '
            "WHERE scope_bo = ? AND level = ? AND status = 'active'",
            (SCOPE_BO, LEVEL)).fetchall()
        found = {row[0] for row in rows}
        missing = [item[0] for item in PROJECT_TYPES if item[0] not in found]
        if missing:
            print('[v174 verify] FAIL: 类型缺失 %s' % missing)
            return False
        print('[v174 verify] OK: %d 条项目类型已就位' % len(PROJECT_TYPES))
        return True
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v174 rollback] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        has_projects = _table_exists(conn, 'projects')
        for code, _name, _desc in PROJECT_TYPES:
            row = _type_row(conn, code)
            if not row:
                continue
            if has_projects and conn.execute(
                    'SELECT COUNT(1) FROM projects WHERE project_type_id = ?',
                    (row[0],)).fetchone()[0]:
                print('[v174 rollback] 跳过 %s: 仍有项目引用' % code)
                continue
            conn.execute('DELETE FROM type_definitions WHERE id = ?', (row[0],))
        conn.commit()
        print('[v174 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v174 rollback] 失败: %s' % e)
        return False
    finally:
        conn.close()
