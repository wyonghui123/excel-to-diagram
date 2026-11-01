"""v173 — 需求入口审批控制参数（M1）

依据:
  docs/specs/spec-unified-demand-execution-milestone-2026-10-31.md §2 M1
  docs/specs/spec-procurement-task-object-model-2026-10-31.md T-D20
  平台口径: 行为参数放 control_parameter（勿塞类型字典）

定义 2 个参数（维度 org_id / document_type_id / line_type_id / item_group_id）:
  · demand_approval_required  提交后是否需审批（bool）
  · demand_approval_policy    审批策略（string/JSON；空 = 免审批）

不播种取值: 未配置时服务回退单据固有口径（服务请求看目录项，采购申请免审批），
避免改变既有行为；需要审批的单据类型由实施侧在「控制参数取值」里配。

幂等:
  定义按 code 判存在；已存在则刷新名称/值类型/默认值/说明，不重置 status。

回滚:
  删除本迁移创建的 2 条定义（仅当该定义下无取值）。
"""
import sqlite3
from pathlib import Path

PARAM_DEFS = (
    ('demand_approval_required', '需求入口是否需要审批', 'bool', None,
     '服务请求 / 采购申请提交后是否需要审批；未配置时回退单据固有口径'),
    ('demand_approval_policy', '需求入口审批策略', 'string', None,
     '审批策略（JSON：审批人/层级）；空值视为免审批'),
)

DOMAIN = 'demand'


def _table_exists(conn, name):
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _param_id(conn, code):
    row = conn.execute(
        'SELECT id FROM control_parameter_defs WHERE code = ?', (code,)
    ).fetchone()
    return row[0] if row else None


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print('[v173] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v173] 开始: 需求入口审批控制参数')
        if not _table_exists(conn, 'control_parameter_defs'):
            print('[v173] 缺少 control_parameter_defs，跳过')
            return False

        for code, name, value_type, default_value, desc in PARAM_DEFS:
            if _param_id(conn, code):
                conn.execute(
                    'UPDATE control_parameter_defs SET name = ?, domain = ?, '
                    'value_type = ?, default_value = ?, description = ?, status = ? '
                    'WHERE code = ?',
                    (name, DOMAIN, value_type, default_value, desc, 'active', code))
                print('  ~ UPDATE def %s' % code)
            else:
                conn.execute(
                    'INSERT INTO control_parameter_defs '
                    '(code, name, domain, value_type, target_bo, default_value, '
                    ' status, description, created_at) '
                    "VALUES (?, ?, ?, ?, NULL, ?, 'active', ?, datetime('now'))",
                    (code, name, DOMAIN, value_type, default_value, desc))
                print('  + INSERT def %s' % code)

        conn.commit()
        print('[v173] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v173] migrate 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v173 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        missing = [code for code, *_ in PARAM_DEFS if not _param_id(conn, code)]
        if missing:
            print('[v173 verify] FAIL: 定义缺失 %s' % missing)
            return False
        print('[v173 verify] OK: 2 条控制参数定义已就位')
        return True
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v173 rollback] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        for code, *_ in PARAM_DEFS:
            param_id = _param_id(conn, code)
            if not param_id:
                continue
            remain = conn.execute(
                'SELECT COUNT(*) FROM control_parameter_values '
                'WHERE control_parameter_id = ?', (param_id,)).fetchone()[0]
            if remain:
                print('  ! 定义 %s 仍有 %s 条取值，保留' % (code, remain))
                continue
            conn.execute('DELETE FROM control_parameter_defs WHERE id = ?', (param_id,))
            print('  - DELETE def %s' % code)
        conn.commit()
        print('[v173 rollback] 完成')
        return True
    finally:
        conn.close()
