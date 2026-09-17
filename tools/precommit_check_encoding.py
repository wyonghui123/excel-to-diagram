#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
check_encoding.py - Pre-commit hook to verify file encoding health
[V007.70] Replaces missing d:/filework/check_encoding.py

Checks each staged file:
1. UTF-8 decodable (no GBK mojibake)
2. LF line endings (no CRLF)
3. For .py files: ast.parse() succeeds (no unterminated triple-quote etc.)

Usage (as pre-commit hook):
    python tools/check_encoding.py [FILES...]
    # exit 0 = pass, 1 = fail
"""
import sys
import ast
from pathlib import Path


def check_utf8(filepath: Path) -> tuple[bool, str]:
    """Check file is valid UTF-8 (not GBK mojibake)"""
    try:
        data = filepath.read_bytes()
    except Exception as e:
        return False, f"read error: {e}"
    try:
        data.decode('utf-8')
    except UnicodeDecodeError as e:
        return False, f"NOT UTF-8: byte {e.start}:{e.end} - {e.reason}"
    # Check for U+FFFD (replacement char, indicates mojibake)
    if b'\xef\xbf\xbd' in data:
        # Count occurrences
        count = data.count(b'\xef\xbf\xbd')
        return False, f"mojibake detected: {count} U+FFFD chars"
    return True, "ok"


def check_lf(filepath: Path) -> tuple[bool, str]:
    """Check file uses LF (not CRLF)"""
    data = filepath.read_bytes()
    if b'\r\n' in data:
        # Count CRLF vs LF
        crlf_count = data.count(b'\r\n')
        lf_count = data.count(b'\n')
        if crlf_count > 0 and crlf_count == lf_count:
            return False, f"CRLF line endings: {crlf_count} CRLF (expected LF)"
    return True, "ok"


def check_python_syntax(filepath: Path) -> tuple[bool, str]:
    """Check .py file is syntactically valid (catches unterminated triple-quote)"""
    if filepath.suffix != '.py':
        return True, "skip (not .py)"
    try:
        source = filepath.read_text(encoding='utf-8')
        ast.parse(source, filename=str(filepath))
    except SyntaxError as e:
        return False, f"SyntaxError: line {e.lineno} - {e.msg}"
    except UnicodeDecodeError as e:
        return False, f"NOT UTF-8: {e.reason}"
    return True, "ok"


def main():
    if len(sys.argv) < 2:
        print("Usage: check_encoding.py FILE [FILE ...]")
        print("Exits 0 if all pass, 1 if any fail.")
        return 1

    failed = []
    for arg in sys.argv[1:]:
        filepath = Path(arg)
        if not filepath.exists():
            print(f"  [SKIP] {filepath}: does not exist")
            continue
        ok_utf8, msg_utf8 = check_utf8(filepath)
        ok_lf, msg_lf = check_lf(filepath)
        ok_py, msg_py = check_python_syntax(filepath)
        overall = ok_utf8 and ok_lf and ok_py
        status = "OK" if overall else "FAIL"
        print(f"  [{status}] {filepath}")
        if not ok_utf8:
            print(f"    - utf8: {msg_utf8}")
        if not ok_lf:
            print(f"    - lf: {msg_lf}")
        if not ok_py:
            print(f"    - py: {msg_py}")
        if not overall:
            failed.append(str(filepath))

    if failed:
        print(f"\n[FAIL] {len(failed)} file(s) failed encoding check:")
        for f in failed:
            print(f"  - {f}")
        return 1
    print(f"\n[OK] All {len(sys.argv)-1} file(s) passed encoding check")
    return 0


if __name__ == '__main__':
    sys.exit(main())
