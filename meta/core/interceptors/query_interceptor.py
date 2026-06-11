# -*- coding: utf-8 -*-
import logging
from typing import TYPE_CHECKING

from meta.core.interceptors.base import Interceptor

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)


class QueryInterceptor(Interceptor):
    """
    查询增强拦截器

    after_action 阶段对查询结果进行增强：
    1. type标记注入 — 每条记录添加 object_type 字段
    2. 记录增强(冗余字段JOIN) — enrichment_engine 填充虚拟冗余字段
    3. 计算列批量计算 — computation_service 计算 UI 定义的计算列
    4. can_delete检查 — 从 meta_obj.deletability 判断是否可删除
    """

    @property
    def name(self) -> str:
        return "query"

    @property
    def priority(self) -> int:
        return 50

    def before_action(self, context: 'ActionContext') -> None:
        pass

    def after_action(self, context: 'ActionContext') -> None:
        if not context.result or not context.result.success:
            return

        if context.is_query_action:
            items = self._extract_items(context)
            if not items:
                return
            self._inject_type_tag(context, items)
            self._enrich_records(context, items)
            # [V1.1.6 2026-06-11] 关闭 effective_owner_id 派生
            # V1.1.4 已删 yaml 字段定义 + list columns, V1.1.5 已删 owner_id DB 列
            # effective_owner_id 不再注入 (UI 不显示, Excel 不导出, 顶层 owner 在 product)
            # self._inject_effective_owner(context, items)
            self._inject_display_values(context, items)  # [DECORATIVE] [NEW] v1.2 / FR-3.2: 在 enrichment 之后、compute 之前
            self._compute_columns(context, items)
            self._check_can_delete(context, items)
        elif context.action in ('crud_update', 'crud_create'):
            items = self._extract_items(context)
            if items:
                self._enrich_records(context, items)

    def _extract_items(self, context: 'ActionContext') -> list:
        data = context.result.data
        if data is None:
            return []
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            if 'items' in data:
                return data['items']
            if 'data' in data and isinstance(data['data'], list):
                return data['data']
            if context.action == 'crud_read':
                return [data]
        return []

    def _inject_type_tag(self, context: 'ActionContext', items: list) -> None:
        object_type = context.object_type
        for item in items:
            if isinstance(item, dict):
                item['type'] = object_type

    def _enrich_records(self, context: 'ActionContext', items: list) -> None:
        try:
            from meta.core.enrichment_engine import enrich_records
            enriched = enrich_records(context.object_type, items)
            if enriched and isinstance(context.result.data, dict) and 'items' in context.result.data:
                context.result.data['items'] = enriched
            elif enriched and isinstance(context.result.data, list):
                context.result.data = enriched
        except Exception as e:
            logger.debug(f"[QueryInterceptor] enrichment skipped for {context.object_type}: {e}")

        # [FIX 2026-06-10] virtual FK fields（如 business_object.domain_id）由 enrich_batch
        # 通过 join_path 填充。PersistenceInterceptor._do_list 先于本拦截器运行，
        # 那时这些 virtual FK 字段还是 None，导致 enrich_fk_display_names 被跳过、
        # domain_id_display / sub_domain_id_display 缺失。这里在 virtual FK 字段已就位后
        # 重新跑一次 enrich_fk_display_names，再注入到 display_values。
        try:
            from meta.core.models import registry as meta_registry
            from meta.core.enrichment_engine import EnrichmentEngine
            meta_obj = meta_registry.get(context.object_type)
            if meta_obj is not None:
                items_now = self._extract_items(context)
                if items_now:
                    EnrichmentEngine().enrich_fk_display_names(meta_obj, items_now)
        except Exception as e:
            logger.debug(f"[QueryInterceptor] post-enrich fk_display skipped for {context.object_type}: {e}")

    def _compute_columns(self, context: 'ActionContext', items: list) -> None:
        try:
            from meta.services.computation_service import computation_service
            from meta.core.models import registry as meta_registry

            meta_obj = meta_registry.get(context.object_type)
            if not meta_obj or not hasattr(meta_obj, 'ui_view_config') or not meta_obj.ui_view_config:
                return

            list_config = getattr(meta_obj.ui_view_config, 'list', None)
            ui_computed_columns = []
            if list_config and hasattr(list_config, 'columns'):
                ui_computed_columns = [
                    {'key': col.key, 'computation': getattr(col, 'computation', None)}
                    for col in list_config.columns
                    if getattr(col, 'computed', False) and getattr(col, 'computation', None)
                ]

            rule_computed_columns = computation_service.get_computed_columns_from_rules(context.object_type)
            computed_columns = computation_service.merge_computed_columns(ui_computed_columns, rule_computed_columns)

            if computed_columns:
                computation_service.compute_batch(context.data_source, context.object_type, items, computed_columns)
        except Exception as e:
            logger.debug(f"[QueryInterceptor] computation skipped for {context.object_type}: {e}")

    def _check_can_delete(self, context: 'ActionContext', items: list) -> None:
        meta_obj = context.meta_object
        if not meta_obj or not getattr(meta_obj, 'deletability', None):
            return

        try:
            from meta.services.manage_service import ManageService
            service = ManageService(context.data_source)
            can_delete_map = service.batch_check_can_delete(context.object_type, items)
            for item in items:
                if isinstance(item, dict):
                    item_id = item.get('id')
                    item['can_delete'] = can_delete_map.get(item_id, True)
        except Exception as e:
            logger.debug(f"[QueryInterceptor] can_delete check skipped: {e}")
            for item in items:
                if isinstance(item, dict):
                    item['can_delete'] = True

    def _inject_display_values(self, context: 'ActionContext', items: list) -> None:
        """[DECORATIVE] [NEW] v1.2 / FR-3.1: 为每条记录追加 display_values 字段

        规则:
        - FK 字段 → 关联对象的 display_field 值（通过 enrichment_engine 生成的 <field>_display 虚拟字段）
        - enum 字段 → 枚举标签（metaObj.fields[].enum_values 中 label/value）
        - boolean 字段 → 是/否 标签
        - date/datetime → 格式化字符串

        Args:
            context: ActionContext（含 object_type + data_source）
            items: 查询结果记录列表

        Note:
            - 必须容错：缺 meta_obj 时静默跳过
            - enum_values 元素兼容 str 和 dict（与 Agent A bug #4 修复一致）
        """
        object_type = context.object_type
        try:
            from meta.core.models import registry
            meta_obj = registry.get(object_type)
            if not meta_obj:
                return
        except Exception as e:
            logger.debug(f"[QueryInterceptor] display_values skipped: registry error: {e}")
            return

        # 1. 预分类字段（按类型）
        fk_fields = []     # (field_id, display_field) — 来自 ui.relation
        enum_fields = []   # 字段定义
        bool_fields = []   # field_id
        date_fields = []   # field_id

        for field in meta_obj.fields:
            ui = getattr(field, 'ui', None)
            relation = None
            display_field = None
            if isinstance(ui, dict):
                relation = ui.get('relation')
                display_field = ui.get('display_field')
            elif ui is not None:
                relation = getattr(ui, 'relation', None)
                display_field = getattr(ui, 'display_field', None)

            if relation:
                fk_fields.append((field.id, display_field))
            elif getattr(field, 'enum_values', None):
                enum_fields.append(field)
            else:
                ft = getattr(field, 'field_type', None)
                ft_name = getattr(ft, 'name', str(ft)) if ft else ''
                if ft_name == 'BOOLEAN':
                    bool_fields.append(field.id)
                elif ft_name in ('DATE', 'DATETIME'):
                    date_fields.append(field.id)

        if not (fk_fields or enum_fields or bool_fields or date_fields):
            return  # 无可处理字段

        # 2. 为每条 item 计算 display_values
        for item in items:
            if not isinstance(item, dict):
                continue
            display_values = item.get('display_values', {}) or {}

            # FK: enrichment 已生成 <field>_display 虚拟字段
            for field_id, _display_field in fk_fields:
                virtual_key = f'{field_id}_display'
                if virtual_key in item and item[virtual_key] is not None:
                    display_values[field_id] = item[virtual_key]

            # enum: 查 enum_values 找 label
            for field in enum_fields:
                value = item.get(field.id)
                if value is None:
                    continue
                for ev in field.enum_values:
                    if isinstance(ev, dict):
                        if ev.get('value') == value:
                            display_values[field.id] = ev.get('label', str(value))
                            break
                    elif ev == value:
                        display_values[field.id] = str(value)
                        break

            # boolean → 是/否
            for fid in bool_fields:
                v = item.get(fid)
                if v is None:
                    continue
                display_values[fid] = '是' if v else '否'

            # date/datetime → 截取
            for fid in date_fields:
                v = item.get(fid)
                if v is None:
                    continue
                s = str(v)
                # 简单处理：DATE 取前 10 字符，DATETIME 取前 19 字符
                if 'T' in s or len(s) > 10:
                    display_values[fid] = s[:19]
                else:
                    display_values[fid] = s[:10]

            if display_values:
                item['display_values'] = display_values
