# -*- coding: utf-8 -*-
"""
[V007.42 FR-011] SQLite 版本基线检查

背景:
  - yonaa 当前 Python 3.14.3 + SQLite 3.50.4, 低于 3.51.3
  - SQLite 3.51.3 (2026-03-13) 修复了 WAL-reset race
  - mmap 会把 WAL race 放大为 corruption (Django 案例)
  - FR-008 已禁用 mmap, 但仍应记录版本基线

策略:
  - 应用启动时检测 sqlite3.sqlite_version
  - < 3.51.3 时记 WARNING 日志
  - 设 metric sqlite_version_compliant (0/1)
  - 不阻断启动 (环境升级可能不在控制范围内)
  - SQLITE_REQUIRE_MIN_VERSION 可强制 raise
"""
import logging
import os
import sqlite3
from typing import Tuple

logger = logging.getLogger(__name__)


# 建议最低版本: 3.51.3 (含 WAL-reset race 修复)
# 来源: https://www.sqlite.org/forum/forumpost/{case}
# Django 案例: https://blog.bythewood.me/posts/optimizing-sqlite-for-django-in-production/
DEFAULT_MIN_VERSION = "3.51.3"


def parse_version(version_str: str) -> Tuple[int, int, int]:
    """解析 SQLite 版本字符串 '3.51.3' → (3, 51, 3)"""
    parts = version_str.split('.')
    major = int(parts[0]) if len(parts) > 0 else 0
    minor = int(parts[1]) if len(parts) > 1 else 0
    patch = int(parts[2]) if len(parts) > 2 else 0
    return (major, minor, patch)


def check_sqlite_version(min_version: str = None) -> bool:
    """检查 SQLite 版本是否 >= min_version.

    Returns:
        True = compliant (>= min_version)
        False = non-compliant (< min_version)

    Raises:
        RuntimeError: 仅当 SQLITE_REQUIRE_MIN_VERSION=strict 时强制 raise
    """
    if min_version is None:
        min_version = os.environ.get('SQLITE_REQUIRE_MIN_VERSION', DEFAULT_MIN_VERSION)

    current_str = sqlite3.sqlite_version
    current = parse_version(current_str)
    minimum = parse_version(min_version)
    compliant = current >= minimum

    try:
        from meta.core.observability import metrics_inc
        if compliant:
            metrics_inc('sqlite_version_compliant')
        else:
            # 对于 Gauge 类型 metric, 无法 inc(0) 直接表达不达标
            # 通过日志 WARNING 表达
            pass
    except ImportError:
        pass

    if compliant:
        logger.info(
            "[V007.42] SQLite version check passed: %s >= %s",
            current_str, min_version
        )
        return True

    # 不达标
    msg = (
        f"[V007.42] SQLite {current_str} < {min_version}, "
        f"WAL-reset race risk (3.51.3 fixes this). "
        f"Upgrade Python or use system SQLite >= 3.51.3."
    )
    if os.environ.get('SQLITE_REQUIRE_MIN_VERSION', '').lower() == 'strict':
        logger.error(msg)
        raise RuntimeError(msg)
    else:
        logger.warning(msg)
        return False


def get_version_info() -> dict:
    """获取版本信息 (用于诊断和 verify 测试)"""
    import sys
    return {
        'sqlite_version': sqlite3.sqlite_version,
        'sqlite_version_tuple': parse_version(sqlite3.sqlite_version),
        'python_version': sys.version.split()[0],
        'min_required': DEFAULT_MIN_VERSION,
        'compliant': parse_version(sqlite3.sqlite_version) >= parse_version(DEFAULT_MIN_VERSION),
    }


# 模块导入时自动检查一次
_check_done = False


def ensure_version_checked():
    """确保版本检查已执行 (幂等). 用于应用启动入口调用."""
    global _check_done
    if not _check_done:
        check_sqlite_version()
        _check_done = True


if __name__ == '__main__':
    info = get_version_info()
    print(f"SQLite version: {info['sqlite_version']}")
    print(f"Min required:   {info['min_required']}")
    print(f"Compliant:      {info['compliant']}")
    check_sqlite_version()