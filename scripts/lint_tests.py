"""测试用例资产 lint（TEST-EFF P0-2）

规范只写在文档里没人遵守，写进可执行检查才会。本脚本只读扫描
`meta/tests/`，把 P2-1 / P2-2 / P1-7 / P1-8 等优化中反复人工发现的问题
固化成检查项，每条 finding 都带「为什么」和「怎么改」。

默认检查（高信号，误报低）：
- syntax-error        文件无法被 AST 解析（该文件在 pytest 收集期会被跳过）
- duplicate-file      两个文件归一化后内容一致（v3.6 的整文件副本）
- duplicate-test-def  同名 test 函数出现在 >=2 个文件（P2-2）
- inline-sql          测试内直接用 execute("INSERT/UPDATE/...")，未走
                      factories/_raw_sql_bridge，会绕过 raw-SQL 守卫（P1-8）
- sleep               非注释的 time.sleep 忙等（P1-7，应改用轮询 helper）

`--strict` 追加（噪音较大，默认关闭）：
- missing-marker      缺 pytestmark
- no-assert           test_* 内既无 assert 也无断言 helper 调用
- direct-create-app   自行 create_app() 而非共享 app 工厂
- hardcoded-version-id 硬编码 version_id = 1

用法：
    python scripts/lint_tests.py
    python scripts/lint_tests.py --strict --json test_temp/lint.json
    python scripts/lint_tests.py --fail-on high     # 供 CI / 提交前门禁

退出码：0 正常；1 存在 >= --fail-on 级别的问题；2 参数/路径错误。
"""

import argparse
import ast
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SQL_RE = re.compile(
    r"\b(?:INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|"
    r"CREATE\s+(?:TABLE|INDEX|VIEW)|ALTER\s+TABLE|DROP\s+(?:TABLE|INDEX|VIEW))\b",
    re.IGNORECASE,
)
SQL_METHODS = {
    "execute", "executescript", "executemany", "execute_many",
    "query", "execute_query", "raw",
}
VERSION_ID_RE = re.compile(r"\bversion_id\s*=\s*1(?!\d)")

SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1, "info": 0}

CHECKS = {
    "syntax-error": ("high", "文件无法解析，pytest 收集期会整文件跳过"),
    "duplicate-file": ("high", "整文件与另一文件内容重复，覆盖等价"),
    "duplicate-test-def": ("medium", "同名 test 函数跨文件重复定义"),
    "inline-sql": ("high", "内联 DML 绕过 raw-SQL 守卫，DB 隔离会静默失效"),
    "sleep": ("medium", "sleep 忙等，慢机器上会假失败"),
    "missing-marker": ("low", "缺 pytestmark，无法按层筛选"),
    "no-assert": ("medium", "test_* 内没有任何断言"),
    "direct-create-app": ("low", "自行 create_app() 绕过共享工厂/预热"),
    "hardcoded-version-id": ("low", "硬编码 version_id = 1"),
}


def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _literal_text(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            part.value for part in node.values
            if isinstance(part, ast.Constant) and isinstance(part.value, str)
        )
    return None


def _call_has_sql(call):
    for arg in list(call.args) + [kw.value for kw in call.keywords]:
        text = _literal_text(arg)
        if text and SQL_RE.search(text):
            return True
    return False


def _has_assertion(func_node):
    for node in ast.walk(func_node):
        if isinstance(node, ast.Assert):
            return True
        if isinstance(node, ast.Call):
            name = _dotted(node.func)
            last = name.rsplit(".", 1)[-1]
            if last.startswith("assert") or last in ("fail", "expect"):
                return True
        if isinstance(node, ast.Attribute) and node.attr.startswith("assert"):
            return True
    return False


