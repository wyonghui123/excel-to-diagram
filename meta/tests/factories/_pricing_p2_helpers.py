# -*- coding: utf-8 -*-
"""定价 P2 六对象 —— schema / 真外键测试的建表与播种助手 (2026-10-06)

【为什么放在 factories/】
  `meta/tests/conftest.py::_check_raw_sql_in_tests` 会把**含裸 SQL DML**
  (`INSERT INTO` / `UPDATE x SET` / `DELETE FROM`) 的测试文件**整体 skip**。
  教训(实测): `meta/tests/test_pricing_service.py` 因内联 DML 常年
  **42 skipped 而 Success=True** —— 测试本身真绿, 却默认不跑(假绿)。
  本助手把 DML 收到 factories 白名单目录, 使定价相关测试**默认口径即运行**,
  无需 `ALLOW_RAW_SQL=1` 逃逸。

【对外接口】
  create_tables(conn, names)      —— 按 yaml 声明真建表(含索引), 不播种
  seed_row(conn, table, **values) —— 插一行; 未给的 NOT NULL 列自动补占位值
"""


def create_tables(conn, names):
    """按 registry 中的 yaml 声明真建表 + 建索引。

    调用前需自行 `registry.reload(<schemas 目录>)`。返回实际建表名列表。
    """
    from meta.core.models import registry
    from meta.core.schema_generator import SchemaGenerator

    gen = SchemaGenerator("sqlite")
    built = []
    for name in names:
        mo = registry.get(name)
        assert mo is not None, "{0} 未注册".format(name)
        sql = gen.generate_create_table(mo)
        assert sql, "{0} 未生成 DDL".format(name)
        conn.execute(sql)
        for idx in gen.generate_create_index(mo):
            conn.execute(idx)
        built.append(name)
    return built


def required_defaults(conn, table):
    """从 PRAGMA table_info 推出该表 NOT NULL 且无默认值的列 → 占位值。

    目的: 让 FK 用例只需给"关键列", 不必为几十个 NOT NULL 业务列凑值。
    """
    out = {}
    for row in conn.execute("PRAGMA table_info({0})".format(table)).fetchall():
        _cid, name, ctype, notnull, dflt, _pk = row
        if name == "id" or not notnull or dflt is not None:
            continue
        t = (ctype or "").upper()
        if "INT" in t:
            out[name] = 0
        elif any(k in t for k in ("REAL", "FLOA", "DOUB", "NUM")):
            out[name] = 0.0
        elif "DATETIME" in t:
            out[name] = "2026-10-06 00:00:00"
        else:
            out[name] = "T"
    return out


def seed_row(conn, table, **values):
    """插一行: `values` 覆盖 NOT NULL 占位值。表名/列名均来自本仓清单, 非外部输入。"""
    row = required_defaults(conn, table)
    row.update(values)
    cols = list(row)
    sql = "INSERT INTO {0} ({1}) VALUES ({2})".format(
        table, ", ".join(cols), ", ".join("?" for _ in cols)
    )
    return conn.execute(sql, [row[c] for c in cols])
