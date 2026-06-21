"""
Shared helpers for adding --safe-output / --safe-output-dir arguments to debug scripts.

Usage:
    from scripts.debug.utils.safe_io import add_safe_output_args, emit_safe_output

    parser = argparse.ArgumentParser(...)
    add_safe_output_args(parser)

    args = parser.parse_args()
    # ... compute results ...

    if args.safe_output:
        emit_safe_output(results, prefix="my_query", output_dir=args.safe_output_dir)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Try to import sandbox_safe, otherwise use built-in fallback
try:
    from scripts.debug.utils.sandbox_safe import output as _ss_output
    _SANDBOX_SAFE_AVAILABLE = True
except ImportError:
    _ss_output = None
    _SANDBOX_SAFE_AVAILABLE = False


def add_safe_output_args(parser) -> None:
    """Add --safe-output and --safe-output-dir to an ArgumentParser.

    Args:
        parser: argparse.ArgumentParser instance
    """
    parser.add_argument(
        "--safe-output",
        action="store_true",
        help="V3.5: 写入 .trae/debug/queries/ 文件（sandbox-safe，绕过 stdout 拦截）",
    )
    parser.add_argument(
        "--safe-output-dir",
        metavar="DIR",
        help="V3.5: 自定义 sandbox-safe 输出目录",
    )


def emit_safe_output(
    data: Any,
    prefix: str,
    output_dir: Optional[str] = None,
    *,
    also_stdout: bool = True,
) -> Optional[Path]:
    """Emit data to a sandbox-safe file and optionally print the path to stdout.

    Args:
        data: Any JSON-serializable data
        prefix: Filename prefix (e.g., "user_context", "diagnose")
        output_dir: Custom output directory, or None for default .trae/debug/queries/
        also_stdout: If True, also print short path to stdout

    Returns:
        Path to the written file, or None on failure
    """
    if output_dir:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        out_file = out_dir / f"{prefix}_{ts}.json"
        try:
            out_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            if also_stdout:
                print(f"[SAFE_OUTPUT] {out_file}")
            return out_file
        except Exception as e:
            if also_stdout:
                print(f"[SAFE_OUTPUT_ERROR] {e}", file=sys.stderr)
            return None

    if _SANDBOX_SAFE_AVAILABLE and _ss_output is not None:
        out_file = _ss_output(data, prefix=prefix, also_stdout=also_stdout)
        if also_stdout and out_file:
            print(f"[SAFE_OUTPUT] {out_file}")
        return out_file

    # Fallback: write to .trae/debug/queries/ directly
    project_root = Path.cwd()
    for p in [project_root, *project_root.parents]:
        if (p / ".trae").is_dir() or (p / ".git").exists():
            project_root = p
            break
    queries_dir = project_root / ".trae" / "debug" / "queries"
    queries_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    out_file = queries_dir / f"{prefix}_{ts}.json"
    try:
        out_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        if also_stdout:
            print(f"[SAFE_OUTPUT] {out_file}")
        return out_file
    except Exception as e:
        if also_stdout:
            print(f"[SAFE_OUTPUT_ERROR] {e}", file=sys.stderr)
        return None


__all__ = ["add_safe_output_args", "emit_safe_output"]
