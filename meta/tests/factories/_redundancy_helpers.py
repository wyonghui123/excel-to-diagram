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


def build_purchase_order_aggregate_fixture(ds):
    """[P2 2026-11-06] 造 4 张订单：一致 / 合计漂移 / 无明细零合计 / 无明细残留合计。"""
    ds.execute(
        'CREATE TABLE purchase_orders ('
        'id INTEGER PRIMARY KEY, net_amount NUMERIC, tax_amount NUMERIC, '
        'gross_amount NUMERIC)')
    ds.execute(
        'CREATE TABLE purchase_order_lines ('
        'id INTEGER PRIMARY KEY, order_id INTEGER, net_amount NUMERIC, '
        'tax_amount NUMERIC, gross_amount NUMERIC)')
    ds.execute(
        'INSERT INTO purchase_orders (id, net_amount, tax_amount, gross_amount) '
        'VALUES (1, 100, 0, 100)')
    ds.execute(
        'INSERT INTO purchase_orders (id, net_amount, tax_amount, gross_amount) '
        'VALUES (2, 90, 0, 90)')
    ds.execute(
        'INSERT INTO purchase_orders (id, net_amount, tax_amount, gross_amount) '
        'VALUES (3, 0, 0, 0)')
    ds.execute(
        'INSERT INTO purchase_orders (id, net_amount, tax_amount, gross_amount) '
        'VALUES (4, 50, 0, 50)')
    ds.execute(
        'INSERT INTO purchase_order_lines '
        '(id, order_id, net_amount, tax_amount, gross_amount) '
        'VALUES (1, 1, 60, 0, 60)')
    ds.execute(
        'INSERT INTO purchase_order_lines '
        '(id, order_id, net_amount, tax_amount, gross_amount) '
        'VALUES (2, 1, 40, 0, 40)')
    ds.execute(
        'INSERT INTO purchase_order_lines '
        '(id, order_id, net_amount, tax_amount, gross_amount) '
        'VALUES (3, 2, 100, 0, 100)')


def repair_purchase_order_gross_amount(ds):
    """把订单 2 的不含税 / 含税合计修正为明细聚合值。"""
    ds.execute(
        'UPDATE purchase_orders SET net_amount = 100, gross_amount = 100 '
        'WHERE id = 2')
