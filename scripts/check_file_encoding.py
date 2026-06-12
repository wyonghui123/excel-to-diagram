#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_file_encoding.py - File encoding health check (v1.0)

Detects the GBK-mojibake pattern observed in 2026-06-12 httpClient.js incident:
  - Invalid UTF-8 sequences
  - 0x3F (ASCII '?') immediately following 0x80+ high bytes
    (signature of lossy GBK re-encoding: full-width "?" efbc9f -> ascii ? 3f)
  - Suspicious GBK-mojibake characters in text content
  - File-size bloat beyond a sane threshold vs HEAD

Usage:
    python scripts/check_file_encoding.py                  # check working tree
    python scripts/check_file_encoding.py --staged        # check staged only
    python scripts/check_file_encoding.py <path>...       # check specific files
    python scripts/check_file_encoding.py --json          # JSON output for CI

Exit codes:
    0  - all files OK
    1  - at least one file has encoding issues
    2  - tool internal error

Author: AI Agent (preventive tool, post-incident 2026-06-12)
Reference: .trae/rules/file-encoding-rules.md
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# GBK-mojibake signature characters (from observed 缁熶竴 etc.)
# These are what you get when you interpret UTF-8 bytes as GBK.
MOJIBAKE_SIGNATURE_CHARS = set(
    "缁熶竴鐎广垺鍩涚粩瀹㈡埛绔璇锋眰瓒呮椂缃戠粶閿欒"
    "鐮鏋氫妇鎷︽埅鍣鍥炶皟璁剧疆鏈杁br>"
    "鍛藉悕绌洪棿瀵煎嚮娉ㄥ唽澶勭悊"
)

# File types we check
CHECK_EXTENSIONS = {
    ".js", ".jsx", ".ts", ".tsx", ".vue", ".py",
    ".md", ".json", ".yml", ".yaml", ".css", ".scss",
    ".html", ".sql", ".sh", ".ps1",
}

# Skip these paths
SKIP_PATH_PATTERNS = (
    "node_modules/",
    ".git/",
    "dist/",
    "build/",
    ".vite/",
    "uploads/",
    "playwright-report/",
    "test-results/",
    "test_telemetry/",
    "test_debug.py",  # temp debug files
    "check_parse.py",  # temp debug files
)

# Maximum file size ratio vs HEAD (current/head) to flag
MAX_SIZE_RATIO_VS_HEAD = 2.0


def should_check(path: str) -> bool:
    """Decide whether a file should be encoding-checked."""
    p = path.replace("\\", "/")
    for pat in SKIP_PATH_PATTERNS:
        if pat in p:
            return False
    return Path(p).suffix.lower() in CHECK_EXTENSIONS


def is_high_byte(b: int) -> bool:
    return b >= 0x80


def detect_3f_replacement(raw: bytes) -> int:
    """Count occurrences of 0x3F immediately following a high byte.

    This is the signature of:
      - Editor reading UTF-8 as GBK
      - Encountering 3-byte UTF-8 sequence
      - Cannot map to GBK
      - Substitutes with ASCII '?' (0x3F)
    """
    count = 0
    for i in range(1, len(raw)):
        if raw[i] == 0x3F and is_high_byte(raw[i - 1]):
            count += 1
    return count


def detect_invalid_utf8(raw: bytes) -> list:
    """Return list of (offset, hex) for invalid UTF-8 sequences."""
    invalid = []
    i = 0
    while i < len(raw):
        b = raw[i]
        if b < 0x80:
            i += 1
            continue
        if 0xC0 <= b <= 0xDF:
            if i + 1 < len(raw) and 0x80 <= raw[i + 1] <= 0xBF:
                i += 2
            else:
                invalid.append((i, raw[i:i + 2].hex()))
                i += 1
        elif 0xE0 <= b <= 0xEF:
            if i + 2 < len(raw) and 0x80 <= raw[i + 1] <= 0xBF and 0x80 <= raw[i + 2] <= 0xBF:
                i += 3
            else:
                invalid.append((i, raw[i:i + 3].hex()))
                i += 1
        elif 0xF0 <= b <= 0xF7:
            if i + 3 < len(raw) and 0x80 <= raw[i + 1] <= 0xBF and 0x80 <= raw[i + 2] <= 0xBF and 0x80 <= raw[i + 3] <= 0xBF:
                i += 4
            else:
                invalid.append((i, raw[i:i + 4].hex()))
                i += 1
        else:
            invalid.append((i, raw[i:i + 1].hex()))
            i += 1
    return invalid


