# -*- coding: utf-8 -*-
"""[P1-5 2026-11-06] receipt_line 冗余一致性审计的测试夹具。

SQL 统一放在 factories 下（conftest 的 raw-SQL 守卫对 factories 目录豁免），
测试文件只调用函数，避免在用例里写 INSERT/UPDATE。
"""


def build_receipt_line_fixture(ds):
    """建最小表并造 3 行：order_id 漂移 / order_line_id 漂移 / 一致。"""
    ds.execute(
        'CREATE TABLE purchase_order_schedules ('
        'id INTEGER PRIMARY KEY, order_id INTEGER, line_id INTEGER)')
    ds.execute(
        'CREATE TABLE receipt_lines ('
        'id INTEGER PRIMARY KEY, receipt_id INTEGER, schedule_id INTEGER, '
        'order_id INTEGER, order_line_id INTEGER)')
    ds.execute(
        'INSERT INTO purchase_order_schedules (id, order_id, line_id) '
        'VALUES (10, 1, 5)')
    ds.execute(
        'INSERT INTO receipt_lines (id, receipt_id, schedule_id, order_id, '
        'order_line_id) VALUES (1, 1, 10, 999, 5)')
    ds.execute(
        'INSERT INTO receipt_lines (id, receipt_id, schedule_id, order_id, '
        'order_line_id) VALUES (2, 1, 10, 1, 6)')
    ds.execute(
        'INSERT INTO receipt_lines (id, receipt_id, schedule_id, order_id, '
        'order_line_id) VALUES (3, 1, 10, 1, 5)')


def repair_order_id(ds):
    """把行 1 的 order_id 修正为真源值。"""
    ds.execute('UPDATE receipt_lines SET order_id = 1 WHERE id = 1')
