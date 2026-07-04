#!/usr/bin/env python3
"""
check_rules_consistency.py - 规范一致性检查

检测项目内 .trae/rules/, AGENT_GUIDELINES.md, AGENT_INDEX.md, PARALLEL_DEV_SOP.md 等
规范文档的 4 类一致性问题：

  1. 死链: 引用的 .md / .ps1 / .py 文件不存在
  2. 双版本: 跨目录同名文件 md5 不一致
  3. 过期引用: 引用的脚本不在 scripts/ 目录
  4. 关键 SOP 未索引: 新 SOP 没在 AGENT_INDEX.md

用法:
  python scripts/check_rules_consistency.py              # 全部检查
  python scripts/check_rules_consistency.py --deadlinks  # 仅死链
  python scripts/check_rules_consistency.py --duplicates # 仅双版本
  python scripts/check_rules_consistency.py --strict     # 严格模式 (CI 用)

退出码:
  0 - 全部通过
  1 - 发现问题 (默认 warning)
  2 - 严格模式失败
"""

import argparse
import hashlib
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

# 项目根目录 (脚本在 scripts/ 下)
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
RULES_DIR = PROJECT_ROOT / ".trae" / "rules"

# 扫描范围: 仅规范文件
SCAN_ROOTS = [
    PROJECT_ROOT / ".trae" / "rules",
    PROJECT_ROOT / ".trae" / "templates",
    PROJECT_ROOT / "AGENT_GUIDELINES.md",
    PROJECT_ROOT / "AGENT-GUIDE.md",
    PROJECT_ROOT / "AGENTS.md",
    PROJECT_ROOT / "PARALLEL_DEV_SOP.md",
    PROJECT_ROOT / "QUICK_START.md",
    PROJECT_ROOT / "START_HERE.md",
]

# 排除目录 (在 .trae/rules/ 内仍有这些)
EXCLUDE_DIRS = {
    "node_modules",
    ".git",
    "dist",
    "build",
    "coverage",
    "playwright-report",
    "test-results",
    "__pycache__",
    ".pytest_cache",
    ".vercel",
    "logs",
    "backups",
    "archive",
    "chats",
    "backlog",
    "specs",       # 任务规格，引用范围多
    "skills",      # Skill 定义
    "prompts",     # Prompt 模板
    "context",     # 角色上下文
    "agents",      # Agent 定义
    "roles",       # 角色配置
    "debug",       # 调试记录
    "memory",      # 项目记忆 (含历史引用)
    "decisions",   # 决策记录
    "state",       # 状态文件
    "commands",    # 命令定义
    "scripts",     # scripts/ 自包含
    "scripts_metadata",  # 脚本元数据
}

# 引用模式: 严格匹配 .md/.ps1/.py/.sh 文件引用
REF_PATTERNS = [
    re.compile(r"\[([^\]]+)\]\(([^)]+\.(?:md|ps1|py|sh|js|ts|vue))\)"),
    re.compile(r"`([a-zA-Z_./\\\\][a-zA-Z_0-9.\\\\/-]*\.(?:md|ps1|py|sh|js|ts|vue))`"),
]

# 跳过文件 (符合某个条件的引用视为合法)
SKIP_REF_SUBSTRINGS = [
    "http://", "https://", "mailto:",
    "node_modules",  # 依赖里的文件
    "playwright-report",  # 测试报告
    "test-results",
    ".pytest_cache",
    "v[0-9]+\\.[0-9]+\\.[0-9]+",  # 版本号
    "v\\d{8}_",  # 部署版本目录
    "{{", "}}",  # 模板变量
    "node:", "npm:", "git:",
]

# 排除文件扩展名 (内联示例常误匹配)
SKIP_REF_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",  # 图片
    ".json", ".yml", ".yaml", ".toml", ".ini",  # 配置
    ".log", ".txt", ".csv", ".xlsx", ".pdf",  # 数据/日志
    ".html", ".css", ".scss", ".less",
    ".zip", ".tar", ".gz", ".7z",
    ".out", ".err",
}

