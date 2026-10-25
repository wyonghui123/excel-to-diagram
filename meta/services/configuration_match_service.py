# -*- coding: utf-8 -*-
"""配置复用匹配（Configuration Match Service）— P4 T6

`item.config_match_policy = one_time_standard` 时，求解产物按 `config_hash`
在同结构版本下找最近一条 `frozen` 实例；命中即**新建一条**实例承接（D1）：
`config_hash` 不变（订单侧配置键不变）、`id` 必变、`revision = 源.revision + 1`、
`reused_from_id` 指向源；刚求解出的实例置 `superseded`（Spec §6.6）。

[边界]
  - 只接受 `solved` 实例：复用发生在"求解成功之后、冻结之前"的窗口内。
  - 源实例（`frozen`）**只读不改**，R10 不被破坏；多张订单也不共享同一实例。
  - 判据含 `structure_id`，模型版本升级即结构版本换行，天然不复用（§6.4）。
  - 不加唯一索引：同 `(structure_id, config_hash)` 允许多条（源 + 各次复用），
    唯一约束会把合法的第二次复用判错（§4.2）。
"""
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from meta.services.item_structure_config_service import (
    ItemStructureConfigError,
    ItemStructureConfigService,
)

logger = logging.getLogger(__name__)

ONE_TIME_STANDARD = 'one_time_standard'

_CONFIG_TABLE = 'configurations'
_ITEM_TABLE = 'items'
_VALUE_TABLE = 'configuration_values'
_COMPONENT_TABLE = 'configuration_components'

_MATCHABLE_STATUS = 'solved'

_VALUE_COLUMNS = (
    'attribute_code', 'seq', 'value_text', 'value_number', 'value_boolean',
    'source', 'source_rule_id')

_COMPONENT_COLUMNS = (
    'component_key', 'structure_line_id', 'component_item_id', 'qty',
    'uom_code', 'parent_component_key', 'selection_source', 'source_rule_id',
    'substitute_for_key', 'child_configuration_id', 'seq')


class ConfigurationMatchService:
    """`one_time_standard` 命中与复用。构造注入数据源，便于测试用内存 SQLite。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ------------------------------------------------------------------
    # 入口
    # ------------------------------------------------------------------
    def match(self, configuration_id: Any) -> Dict[str, Any]:
        """对刚求解出的实例尝试复用，返回订单侧应使用的配置。

        Returns:
            {
              configuration_id: 订单侧应引用的实例 ID（未复用时为原实例）,
              reused:           是否走到复用分支,
              source_id:        复用的源实例（未复用为 None）,
              revision:         返回实例的 revision,
              config_hash:      配置键（复用前后不变）,
              status:           返回实例的状态,
            }

        Raises:
            ItemStructureConfigError: 实例不存在
        """
        head = self._fetch_head(configuration_id)
        if not head:
            raise ItemStructureConfigError(
                f'配置实例不存在: {configuration_id}',
                code='CONFIG_VERSION_MISMATCH',
                rule='configuration_not_found', field_name='id',
                configuration_id=configuration_id)

        result = {
            'configuration_id': configuration_id,
            'reused': False,
            'source_id': None,
            'revision': head.get('revision'),
            'config_hash': head.get('config_hash'),
            'status': head.get('status'),
        }

        if str(head.get('status') or '') != _MATCHABLE_STATUS:
            return result
        if not str(head.get('config_hash') or ''):
            return result
        if self._policy(head.get('model_item_id')) != ONE_TIME_STANDARD:
            return result

        with self.ds.transaction():
            source = self._find_source(head, configuration_id)
            if not source:
                return result
            # 事务内二次确认：两个调用并发时，后进入者读到先进入者刚落的新实例
            source = self._find_source(head, configuration_id) or source
            new_id = self._clone(head, source)
            self._supersede(configuration_id)

        logger.info('配置复用: %s -> %s（源 %s）', configuration_id, new_id,
                    source.get('id'))
        return {
            'configuration_id': new_id,
            'reused': True,
            'source_id': source.get('id'),
            'revision': int(source.get('revision') or 0) + 1,
            'config_hash': head.get('config_hash'),
            'status': source.get('status') or 'frozen',
        }

    # ------------------------------------------------------------------
    # 判据
    # ------------------------------------------------------------------
    def _find_source(self, head: Dict[str, Any],
                     configuration_id: Any) -> Optional[Dict[str, Any]]:
        """同结构版本、同 hash、最近一条 frozen（取最新，收敛重复插入）。"""
        rows = self.ds.query(
            f"SELECT * FROM {_CONFIG_TABLE}"
            " WHERE structure_id = ? AND config_hash = ?"
            "   AND status = 'frozen' AND id <> ?"
            " ORDER BY id DESC LIMIT 1",
            [head.get('structure_id'), head.get('config_hash'),
             configuration_id])
        return rows[0] if rows else None

    def _policy(self, model_item_id: Any) -> str:
        rows = self.ds.query(
            f"SELECT config_match_policy FROM {_ITEM_TABLE} WHERE id = ?",
            [model_item_id])
        if not rows:
            return ''
        return str(rows[0].get('config_match_policy') or '')

    # ------------------------------------------------------------------
    # 复制与置位
    # ------------------------------------------------------------------
    def _clone(self, head: Dict[str, Any],
               source: Dict[str, Any]) -> Any:
        """新建承接实例：内容照抄当前求解结果，审计字段按复用语义改写。"""
        now = datetime.now().isoformat(timespec='seconds')
        head_row = {
            'model_item_id': head.get('model_item_id'),
            'structure_id': head.get('structure_id'),
            'status': source.get('status') or 'frozen',
            'config_hash': head.get('config_hash'),
            'revision': int(source.get('revision') or 0) + 1,
            'reused_from_id': source.get('id'),
            'match_policy_used': ONE_TIME_STANDARD,
            'source_level': head.get('source_level'),
            'context_json': head.get('context_json'),
            'validation_result_json': head.get('validation_result_json'),
            'solved_at': head.get('solved_at'),
            'frozen_at': source.get('frozen_at') or now,
        }
        values = self.ds.query(
            f"SELECT {', '.join(_VALUE_COLUMNS)} FROM {_VALUE_TABLE}"
            " WHERE configuration_id = ? ORDER BY id",
            [head.get('id')])
        components = self.ds.query(
            f"SELECT {', '.join(_COMPONENT_COLUMNS)} FROM {_COMPONENT_TABLE}"
            " WHERE configuration_id = ? ORDER BY id",
            [head.get('id')])

        new_id = self.ds.insert(_CONFIG_TABLE, head_row)
        for row in values:
            self.ds.insert(_VALUE_TABLE, {'configuration_id': new_id, **row})
        for row in components:
            self.ds.insert(_COMPONENT_TABLE, {'configuration_id': new_id, **row})
        return new_id

    def _supersede(self, configuration_id: Any) -> None:
        """被复用替代的求解实例置 superseded（变更走新实例，§6.6）。"""
        self.ds.update(_CONFIG_TABLE, configuration_id, {'status': 'superseded'})

    # ------------------------------------------------------------------
    # 小工具
    # ------------------------------------------------------------------
    def _fetch_head(self, configuration_id: Any) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            f"SELECT * FROM {_CONFIG_TABLE} WHERE id = ?", [configuration_id])
        return rows[0] if rows else None
