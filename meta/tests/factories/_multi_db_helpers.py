# -*- coding: utf-8 -*-
"""[多产品平台] 多库隔离测试辅助

DDL + DML 集中在此 —— `meta/tests/conftest.py` 的 `_check_raw_sql_in_tests()`
会 skip 含 `INSERT INTO` / `UPDATE ... SET` / `DELETE FROM` 的**测试文件**,
`meta/tests/factories/` 是唯一白名单目录。
"""
from typing import List

MARKER_TABLE = 'multi_db_marker'


def create_marker_table(ds) -> None:
    """在给定数据源上建标记表（幂等）。"""
    ds.execute(
        f'CREATE TABLE IF NOT EXISTS {MARKER_TABLE} '
        f'(id INTEGER PRIMARY KEY AUTOINCREMENT, origin VARCHAR(32))'
    )


def insert_marker(ds, origin: str) -> None:
    """写入一行来源标记。"""
    ds.execute(f'INSERT INTO {MARKER_TABLE} (origin) VALUES (?)', (origin,))


def read_markers(ds) -> List[str]:
    """读回全部来源标记（按 id 升序）。"""
    rows = ds.query(f'SELECT origin FROM {MARKER_TABLE} ORDER BY id')
    return [row['origin'] for row in rows]