# 标记废弃的文件 (其内部死链不报错)
DEPRECATED_FILES = {
    "RULES_INDEX.md",  # 2026-07-04 deprecated, use AGENT_INDEX.md
    "e2e-testing.md",  # 2026-07-04 deprecated v1, use core/e2e-testing.md
}

# Windows 路径前缀 (file:// 形式, 主工作树根)
WINDOWS_FILE_URL = re.compile(r"^file:///([a-zA-Z]:[/\\].*)$")


def md5(path: Path) -> str:
    """计算文件 md5"""
    if not path.is_file():
        return ""
    h = hashlib.md5()
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except (OSError, PermissionError):
        return ""
    return h.hexdigest()


def scan_files(root: Path = PROJECT_ROOT) -> List[Path]:
    """
    扫描规范文件 (仅 SCAN_ROOTS 范围)
    """
    files: List[Path] = []
    seen: Set[Path] = set()

    for scan_root in SCAN_ROOTS:
        if not scan_root.exists():
            continue
        if scan_root.is_file():
            if scan_root not in seen and scan_root.suffix.lower() in {".md", ".ps1", ".py", ".sh", ".js", ".ts", ".vue"}:
                files.append(scan_root)
                seen.add(scan_root)
            continue
        # 目录: 递归
        for path in scan_root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".md", ".ps1", ".py", ".sh", ".js", ".ts", ".vue"}:
                continue
            # 检查排除目录
            try:
                rel = path.relative_to(PROJECT_ROOT)
            except ValueError:
                continue
            if any(part in EXCLUDE_DIRS for part in rel.parts):
                continue
            if path not in seen:
                files.append(path)
                seen.add(path)
    return files


def strip_code_blocks(content: str) -> str:
    """
    移除代码块 (```...```) 和行内代码中的引用
    因为代码示例里的字符串不是真引用
    """
    # 移除多行代码块
    content = re.sub(r"```[^\n]*\n.*?```", "", content, flags=re.DOTALL)
    # 移除行内代码 `...` 中的内容 (替换为空格保留位置)
    content = re.sub(r"`[^`\n]+`", " ", content)
    return content


def extract_refs(path: Path) -> List[str]:
    """
    提取文件中的文件引用 (排除代码块)
    """
    if not path.is_file():
        return []
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, UnicodeDecodeError):
        return []

    # 去除代码块
    content = strip_code_blocks(raw)

    refs: List[str] = []
    for pattern in REF_PATTERNS:
        for match in pattern.finditer(content):
            # 第二个 group 是 (url) 或 第一个是 (file)
            url = match.group(2) if pattern.groups == 2 else match.group(1)
            if not url:
                continue
            # 跳过 URL 和锚点
            if url.startswith(("http://", "https://", "#", "mailto:")):
                continue
            # 跳过模板变量
            if "{{" in url or "<" in url or ">" in url:
                continue
            # 跳过包含跳过子串的
            if any(skip in url for skip in SKIP_REF_SUBSTRINGS):
                continue
            # 跳过内联示例扩展名
            if any(url.lower().endswith(ext) for ext in SKIP_REF_EXTENSIONS):
                continue
            # 跳过 template variable in URL
            if "${" in url:
                continue
            # 去掉锚点
            url = url.split("#")[0]
            if url and len(url) > 3:  # 跳过太短的无意义引用
                refs.append(url)
    return refs


def resolve_ref(ref: str, source: Path) -> Path:
    """解析引用为绝对路径"""
    # 处理 file:///c:/... 形式
    m = WINDOWS_FILE_URL.match(ref)
    if m:
        win_path = m.group(1).replace("/", "\\")
        p = Path(win_path)
        # 如果在主工作树根 (d:/filework/excel-to-diagram/), 映射到当前 PROJECT_ROOT
        main_root = Path("d:/filework/excel-to-diagram").resolve()
        try:
            rel = p.relative_to(main_root)
            candidate = PROJECT_ROOT / rel
            if candidate.exists():
                return candidate
        except ValueError:
            pass
        return p
    if ref.startswith(("/", "\\")):
        return PROJECT_ROOT / ref.lstrip("/\\")
    if ref.startswith("~"):
        return Path(ref).expanduser()
    return (source.parent / ref).resolve()


