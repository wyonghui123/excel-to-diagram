# -*- coding: utf-8 -*-
"""裸 SQL DML 桥接助手 —— 让测试文件默认口径即运行 (2026-10-06)

【为什么放在 factories/】
  `meta/tests/conftest.py::_check_raw_sql_in_tests` 会把含裸 SQL DML
  (`INSERT INTO` / `UPDATE x SET` / `DELETE FROM`) 的测试文件**整体 skip**。
  教训(实测): `meta/tests/test_pricing_service.py` / `test_pricing_api.py`
  因内联 DML 常年 **42/30 skipped 而 Success=True** —— 测试本身真绿,
  却默认不跑(假绿)。本助手把 DML 收到 factories 白名单目录, 测试文件
  只以参数形式表达表/列/值, 从而不再命中正则, 无需 `ALLOW_RAW_SQL=1` 逃逸。

【对外接口】
  insert(ds, table, **values)             —— 插一行
  insert(ds, table, rows=[{...}, {...}])  —— 一次插多行
  update(ds, table, where, **values)      —— UPDATE ... SET ... WHERE ...
  delete(ds, table, **where)              —— DELETE FROM ... WHERE ...

  where 的值为 list/tuple/set 时展开成 `col IN (?, ?, ...)`, 否则 `col = ?`。

  ds 兼容 sqlite3.Connection 与 SQLiteAdapter: 二者都提供 `.execute(sql, params)`;
  无参数时改按 `.execute(sql)` 调用。
"""


def _run(ds, sql, params):
    if params:
        return ds.execute(sql, params)
    return ds.execute(sql)


def _where_clause(where):
    parts, params = [], []
    for col, val in where.items():
        if isinstance(val, (list, tuple, set)):
            vals = list(val)
            parts.append("{0} IN ({1})".format(
                col, ", ".join("?" for _ in vals)))
            params.extend(vals)
        else:
            parts.append("{0} = ?".format(col))
            params.append(val)
    return " AND ".join(parts), params


def insert(ds, table, rows=None, **values):
    """动态拼 INSERT INTO; `rows` 给定 dict 列表时一次插多行。"""
    if rows is not None:
        cols = []
        for row in rows:
            for key in row:
                if key not in cols:
                    cols.append(key)
        # [2026-10-20 修] VALUES 占位符组数须等于行数 —— 原实现只按列数生成
        # 一组 (len(cols) 个 "?"), 却按 行数×列数 传参 ⇒ sqlite3 报
        # "Incorrect number of bindings supplied" (5 used, 15 supplied)。
        # 该路径此前无测试覆盖(全库仅本文件用到 rows=), 故一直潜伏。
        sql = "INSERT INTO {0} ({1}) VALUES {2}".format(
            table, ", ".join(cols),
            ", ".join(
                "({0})".format(", ".join("?" for _ in cols))
                for _ in rows))
        params = []
        for row in rows:
            params.extend(row.get(c) for c in cols)
        return _run(ds, sql, params)
    cols = list(values)
    sql = "INSERT INTO {0} ({1}) VALUES ({2})".format(
        table, ", ".join(cols), ", ".join("?" for _ in cols))
    return _run(ds, sql, [values[c] for c in cols])


def update(ds, table, where, **values):
    """动态拼 UPDATE ... SET ... WHERE ..."""
    set_cols = list(values)
    set_sql = ", ".join("{0} = ?".format(c) for c in set_cols)
    where_sql, where_params = _where_clause(where)
    sql = "UPDATE {0} SET {1} WHERE {2}".format(table, set_sql, where_sql)
    params = [values[c] for c in set_cols] + where_params
    return _run(ds, sql, params)


def delete(ds, table, **where):
    """动态拼 DELETE FROM ... WHERE ..."""
    where_sql, where_params = _where_clause(where)
    sql = "DELETE FROM {0} WHERE {1}".format(table, where_sql)
    return _run(ds, sql, where_params)
