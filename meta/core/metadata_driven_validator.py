# -*- coding: utf-8 -*-
"""
元数据驱动校验器 - 基于 YAML 元模型的统一字段级校验

所有校验逻辑基于 YAML 元数据声明自动执行，
覆盖 Create/Update 操作的字段级校验：
- required / mandatory / business_key 必填
- unique 单字段唯一性
- pattern 正则校验
- max_length 长度校验
- enum_values 枚举值范围校验
- FK 存在性校验
- business_key 组合唯一性
- indexes 复合唯一索引
"""

import re
import logging
from typing import List, Dict, Any, Optional, TYPE_CHECKING

from meta.core.validation_messages import ValidationDetail, ValidationMessageRegistry

if TYPE_CHECKING:
    from meta.core.models import MetaObject, MetaField
    from meta.core.datasource import DataSource

logger = logging.getLogger(__name__)


class MetadataDrivenValidator:
    def __init__(self, data_source: 'DataSource'):
        self.ds = data_source

    def validate_create(self, meta_object: 'MetaObject', data: Dict[str, Any]) -> List[ValidationDetail]:
        errors: List[ValidationDetail] = []
        for field in meta_object.fields:
            if self._skip_field(field, "create"):
                continue
            field_value = data.get(field.id) or data.get(field.db_column)
            field_name = self._get_field_name(meta_object, field)

            errors.extend(self._check_required(field, field_value, field_name, meta_object))
            if field_value is None or field_value == '':
                continue
            errors.extend(self._check_unique(field, field_value, field_name, meta_object))
            errors.extend(self._check_pattern(field, field_value, field_name))
            errors.extend(self._check_max_length(field, field_value, field_name))
            errors.extend(self._check_enum_values(field, field_value, field_name))
            errors.extend(self._check_fk_existence(field, field_value, field_name, data))

        errors.extend(self._check_business_key_composite(meta_object, data))
        errors.extend(self._check_unique_indexes(meta_object, data))
        return errors

    def validate_update(self, meta_object: 'MetaObject', data: Dict[str, Any],
                        original_data: Optional[Dict[str, Any]] = None,
                        exclude_id: Any = None) -> List[ValidationDetail]:
        errors: List[ValidationDetail] = []
        for field in meta_object.fields:
            if self._skip_field(field, "update"):
                continue

            field_id = field.id
            field_db = field.db_column
            is_in_data = field_id in data or field_db in data
            field_value = data.get(field_id) or data.get(field_db)

            if is_in_data:
                errors.extend(self._check_required(field, field_value, self._get_field_name(meta_object, field)))
                if field_value is not None and field_value != '':
                    errors.extend(self._check_unique(field, field_value,
                                                      self._get_field_name(meta_object, field),
                                                      meta_object, exclude_id=exclude_id))
                    errors.extend(self._check_pattern(field, field_value, self._get_field_name(meta_object, field)))
                    errors.extend(self._check_max_length(field, field_value, self._get_field_name(meta_object, field)))
                    errors.extend(self._check_enum_values(field, field_value, self._get_field_name(meta_object, field)))
                    errors.extend(self._check_fk_existence(field, field_value,
                                                            self._get_field_name(meta_object, field), data))

        errors.extend(self._check_business_key_composite(meta_object, data, exclude_id=exclude_id))
        errors.extend(self._check_unique_indexes(meta_object, data, exclude_id=exclude_id))
        return errors

    def _skip_field(self, field: 'MetaField', action: str) -> bool:
        if field.id == 'id':
            return True
        is_virtual = (hasattr(field, 'storage') and field.storage.value == 'virtual') or \
                     getattr(field.semantics, 'virtual', False)
        if is_virtual:
            return True
        return False

    def _get_field_name(self, meta_object: 'MetaObject', field: 'MetaField') -> str:
        if field.name:
            return field.name
        # 尝试从 semantics.meaning 获取友好名
        if hasattr(field, 'semantics') and field.semantics and getattr(field.semantics, 'meaning', None):
            return field.semantics.meaning
        return field.id

    def _is_empty(self, value: Any) -> bool:
        return value is None or value == ''

    def _check_required(self, field: 'MetaField', value: Any, field_name: str,
                        meta_object: 'MetaObject' = None) -> List[ValidationDetail]:
        errors = []
        if field.required and self._is_empty(value):
            errors.append(ValidationDetail(
                field_id=field.id, field_name=field_name, rule="required",
                message=ValidationMessageRegistry.get("validation.field.required", field_name=field_name),
                i18n_key="validation.field.required",
                params={"field_name": field_name}
            ))
            return errors

        if hasattr(field.semantics, 'mandatory') and field.semantics.mandatory and self._is_empty(value):
            errors.append(ValidationDetail(
                field_id=field.id, field_name=field_name, rule="mandatory",
                message=ValidationMessageRegistry.get("validation.field.mandatory", field_name=field_name),
                i18n_key="validation.field.mandatory",
                params={"field_name": field_name}
            ))
            return errors

        if getattr(field.semantics, 'business_key', False) and self._is_empty(value):
            # [FIX 2026-06-17] 如果对象有 key_template 且 enabled + auto_suggest，
            # 则 business_key 为空时不应报必填错误，因为 KeyTemplateInterceptor 会自动生成
            # 例: relationship 的 code 字段，pattern="{source_code}-{target_code}-{SEQ:2}"
            if meta_object:
                kt = getattr(meta_object, 'key_template', None) or {}
                if isinstance(kt, dict) and kt.get('enabled') and kt.get('auto_suggest'):
                    return errors  # key_template 会自动生成，跳过必填验证
            errors.append(ValidationDetail(
                field_id=field.id, field_name=field_name, rule="business_key_required",
                message=ValidationMessageRegistry.get("validation.field.business_key_required", field_name=field_name),
                i18n_key="validation.field.business_key_required",
                params={"field_name": field_name}
            ))
        return errors

    def _check_unique(self, field: 'MetaField', value: Any, field_name: str,
                      meta_object: 'MetaObject', exclude_id: Any = None) -> List[ValidationDetail]:
        if not (hasattr(field, 'unique') and field.unique):
            return []
        try:
            query = f"SELECT COUNT(*) as cnt FROM {meta_object.table_name} WHERE {field.db_column} = ?"
            params = [value]
            if exclude_id:
                query += " AND id != ?"
                params.append(exclude_id)
            cursor = self.ds.execute(query, tuple(params))
            row = cursor.fetchone()
            if row and row[0] > 0:
                return [ValidationDetail(
                    field_id=field.id, field_name=field_name, rule="unique",
                    message=ValidationMessageRegistry.get("validation.field.unique", field_name=field_name),
                    i18n_key="validation.field.unique",
                    params={"field_name": field_name}
                )]
        except Exception:
            pass
        return []

    def _check_pattern(self, field: 'MetaField', value: Any, field_name: str) -> List[ValidationDetail]:
        pattern = getattr(field.semantics, 'pattern', None)
        if not pattern:
            return []
        try:
            if not re.match(pattern, str(value)):
                return [ValidationDetail(
                    field_id=field.id, field_name=field_name, rule="pattern",
                    message=ValidationMessageRegistry.get("validation.field.pattern_mismatch",
                                                           field_name=field_name, pattern=pattern),
                    i18n_key="validation.field.pattern_mismatch",
                    params={"field_name": field_name, "pattern": pattern}
                )]
        except re.error:
            logger.warning(f"Invalid regex pattern for field {field.id}: {pattern}")
        return []

    def _check_max_length(self, field: 'MetaField', value: Any, field_name: str) -> List[ValidationDetail]:
        max_length = getattr(field, 'max_length', None)
        if not max_length:
            return []
        if field.field_type.value not in ('string', 'text'):
            return []
        if len(str(value)) > max_length:
            return [ValidationDetail(
                field_id=field.id, field_name=field_name, rule="max_length",
                message=ValidationMessageRegistry.get("validation.field.max_length_exceeded",
                                                       field_name=field_name, max_length=max_length),
                i18n_key="validation.field.max_length_exceeded",
                params={"field_name": field_name, "max_length": max_length}
            )]
        return []

    def _check_enum_values(self, field: 'MetaField', value: Any, field_name: str) -> List[ValidationDetail]:
        enum_values = getattr(field, 'enum_values', None)
        if not enum_values:
            return []

        # 收集 valid_values：同时保留字符串 + 数字形式（兼容 boolean 字段）
        # Fix 2026-06-05: boolean 字段同时入 0/1 字符串形式，避免 str(1)="1" 不在 ["True","False"] 中的 false-negative
        valid_values = []
        for ev in enum_values:
            if isinstance(ev, dict):
                v = ev.get('value', '')
            elif hasattr(ev, 'value'):
                v = ev.value
            else:
                v = ev
            valid_values.append(str(v))
            # boolean 字段：额外入 0/1 形式
            if isinstance(v, bool):
                valid_values.append('1' if v else '0')

        check_value = value
        if field.field_type.value == 'boolean':
            if isinstance(value, bool):
                check_value = 1 if value else 0
            elif isinstance(value, int):
                check_value = 1 if value else 0

        if str(check_value) not in valid_values:
            return [ValidationDetail(
                field_id=field.id, field_name=field_name, rule="enum_values",
                message=ValidationMessageRegistry.get("validation.field.enum_value_invalid",
                                                       field_name=field_name, value=value,
                                                       valid_values=", ".join(sorted(set(valid_values)))),
                i18n_key="validation.field.enum_value_invalid",
                params={"field_name": field_name, "value": value, "valid_values": sorted(set(valid_values))}
            )]
        return []

    def _check_fk_existence(self, field: 'MetaField', value: Any, field_name: str,
                            data: Dict[str, Any]) -> List[ValidationDetail]:
        resolve_to = getattr(field.semantics, 'resolve_to_object', None)
        parent_key = getattr(field.semantics, 'parent_key', False)
        context_field = getattr(field.semantics, 'context_field', False)
        if not resolve_to and not parent_key:
            return []
        if context_field:
            return []
        target_object = resolve_to or self._infer_parent_object(field)
        if not target_object:
            return []
        from meta import get_meta_object
        target_meta = get_meta_object(target_object)
        if not target_meta:
            return []
        try:
            # [NEW v1.2.13 2026-06-19] 用业务编码(code) 替代 id 查询
            # 用户填的是 code, 错误信息也应显示 code, 而不是数字 id
            lookup_value = value
            lookup_field = 'id'
            target_fields = getattr(target_meta, 'fields', [])
            # 查找目标对象的 code 字段 (业务关键字)
            for tf in target_fields:
                if getattr(tf.semantics, 'business_key', False):
                    lookup_field = tf.db_column
                    break
            # 如果有 value 不是数字, 用 code 字段查
            if value is not None and not str(value).isdigit():
                for tf in target_fields:
                    if getattr(tf.semantics, 'business_key', False):
                        lookup_field = tf.db_column
                        break
            query = f"SELECT id FROM {target_meta.table_name} WHERE {lookup_field} = ? LIMIT 1"
            cursor = self.ds.execute(query, (value,))
            row = cursor.fetchone()
            if not row:
                target_name = target_meta.name or target_object
                # [NEW v1.2.13 2026-06-19] 错误信息包含字段名和值
                display_value = value if value is not None else ''
                return [ValidationDetail(
                    field_id=field.id, field_name=field_name, rule="fk_existence",
                    message=ValidationMessageRegistry.get("validation.field.fk_not_found",
                                                           target_name=target_name,
                                                           field_name=field_name,
                                                           value=display_value),
                    i18n_key="validation.field.fk_not_found",
                    params={"target_name": target_name, "field_name": field_name, "value": display_value}
                )]
        except Exception:
            pass
        return []

    def _infer_parent_object(self, field: 'MetaField') -> Optional[str]:
        field_id = field.id
        if field_id.endswith('_id'):
            candidate = field_id[:-3]
            from meta import get_meta_object
            if get_meta_object(candidate):
                return candidate
        return None

    def _check_business_key_composite(self, meta_object: 'MetaObject', data: Dict[str, Any],
                                       exclude_id: Any = None) -> List[ValidationDetail]:
        bk_fields = []
        for f in meta_object.fields:
            if getattr(f.semantics, 'business_key', False):
                is_virtual = (hasattr(f, 'storage') and f.storage.value == 'virtual') or \
                             getattr(f.semantics, 'virtual', False)
                if not is_virtual:
                    bk_fields.append(f)
        if not bk_fields:
            return []

        bk_values = []
        for bk_field in bk_fields:
            value = data.get(bk_field.id)
            if value is not None and str(value).strip() != "":
                bk_values.append((bk_field, str(value).strip()))

        if not bk_values:
            return []

        where_clauses = []
        params = []
        for bk_field, bk_value in bk_values:
            where_clauses.append(f"{bk_field.db_column} = ?")
            params.append(bk_value)

        has_version_id = any(f.id == 'version_id' for f in meta_object.fields)
        version_id_value = data.get('version_id')
        if has_version_id and version_id_value is not None:
            where_clauses.append("version_id = ?")
            params.append(version_id_value)

        # [BMRD 2026-06-14 FIX] BUG-V006: business_key 配合 FK 字段实现"范围内唯一"
        # 例: version.name semantics.meaning="产品内唯一" → 加 AND product_id = ?
        # 规则: 检测 bk_field.semantics.meaning 含"X内唯一", 自动找对应 FK 字段
        for bk_field, _ in bk_values:
            meaning = (getattr(bk_field.semantics, 'meaning', '') or '').lower()
            scope_fk_map = {
                '产品内唯一': ['product_id', 'parent_id'],
                'product内唯一': ['product_id', 'parent_id'],
                'product 内唯一': ['product_id', 'parent_id'],
                '父对象内唯一': ['parent_id'],
                '客户内唯一': ['customer_id', 'client_id'],
                '租户内唯一': ['tenant_id'],
            }
            for keyword, fk_candidates in scope_fk_map.items():
                if keyword in meaning or keyword.lower() in meaning:
                    for fk_id in fk_candidates:
                        fk_field = next((x for x in meta_object.fields if x.id == fk_id), None)
                        if fk_field:
                            fk_value = data.get(fk_field.id)
                            if fk_value is not None and f"{fk_field.db_column} = ?" not in where_clauses:
                                where_clauses.append(f"{fk_field.db_column} = ?")
                                params.append(fk_value)
                                import logging
                                logging.info(f"[BusinessKey] BUG-V006 fix: 加 {fk_field.db_column}={fk_value} 到唯一检查")
                    break

        query = f"SELECT id FROM {meta_object.table_name} WHERE {' AND '.join(where_clauses)}"
        if exclude_id:
            query += " AND id != ?"
            params.append(exclude_id)

        try:
            cursor = self.ds.execute(query, tuple(params))
            row = cursor.fetchone()
            if row:
                bk_field_names = "、".join([f.name for f, v in bk_values])
                bk_value_str = " + ".join([v for f, v in bk_values])
                # [NEW v1.2.13 2026-06-19] 单字段时不显示"组合"
                if len(bk_values) == 1:
                    msg_key = "validation.object.business_key_single"
                    msg_params = {"field_name": bk_values[0][0].name, "value": bk_values[0][1]}
                else:
                    msg_key = "validation.object.business_key_composite"
                    msg_params = {"field_names": bk_field_names, "values": bk_value_str}
                return [ValidationDetail(
                    rule="business_key_composite",
                    message=ValidationMessageRegistry.get(msg_key, **msg_params),
                    i18n_key=msg_key,
                    params=msg_params
                )]
        except Exception:
            pass
        return []

    def _check_unique_indexes(self, meta_object: 'MetaObject', data: Dict[str, Any],
                               exclude_id: Any = None) -> List[ValidationDetail]:
        indexes = getattr(meta_object, 'indexes', None)
        if not indexes:
            return []
        errors = []
        for index in indexes:
            # 兼容两种形式: dict (原始 yaml) / MetaIndex 对象 (parse_index 解析后)
            if isinstance(index, dict):
                index_type_str = index.get('type', '')
                index_fields = index.get('fields', [])
                index_name = index.get('name', 'unknown')
                is_unique = index_type_str == 'unique'
            else:
                # MetaIndex 对象: index_type 可能是 enum 或 str
                idx_type = getattr(index, 'index_type', None)
                idx_type_value = getattr(idx_type, 'value', idx_type)
                index_fields = list(getattr(index, 'fields', []) or [])
                index_name = getattr(index, 'name', '') or 'unknown'
                is_unique = (
                    idx_type_value == 'unique'
                    or getattr(index, 'unique', False)
                )

            if not is_unique:
                continue
            if not index_fields:
                continue

            is_bk_index = True
            for idx_f in index_fields:
                is_bk_field = any(
                    getattr(f.semantics, 'business_key', False) and f.id == idx_f
                    for f in meta_object.fields
                )
                if not is_bk_field and idx_f != 'version_id':
                    is_bk_index = False
                    break
            if is_bk_index:
                continue

            where_clauses = []
            params = []
            all_present = True
            for idx_field in index_fields:
                value = data.get(idx_field)
                if value is None:
                    all_present = False
                    break
                where_clauses.append(f"{idx_field} = ?")
                params.append(value)

            if not all_present:
                continue

            query = f"SELECT id FROM {meta_object.table_name} WHERE {' AND '.join(where_clauses)}"
            if exclude_id:
                query += " AND id != ?"
                params.append(exclude_id)

            try:
                cursor = self.ds.execute(query, tuple(params))
                row = cursor.fetchone()
                if row:
                    # 将技术 field ID 解析为用户友好的字段名
                    resolved_names = []
                    for idx_field in index_fields:
                        f = next((x for x in meta_object.fields if x.id == idx_field), None)
                        resolved_names.append(f.name if f and f.name else idx_field)
                    field_names = "、".join(resolved_names)
                    # index_name 改用 description 友好描述，避免暴露技术索引名
                    index_display = ""
                    if isinstance(index, dict):
                        index_display = index.get('description', '') or index_name
                    else:
                        index_display = getattr(index, 'description', '') or index_name
                    errors.append(ValidationDetail(
                        rule="index_unique",
                        message=ValidationMessageRegistry.get("validation.object.index_unique",
                                                               index_name=index_display, field_names=field_names),
                        i18n_key="validation.object.index_unique",
                        params={"index_name": index_display, "field_names": field_names}
                    ))
            except Exception:
                pass
        return errors
