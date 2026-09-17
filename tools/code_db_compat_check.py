#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
code_db_compat_check.py - 通用 SQL 列引用 vs DB schema 兼容性检查

设计原则 (无开发假设):
  - 不假设具体表名/列名/SQL 方言
  - 输入: 任意 .py 文件 + 任意 SQLite DB
  - 输出: JSON 报告 {compatibility_issues: [{file, line, sql, table, column, reason}]}

用法:
  python code_db_compat_check.py --files f1.py f2.py --db /path/to.db
  python code_db_compat_check.py --files f1.py --db db.sqlite --json

实现策略 (双引擎, 兜底):
  1. AST 解析: 提取 .py 里的所有 string literal, 过滤出 SQL
  2. sqlparse 解析: 提取 SQL 中的 (table, column) 引用
  3. 正则兜底: sqlparse 失败时用 column/table pattern 提取
  4. DB schema: PRAGMA table_info + sqlite_master
  5. 比对: code 引用 column 是否在 table 存在

不依赖:
  - ORM 模型
  - 特定 Python 框架
  - 特定的 migration 系统
  - 特定的命名约定
"""
import argparse
import ast
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any


# --------------------------------------------------------------------------
# 1. 提取 .py 文件中的所有 SQL 字符串
# --------------------------------------------------------------------------
def extract_sql_strings(py_file: Path) -> list:
    """AST 提取 .py 文件里所有 string literal, 过滤出 SQL-like 的.

    Returns:
        list of {line, col, sql} dicts
    """
    try:
        source = py_file.read_text(encoding='utf-8', errors='replace')
        tree = ast.parse(source, filename=str(py_file))
    except SyntaxError:
        # 文件可能有语法错误 (e.g. half-written), 退回用 regex
        return _extract_sql_regex_fallback(source, py_file)

    results = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            sql = node.value.strip()
            if _looks_like_sql(sql):
                results.append({
                    'line': node.lineno,
                    'col': node.col_offset,
                    'sql': sql,
                })
    return results


def _extract_sql_regex_fallback(source: str, py_file: Path) -> list:
    """Fallback: 用 triple-quote / 双引号 字符串 pattern 找 SQL."""
    results = []
    # 匹配 """...""" 或 '''...''' 或 "..." 或 '...'
    patterns = [
        (r'"""(.*?)"""', re.DOTALL),
        (r"'''(.*?)'''", re.DOTALL),
        (r'"([^"\\]*(?:\\.[^"\\]*)*)"', 0),
        (r"'([^'\\]*(?:\\.[^'\\]*)*)'", 0),
    ]
    line = 1
    for pat, flags in patterns:
        for m in re.finditer(pat, source, flags):
            content = m.group(1) if '(' in pat else m.group(0)[1:-1]
            if _looks_like_sql(content):
                results.append({
                    'line': line,
                    'col': m.start(),
                    'sql': content.strip(),
                })
        line = source[:m.start()].count('\n') + 1 if m else line
    return results


def _looks_like_sql(text: str) -> bool:
    """判断字符串是否像 SQL (启发式)."""
    if not text or len(text) < 5:
        return False
    text_upper = text.upper().lstrip()
    sql_keywords = (
        'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP',
        'ALTER', 'REPLACE', 'PRAGMA', 'WITH', 'EXPLAIN', 'VACUUM',
    )
    return any(text_upper.startswith(kw) for kw in sql_keywords)


# --------------------------------------------------------------------------
# 2. 解析 SQL 提取 (table, column) 引用
# --------------------------------------------------------------------------
def parse_sql_references(sql: str) -> list:
    """解析 SQL, 提取所有 (table, column, op) 引用.

    Returns:
        list of {table, column, op} dicts, op ∈ {create_table, create_index, insert, select, where, fk, unique}
    """
    refs = []

    # 尝试用 sqlparse (可选依赖)
    try:
        import sqlparse
        return _parse_with_sqlparse(sql)
    except ImportError:
        pass

    # Fallback: 正则解析
    return _parse_with_regex(sql)


def _parse_with_sqlparse(sql: str) -> list:
    """用 sqlparse 解析. 提取 CREATE TABLE/INDEX + INSERT + SELECT/WHERE."""
    import sqlparse
    from sqlparse.sql import Identifier, IdentifierList, Where, Parenthesis, Function
    from sqlparse.tokens import Keyword, DML, DDL, Punctuation, Name

    refs = []
    parsed = sqlparse.parse(sql)
    for stmt in parsed:
        stmt_type = stmt.get_type()
        # CREATE TABLE
        if 'CREATE' in stmt_type.upper() or any(t.ttype is Keyword and t.value.upper() == 'CREATE'
                                              for t in stmt.tokens):
            refs.extend(_extract_create_table(stmt))
        # CREATE INDEX
        if any(t.value.upper() == 'CREATE' for t in stmt.tokens if hasattr(t, 'value')):
            refs.extend(_extract_create_index(stmt))
        # INSERT
        if stmt_type.upper() == 'INSERT':
            refs.extend(_extract_insert(stmt))
        # SELECT
        if stmt_type.upper() == 'SELECT':
            refs.extend(_extract_select(stmt))
        # UPDATE/DELETE
        if stmt_type.upper() in ('UPDATE', 'DELETE'):
            refs.extend(_extract_update_delete(stmt))

    return refs


def _extract_create_table(stmt) -> list:
    """提取 CREATE TABLE 中的列名."""
    refs = []
    table_name = None
    in_columns = False
    paren_depth = 0

    for tok in stmt.flatten():
        if hasattr(tok, 'value'):
            val = tok.value.strip()
            # 找表名: CREATE TABLE [IF NOT EXISTS] table_name
            if table_name is None and val.upper() in ('TABLE', 'IF', 'NOT', 'EXISTS'):
                continue
            if table_name is None and val and not val.startswith('(') and not val.upper() in (
                'TEMP', 'TEMPORARY', 'UNIQUE', 'INDEX', 'VIEW', 'TRIGGER'):
                table_name = val.strip('"[]`')

    # 简化: 用正则兜底
    text = str(stmt)
    m = re.search(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`[]?(\w+)["`\]]?', text, re.IGNORECASE)
    if m:
        table_name = m.group(1)
        # 找列定义 (在括号内)
        col_m = re.search(r'\((.+)\)', text, re.DOTALL)
        if col_m:
            cols_text = col_m.group(1)
            # 拆分行/字段
            for line in cols_text.split(','):
                line = line.strip()
                if not line:
                    continue
                # 列定义: column_name TYPE [constraints...]
                parts = line.split()
                if parts and re.match(r'^[a-zA-Z_]\w*$', parts[0]):
                    col_name = parts[0]
                    refs.append({'table': table_name, 'column': col_name, 'op': 'create_table'})
                # UNIQUE(col1, col2)
                um = re.match(r'UNIQUE\s*\(([^)]+)\)', line, re.IGNORECASE)
                if um:
                    for col in um.group(1).split(','):
                        col = col.strip()
                        if re.match(r'^[a-zA-Z_]\w*$', col):
                            refs.append({'table': table_name, 'column': col, 'op': 'unique'})
                # FOREIGN KEY (col) REFERENCES other(col)
                fkm = re.match(r'FOREIGN\s+KEY\s*\(([^)]+)\)', line, re.IGNORECASE)
                if fkm:
                    for col in fkm.group(1).split(','):
                        col = col.strip()
                        if re.match(r'^[a-zA-Z_]\w*$', col):
                            refs.append({'table': table_name, 'column': col, 'op': 'fk'})
    return refs


def _extract_create_index(stmt) -> list:
    """提取 CREATE INDEX 中的列名."""
    refs = []
    text = str(stmt)
    # CREATE [UNIQUE] INDEX [IF NOT EXISTS] idx_name ON table_name (col1, col2)
    m = re.search(
        r'CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?'
        r'(?:\w+\s+)?ON\s+["`[]?(\w+)["`\]]?\s*\(([^)]+)\)',
        text, re.IGNORECASE
    )
    if m:
        table_name = m.group(1)
        cols = [c.strip() for c in m.group(2).split(',')]
        for col in cols:
            if re.match(r'^[a-zA-Z_]\w*$', col):
                refs.append({'table': table_name, 'column': col, 'op': 'create_index'})
    return refs


def _extract_insert(stmt) -> list:
    """提取 INSERT INTO ... (col1, col2) 列名."""
    refs = []
    text = str(stmt)
    # INSERT INTO table_name (col1, col2) VALUES (...)
    m = re.search(
        r'INSERT\s+(?:OR\s+\w+\s+)?INTO\s+["`[]?(\w+)["`\]]?\s*\(([^)]+)\)',
        text, re.IGNORECASE
    )
    if m:
        table_name = m.group(1)
        cols = [c.strip() for c in m.group(2).split(',')]
        for col in cols:
            if re.match(r'^[a-zA-Z_]\w*$', col):
                refs.append({'table': table_name, 'column': col, 'op': 'insert'})
    return refs


def _extract_select(stmt) -> list:
    """提取 SELECT/WHERE 中的列引用 (简化, 只抓 WHERE col)."""
    refs = []
    text = str(stmt)
    # WHERE col = ? / WHERE col = 'x'
    for m in re.finditer(r'WHERE\s+["`[]?(\w+)["`\]]?\s*[=<>!]', text, re.IGNORECASE):
        col = m.group(1)
        if col.upper() in ('NOT', 'NULL', 'EXISTS', 'LIKE', 'IN'):
            continue
        refs.append({'table': None, 'column': col, 'op': 'where'})
    return refs


def _extract_update_delete(stmt) -> list:
    """提取 UPDATE table SET col=... / DELETE FROM table."""
    refs = []
    text = str(stmt)
    # UPDATE table SET col=...
    m = re.search(r'UPDATE\s+["`[]?(\w+)["`\]]?\s+SET\s+["`[]?(\w+)["`\]]?', text, re.IGNORECASE)
    if m:
        refs.append({'table': m.group(1), 'column': m.group(2), 'op': 'update'})
    return refs


def _parse_with_regex(sql: str) -> list:
    """Fallback 正则解析 (覆盖 CREATE TABLE / INDEX / INSERT)."""
    refs = []
    # Multiple statements separated by ;
    for one_sql in sql.split(';'):
        one_sql = one_sql.strip()
        if not one_sql:
            continue
        # CREATE TABLE
        m = re.search(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`[]?(\w+)["`\]]?', one_sql, re.IGNORECASE)
        if m:
            table_name = m.group(1)
            paren_match = re.search(r'\((.+)\)', one_sql, re.DOTALL)
            if paren_match:
                for col in _extract_columns_from_definition(paren_match.group(1)):
                    refs.append({'table': table_name, 'column': col, 'op': 'create_table'})
        # CREATE INDEX
        m = re.search(
            r'CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?'
            r'(?:\w+\s+)?ON\s+["`[]?(\w+)["`\]]?\s*\(([^)]+)\)',
            one_sql, re.IGNORECASE
        )
        if m:
            table_name = m.group(1)
            for col in m.group(2).split(','):
                col = col.strip()
                if re.match(r'^[a-zA-Z_]\w*$', col):
                    refs.append({'table': table_name, 'column': col, 'op': 'create_index'})
        # INSERT
        m = re.search(
            r'INSERT\s+(?:OR\s+\w+\s+)?INTO\s+["`[]?(\w+)["`\]]?\s*\(([^)]+)\)',
            one_sql, re.IGNORECASE
        )
        if m:
            for col in m.group(2).split(','):
                col = col.strip()
                if re.match(r'^[a-zA-Z_]\w*$', col):
                    refs.append({'table': m.group(1), 'column': col, 'op': 'insert'})
    return refs


def _extract_columns_from_definition(cols_text: str) -> list:
    """从 CREATE TABLE 的列定义块中提取列名."""
    cols = []
    for line in cols_text.split(','):
        line = line.strip()
        if not line:
            continue
        # PRIMARY KEY(col) / UNIQUE(col1, col2) / FOREIGN KEY(col) - 这些是约束
        um = re.match(r'UNIQUE\s*\(([^)]+)\)', line, re.IGNORECASE)
        if um:
            for c in um.group(1).split(','):
                c = c.strip()
                if re.match(r'^[a-zA-Z_]\w*$', c):
                    cols.append(c)
            continue
        fkm = re.match(r'FOREIGN\s+KEY\s*\(([^)]+)\)', line, re.IGNORECASE)
        if fkm:
            for c in fkm.group(1).split(','):
                c = c.strip()
                if re.match(r'^[a-zA-Z_]\w*$', c):
                    cols.append(c)
            continue
        # PRIMARY KEY (col) - 单列
        pm = re.match(r'PRIMARY\s+KEY\s*\(([^)]+)\)', line, re.IGNORECASE)
        if pm:
            for c in pm.group(1).split(','):
                c = c.strip()
                if re.match(r'^[a-zA-Z_]\w*$', c):
                    cols.append(c)
            continue
        # CONSTRAINT name ... 跳过
        if line.upper().startswith('CONSTRAINT'):
            continue
        # 列定义: column_name TYPE
        parts = line.split()
        if parts and re.match(r'^[a-zA-Z_]\w*$', parts[0]):
            cols.append(parts[0])
    return cols


# --------------------------------------------------------------------------
# 3. 加载 DB schema
# --------------------------------------------------------------------------
def load_db_schema(db_path: Path) -> dict:
    """加载 DB 全 schema, 返回 {table: [columns]}.

    Returns:
        dict[str, list[str]] - table name -> column list
    """
    if not db_path.exists():
        return {}
    conn = sqlite3.connect(str(db_path))
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        schema = {}
        for t in tables:
            cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{t}")').fetchall()]
            schema[t] = cols
        return schema
    finally:
        conn.close()


# --------------------------------------------------------------------------
# 4. 对比 + 输出报告
# --------------------------------------------------------------------------
def check_compatibility(py_files: list, db_path: Path) -> dict:
    """主入口: 检查 .py 文件 SQL 引用 vs DB schema 兼容性."""
    schema = load_db_schema(db_path)
    issues = []
    stats = {
        'files_scanned': len(py_files),
        'sql_strings_extracted': 0,
        'refs_extracted': 0,
    }

    for py_file in py_files:
        if not py_file.exists():
            issues.append({
                'file': str(py_file),
                'line': 0,
                'table': None,
                'column': None,
                'reason': 'file not found',
            })
            continue

        sql_strings = extract_sql_strings(py_file)
        stats['sql_strings_extracted'] += len(sql_strings)

        for sql_info in sql_strings:
            refs = parse_sql_references(sql_info['sql'])
            stats['refs_extracted'] += len(refs)

            for ref in refs:
                table = ref.get('table')
                column = ref.get('column')
                op = ref.get('op')

                if not table:
                    # WHERE col - 无法确定表, 跳过 (除非所有表都没这个列)
                    if column:
                        in_any_table = any(column in cols for cols in schema.values())
                        if not in_any_table and schema:
                            issues.append({
                                'file': str(py_file),
                                'line': sql_info['line'],
                                'table': '*unknown*',
                                'column': column,
                                'op': op,
                                'reason': f'column "{column}" not found in any table',
                                'sql_snippet': sql_info['sql'][:200],
                            })
                    continue

                if table not in schema:
                    issues.append({
                        'file': str(py_file),
                        'line': sql_info['line'],
                        'table': table,
                        'column': column,
                        'op': op,
                        'reason': f'table "{table}" not found in DB',
                        'sql_snippet': sql_info['sql'][:200],
                    })
                    continue

                if column not in schema[table]:
                    issues.append({
                        'file': str(py_file),
                        'line': sql_info['line'],
                        'table': table,
                        'column': column,
                        'op': op,
                        'reason': f'column "{column}" not found in table "{table}" (existing: {schema[table][:10]}...)',
                        'sql_snippet': sql_info['sql'][:200],
                    })

    return {
        'db_path': str(db_path),
        'db_tables_count': len(schema),
        'compatibility_issues': issues,
        'stats': stats,
        'ok': len(issues) == 0,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description='[P0-1] 通用 SQL 列引用 vs DB schema 兼容性检查 (无开发假设)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python code_db_compat_check.py --files meta/scripts/init_auth.py --db db.sqlite
  python code_db_compat_check.py --files f1.py f2.py --db db.sqlite --json
  python code_db_compat_check.py --files init_auth.py --db db.sqlite --exit-code
        """
    )
    parser.add_argument('--files', nargs='+', required=True, help='要扫描的 .py 文件列表')
    parser.add_argument('--db', required=True, help='SQLite DB 路径')
    parser.add_argument('--json', action='store_true', help='JSON 输出')
    parser.add_argument('--exit-code', action='store_true', help='不兼容时 exit 1')

    args = parser.parse_args()

    py_files = [Path(f).resolve() for f in args.files]
    db_path = Path(args.db).resolve()

    result = check_compatibility(py_files, db_path)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        # Human-readable
        print(f"[DB] {result['db_path']}")
        print(f"[DB] {result['db_tables_count']} tables")
        print(f"[STATS] files={result['stats']['files_scanned']}, "
              f"sql_strings={result['stats']['sql_strings_extracted']}, "
              f"refs={result['stats']['refs_extracted']}")
        print(f"[STATS] issues={len(result['compatibility_issues'])}")
        print()
        if result['compatibility_issues']:
            print(f"[!!] {len(result['compatibility_issues'])} compatibility issues:")
            for i, issue in enumerate(result['compatibility_issues'][:50], 1):
                print(f"  {i}. {issue['file']}:{issue['line']}")
                print(f"     table={issue['table']}, column={issue['column']}, op={issue.get('op', '?')}")
                print(f"     reason: {issue['reason']}")
                if 'sql_snippet' in issue:
                    print(f"     sql: {issue['sql_snippet'][:120]}")
        else:
            print("[OK] No compatibility issues found")

    if args.exit_code and not result['ok']:
        sys.exit(1)
    sys.exit(0 if result['ok'] else (1 if args.exit_code else 0))


if __name__ == '__main__':
    main()