def detect_mojibake_chars(text: str) -> int:
    """Count occurrences of known GBK-mojibake signature characters."""
    return sum(1 for c in text if c in MOJIBAKE_SIGNATURE_CHARS)


def get_head_size(path: str) -> int:
    """Get the file size at HEAD. Returns -1 if file is new or git error."""
    try:
        result = subprocess.run(
            ["git", "show", f"HEAD:{path}"],
            capture_output=True,
            cwd=".",
        )
        if result.returncode == 0:
            return len(result.stdout)
    except Exception:
        pass
    return -1


def check_file(path: str) -> dict:
    """Run all encoding checks on a single file. Returns a report dict."""
    report = {
        "file": path,
        "size_bytes": 0,
        "head_size_bytes": -1,
        "issues": [],
    }
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except (OSError, IOError) as e:
        report["issues"].append(f"READ_ERROR: {e}")
        return report

    report["size_bytes"] = len(raw)

    # Check 1: invalid UTF-8
    invalid = detect_invalid_utf8(raw)
    if invalid:
        report["issues"].append(
            f"INVALID_UTF8: {len(invalid)} bad sequences (first: pos={invalid[0][0]} hex={invalid[0][1]})"
        )

    # Check 2: 0x3F after high byte (the GBK-mojibake fingerprint)
    qmark_count = detect_3f_replacement(raw)
    if qmark_count > 0:
        report["issues"].append(
            f"GBK_MOJIBAKE_FINGERPRINT: {qmark_count} occurrences of 0x3F after high byte "
            f"(typical of full-width '?' efbc9f -> ascii '?' 3f replacement)"
        )

    # Check 3: known mojibake signature characters (only if UTF-8 decodes cleanly)
    if not invalid:
        try:
            text = raw.decode("utf-8")
            moji_count = detect_mojibake_chars(text)
            if moji_count > 0:
                report["issues"].append(
                    f"MOJIBAKE_CHARS: {moji_count} known GBK-mojibake signature chars found"
                )
        except UnicodeDecodeError:
            pass  # already reported in check 1

    # Check 4: file size bloat vs HEAD
    head_size = get_head_size(path)
    report["head_size_bytes"] = head_size
    if head_size > 0:
        ratio = len(raw) / head_size
        if ratio > MAX_SIZE_RATIO_VS_HEAD:
            report["issues"].append(
                f"SIZE_BLOAT: current={len(raw)} head={head_size} ratio={ratio:.2f}x "
                f"(threshold={MAX_SIZE_RATIO_VS_HEAD}x; possible mixed encoding/duplication)"
            )

    return report


def get_target_files(args) -> list:
    """Resolve the list of files to check based on args."""
    if args.paths:
        return [p for p in args.paths if should_check(p)]

    if args.staged:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True,
            text=True,
        )
        return [p for p in result.stdout.split("\n") if p and should_check(p)]

    # default: working tree
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        capture_output=True,
        text=True,
    )
    diff_files = [p for p in result.stdout.split("\n") if p and should_check(p)]

    # also include untracked text files
    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
    )
    for p in result.stdout.split("\n"):
        if p and should_check(p) and os.path.exists(p):
            diff_files.append(p)

    return diff_files


def main():
    parser = argparse.ArgumentParser(
        description="Detect GBK-mojibake and other encoding corruption in text files."
    )
    parser.add_argument("paths", nargs="*", help="Specific files to check")
    parser.add_argument("--staged", action="store_true", help="Check only staged files")
    parser.add_argument("--json", action="store_true", help="JSON output for CI")
    parser.add_argument("--quiet", action="store_true", help="Only print files with issues")
    args = parser.parse_args()

    files = get_target_files(args)
    if not files:
        if not args.json:
            print("[OK] No files to check.")
        return 0

    reports = []
    for path in files:
        if not os.path.exists(path):
            continue
        reports.append(check_file(path))

    bad_reports = [r for r in reports if r["issues"]]

    if args.json:
        print(json.dumps(
            {"total": len(reports), "bad": len(bad_reports), "reports": reports},
            ensure_ascii=False, indent=2,
        ))
    else:
        if not args.quiet:
            print(f"[INFO] Checked {len(reports)} file(s).")
        for r in bad_reports:
            print(f"\n[BAD] {r['file']}  (size={r['size_bytes']}, head={r['head_size_bytes']})")
            for issue in r["issues"]:
                print(f"      - {issue}")

    return 1 if bad_reports else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(2)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(2)
