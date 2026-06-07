# -*- coding: utf-8 -*-
import logging

from meta.core.interceptors.base import Interceptor
from meta.core.action_context import ActionContext
from meta.core.key_template_engine import KeyTemplateEngine, KeyTemplateConfig

logger = logging.getLogger(__name__)


class KeyTemplateInterceptor(Interceptor):
    """
    KeyTemplate 自动编码拦截器

    在 BO 创建时，如果：
    1. meta_object 定义了 key_template 配置
    2. key_template.enabled = True
    3. 用户未提供 code 值（或 code 为空）
    4. 且 auto_suggest 开启

    则自动生成编码并注入 context.params['code']。

    优先级设计：
    - 45：在 FieldPolicyInterceptor(25) 和 EnumProtectionInterceptor(22) 之后
    - 在 PersistenceInterceptor(95) 之前
    - 确保字段策略和枚举校验已完成，但持久化尚未发生
    """

    def __init__(self, engine: KeyTemplateEngine = None):
        self._engine = engine

    def set_engine(self, engine: KeyTemplateEngine):
        self._engine = engine

    @property
    def priority(self) -> int:
        return 45

    def before_action(self, context: ActionContext) -> None:
        if not context.is_create_action:
            return

        if not self._engine:
            return

        meta_object = context.meta_object
        key_template_raw = getattr(meta_object, 'key_template', None)
        if not key_template_raw or not key_template_raw.get('enabled'):
            return

        config = KeyTemplateConfig.from_dict(meta_object.id, key_template_raw)
        if not config.enabled or not config.auto_suggest:
            return

        params = context.params
        code_value = params.get('code', '')
        if code_value and str(code_value).strip():
            return

        field_values = dict(params)
        field_values.pop('code', None)

        self._resolve_parent_fields(context, field_values, config)

        code = self._engine.generate_code(config, field_values, meta_object.id)
        if code:
            params['code'] = code
            logger.info(
                f"[KeyTemplateInterceptor] Auto-generated code '{code}' "
                f"for {meta_object.id}"
            )

    def _resolve_parent_fields(self, context: ActionContext,
                               field_values: dict, config: KeyTemplateConfig) -> None:
        import re
        field_refs = re.findall(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', config.pattern)
        for ref in field_refs:
            if ref.upper().startswith('SEQ'):
                continue
            if ref in field_values and field_values[ref]:
                continue
            parent_field = f"{ref}_id"
            if parent_field not in context.params:
                parent_field = ref.replace('_code', '_id')
                if parent_field not in context.params:
                    parent_field = ref.removesuffix('_no')
                    parent_field = f"{parent_field}_id"
            if parent_field in context.params and context.params[parent_field]:
                parent_id = context.params[parent_field]
                base_type = ref.replace('_code', '').replace('_no', '')
                from meta.core.metadata_resolver import MetadataResolver
                resolved = MetadataResolver.get_table_name(base_type)
                candidate_tables = [resolved] if resolved != base_type else [base_type, base_type + 's', base_type + 'es']
                try:
                    ds = context.data_source
                    existing_tables = set()
                    try:
                        tables_result = ds.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        ).fetchall()
                        for t in tables_result:
                            existing_tables.add(
                                t[0] if isinstance(t, tuple) else (t.get('name', '') if isinstance(t, dict) else '')
                            )
                    except Exception:
                        pass
                    object_type = base_type
                    for ct in candidate_tables:
                        if ct in existing_tables:
                            object_type = ct
                            break
                    table_cols = ds.execute(
                        f"PRAGMA table_info({object_type})"
                    ).fetchall()
                    col_names = [c[1] if isinstance(c, tuple) else (c.get('name', '') if isinstance(c, dict) else '') for c in table_cols]
                    code_col = 'code' if 'code' in col_names else 'name'
                    result = ds.execute(
                        f"SELECT {code_col} FROM {object_type} WHERE id = ?",
                        (parent_id,)
                    ).fetchone()
                    if result:
                        val = result[0] if isinstance(result, tuple) else (result.get(code_col) if isinstance(result, dict) else result)
                        if val:
                            field_values[ref] = val
                            logger.info(
                                f"[KeyTemplateInterceptor] Resolved {ref}={val} "
                                f"from {object_type}.id={parent_id}"
                            )
                except Exception as e:
                    logger.debug(
                        f"[KeyTemplateInterceptor] Could not resolve {ref}: {e}"
                    )

    def after_action(self, context: ActionContext) -> None:
        pass

    def should_execute(self, context: ActionContext) -> bool:
        if not context.is_create_action:
            return False
        meta_object = context.meta_object
        key_template_raw = getattr(meta_object, 'key_template', None)
        if not key_template_raw:
            return False
        return True