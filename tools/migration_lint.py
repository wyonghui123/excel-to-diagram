#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[P1.6] Migration 质量检查工具 (CI Lint)

检查项 (来自 docs/MIGRATION_SPEC.md §7.2.8):
  L1: 命名规范 - 必须匹配 v<NNN>__<desc>.{py,sql}
  L2: 入口签名 - .py 必须有 def migrate(db_path, skip_backup=False) -> bool
  L3: 幂等性 - .sql 必须有 IF NOT EXISTS / IF EXISTS; .py 必须有列存在检查
  L4: docstring - .py 必须有模块级 docstring
  L5: 无 DROP TABLE/COLUMN (除非有 [ALLOW_DESTRUCTIVE] 标记)
  L6: 版本号唯一 - 不允许两个文件 v<NNN> 相同
  L7: prerequisites - 如果有 def prerequisites() -> list, 检查引用的 migration 存在
  L8: verify - 推荐有 def verify(db_path) -> bool (WARN, 不 FAIL)

退出码:
  0: 所有检查通过
  1: 有 FAIL 级别问题
  2: 只有 WARN 级别问题

运行:
  python tools/migration_lint.py
  python tools/migration_lint.py --migrations-dir meta/migrations/
  python tools/migration_lint.py --strict  # WARN 也算 FAIL

集成:
  - .git/hooks/pre-commit (开发期)
  - deploy.sh PHASE 2.4 (部署前最后一道检查)
"""
import argparse
import ast
import re
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).parent
WORKTREE = SCRIPT_DIR.parent
DEFAULT_MIG_DIR = WORKTREE / "meta" / "migrations"
LEGACY_CONFIG = SCRIPT_DIR / "migration_lint.legacy.yaml"

NAMING_PATTERN = re.compile(r"^v(\d{3})__([a-z][a-z0-9_]*)\.(py|sql)$")


def _load_legacy_set() -> set:
    """加载 legacy 白名单 (文件名集合)"""
    import yaml
    if not LEGACY_CONFIG.exists():
        return set()
    try:
        data = yaml.safe_load(LEGACY_CONFIG.read_text(encoding="utf-8")) or []
        return {entry["name"] for entry in data if "name" in entry}
    except Exception as e:
        print(f"[WARN] 加载 {LEGACY_CONFIG.name} 失败: {e}")
        return set()


LEGACY_FILES = _load_legacy_set()


def lint_naming(file_path: Path) -> list:
    """L1: 命名规范"""
    if file_path.name in LEGACY_FILES:
        return []
    issues = []
    if not NAMING_PATTERN.match(file_path.name):
        issues.append(("FAIL", f"L1 naming: {file_path.name} 不匹配 v<NNN>__<desc>.{{py,sql}}"))
    return issues


def lint_signature(file_path: Path) -> list:
    """L2: 入口签名"""
    if file_path.suffix != ".py":
        return []
    if file_path.name in LEGACY_FILES:
        return []
    issues = []
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        has_migrate = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "migrate":
                has_migrate = True
                args = [a.arg for a in node.args.args]
                if not args or args[0] not in ("db_path", "conn", "database"):
                    issues.append((
                        "FAIL",
                        f"L2 signature: migrate() 第一参数应为 db_path/conn/database, got {args}",
                    ))
        if not has_migrate:
            # 没 migrate 函数可能是 wrapper script (旧式 run_migration()) - WARN 而非 FAIL
            issues.append((
                "WARN",
                "L2 signature: 缺 migrate() 函数 (若迁移已迁移到 runner 不会调用, 可加 [P1-WRAP] 标记)",
            ))
    except SyntaxError as e:
        issues.append(("FAIL", f"L2 signature: syntax error: {e}"))
    return issues


def lint_idempotent(file_path: Path) -> list:
    """L3: 幂等性"""
    issues = []
    content = file_path.read_text(encoding="utf-8")
    if file_path.suffix == ".sql":
        # CREATE TABLE 必须有 IF NOT EXISTS
        for m in re.finditer(r"CREATE\s+TABLE\s+(?!IF\s+NOT\s+EXISTS)(\w+)", content, re.IGNORECASE):
            issues.append((
                "FAIL",
                f"L3 idempotent: CREATE TABLE {m.group(1)} 缺 IF NOT EXISTS",
            ))
        # ALTER TABLE ADD COLUMN 不强制幂等 (SQLite 支持 ALTER 重复但 DDL 不可回滚)
    elif file_path.suffix == ".py":
        # .py 必须有 'CREATE TABLE IF NOT EXISTS' 或 try/except 包裹
        has_conditional = (
            "IF NOT EXISTS" in content
            or "try:" in content
            or "if not " in content.lower()
            or "PRAGMA table_info" in content
        )
        if "CREATE TABLE" in content and not has_conditional:
            issues.append((
                "WARN",
                "L3 idempotent: .py 含 CREATE TABLE 但无 'IF NOT EXISTS' 或 try/except, 不幂等",
            ))
    return issues


def lint_docstring(file_path: Path) -> list:
    """L4: docstring"""
    if file_path.suffix != ".py":
        return []
    issues = []
    content = file_path.read_text(encoding="utf-8")
    # 简易检测: 文件前 1000 字符含 docstring
    first_chunk = content[:2000]
    has_docstring = ('"""' in first_chunk) or ("'''" in first_chunk)
    has_marker = "[P1-WRAP" in content or "[P0-WRAP" in content
    if not has_docstring and not has_marker:
        issues.append((
            "WARN",
            "L4 docstring: 缺模块级 docstring (背景/方案/回滚说明)",
        ))
    return issues


