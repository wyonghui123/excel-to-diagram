# -*- coding: utf-8 -*-
"""v250 —— 补齐「被引用但从未播种」的权限码（T1 遗留）。

背景:
  门禁 R1（scripts/check_permission_consistency.py）报 17 条权限码被真实引用
  （YAML 按钮 `permission:` / Python `@require_permission` /
  `bo_action_registrations.permission_required`），但 permissions 表里既没有
  单段码也没有双段旧码 —— 授予侧永远勾不到，strict 模式下动作必然 403。

  T1 已把代码侧字面量统一为单段 `{bo}:{action}`（v249 收敛存量双段码），
  本迁移只补播种，不改任何代码/声明位，所以不会改变授权语义：这些码原本就
  被运行时检查，播种后只是变得「可授予」。

范围（17 条）:
  · 运行时动作：change_request apply/approve/reject、
    transfer_order reverse_shipment、customer_invoice
    credit_memo/debit_memo/post/reverse/submit
  · 平台页按钮：org / permission_set export+import、enum_type:export
  · 打印按钮：customer_invoice:print
  · PoC 应用：hello_world:create、tms:create

  `new_object:create/delete` 不在此列：它们来自 `meta/schemas/_template.yaml`
  模板占位，模板对象不注册，门禁已改为跳过 `_*.yaml`。

幂等: INSERT OR IGNORE，重复执行为 no-op。
"""
import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v250__seed_referenced_permission_codes'

PERMISSIONS = 'permissions'

SEED = (
    ('change_request:apply', '变更申请执行'),
    ('change_request:approve', '变更申请审批通过'),
    ('change_request:reject', '变更申请驳回'),
    ('customer_invoice:credit_memo', '销售发票贷项凭证'),
    ('customer_invoice:debit_memo', '销售发票借项通知单'),
    ('customer_invoice:post', '销售发票过账'),
    ('customer_invoice:print', '销售发票打印'),
    ('customer_invoice:reverse', '销售发票红冲'),
    ('customer_invoice:submit', '销售发票提交'),
    ('enum_type:export', '枚举类型导出'),
    ('hello_world:create', 'Hello World 创建'),
    ('org:export', '组织导出'),
    ('org:import', '组织导入'),
    ('permission_set:export', '权限集导出'),
    ('permission_set:import', '权限集导入'),
    ('tms:create', '运单管理创建'),
    ('transfer_order:reverse_shipment', '调拨单反向发货'),
)


def _has_table(conn, name):
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", [name]).fetchone())


def migrate(db_path, skip_backup=False):
    # skip_backup: MigrationRunner 已统一备份，迁移内部不再重复备份
    path = Path(db_path)
    conn = sqlite3.connect(str(path), timeout=30)
    try:
        print('[v250] 开始: 补齐被引用未播种的权限码')
        if not _has_table(conn, PERMISSIONS):
            print('[v250] [SKIP] permissions 表不存在')
            return True
        conn.execute('BEGIN')
        created = 0
        for code, name in SEED:
            resource_type, action = code.split(':', 1)
            cur = conn.execute(
                'INSERT OR IGNORE INTO permissions (code, name, resource_type, action) '
                'VALUES (?, ?, ?, ?)', [code, name, resource_type, action])
            if cur.rowcount and cur.rowcount > 0:
                created += 1
        conn.commit()
        print('[v250] 完成: 新增权限码 %d 条（共 %d 条候选）' % (created, len(SEED)))
        if not created:
            print('[v250] [SKIP] 全部已存在')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


upgrade = migrate


def verify(db_path) -> bool:
    path = Path(db_path)
    if not path.exists():
        print('[v250 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        existing = {row[0] for row in conn.execute('SELECT code FROM %s' % PERMISSIONS)}
        missing = [code for code, _ in SEED if code not in existing]
        if missing:
            print('[v250 verify] FAIL: 缺失 %d 条: %s' % (len(missing), ', '.join(missing)))
            return False
        return True
    finally:
        conn.close()