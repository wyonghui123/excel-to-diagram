SYSTEM_FIELDS = frozenset({'id', 'created_at', 'updated_at', 'created_by', 'updated_by'})
DATETIME_TYPES = frozenset({'datetime', 'timestamp', 'date'})
# [P1 2026-10-29] 敏感字段单一声明（PII 字段级安全域 Spec v0.1）
# 明细表见 meta/core/security/sensitive_fields.py，此处 re-export UI 隐藏视图。
# 'password' 刻意不在此集合：它是 user.yaml 的 virtual 输入字段，
# admin 新建用户必须看到密码输入框（原 [FIX 2026-06-08] 结论，现已写入声明表 note）。
from meta.core.security.sensitive_fields import UI_HIDDEN_IDS as SENSITIVE_FIELDS  # noqa: E402

DEFAULT_VISIBILITY = {
    'visible': True, 'editable': True, 'readonly': False,
    'hidden_in_detail': False, 'hidden_in_form': False, 'hidden_in_list': False,
}
