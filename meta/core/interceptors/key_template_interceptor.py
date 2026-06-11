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

        # [FIXED 2026-06-11] 同步 relation_type → relation_code
        # UNIQUE INDEX uidx_relationships_version_source_target_type 在
        # (version_id, source_bo_id, target_bo_id, relation_code) 上。
        # 如果前端只传 relation_type 而 relation_code 为 NULL，
        # 多个相同源/目标/版本的关系都会 NULL 冲突失败（实际 SQLite 中多个 NULL 不冲突），
        # 但 ORM/驱动层可能判定为重复。
        # 修复：拦截器自动同步，保证两个字段值一致。
        if 'relation_type' in params and 'relation_code' not in params:
            params['relation_code'] = params['relation_type']
        elif 'relation_code' in params and 'relation_type' not in params:
            params['relation_type'] = params['relation_code']

        code_value = params.get('code', '')
        if code_value and str(code_value).strip():
            return

        field_values = dict(params)
        field_values.pop('code', None)

        self._resolve_parent_fields(context, field_values, config)

        # [FIXED 2026-06-11] 传递 table_name 和 prefix_filter 以支持 auto_detect_start
        # 原 BUG: generate_code 不传这两个参数，SequenceEngine.auto_detect_start 使用
        # config.object_id 作表名（如 'relationship'），但实际表是 'relationships'；
        # 且没有 prefix_filter，所有关系的 code 混在一起取最大序号。
        import re as _re
        physical_table = self._resolve_physical_table(meta_object.id, context)
        tokens = self._engine._parser.parse(config.pattern)
        prefix_filter = self._engine._parser.resolve_prefix(tokens, field_values)

        code = self._engine.generate_code(
            config, field_values, meta_object.id,
            table_name=physical_table,
            prefix_filter=prefix_filter
        )
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
                    if parent_field not in context.params:
                        # 🆕 2026-06-10 兼容 _bo_id 后缀（如 source_bo_id / target_bo_id）
                        # ref 可能是 source_code/target_code，但 params 字段是 source_bo_id/target_bo_id
                        bo_id_field = f"{ref.replace('_code', '')}_bo_id"
                        if bo_id_field in context.params:
                            parent_field = bo_id_field
            if parent_field in context.params and context.params[parent_field]:
                parent_id = context.params[parent_field]
                base_type = ref.replace('_code', '').replace('_no', '')
                from meta.core.metadata_resolver import MetadataResolver
                resolved = MetadataResolver.get_table_name(base_type)
                candidate_tables = [resolved] if resolved != base_type else [base_type, base_type + 's', base_type + 'es']
                # 🆕 2026-06-10 如果是 source_bo_id/target_bo_id，直接查 business_objects 表
                if parent_field in ('source_bo_id', 'target_bo_id'):
                    candidate_tables = ['business_objects']
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

    def _resolve_physical_table(self, object_type: str, context: ActionContext) -> str:
        """
        [NEW 2026-06-11] 将逻辑对象名解析为物理表名。
        例如 'relationship' → 'relationships'（SQLite 中实际表名带复数 s）。
        """
        ds = context.data_source
        try:
            existing_tables = set()
            tables_result = ds.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            for t in tables_result:
                existing_tables.add(
                    t[0] if isinstance(t, tuple) else (t.get('name', '') if isinstance(t, dict) else '')
                )
            candidate_tables = [object_type, object_type + 's', object_type + 'es']
            for ct in candidate_tables:
                if ct in existing_tables:
                    logger.debug(
                        f"[KeyTemplateInterceptor] Resolved table name: {object_type} -> {ct}"
                    )
                    return ct
        except Exception as e:
            logger.debug(f"[KeyTemplateInterceptor] _resolve_physical_table fallback: {e}")
        return object_type

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