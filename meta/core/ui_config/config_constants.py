SYSTEM_FIELDS = frozenset({'id', 'created_at', 'updated_at', 'created_by', 'updated_by'})
DATETIME_TYPES = frozenset({'datetime', 'timestamp', 'date'})
SENSITIVE_FIELDS = frozenset({'password_hash', 'secret', 'token', 'api_key', 'password', 'pwd'})

DEFAULT_VISIBILITY = {
    'visible': True, 'editable': True, 'readonly': False,
    'hidden_in_detail': False, 'hidden_in_form': False, 'hidden_in_list': False,
}
