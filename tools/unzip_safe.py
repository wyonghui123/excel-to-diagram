"""Magic number 检测 + multipart 自动剥离 [V007.50 2026-07-14]
[L8.6 unzip_safe]

用法:
  python unzip_safe.py <file_or_dir> [--recursive] [--check] [--json]

选项:
  --check      只检测不修改
  --recursive  递归处理目录
  --json       JSON 输出
"""
import re
import sys
import json
import argparse
from pathlib import Path


# Magic number 字典: 顺序敏感, 先匹配先生效
MAGIC_PATTERNS = [
    ("zip", re.compile(rb"^PK\x03\x04")),
    ("gzip", re.compile(rb"^\x1f\x8b\x08")),
    ("python", re.compile(rb'^(?:"""|import |from )')),
    ("shell", re.compile(rb"^#!.*(?:/bin/bash|/bin/sh|/usr/bin/env)")),
    ("javascript", re.compile(rb"^(?:import |const |function |var |let )")),
    ("markdown", re.compile(rb"^# ")),
    ("json", re.compile(rb'^\{')),
    ("yaml", re.compile(rb"^[a-zA-Z_]+:")),
]


def detect_magic(data: bytes) -> str:
    """检测文件 magic number, 返回类型名 (未知时返回 "unknown")"""
    head = data[:100]
    for name, pattern in MAGIC_PATTERNS:
        if pattern.match(head):
            return name
    return "unknown"


def auto_strip_multipart(data: bytes) -> bytes:
    """如果文件被 multipart 头污染, 自动剥离

    Returns:
        最长的 part body, 或原始 data (无 multipart 边界时)
    """
    # 找 multipart boundary (开头处, 可能字符串开头就是)
    m = re.search(rb'^--([A-Za-z0-9_-]{8,})', data[:500])
    if not m:
        return data

    boundary = b"--" + m.group(1)
    parts = data.split(boundary)
    candidates = []
    for part in parts:
        # 跳过前导的 \r\n (boundary 之后的换行)
        part = part.lstrip(b"\r\n")
        # 找 headers/body 分隔的 \r\n\r\n
        header_end = part.find(b"\r\n\r\n")
        if header_end == -1:
            continue
        body = part[header_end + 4:].rstrip(b"\r\n")
        if len(body) > 10:
            candidates.append(body)
    if not candidates:
        return data
    return max(candidates, key=len)


def check_file(p: Path) -> dict:
    """检测单个文件: 返回 dict 含 original/cleaned type + is_polluted"""
    if not p.exists():
        return {"file": str(p), "error": "not found"}
    try:
        data = p.read_bytes()
    except Exception as e:
        return {"file": str(p), "error": str(e)}
    original_type = detect_magic(data[:100])
    cleaned = auto_strip_multipart(data)
    cleaned_type = detect_magic(cleaned[:100])
    is_polluted = (original_type == "unknown" and cleaned_type != "unknown")
    return {
        "file": str(p),
        "size": len(data),
        "original_type": original_type,
        "cleaned_type": cleaned_type,
        "is_polluted": is_polluted,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="File or directory to check")
    parser.add_argument("--recursive", "-r", action="store_true")
    parser.add_argument("--check", action="store_true", help="Don't modify, just check")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    p = Path(args.path)
    if p.is_file():
        files = [p]
    elif p.is_dir() and args.recursive:
        files = [f for f in p.rglob("*") if f.is_file()]
    else:
        print(f"ERROR: {p} not a file (use --recursive for directory)", file=sys.stderr)
        sys.exit(2)

    results = []
    for f in files:
        r = check_file(f)
        if r.get("is_polluted") and not args.check:
            cleaned = auto_strip_multipart(f.read_bytes())
            f.write_bytes(cleaned)
            r["action"] = "cleaned"
        results.append(r)

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        polluted = [r for r in results if r.get("is_polluted")]
        if polluted:
            print(f"\n[!] Found {len(polluted)} polluted file(s):")
            for r in polluted:
                print(f"    {r['file']}: {r['original_type']} -> {r['cleaned_type']}")
        else:
            print(f"\n[OK] {len(results)} file(s) clean")

    sys.exit(0 if not polluted else 1)


if __name__ == "__main__":
    main()