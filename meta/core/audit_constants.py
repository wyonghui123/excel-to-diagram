# -*- coding: utf-8 -*-
"""
audit_constants.py — 审计常量与派生工具 (v3.18)

- AuditCategory: 7 类 (FR-003)
- AuditLevel: 3 级 (FR-004)
- AuditOutcome: 4 种 (FR-005)
- 派生工具: derive_category / derive_level / normalize_user_name
"""
from __future__ import annotations
import re
from enum import Enum
from typing import Optional, Dict, Any


# ============ 枚举 ============

class AuditCategory(str, Enum):
    """审计类别 — 7 类 (FR-003)"""
    BUSINESS = "business"     # CRUD 业务操作
    SECURITY = "security"     # 登录/密码/2FA/会话
    AUTHZ = "authz"           # role/permission 授权
    ACCESS = "access"         # READ/EXPORT/查询
    ADMIN = "admin"           # DELETE_BLOCKED/审计配置
    SYSTEM = "system"         # AUDIT_WRITE_FAILED/系统故障
    CASCADE = "cascade"       # 级联衍生


class AuditLevel(str, Enum):
    """审计级别 — 3 级 (FR-004)"""
    INFO = "INFO"     # 成功
    WARN = "WARN"     # 拒绝/阻塞
    ERROR = "ERROR"   # 系统故障


class AuditOutcome(str, Enum):
    """审计结果 — 4 种 (FR-005)"""
    SUCCESS = "success"
    FAILURE = "failure"
    BLOCKED = "blocked"
    RETRY = "retry"


# ============ 派生规则 ============

# 哪些 action 属于 security
_SECURITY_ACTIONS = frozenset([
    "LOGIN", "LOGOUT", "PASSWORD_CHANGE", "PASSWORD_RESET",
    "2FA_ENABLE", "2FA_DISABLE", "TOTP_VERIFY", "SESSION_CREATE",
    "SESSION_REVOKE", "TOKEN_REFRESH", "OAUTH_LOGIN", "OAUTH_LINK",
])

# 哪些 action 属于 authz
_AUTHZ_ACTIONS = frozenset([
    "ROLE_ASSIGN", "ROLE_UNASSIGN", "ROLE_CREATE", "ROLE_UPDATE",
    "ROLE_DELETE", "PERMISSION_GRANT", "PERMISSION_REVOKE",
])

# 哪些 action 属于 access
_ACCESS_ACTIONS = frozenset([
    "READ", "EXPORT", "QUERY", "LIST", "SEARCH", "DOWNLOAD",
])

# 哪些 action 属于 admin
_ADMIN_ACTIONS = frozenset([
    "DELETE_BLOCKED", "ACCESS_DENIED", "AUDIT_CONFIG_CHANGE",
    "USER_GROUP_TRANSFER", "PRODUCT_TRANSFER",
])

# 哪些 action 属于 system
_SYSTEM_ACTIONS = frozenset([
    "AUDIT_WRITE_FAILED", "AUDIT_RETRY", "SYSTEM_MAINTENANCE",
    "DB_RESTORE", "AUDIT_EXPORT",
])


def derive_category(action: str, *, cascade: bool = False) -> str:
    """根据 action 自动派生 log_category (FR-003)

    Args:
        action: 审计动作名 (e.g. 'CREATE', 'LOGIN', 'DELETE_BLOCKED')
        cascade: 是否为级联衍生 (cascade_interceptor 设置)

    Returns:
        AuditCategory 枚举值
    """
    if cascade:
        return AuditCategory.CASCADE.value
    action_upper = (action or "").upper()
    if action_upper in _SECURITY_ACTIONS:
        return AuditCategory.SECURITY.value
    if action_upper in _AUTHZ_ACTIONS:
        return AuditCategory.AUTHZ.value
    if action_upper in _ACCESS_ACTIONS:
        return AuditCategory.ACCESS.value
    if action_upper in _ADMIN_ACTIONS:
        return AuditCategory.ADMIN.value
    if action_upper in _SYSTEM_ACTIONS:
        return AuditCategory.SYSTEM.value
    return AuditCategory.BUSINESS.value


def derive_level(action: str, *, outcome: str = "success") -> str:
    """根据 action 和 outcome 自动派生 log_level (FR-004)

    规则:
      - 系统故障 (AUDIT_WRITE_FAILED) → ERROR
      - 拒绝/阻塞 (DELETE_BLOCKED, ACCESS_DENIED, outcome=failure) → WARN
      - 成功 → INFO
    """
    action_upper = (action or "").upper()
    if action_upper in ("AUDIT_WRITE_FAILED",):
        return AuditLevel.ERROR.value
    if action_upper in ("DELETE_BLOCKED", "ACCESS_DENIED"):
        return AuditLevel.WARN.value
    if outcome in ("failure", "blocked"):
        return AuditLevel.WARN.value
    return AuditLevel.INFO.value


