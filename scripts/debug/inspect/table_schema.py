#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据库表结构探索工具 - 调试基础设施 P1 (v2026.06.21)

背景：2026-06-21 复盘两次调试事故（SM/BO 误拦 + 字段映射错误），
     Agent 反复查询表结构 + 字段映射。第二次调试中：
     `source_bo_code` 字段实际全 NULL，应该用 `source_code`。
     字段名错浪费 1+ 小时。

核心功能：
- 一键列出表的所有字段 + 字段类型 + 非空比例 + 实际有值的字段
- 检测"字段映射错误"（代码用 NULL 字段，应该用非空字段）
- 列出"包含 'code' 的字段"（用于发现正确字段名）

用法：
    # 查看表结构 + 实际有值的字段
    python scripts/debug/inspect/table_schema.py relationships

    # 只看字段名（用于发现正确字段）
    python scripts/debug/inspect/table_schema.py relationships --fields-only

    # 检测字段映射错误（对比代码期望 vs 实际）
    python scripts/debug/inspect/table_schema.py relationships --check-code-fields

    # 多表对比
    python scripts/debug/inspect/table_schema.py relationships business_objects users
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# 修复 Windows GBK 编码问题
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass



def _log(msg: str, level: str = "INFO"):
    icons = {"OK": "[OK]", "FAIL": "[X]", "WARN": "[!]", "INFO": "[i]"}
    print(f"{icons.get(level, '[?]}')} {msg}", file=sys.stderr)


