# -*- coding: utf-8 -*-
"""frontend 测试 helper"""
from pathlib import Path


def read_vue_source(rel_path: str) -> str:
    fpath = Path(rel_path)
    if not fpath.exists():
        return ""
    return fpath.read_text(encoding='utf-8')
