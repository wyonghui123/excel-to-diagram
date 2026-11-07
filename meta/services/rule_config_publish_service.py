# -*- coding: utf-8 -*-
"""规则配置发布流（FR-018 / §9.6.8）。

范围：控制参数取值、行类型确定规则两类已 BO 化的配置（P2）。
状态机：draft →（校验通过）active →（被同键新版本取代）inactive；回滚回到上一个发布版本。
``validated`` 是发布前的校验闸门，不落库、不新增枚举值（零 DDL）。

约束：
    - 编辑只写 draft；运行期解析只读 active，因此草稿天然不参与解析。
    - 同键多条 active 在发布时置为 inactive（历史行保留，供回滚）。
    - 每次 save / publish / rollback 都写 audit_logs：object_type=rule_config，
      object_id=<target>:<rule_key>，old_data/new_data 携带前后快照。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

AUDIT_OBJECT_TYPE = 'rule_config'
MAX_HISTORY = 50

TARGETS: Dict[str, Dict[str, Any]] = {
    'control_parameter_value': {
        'table': 'control_parameter_values',
        'label': '控制参数取值',
        'key_fields': ('control_parameter_id', 'org_id', 'document_type_id',
                       'line_type_id', 'item_group_id'),
        'value_fields': ('specificity_rank', 'value', 'description'),
        'required': ('control_parameter_id', 'value'),
    },
    'line_type_assignment': {
        'table': 'line_type_assignments',
        'label': '行类型确定规则',
        'key_fields': ('document_type_id', 'item_group_id'),
        'value_fields': ('specificity_rank', 'line_type_id', 'description'),
        'required': ('document_type_id', 'line_type_id'),
    },
}


class RuleConfigError(ValueError):
    """配置发布入参或状态非法（API 层转 400）。"""


class RuleConfigNotFound(RuleConfigError):
    """目标配置不存在（API 层转 404）。"""


def _meta_db():
    from meta.core.db_path import get_meta_db_path
    from meta.core.datasource import get_data_source
    return get_data_source('sqlite', database=get_meta_db_path())


def _now() -> str:
    return datetime.now().isoformat()


def _to_int(value: Any) -> Optional[int]:
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise RuleConfigError(f'期望整数，收到 {value!r}')


class RuleConfigPublishService:
    """配置草稿 / 发布 / 回滚 / 历史（均为写路径，调用方须校验写权限）。"""

    def __init__(self, data_source=None):
        self._ds = data_source

    @property
    def ds(self):
        if self._ds is None:
            self._ds = _meta_db()
        return self._ds

    # ------------------------------------------------------------------
    # 草稿
    # ------------------------------------------------------------------

    def save_draft(self, target: str, payload: Dict[str, Any],
                   user_id: Any = None, user_name: str = None) -> Dict[str, Any]:
        spec = self._spec(target)
        data = self._normalize(target, payload)
        self.validate(target, data)

        rule_key = self._rule_key(target, data)
        existing = self._find_draft(target, data)
        now = _now()
        if existing:
            values = {f: data.get(f) for f in spec['value_fields']}
            sets = ', '.join(f'{f} = ?' for f in values)
            self.ds.execute(
                f"UPDATE {spec['table']} SET {sets} WHERE id = ?",
                tuple(list(values.values()) + [existing['id']]))
            draft_id = existing['id']
            action = 'SAVE'
        else:
            columns = list(spec['key_fields']) + list(spec['value_fields'])
            row = {f: data.get(f) for f in columns}
            row['status'] = 'draft'
            row['created_at'] = now
            placeholders = ', '.join('?' for _ in row)
            self.ds.execute(
                f"INSERT INTO {spec['table']} ({', '.join(row)}) VALUES ({placeholders})",
                tuple(row.values()))
            draft_id = self._last_id(spec['table'])
            action = 'SAVE'

        draft = self._load(target, draft_id)
        self._audit(action, target, rule_key, user_id, user_name,
                    before=None, after=draft,
                    extra={'draft_id': draft_id, 'rule_key': rule_key})
        # 草稿不参与 active 解析，但会进入 include_draft 的试算结果，需清试算缓存
        self._invalidate()
        return self._envelope(target, rule_key, draft, draft_id, status='draft')

    # ------------------------------------------------------------------
    # 发布
    # ------------------------------------------------------------------

    def publish(self, target: str, payload: Optional[Dict[str, Any]] = None,
                draft_id: Any = None, user_id: Any = None,
                user_name: str = None) -> Dict[str, Any]:
        spec = self._spec(target)
        payload = payload or {}
        if draft_id is not None:
            draft = self._load(target, _to_int(draft_id))
            if not draft:
                raise RuleConfigNotFound('草稿不存在')
        else:
            data = self._normalize(target, payload)
            draft = self._find_draft(target, data)
            if not draft:
                raise RuleConfigNotFound('未找到待发布的草稿')

        if str(draft.get('status') or '') != 'draft':
            raise RuleConfigError('只有 draft 状态可发布，当前状态: {0}'.format(
                draft.get('status')))
        self.validate(target, draft)

        rule_key = self._rule_key(target, draft)
        superseded = self._active_rows(target, draft)
        previous = [dict(r) for r in superseded]

        with self.ds.transaction():
            for row in superseded:
                self.ds.execute(
                    f"UPDATE {spec['table']} SET status = 'inactive' WHERE id = ?",
                    (row.get('id'),))
            self.ds.execute(
                f"UPDATE {spec['table']} SET status = 'active' WHERE id = ?",
                (draft.get('id'),))

        self._invalidate()
        published = self._load(target, draft.get('id')) or draft
        self._audit('PUBLISH', target, rule_key, user_id, user_name,
                    before={'rows': previous}, after=published,
                    extra={'draft_id': draft.get('id'),
                           'superseded_ids': [r.get('id') for r in previous],
                           'rule_key': rule_key})
        result = self._envelope(target, rule_key, published, draft.get('id'),
                                status='active')
        result['superseded'] = len(previous)
        return result

    # ------------------------------------------------------------------
    # 回滚
    # ------------------------------------------------------------------

    def rollback(self, target: str, payload: Dict[str, Any],
                 user_id: Any = None, user_name: str = None) -> Dict[str, Any]:
        spec = self._spec(target)
        payload = payload or {}
        rule_key = payload.get('rule_key') or self._rule_key(
            target, self._normalize(target, payload))
        object_id, mode = self._history_object_id(target, rule_key)
        last = (self._last_publish(object_id) if mode == 'exact'
                else self._last_publish_prefix(object_id))
        if not last:
            raise RuleConfigNotFound('该规则没有可回滚的发布版本')
        rule_key = (last.get('extra') or {}).get('rule_key') or rule_key

        before_rows = (last.get('before') or {}).get('rows') or []
        if not before_rows:
            raise RuleConfigError('上一个发布版本没有可恢复的前值')

        key = {f: last.get('after', {}).get(f) for f in spec['key_fields']}
        current = self._active_rows(target, key)
        restored_ids: List[Any] = []
        with self.ds.transaction():
            for row in current:
                self.ds.execute(
                    f"UPDATE {spec['table']} SET status = 'inactive' WHERE id = ?",
                    (row.get('id'),))
            for row in before_rows:
                restored = {f: row.get(f) for f in
                            spec['key_fields'] + spec['value_fields']}
                if self._load(target, row.get('id')) is not None:
                    sets = ', '.join(f'{f} = ?' for f in restored)
                    self.ds.execute(
                        f"UPDATE {spec['table']} SET {sets}, status = 'active' "
                        f"WHERE id = ?",
                        tuple(list(restored.values()) + [row.get('id')]))
                    restored_ids.append(row.get('id'))
                else:
                    restored['status'] = 'active'
                    restored['created_at'] = _now()
                    placeholders = ', '.join('?' for _ in restored)
                    self.ds.execute(
                        f"INSERT INTO {spec['table']} ({', '.join(restored)}) "
                        f"VALUES ({placeholders})",
                        tuple(restored.values()))
                    restored_ids.append(self._last_id(spec['table']))

        self._invalidate()
        after = [self._load(target, rid) for rid in restored_ids]
        self._audit('ROLLBACK', target, rule_key, user_id, user_name,
                    before={'rows': current}, after={'rows': after},
                    extra={'restored_ids': restored_ids,
                           'source_publish_audit_id': last.get('id'),
                           'rule_key': rule_key})
        result = self._envelope(target, rule_key,
                                after[0] if after else None,
                                restored_ids[0] if restored_ids else None,
                                status='active')
        result['restored'] = len(restored_ids)
        return result

    # ------------------------------------------------------------------
    # 历史
    # ------------------------------------------------------------------

    def history(self, target: Optional[str] = None,
                rule_key: Optional[str] = None,
                limit: int = 20) -> Dict[str, Any]:
        if not target and rule_key:
            target = self._target_from_rule_key(rule_key)
        sql = ("SELECT id, object_id, action, user_id, user_name, created_at, "
               "extra_data, trace_id FROM audit_logs "
               "WHERE object_type = ?")
        params: List[Any] = [AUDIT_OBJECT_TYPE]
        if target:
            sql += " AND object_id LIKE ?"
            params.append(f'{target}:%')
        if rule_key:
            object_id, mode = self._history_object_id(target, rule_key)
            if mode == 'prefix':
                sql += " AND object_id LIKE ?"
                params.append(f'{object_id}%')
            else:
                sql += " AND object_id = ?"
                params.append(object_id)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, min(int(limit or 20), MAX_HISTORY)))
        try:
            rows = self.ds.query(sql, tuple(params))
        except Exception as e:  # noqa: BLE001
            raise RuleConfigError(f'读取配置历史失败: {e}') from e

        items = []
        for row in rows:
            extra = _json(row.get('extra_data')) or {}
            items.append({
                'id': row.get('id'),
                'action': row.get('action'),
                'operator': row.get('user_name') or row.get('user_id'),
                'created_at': row.get('created_at'),
                'trace_id': row.get('trace_id'),
                'before': extra.get('before'),
                'after': extra.get('after'),
                'extra': extra,
            })
        return {'items': items, 'total': len(items)}

    # ------------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------------

    def validate(self, target: str, data: Dict[str, Any]) -> None:
        spec = self._spec(target)
        errors: List[str] = []
        for field in spec['required']:
            if data.get(field) in (None, ''):
                errors.append(f'{field} 不能为空')

        if target == 'control_parameter_value':
            definition = self._one(
                "SELECT * FROM control_parameter_defs WHERE id = ? AND status = 'active'",
                (data.get('control_parameter_id'),))
            if not definition:
                errors.append('控制参数定义不存在或已停用')
            else:
                value = data.get('value')
                if value not in (None, ''):
                    try:
                        from meta.services.control_parameter_service import (
                            get_control_parameter_resolver,
                        )
                        get_control_parameter_resolver()._convert(definition, value)
                    except Exception as e:  # noqa: BLE001
                        errors.append(f'取值不合法: {e}')
            for field, table in (('document_type_id', 'type_definitions'),
                                 ('line_type_id', 'type_definitions'),
                                 ('item_group_id', 'item_groups')):
                value = data.get(field)
                if value is not None and not self._exists(table, value):
                    errors.append(f'{field} 引用的记录不存在: {value}')
        else:
            if not self._exists('type_definitions', data.get('document_type_id')):
                errors.append('document_type_id 引用的单据类型不存在')
            if not self._exists('type_definitions', data.get('line_type_id')):
                errors.append('line_type_id 引用的行类型不存在')
            item_group_id = data.get('item_group_id')
            if item_group_id is not None and not self._exists('item_groups', item_group_id):
                errors.append(f'item_group_id 引用的物料组不存在: {item_group_id}')

        rank = data.get('specificity_rank')
        if rank is not None:
            try:
                if int(rank) < 0:
                    errors.append('specificity_rank 不能为负')
            except (TypeError, ValueError):
                errors.append('specificity_rank 必须为整数')

        if errors:
            raise RuleConfigError('；'.join(errors))

    # ------------------------------------------------------------------
    # 查询辅助
    # ------------------------------------------------------------------

    def _spec(self, target: str) -> Dict[str, Any]:
        spec = TARGETS.get(target)
        if not spec:
            raise RuleConfigError(
                '不支持的配置目标: {0}；可选 {1}'.format(target, list(TARGETS)))
        return spec

    def _normalize(self, target: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        spec = self._spec(target)
        data: Dict[str, Any] = {}
        for field in spec['key_fields']:
            data[field] = _to_int(payload.get(field))
        for field in spec['value_fields']:
            if field == 'description':
                data[field] = payload.get(field)
            elif field == 'value':
                data[field] = payload.get(field)
            else:
                data[field] = _to_int(payload.get(field))
        if data.get('specificity_rank') is None:
            data['specificity_rank'] = 100
        return data

    def _key_where(self, spec: Dict[str, Any], row: Dict[str, Any]
                   ) -> Tuple[str, List[Any]]:
        clauses: List[str] = []
        params: List[Any] = []
        for field in spec['key_fields']:
            value = row.get(field)
            if value is None:
                clauses.append(f'{field} IS NULL')
            else:
                clauses.append(f'{field} = ?')
                params.append(value)
        return ' AND '.join(clauses), params

    def _find_draft(self, target: str, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        spec = self._spec(target)
        where, params = self._key_where(spec, row)
        return self._one(
            f"SELECT * FROM {spec['table']} WHERE {where} AND status = 'draft' "
            f"ORDER BY id DESC LIMIT 1", tuple(params))

    def _active_rows(self, target: str, row: Dict[str, Any]) -> List[Dict[str, Any]]:
        spec = self._spec(target)
        where, params = self._key_where(spec, row)
        return list(self.ds.query(
            f"SELECT * FROM {spec['table']} WHERE {where} AND status = 'active'",
            tuple(params)) or [])

    def _load(self, target: str, row_id: Any) -> Optional[Dict[str, Any]]:
        spec = self._spec(target)
        return self._one(f"SELECT * FROM {spec['table']} WHERE id = ?", (row_id,))

    def _one(self, sql: str, params: tuple) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(sql, params) or []
        return dict(rows[0]) if rows else None

    def _exists(self, table: str, value: Any) -> bool:
        if value is None:
            return False
        try:
            return self._one(
                f"SELECT id FROM {table} WHERE id = ? AND status = 'active'",
                (value,)) is not None
        except Exception:  # noqa: BLE001 - 表不存在时不做强校验
            return True

    def _last_id(self, table: str) -> Any:
        row = self._one(f"SELECT MAX(id) AS id FROM {table}", ())
        return row.get('id') if row else None

    def _rule_key(self, target: str, row: Dict[str, Any]) -> str:
        if target == 'control_parameter_value':
            code = self._param_code(row.get('control_parameter_id'))
            dims = '|'.join('*' if row.get(f) is None else str(row.get(f))
                            for f in ('org_id', 'document_type_id',
                                      'line_type_id', 'item_group_id'))
            return f'{code}|{dims}'
        item_group = row.get('item_group_id')
        return '{0}.{1}'.format(row.get('document_type_id'),
                                item_group if item_group is not None else '*')

    def _param_code(self, control_parameter_id: Any) -> str:
        definition = self._one(
            "SELECT code FROM control_parameter_defs WHERE id = ?",
            (control_parameter_id,))
        return str((definition or {}).get('code') or control_parameter_id)

    @staticmethod
    def _target_from_rule_key(rule_key: str) -> Optional[str]:
        """目录 rule_key 前缀 → 发布目标；未知前缀返回 None。"""
        for prefix, target in (('control_parameter:', 'control_parameter_value'),
                               ('line_type:', 'line_type_assignment')):
            if rule_key.startswith(prefix):
                return target
        return None

    def _history_object_id(self, target: Optional[str],
                           rule_key: str) -> Tuple[str, str]:
        """把规则目录的 rule_key 映射为 audit_logs.object_id 与匹配模式。

        目录键：control_parameter:<code> / line_type:<doc>.<group>
        审计键：<target>:<code|dims> / <target>:<doc>.<group>
        控制参数按定义聚合多条维度行，故用前缀匹配。
        """
        prefix = f'{target}:' if target else '%:'
        if rule_key.startswith('control_parameter:'):
            code = rule_key.split(':', 1)[1]
            return f'{prefix}{code}|', 'prefix'
        if rule_key.startswith('line_type:'):
            return f"{prefix}{rule_key.split(':', 1)[1]}", 'exact'
        return f'{prefix}{rule_key}', 'exact'

    def _last_publish(self, object_id: str) -> Optional[Dict[str, Any]]:
        return self._last_publish_where("object_id = ?", (object_id,))

    def _last_publish_prefix(self, object_id_prefix: str) -> Optional[Dict[str, Any]]:
        return self._last_publish_where("object_id LIKE ?", (f'{object_id_prefix}%',))

    def _last_publish_where(self, where: str,
                            params: tuple) -> Optional[Dict[str, Any]]:
        row = self._one(
            f"SELECT * FROM audit_logs WHERE object_type = ? AND {where} "
            f"AND action = 'PUBLISH' ORDER BY id DESC LIMIT 1",
            (AUDIT_OBJECT_TYPE,) + params)
        if not row:
            return None
        extra = _json(row.get('extra_data')) or {}
        return {
            'id': row.get('id'),
            'before': extra.get('before') or {},
            'after': extra.get('after') or {},
            'extra': extra,
        }

    def _envelope(self, target: str, rule_key: str, row: Optional[Dict[str, Any]],
                  row_id: Any, status: str) -> Dict[str, Any]:
        return {
            'target': target,
            'rule_key': rule_key,
            'id': row_id,
            'status': status,
            'row': row,
        }

    def _audit(self, action: str, target: str, rule_key: str, user_id: Any,
               user_name: Optional[str], before: Any, after: Any,
               extra: Dict[str, Any]) -> None:
        try:
            from meta.services.audit_service import AuditService
            AuditService(self.ds).log(
                object_type=AUDIT_OBJECT_TYPE,
                object_id=f'{target}:{rule_key}',
                action=action,
                user_id=user_id,
                user_name=user_name,
                old_data=before,
                new_data=after,
                extra_data=dict(extra, biz_type=AUDIT_OBJECT_TYPE,
                                target=target, before=before, after=after),
            )
        except Exception as e:  # noqa: BLE001 - 审计失败不回滚业务写
            logger.exception('规则配置审计写入失败: %s', e)

    def _invalidate(self) -> None:
        try:
            from meta.services.control_parameter_service import (
                get_control_parameter_resolver,
            )
            from meta.services.line_type_service import get_line_type_resolver
            from meta.services.rule_simulate_service import invalidate_simulate_cache

            get_control_parameter_resolver().invalidate()
            get_line_type_resolver().invalidate()
            invalidate_simulate_cache()
        except Exception as e:  # noqa: BLE001
            logger.warning('规则配置缓存失效失败: %s', e)


def _json(value: Any) -> Any:
    if value in (None, ''):
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


_publisher: Optional[RuleConfigPublishService] = None


def get_rule_config_publish_service() -> RuleConfigPublishService:
    global _publisher
    if _publisher is None:
        _publisher = RuleConfigPublishService()
    return _publisher