def check_deadlinks(files: List[Path] = None) -> List[Tuple[Path, str, str]]:
    """
    检查死链 (跳过已废弃文件)
    返回: [(source_file, ref, resolved_path), ...]
    """
    if files is None:
        files = scan_files()
    dead: List[Tuple[Path, str, str]] = []
    for path in files:
        # 跳过废弃文件
        if path.name in DEPRECATED_FILES:
            continue
        for ref in extract_refs(path):
            resolved = resolve_ref(ref, path)
            if resolved.exists():
                continue
            dead.append((path, ref, str(resolved)))
    return dead


def check_duplicates() -> List[Tuple[str, List[Path], Set[str]]]:
    """
    检查双版本冲突 (跨 SCAN_ROOTS 范围)
    """
    name_index: Dict[str, List[Path]] = {}
    for path in scan_files():
        name_index.setdefault(path.name, []).append(path)

    duplicates = []
    for name, paths in name_index.items():
        if len(paths) <= 1:
            continue
        # 排除标记为 deprecated 的文件 (其内容差异是有意的历史保留)
        if name in DEPRECATED_FILES:
            continue
        # 排除 .trae/rules/active/ 和 archive/ 是有意版本控制
        rel_paths = [p.relative_to(PROJECT_ROOT) for p in paths]
        if any(".trae/rules/active" in str(p) or ".trae/rules/archive" in str(p) for p in rel_paths):
            continue
        # 排除 .deprecated/ 目录 (内含历史文件, 故意双版本)
        if any(".deprecated" in str(p) for p in rel_paths):
            continue
        # 排除单一目录
        if len({str(p.parent) for p in paths}) <= 1:
            continue
        md5s = {md5(p) for p in paths}
        if len(md5s) > 1:
            duplicates.append((name, paths, md5s))
    return duplicates


def check_key_sops_indexed() -> List[str]:
    """
    检查关键 SOP 是否在 AGENT_INDEX.md 索引
    """
    key_sops = [
        "PARALLEL_DEV_SOP.md",
        "DEPLOY_HANDOVER_BUG_V043.md",
        "DEPLOY_HANDOVER_BUG_V044.md",
    ]
    index_path = RULES_DIR / "AGENT_INDEX.md"
    if not index_path.is_file():
        return [f"AGENT_INDEX.md 不存在: {index_path}"]
    try:
        content = index_path.read_text(encoding="utf-8")
    except OSError:
        return [f"无法读取: {index_path}"]

    missing = []
    for sop in key_sops:
        if sop not in content:
            missing.append(sop)
    return missing


def check_stale_scripts() -> List[Tuple[Path, str]]:
    """
    检查过期脚本引用 (引用的脚本位于 archive/.deprecated/ 等历史目录)
    注意: 规范文档引用项目代码 (dev.py, meta/server.py) 是合法的, 不算 stale
    """
    stale: List[Tuple[Path, str]] = []
    for path in scan_files(RULES_DIR):
        if path.suffix != ".md":
            continue
        for ref in extract_refs(path):
            if not (ref.endswith(".ps1") or ref.endswith(".py")):
                continue
            if "scripts/" in ref or ref.startswith("scripts"):
                continue
            # 引用了 .ps1/.py 但不在 scripts/
            resolved = resolve_ref(ref, path)
            if not resolved.exists():
                # 已记入 deadlinks, 不重复
                continue
            # 文件存在但不在 scripts/ 下
            try:
                rel = resolved.relative_to(PROJECT_ROOT)
            except ValueError:
                continue
            # 排除项目代码 (meta/ 目录、根目录入口) - 这些是项目本身代码, 不是脚本工具
            if rel.parts[0] in {"meta", "dev.py", "server.py"}:
                continue
            if len(rel.parts) > 0 and rel.parts[0] == "test_helpers":
                continue
            # 只标记引用了 archive/.deprecated/ 下的脚本 (历史脚本, 应改用 scripts/ 下当前版本)
            if "archive" in rel.parts or ".deprecated" in rel.parts:
                stale.append((path, ref))
    return stale


