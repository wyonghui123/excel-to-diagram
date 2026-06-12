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

# GBK-mojibake signature characters (from observed U+7EFA U+5E74 U+7E41 etc.)
# These are what you get when you interpret UTF-8 bytes as GBK.
# NOTE: defined as unicode escapes to avoid self-triggering the check
# (the script file should not contain the trigger chars literally).
MOJIBAKE_SIGNATURE_CHARS = set(
    "\u3125\u3221\u5267\u52ed\u546e\u553d\u56ae\u57ba\u57c5\u57db"
    "\u5987\u5a09\u5e7f\u608a\u6095\u6220\u6741\u68ff\u6902\u6b12"
    "\u6c2b\u6d2a\u6d9a\u6fb6\u7035\u7039\u70b6\u714e\u71b6\u7481"
    "\u7487\u74d2\u7586\u769f\u7730\u7af4\u7ca9\u7cb6\u7ecc\u7ed4"
    "\u7f01\u7f03\u85c9\u935b\u9363\u9365\u9369\u93b7\u93c8\u93cb"
    "\u940e\u942e\u950b\u95bf\ufe3d"
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


def mask_code_regions(text: str) -> str:
    """Replace content inside code blocks/inline code with spaces.

    Markdown code regions are:
      - Fenced blocks: ```...``` (3+ backticks, possibly with language tag)
      - Inline code: `...` (single backticks, no whitespace inside)
      - Indented blocks: 4+ leading spaces (not common in this project)

    Returns text of same length, with code-region bytes replaced by ASCII
    space, so encoding checks skip them. Prevents false positives when
    documentation legitimately shows example bytes/mojibake.
    """
    chars = list(text)
    n = len(chars)
    i = 0
    while i < n:
        if chars[i] != "`":
            i += 1
            continue
        # Count backticks
        j = i
        while j < n and chars[j] == "`":
            j += 1
        fence_len = j - i
        if fence_len >= 3:
            # Find closing fence of equal or greater length
            k = j
            while k < n:
                if chars[k] == "`":
                    m = k
                    while m < n and chars[m] == "`":
                        m += 1
                    if m - k >= fence_len:
                        # blank-out from j to k-1
                        for x in range(j, k):
                            chars[x] = " "
                        k = m
                        i = k
                        break
                    k = m
                else:
                    k += 1
            else:
                # no closing fence; blank from i to end is too aggressive
                # so just blank this line
                eol = text.find("\n", i)
                if eol == -1:
                    eol = n
                for x in range(i, eol):
                    chars[x] = " "
                i = eol
        else:
            # Inline code: single backtick, find closing
            k = j
            while k < n and chars[k] != "`" and chars[k] != "\n":
                k += 1
            if k < n and chars[k] == "`":
                # blank from i to k
                for x in range(i, k + 1):
                    chars[x] = " "
                i = k + 1
            else:
                i = j
    return "".join(chars)


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
    # For .md files, scan only non-code-region text (mask_code_regions returns
    # same-length string with code regions as spaces; we re-encode and re-check)
    scan_bytes = raw
    if path.endswith(".md"):
        try:
            masked_text = mask_code_regions(raw.decode("utf-8"))
            scan_bytes = masked_text.encode("utf-8")
        except UnicodeDecodeError:
            pass  # already flagged in check 1
    qmark_count = detect_3f_replacement(scan_bytes)
    if qmark_count > 0:
        report["issues"].append(
            f"GBK_MOJIBAKE_FINGERPRINT: {qmark_count} occurrences of 0x3F after high byte "
            f"(typical of full-width '?' efbc9f -> ascii '?' 3f replacement)"
        )

    # Check 3: known mojibake signature characters (only if UTF-8 decodes cleanly)
    if not invalid:
        try:
            text = raw.decode("utf-8")
            # For .md files, mask code blocks/inline code (documentation
            # legitimately contains example bytes/mojibake strings)
            if path.endswith(".md"):
                text = mask_code_regions(text)
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