def _normalized_hash(text):
    body = "\n".join(
        line.rstrip() for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class Finding:
    __slots__ = ("path", "line", "code", "message")

    def __init__(self, path, line, code, message):
        self.path = path
        self.line = line
        self.code = code
        self.message = message

    def to_dict(self):
        severity, _ = CHECKS.get(self.code, ("low", ""))
        return {
            "path": self.path, "line": self.line, "code": self.code,
            "severity": severity, "message": self.message,
        }


def collect_files(root, include_conftest=False):
    files = []
    for path in sorted(root.rglob("test_*.py")):
        if "__pycache__" in path.parts or "shared" in path.parts:
            continue
        files.append(path)
    if include_conftest:
        for path in sorted(root.rglob("conftest.py")):
            if "__pycache__" not in path.parts:
                files.append(path)
    return files


def scan(files, strict=False):
    findings = []
    test_defs = defaultdict(list)
    content_hash = defaultdict(list)
    total_test_defs = 0

    for path in files:
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            findings.append(Finding(rel, 0, "syntax-error", f"读取失败: {exc}"))
            continue

        content_hash[_normalized_hash(text)].append(rel)
        allow_raw_sql = "ALLOW_RAW_SQL" in text
        has_shared_app = "get_shared_app" in text or "shared" in text
        has_marker = False

        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            findings.append(Finding(
                rel, exc.lineno or 0, "syntax-error",
                f"{exc.msg}（该文件在收集期会被整文件跳过）"))
            continue

        if any(
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "pytestmark"
                    for t in node.targets)
            for node in tree.body
        ):
            has_marker = True

        all_test_defs = [
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test")
        ]
        total_test_defs += len(all_test_defs)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and node.name.startswith("test"):
                test_defs[node.name].append((rel, node.lineno))
        if strict:
            for node in all_test_defs:
                if not _has_assertion(node):
                    findings.append(Finding(
                        rel, node.lineno, "no-assert",
                        f"{node.name} 内没有 assert / 断言 helper"))

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _dotted(node.func)
            if not name:
                continue
            last = name.rsplit(".", 1)[-1]

            if last in SQL_METHODS and _call_has_sql(node) \
                    and not allow_raw_sql:
                snippet = ""
                for arg in list(node.args) + [kw.value for kw in node.keywords]:
                    text_arg = _literal_text(arg)
                    if text_arg and SQL_RE.search(text_arg):
                        snippet = " ".join(text_arg.split())[:60]
                        break
                findings.append(Finding(
                    rel, node.lineno, "inline-sql",
                    f"{name}() 内联 SQL「{snippet}」；改用 factories/"
                    "_raw_sql_bridge，或文件头加 ALLOW_RAW_SQL + 理由"))

            if last == "sleep":
                findings.append(Finding(
                    rel, node.lineno, "sleep",
                    "用轮询 helper 替代固定 sleep（慢机器假失败）"))

            if strict and last == "create_app" and not has_shared_app:
                findings.append(Finding(
                    rel, node.lineno, "direct-create-app",
                    "改用共享 app 工厂；自建 app 会绕过守卫预热"))

        if strict and not has_marker and path.name != "conftest.py":
            findings.append(Finding(
                rel, 0, "missing-marker", "模块级无 pytestmark"))
        if strict:
            for lineno, line in enumerate(text.splitlines(), 1):
                if VERSION_ID_RE.search(line):
                    findings.append(Finding(
                        rel, lineno, "hardcoded-version-id",
                        "不要硬编码 version_id=1，用工厂/真实版本号"))

    for digest, paths in content_hash.items():
        if len(paths) >= 2:
            for rel in paths:
                others = [p for p in paths if p != rel]
                findings.append(Finding(
                    rel, 0, "duplicate-file",
                    f"与 {', '.join(others[:2])} 内容一致（净行哈希相同）"))

    for name, locations in test_defs.items():
        files_with_name = {loc[0] for loc in locations}
        if len(files_with_name) >= 2:
            for rel, lineno in locations:
                others = sorted(f for f in files_with_name if f != rel)
                findings.append(Finding(
                    rel, lineno, "duplicate-test-def",
                    f"{name} 也定义在 {', '.join(others[:2])}"))
    return findings, len(files), total_test_defs


def report(findings, file_count, test_count, max_detail, as_json):
    findings = sorted(
        findings,
        key=lambda f: (-SEVERITY_RANK.get(CHECKS.get(f.code, ("low",))[0], 0),
                       f.code, f.path, f.line),
    )
    payload = {
        "summary": {
            "files": file_count, "test_defs": test_count,
            "total": len(findings),
            "by_code": {
                code: sum(1 for f in findings if f.code == code)
                for code in sorted({f.code for f in findings})
            },
        },
        "findings": [f.to_dict() for f in findings],
    }
    if as_json:
        as_json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON 已写入 {as_json}")

    print(f"== 测试用例资产 lint == 扫描 {file_count} 文件 / "
          f"{test_count} 个 test_* 函数（含类方法）")
    grouped = defaultdict(list)
    for finding in findings:
        grouped[finding.code].append(finding)
    if not grouped:
        print("未发现问题")
    for code in sorted(grouped, key=lambda c: (-SEVERITY_RANK.get(
            CHECKS.get(c, ("low",))[0], 0), c)):
        severity, why = CHECKS.get(code, ("low", ""))
        items = grouped[code]
        print(f"\n[{severity}] {code}  {len(items)} 处 —— {why}")
        for finding in items[:max_detail]:
            loc = f"{finding.path}:{finding.line}" if finding.line else finding.path
            print(f"  {loc}  {finding.message}")
        if len(items) > max_detail:
            print(f"  ... 其余 {len(items) - max_detail} 处见 --json")

    counts = defaultdict(int)
    for finding in findings:
        counts[CHECKS.get(finding.code, ("low",))[0]] += 1
    print("\n汇总: " + " ".join(
        f"{level}={counts.get(level, 0)}" for level in ("high", "medium", "low")))
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description="测试用例资产 lint（只读）")
    parser.add_argument("--root", default=None, help="扫描根目录，默认 meta/tests")
    parser.add_argument("--strict", action="store_true",
                        help="追加 marker/断言/自建 app 等噪音较大的检查")
    parser.add_argument("--include-conftest", action="store_true")
    parser.add_argument("--max-detail", type=int, default=10)
    parser.add_argument("--json", default=None, help="完整结果写入 JSON 文件")
    parser.add_argument("--fail-on", default="none",
                        choices=["none", "low", "medium", "high"],
                        help="存在该级别及以上问题时退出码 1")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else REPO_ROOT / "meta" / "tests"
    if not root.exists():
        print(f"扫描根目录不存在: {root}", file=sys.stderr)
        return 2

    files = collect_files(root, args.include_conftest)
    findings, file_count, test_count = scan(files, strict=args.strict)
    json_path = Path(args.json) if args.json else None
    report(findings, file_count, test_count, args.max_detail, json_path)

    if args.fail_on != "none":
        threshold = SEVERITY_RANK[args.fail_on]
        blocking = [
            f for f in findings
            if SEVERITY_RANK.get(CHECKS.get(f.code, ("low",))[0], 0) >= threshold
        ]
        if blocking:
            print(f"\n门禁失败: {len(blocking)} 处 >= {args.fail_on}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())