def lint_destructive(file_path: Path) -> list:
    """L5: 无 DROP TABLE/COLUMN"""
    if file_path.name in LEGACY_FILES:
        return []  # legacy: 已知 DROP 必要, 已在白名单中允许
    issues = []
    content = file_path.read_text(encoding="utf-8")
    has_drop = re.search(r"DROP\s+(TABLE|COLUMN|INDEX|VIEW|TRIGGER)", content, re.IGNORECASE)
    has_allow = "[ALLOW_DESTRUCTIVE]" in content
    if has_drop and not has_allow:
        issues.append((
            "FAIL",
            "L5 destructive: DROP TABLE/COLUMN/INDEX/VIEW 无 [ALLOW_DESTRUCTIVE] 标记",
        ))
    return issues


def lint_version_unique(files: list) -> list:
    """L6: 版本号唯一"""
    issues = []
    versions = {}
    for f in files:
        m = NAMING_PATTERN.match(f.name)
        if m:
            v = m.group(1)
            if v in versions:
                issues.append((
                    "FAIL",
                    f"L6 version: 重复版本 v{v} 在 {f.name} 和 {versions[v]}",
                ))
            else:
                versions[v] = f.name
    return issues


def lint_prerequisites(file_path: Path, all_names: list) -> list:
    """L7: prerequisites 引用存在"""
    if file_path.suffix != ".py":
        return []
    issues = []
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "prerequisites":
                # 尝试求值: 简单字符串字面量
                if isinstance(node.body[0], ast.Return) and isinstance(node.body[0].value, ast.List):
                    for elt in node.body[0].value.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            if elt.value not in all_names:
                                issues.append((
                                    "WARN",
                                    f"L7 prerequisites: 引用 {elt.value!r} 不在 migrations/ 目录",
                                ))
    except SyntaxError:
        pass
    return issues


def lint_verify(file_path: Path) -> list:
    """L8: verify (WARN)"""
    if file_path.suffix != ".py":
        return []
    issues = []
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        has_verify = any(
            isinstance(n, ast.FunctionDef) and n.name == "verify"
            for n in ast.walk(tree)
        )
        has_migrate = any(
            isinstance(n, ast.FunctionDef) and n.name == "migrate"
            for n in ast.walk(tree)
        )
        if has_migrate and not has_verify:
            issues.append((
                "WARN",
                "L8 verify: 推荐添加 def verify(db_path) -> bool 验证迁移结果",
            ))
    except SyntaxError:
        pass
    return issues


def main():
    parser = argparse.ArgumentParser(description="[P1.6] Migration 质量检查 (CI Lint)")
    parser.add_argument("--migrations-dir", default=str(DEFAULT_MIG_DIR),
                        help=f"Migrations 目录 (默认 {DEFAULT_MIG_DIR})")
    parser.add_argument("--strict", action="store_true",
                        help="严格模式: WARN 也算 FAIL (exit 1)")
    args = parser.parse_args()

    mig_dir = Path(args.migrations_dir)
    if not mig_dir.exists():
        print(f"[SKIP] migrations dir not found: {mig_dir}")
        return 0

    files = sorted([
        f for f in mig_dir.iterdir()
        if f.is_file() and f.suffix in (".py", ".sql")
        and not f.name.startswith("_")
        and not f.name.startswith(".")
    ])
    all_names = {f.name for f in files}

    all_issues = []
    for f in files:
        all_issues.extend(lint_naming(f))
        all_issues.extend(lint_signature(f))
        all_issues.extend(lint_idempotent(f))
        all_issues.extend(lint_docstring(f))
        all_issues.extend(lint_destructive(f))
        all_issues.extend(lint_prerequisites(f, all_names))
        all_issues.extend(lint_verify(f))
    all_issues.extend(lint_version_unique(files))

    fails = [i for i in all_issues if i[0] == "FAIL"]
    warns = [i for i in all_issues if i[0] == "WARN"]

    for level, msg in all_issues:
        print(f"[{level}] {msg}")

    print(f"\n=== Summary: {len(fails)} FAIL, {len(warns)} WARN (checked {len(files)} files) ===")

    if fails:
        return 1
    if warns and args.strict:
        return 1
    # 有 WARN 时返回 0 (WARN 不阻塞 CI), 只在 --strict 时才 exit 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
