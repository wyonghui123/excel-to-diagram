# -*- coding: utf-8 -*-
"""敏感字段单一声明（PII 字段级安全域 Spec v0.1 / P1）

历史问题：同一个名字 `SENSITIVE_FIELDS` 在三处各自维护，成员互不一致，
且差异并非「谁漏了」，而是三种不同语义：

  1. action_models.SENSITIVE_FIELDS           写面脱敏（审计/日志落库前替换为 [REDACTED]）
  2. ui_config.config_constants.SENSITIVE_FIELDS   UI 隐藏（visible=False + 三个 hidden 标志）
  3. log_filter_service.SENSITIVE_KEYS         日志文本子串匹配

合并成一个集合会造成可见回归（最典型：`password` 并入 UI 集合后，
admin 新建用户表单的密码输入框消失）。因此本模块用**一张明细表**声明，
按用途拆成三条派生视图，三处原常量改为 re-export，调用方零改动。

本阶段（P1）成员与收敛前逐元素一致，唯一新增是 `private_key` 进入 UI 隐藏集合
——当前全仓无任何字段 id 叫 `private_key`（仅本常量引用），故无行为影响。

详见 docs/superpowers/specs/2026-10-29-pii-field-level-security-spec.md
"""

from typing import NamedTuple, FrozenSet


class SecretField(NamedTuple):
    """单个敏感字段的声明

    id            字段 id（与 YAML 字段 id 一致）
    log_redact    写面脱敏（审计/日志落库时值替换为 [REDACTED]）
    ui_hidden     UI 隐藏（visible=False + hidden_in_detail/form/list）
    log_text_key  日志文本子串匹配键（大小写不敏感，命中即脱敏）
    note          该字段的用途备注（为何这样标）
    """
    id: str
    log_redact: bool
    ui_hidden: bool
    log_text_key: bool
    note: str


# ────────────────────────────────────────────────────────────────
# 明细表（唯一事实源）
# ────────────────────────────────────────────────────────────────
SECRET_FIELD_DECLARATIONS = (
    SecretField(
        id='password',
        log_redact=True,
        ui_hidden=False,   # 刻意不隐藏：virtual 输入字段，admin 新建用户必须能填
        log_text_key=True,
        note='user.yaml virtual 字段（storage=VIRTUAL, 无 db_column），'
             '新建用户时 admin 手动填或后端自动生成；UI 必须可见',
    ),
    SecretField(
        id='password_hash',
        log_redact=False,  # 收敛前写面集合未含此项（见 Spec §9 遗留 D1）
        ui_hidden=True,
        log_text_key=True,
        note='真正的持久化哈希列；UI 永不可见，日志文本按 key 命中脱敏',
    ),
    SecretField(
        id='secret',
        log_redact=True,
        ui_hidden=True,
        log_text_key=True,
        note='通用密钥类字段',
    ),
    SecretField(
        id='token',
        log_redact=True,
        ui_hidden=True,
        log_text_key=True,
        note='通用令牌类字段',
    ),
    SecretField(
        id='api_key',
        log_redact=True,
        ui_hidden=True,
        log_text_key=True,
        note='API 密钥',
    ),
    SecretField(
        id='pwd',
        log_redact=False,  # 收敛前写面集合未含此项
        ui_hidden=True,
        log_text_key=True,
        note='密码简写别名（历史遗留命名）',
    ),
    SecretField(
        id='private_key',
        log_redact=True,
        ui_hidden=True,
        log_text_key=False,  # 收敛前日志文本集合未含此项
        note='私钥；当前全仓无字段使用该 id，纳入隐藏无行为影响',
    ),
)


# ────────────────────────────────────────────────────────────────
# 派生视图（按用途）
# ────────────────────────────────────────────────────────────────

# 用途 A：写面脱敏 —— action_models.SENSITIVE_FIELDS
# 收敛前 = {'password', 'token', 'secret', 'api_key', 'private_key'}
LOG_REDACT_IDS: FrozenSet[str] = frozenset(
    d.id for d in SECRET_FIELD_DECLARATIONS if d.log_redact
)

# 用途 B：UI 隐藏 —— ui_config.config_constants.SENSITIVE_FIELDS
# 收敛前 = {'password_hash', 'secret', 'token', 'api_key', 'pwd'}
# 新增 'private_key'（无字段使用，零行为影响）
UI_HIDDEN_IDS: FrozenSet[str] = frozenset(
    d.id for d in SECRET_FIELD_DECLARATIONS if d.ui_hidden
)


# 用途 C：日志文本子串匹配 —— log_filter_service.SENSITIVE_KEYS
#
# 明细表只覆盖「字段 id」；日志侧另有若干不是字段 id、但出现在日志键名里的
# 词（含会话/授权/身份证等），它们不是字段声明，故单列一层，保持原集合不变。
EXTRA_LOG_KEYS: FrozenSet[str] = frozenset({
    'passwd',        # password 的另一种拼写（子串匹配无法覆盖）
    'apikey',        # api_key 的驼峰变体
    'access_token',  # 含 'token' 子串，保留原名避免依赖子串行为
    'refresh_token',
    'authorization',
    'auth_token',
    'old_password',
    'new_password',
    'passwordHash',
    'session_id',
    'sessionid',
    'cookie',
    'ssn',
    'id_number',
})

LOG_TEXT_KEYS: FrozenSet[str] = frozenset(
    d.id for d in SECRET_FIELD_DECLARATIONS if d.log_text_key
) | EXTRA_LOG_KEYS