def load_dotenv(dotenv_path: Optional[Path] = None) -> bool:
    """自动加载 .env 文件到 os.environ"""
    if dotenv_path is None:
        dotenv_path = PROJECT_ROOT / ".env"

    if not dotenv_path.exists():
        return False

    try:
        with open(dotenv_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                # 只设置未设置的环境变量（避免覆盖）
                if key and key not in os.environ:
                    os.environ[key] = value
        return True
    except (OSError, UnicodeDecodeError):
        return False


def run_sql(sql: str, timeout: int = 30) -> List[str]:
    """执行 SQL 查询（pipe-separated output）"""
    # V3.3 修复：自动加载 .env
    if not os.environ.get("DATABASE_URL"):
        if load_dotenv():
            _log(f"已加载 .env 文件", "INFO")

    db_url = os.environ.get("DATABASE_URL", "")
    if db_url.startswith("postgres"):
        try:
            result = subprocess.run(
                ["psql", "-t", "-A", "-F", "|", "-c", sql, db_url],
                capture_output=True, text=True, timeout=timeout,
            )
            if result.returncode == 0:
                return [line.strip() for line in result.stdout.splitlines() if line.strip()]
            return []
        except FileNotFoundError:
            _log("psql 未安装", "FAIL")
            return []
    else:
        _log(f"数据库未配置 (DATABASE_URL={db_url!r})", "WARN")
        return []


def get_table_schema(table: str) -> List[Dict]:
    """获取表的字段信息"""
    sql = f"""SELECT column_name, data_type, is_nullable, column_default
              FROM information_schema.columns
              WHERE table_name = '{table}'
              ORDER BY ordinal_position;"""
    rows = run_sql(sql)
    schema = []
    for r in rows:
        if '|' in r:
            parts = r.split('|')
            if len(parts) >= 4:
                schema.append({
                    "column_name": parts[0],
                    "data_type": parts[1],
                    "is_nullable": parts[2],
                    "column_default": parts[3] if parts[3] else None,
                })
    return schema


def get_field_stats(table: str, sample_size: int = 1000) -> Dict[str, Dict]:
    """获取表字段的统计信息（非空比例、唯一值数等）"""
    # 检查表是否有数据
    count_sql = f"SELECT COUNT(*) FROM {table};"
    count_result = run_sql(count_sql)
    total_rows = int(count_result[0]) if count_result else 0

    if total_rows == 0:
        return {}

    schema = get_table_schema(table)
    stats = {}

    for field in schema:
        col = field["column_name"]
        # 非空数
        not_null_sql = f"SELECT COUNT({col}) FROM {table} WHERE {col} IS NOT NULL;"
        nn_result = run_sql(not_null_sql)
        not_null = int(nn_result[0]) if nn_result else 0

        stats[col] = {
            "total": total_rows,
            "not_null": not_null,
            "not_null_ratio": not_null / total_rows if total_rows > 0 else 0,
            "data_type": field["data_type"],
        }

    return stats


def print_table_summary(table: str, schema: List[Dict], stats: Dict[str, Dict]):
    """打印表摘要"""
    print("=" * 70)
    print(f"表: {table}")
    print("=" * 70)
    print()

    if not schema:
        _log(f"表 {table} 不存在或没有字段", "FAIL")
        return

    print(f"## 字段（共 {len(schema)} 个）")
    print()

    # 打印字段 + 统计
    print(f"  {'字段名':<30} {'类型':<20} {'可空':<6} {'非空比例':<10} {'状态'}")
    print(f"  {'-'*30} {'-'*20} {'-'*6} {'-'*10} {'-'*10}")

    for field in schema:
        col = field["column_name"]
        data_type = field["data_type"]
        nullable = field["is_nullable"]

        if col in stats:
            ratio = stats[col]["not_null_ratio"]
            not_null = stats[col]["not_null"]
            total = stats[col]["total"]
            ratio_str = f"{ratio*100:.1f}%"
            status = ""
            if ratio == 0:
                status = "❌ 全 NULL"
            elif ratio < 0.1:
                status = "⚠️  极少"
            elif ratio > 0.9:
                status = "✓  常用"
            else:
                status = ""
        else:
            ratio_str = "N/A"
            status = ""

        print(f"  {col:<30} {data_type:<20} {nullable:<6} {ratio_str:<10} {status}")

    print()

    # 推荐有值的 code 字段
    code_fields = [
        (col, s) for col, s in stats.items()
        if "code" in col.lower() and s["not_null_ratio"] > 0.5
    ]

    if code_fields:
        print("## 推荐 'code' 字段（非空 > 50%）")
        for col, s in sorted(code_fields, key=lambda x: x[1]["not_null_ratio"], reverse=True):
            print(f"  ✓ {col} (非空 {s['not_null_ratio']*100:.1f}%)")
        print()

    # 警告全 NULL 字段
    null_fields = [
        (col, s) for col, s in stats.items()
        if s["not_null_ratio"] == 0
    ]

    if null_fields:
        print("## ⚠️  全 NULL 字段（可能字段名错误）")
        for col, s in null_fields:
            print(f"  - {col}")
        print()


def check_code_fields(table: str, stats: Dict[str, Dict]) -> int:
    """检测代码期望的 code 字段是否真的有值"""
    # 启发式：检测可能"字段名错"的模式
    # 例如 relationship 有 source_bo_code（全NULL）和 source_code（有值）

    code_fields = [(col, s) for col, s in stats.items() if "code" in col.lower()]
    null_codes = [col for col, s in code_fields if s["not_null_ratio"] == 0]
    non_null_codes = [col for col, s in code_fields if s["not_null_ratio"] > 0.5]

    if not (null_codes and non_null_codes):
        return 0

    # 检查 null 字段名是否被 non_null 字段名"包含"
    issues = []
    for null_col in null_codes:
        # 移除后缀比较，例如 source_bo_code vs source_code
        null_stem = re.sub(r'_(?:bo|id)_code$', '_code', null_col)
        for non_null_col in non_null_codes:
            non_null_stem = re.sub(r'_(?:bo|id)_code$', '_code', non_null_col)
            if null_stem == non_null_stem:
                issues.append({
                    "type": "FIELD_NAME_CONFUSION",
                    "null_field": null_col,
                    "real_field": non_null_col,
                    "hint": f"代码用 {null_col} 但实际有值的是 {non_null_col}",
                })

    if not issues:
        return 0

    print("=" * 70)
    print(f"⚠️  字段映射错误检测 - {table}")
    print("=" * 70)
    print()
    for issue in issues:
        print(f"  类型: {issue['type']}")
        print(f"  ❌ 错误字段: {issue['null_field']}")
        print(f"  ✓  正确字段: {issue['real_field']}")
        print(f"  提示: {issue['hint']}")
        print()

    return len(issues)


def main():
    parser = argparse.ArgumentParser(
        description="数据库表结构探索工具 - V2.1 调试基础设施 P1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("tables", nargs="+", help="要查看的表名")
    parser.add_argument("--fields-only", action="store_true",
                        help="只列出字段名（快速模式）")
    parser.add_argument("--check-code-fields", action="store_true",
                        help="检测 code 字段映射错误")
    parser.add_argument("--json", action="store_true",
                        help="输出 JSON 格式")

    args = parser.parse_args()

    total_issues = 0
    all_results = {}

    for table in args.tables:
        if args.fields_only:
            schema = get_table_schema(table)
            if args.json:
                all_results[table] = schema
            else:
                print(f"{table}: {[f['column_name'] for f in schema]}")
            continue

        schema = get_table_schema(table)
        stats = get_field_stats(table)

        if args.json:
            all_results[table] = {
                "schema": schema,
                "stats": stats,
            }
        else:
            print_table_summary(table, schema, stats)

        if args.check_code_fields:
            issues = check_code_fields(table, stats)
            total_issues += issues

    if args.json:
        print(json.dumps(all_results, ensure_ascii=False, indent=2))

    if total_issues > 0:
        _log(f"发现 {total_issues} 个字段映射问题", "FAIL")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)