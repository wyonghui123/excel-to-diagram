SYSTEM_FIELDS = frozenset({'id', 'created_at', 'updated_at', 'created_by', 'updated_by'})
DATETIME_TYPES = frozenset({'datetime', 'timestamp', 'date'})
# [FIX 2026-06-08] 从 SENSITIVE_FIELDS 移除 'password'：
# 'password' 是 user.yaml 里的 virtual 字段（db_column=password_hash），
# admin 在新建用户界面需要看到密码输入框（隐藏_in_form: false），由后端自动生成或 admin 手动填。
# 注意 'password_hash' 仍保留在列表里，确保真正的哈希值不会被前端展示。
SENSITIVE_FIELDS = frozenset({'password_hash', 'secret', 'token', 'api_key', 'pwd'})

DEFAULT_VISIBILITY = {
    'visible': True, 'editable': True, 'readonly': False,
    'hidden_in_detail': False, 'hidden_in_form': False, 'hidden_in_list': False,
}