def main() -> int:
    parser = argparse.ArgumentParser(
        description="检查项目规范一致性 (死链/双版本/过期引用/关键 SOP 索引)"
    )
    parser.add_argument("--deadlinks", action="store_true", help="仅检查死链")
    parser.add_argument("--duplicates", action="store_true", help="仅检查双版本")
    parser.add_argument("--indexed", action="store_true", help="仅检查关键 SOP 索引")
    parser.add_argument("--stale", action="store_true", help="仅检查过期脚本引用")
    parser.add_argument("--strict", action="store_true", help="严格模式 (发现任意问题即返回 2)")
    parser.add_argument("--quiet", action="store_true", help="仅显示错误，不显示 OK")
    args = parser.parse_args()

    run_all = not (args.deadlinks or args.duplicates or args.indexed or args.stale)

    has_error = False

    # 1. 死链检查
    if run_all or args.deadlinks:
        print("[1] 死链检查...")
        dead = check_deadlinks()
        if dead:
            has_error = True
            print(f"  [FAIL] {len(dead)} 个死链:")
            for src, ref, resolved in dead[:30]:
                print(f"    - {src.relative_to(PROJECT_ROOT)}")
                print(f"        ref: {ref}")
                print(f"        ->  {resolved}")
            if len(dead) > 30:
                print(f"    ... 还有 {len(dead) - 30} 个")
        else:
            if not args.quiet:
                print("  [OK] 0 个死链")

    # 2. 双版本检查
    if run_all or args.duplicates:
        print("\n[2] 双版本检查...")
        dupes = check_duplicates()
        if dupes:
            has_error = True
            print(f"  [FAIL] {len(dupes)} 组双版本冲突:")
            for name, paths, md5s in dupes:
                print(f"    - {name} ({len(paths)} 份, {len(md5s)} 个不同内容)")
                for p in paths:
                    print(f"        {p.relative_to(PROJECT_ROOT)} (md5={md5(p)[:8]})")
        else:
            if not args.quiet:
                print("  [OK] 0 个双版本冲突")

    # 3. 关键 SOP 索引
    if run_all or args.indexed:
        print("\n[3] 关键 SOP 索引...")
        missing = check_key_sops_indexed()
        if missing:
            has_error = True
            print(f"  [FAIL] {len(missing)} 个关键 SOP 未在 AGENT_INDEX.md 索引:")
            for sop in missing:
                print(f"    - {sop}")
        else:
            if not args.quiet:
                print("  [OK] 关键 SOP 已索引")

    # 4. 过期脚本引用
    if run_all or args.stale:
        print("\n[4] 过期脚本引用...")
        stale = check_stale_scripts()
        if stale:
            # 仅 warning, 不算 error
            print(f"  [WARN] {len(stale)} 个非 scripts/ 下的脚本引用:")
            for src, ref in stale[:20]:
                print(f"    - {src.relative_to(PROJECT_ROOT)} -> {ref}")
        else:
            if not args.quiet:
                print("  [OK] 0 个过期引用")

    print()
    if has_error:
        print("=" * 50)
        print("[FAIL] 一致性检查发现问题")
        print()
        print("建议:")
        print("  1. 修复死链: 更新引用路径或创建文件")
        print("  2. 解决双版本: 选一份为权威，删除/redirect 另一份")
        print("  3. AGENT_INDEX.md 加入缺失的 SOP")
        print()
        if args.strict:
            return 2
        return 1
    else:
        print("=" * 50)
        print("[OK] 全部检查通过")
        return 0


if __name__ == "__main__":
    sys.exit(main())
