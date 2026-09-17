# -*- coding: utf-8 -*-
"""
[FILE] _spec20_bizkey_helpers.py
[DESCRIPTION] Spec 20 业务键锚定测试数据种子 (DDL/DML 集中于 factories/ 白名单目录)

数据拓扑 (验证业务键跨版本稳定性):
  产品 P_A(id=1): 版本 v01(id=10) → domain SCM(id=64)/FIN(id=70)
                  版本 v02(id=11) → domain SCM(id=88)
  产品 P_B(id=2): 版本 v01(id=20) → domain SCM(id=90)
  domain SCM(id=64) 下: sub_domain SCM_PL(301)/SCM_PUR(302)
"""
import json


def seed_bizkey_data(ds) -> None:
    """种子: 三版本下同 code='SCM' 的领域 (业务键跨版本稳定的 DB 事实)."""
    ds.execute("INSERT INTO products (id, name, code) VALUES (?, ?, ?)", [1, '产品A', 'P_A'])
    ds.execute("INSERT INTO products (id, name, code) VALUES (?, ?, ?)", [2, '产品B', 'P_B'])
    ds.execute("INSERT INTO versions (id, name, code, product_id) VALUES (?, ?, ?, ?)", [10, 'v1', 'v01', 1])
    ds.execute("INSERT INTO versions (id, name, code, product_id) VALUES (?, ?, ?, ?)", [11, 'v2', 'v02', 1])
    ds.execute("INSERT INTO versions (id, name, code, product_id) VALUES (?, ?, ?, ?)", [20, 'v1', 'v01', 2])
    ds.execute("INSERT INTO domains (id, name, code, version_id) VALUES (?, ?, ?, ?)", [64, '供应链云', 'SCM', 10])
    ds.execute("INSERT INTO domains (id, name, code, version_id) VALUES (?, ?, ?, ?)", [88, '供应链云', 'SCM', 11])
    ds.execute("INSERT INTO domains (id, name, code, version_id) VALUES (?, ?, ?, ?)", [70, '财务云', 'FIN', 10])
    ds.execute("INSERT INTO domains (id, name, code, version_id) VALUES (?, ?, ?, ?)", [90, '供应链云', 'SCM', 20])
    ds.execute("INSERT INTO sub_domains (id, name, code, domain_id) VALUES (?, ?, ?, ?)", [301, '计划', 'SCM_PL', 64])
    ds.execute("INSERT INTO sub_domains (id, name, code, domain_id) VALUES (?, ?, ?, ?)", [302, '采购', 'SCM_PUR', 64])


def add_scope(ds, ps_id: int, dim: str, vals: list,
              mode: str = 'include', inherit: int = 1) -> None:
    """插入一条 permission_set_dimension_scopes."""
    ds.execute(
        "INSERT INTO permission_set_dimension_scopes "
        "(permission_set_id, dimension_code, dimension_values, inherit_children, scope_mode) "
        "VALUES (?, ?, ?, ?, ?)",
        [ps_id, dim, json.dumps(vals), inherit, mode]
    )


def insert_domain(ds, domain_id: int, code: str, name: str, version_id: int) -> None:
    """模拟版本升级: 新版本下插入同 code 领域 (G2 铁证用)."""
    ds.execute(
        "INSERT INTO domains (id, name, code, version_id) VALUES (?, ?, ?, ?)",
        [domain_id, name, code, version_id]
    )


def insert_version(ds, version_id: int, code: str, name: str, product_id: int) -> None:
    """插入新版本 (G2 铁证用)."""
    ds.execute(
        "INSERT INTO versions (id, name, code, product_id) VALUES (?, ?, ?, ?)",
        [version_id, name, code, product_id]
    )


def insert_sub_domain(ds, sub_id: int, code: str, name: str, domain_id: int) -> None:
    """插入新 sub_domain (G2 铁证用)."""
    ds.execute(
        "INSERT INTO sub_domains (id, name, code, domain_id) VALUES (?, ?, ?, ?)",
        [sub_id, name, code, domain_id]
    )


def query_ids(ds, table: str, sql_condition: str) -> set:
    """执行条件 SQL 返回命中 id 集合 (G2 铁证用)."""
    rows = ds.execute(f"SELECT id FROM {table} WHERE {sql_condition}").fetchall()
    return {r[0] for r in rows}