def derive_outcome_from_action(action: str) -> str:
    """[v3.18 FR-005] 从 action 字符串自动 derive outcome

    映射:
      DELETE_BLOCKED  → blocked
      DELETE_FAILED   → failure
      AUDIT_WRITE_FAILED / *_FAILED → failure
      AUDIT_RETRY     → retry
      其它            → success
    """
    if not action:
        return AuditOutcome.SUCCESS.value
    action_upper = action.upper()
    if action_upper == "DELETE_BLOCKED" or "BLOCKED" in action_upper:
        return AuditOutcome.BLOCKED.value
    if action_upper == "DELETE_FAILED" or "FAILED" in action_upper:
        return AuditOutcome.FAILURE.value
    if "RETRY" in action_upper:
        return AuditOutcome.RETRY.value
    return AuditOutcome.SUCCESS.value


# ============ user_name 标准化 (FR-006) ============

_USER_NAME_RE = re.compile(r"^(.+?)\s*\(([^()]+)\)$")


def normalize_user_name(display_name: Optional[str], username: Optional[str]) -> str:
    """统一 user_name 格式: "display_name (username)"

    三种情况:
      1. 都为空 → "anonymous"
      2. display_name 缺失或等于 username → 纯 username
      3. 都有且不等 → "{display_name} ({username})"
    """
    d = (display_name or "").strip()
    u = (username or "").strip()
    if not d and not u:
        return "anonymous"
    if not u or not d or d == u:
        # username 缺失 / display_name 缺失 / 两者相同 → 纯 username
        return u or d or "anonymous"
    return f"{d} ({u})"


def parse_user_name(user_name: str) -> Dict[str, str]:
    """反解 user_name → {display_name, username}"""
    if not user_name or user_name == "anonymous":
        return {"display_name": "", "username": user_name or ""}
    m = _USER_NAME_RE.match(user_name.strip())
    if m:
        return {"display_name": m.group(1).strip(), "username": m.group(2).strip()}
    return {"display_name": "", "username": user_name.strip()}


# ============ retention_until 计算 (FR-013) ============

_RETENTION_DAYS = {
    AuditCategory.SECURITY.value: 730,  # 2 年
    AuditCategory.AUTHZ.value: 730,     # 2 年
    AuditCategory.BUSINESS.value: 365,  # 1 年
    AuditCategory.ADMIN.value: 365,     # 1 年
    AuditCategory.ACCESS.value: 90,     # 90 天
    AuditCategory.SYSTEM.value: 90,     # 90 天
    AuditCategory.CASCADE.value: 90,    # 90 天
}


def retention_days(category: str) -> int:
    """根据 category 返保留天数 (3 层策略, TBD-2 决策)"""
    return _RETENTION_DAYS.get(category, 365)


# ============ 自测 ============

if __name__ == "__main__":
    # 单元测试
    assert derive_category("LOGIN") == "security"
    assert derive_category("ROLE_ASSIGN") == "authz"
    assert derive_category("READ") == "access"
    assert derive_category("DELETE_BLOCKED") == "admin"
    assert derive_category("AUDIT_WRITE_FAILED") == "system"
    assert derive_category("CREATE", cascade=True) == "cascade"
    assert derive_category("UPDATE") == "business"
    print("[OK] derive_category 7 类")

    assert derive_level("CREATE", outcome="success") == "INFO"
    assert derive_level("DELETE_BLOCKED") == "WARN"
    assert derive_level("CREATE", outcome="failure") == "WARN"
    assert derive_level("AUDIT_WRITE_FAILED") == "ERROR"
    print("[OK] derive_level 3 级")

    assert derive_outcome_from_action("CREATE") == "success"
    assert derive_outcome_from_action("DELETE_BLOCKED") == "blocked"
    assert derive_outcome_from_action("DELETE_FAILED") == "failure"
    assert derive_outcome_from_action("AUDIT_WRITE_FAILED") == "failure"
    assert derive_outcome_from_action("AUDIT_RETRY") == "retry"
    assert derive_outcome_from_action("") == "success"
    print("[OK] derive_outcome_from_action 4 种")

    assert normalize_user_name("张三", "zhangsan") == "张三 (zhangsan)"
    assert normalize_user_name("zhangsan", "zhangsan") == "zhangsan"
    assert normalize_user_name("", "zhangsan") == "zhangsan"
    assert normalize_user_name("张三", "") == "张三"
    assert normalize_user_name("", "") == "anonymous"
    assert normalize_user_name(None, None) == "anonymous"
    print("[OK] normalize_user_name 5 情况")

    assert retention_days("security") == 730
    assert retention_days("business") == 365
    assert retention_days("access") == 90
    print("[OK] retention_days 3 层")

    print("\n所有单元测试通过")
